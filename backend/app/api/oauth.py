from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.storage.db import SessionLocal, get_session
from app.storage.models import OAuthGrantORM
from app.security.rate_limit import (
    oauth_authorize_get_limit,
    oauth_authorize_post_limit,
    oauth_revoke_limit,
    oauth_token_limit,
)

router = APIRouter(prefix="/oauth", tags=["oauth"])
Session = Annotated[AsyncSession, Depends(get_session)]
ACCESS_TTL_SECONDS = 3600
AUTH_CODE_TTL_SECONDS = 60
SCOPE = "classroom:control"

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Вход — Умная аудитория</title></head>
<body>
  <h1>Умная аудитория — вход</h1>
  <p>Войдите в тестовую аудиторию и подтвердите доступ для Алисы.</p>
  <form method="post" action="/oauth/authorize">
    <input type="hidden" name="client_id" value="{client_id}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="scope" value="{scope}">
    <input type="hidden" name="flow_token" value="{flow_token}">
    <label>Email <input type="email" name="email" required></label>
    <label>Пароль <input type="password" name="password" required></label>
    <label><input type="checkbox" name="consent" value="true" required>
      Разрешаю Алисе управлять симулятором аудитории</label>
    <button type="submit">Войти и разрешить</button>
  </form>
</body>
</html>
"""


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class RevokeRequest(BaseModel):
    token: str = ""
    token_type_hint: str = ""
    client_id: str | None = None
    client_secret: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    # SQLite strips timezone info from DateTime(timezone=True) columns.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _configured_client(client_id: str | None, client_secret: str | None) -> bool:
    return bool(
        settings.YANDEX_CLIENT_ID
        and settings.YANDEX_CLIENT_SECRET
        and hmac.compare_digest(client_id or "", settings.YANDEX_CLIENT_ID)
        and hmac.compare_digest(client_secret or "", settings.YANDEX_CLIENT_SECRET)
    )


def _basic_client_credentials(authorization: str | None) -> tuple[str, str] | None:
    if not authorization or not authorization.lower().startswith("basic "):
        return None
    import base64

    try:
        raw = base64.b64decode(authorization.split(" ", 1)[1], validate=True).decode()
        client_id, separator, client_secret = raw.partition(":")
        if not separator:
            raise ValueError("Missing client secret separator")
        return client_id, client_secret
    except (ValueError, UnicodeDecodeError):
        raise _client_error("invalid_client", 401) from None


def _redirect_allowed(uri: str) -> bool:
    return uri in {
        item.strip()
        for item in settings.YANDEX_REDIRECT_URIS.split(",")
        if item.strip()
    }


def _with_query(uri: str, params: dict[str, str]) -> str:
    parts = urlsplit(uri)
    replaced = set(params)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in replaced
    ]
    query.extend(params.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _safe_template(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _client_error(code: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code})


@router.get(
    "/authorize",
    response_class=HTMLResponse,
    dependencies=[Depends(oauth_authorize_get_limit)],
)
async def authorize(
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    response_type: str = "code",
    scope: str = SCOPE,
) -> str:
    if response_type != "code" or not client_id or not state or len(state) > 1024:
        raise _client_error("invalid_request")
    if not settings.YANDEX_CLIENT_ID or not hmac.compare_digest(client_id, settings.YANDEX_CLIENT_ID):
        raise _client_error("invalid_client", 401)
    if not _redirect_allowed(redirect_uri):
        raise _client_error("invalid_redirect_uri")
    if scope != SCOPE:
        raise _client_error("unsupported_scope")
    flow_token = secrets.token_urlsafe(32)
    now = _now()
    async with SessionLocal() as session:
        session.add(
            OAuthGrantORM(
                token_hash=_hash(flow_token),
                kind="flow",
                family_id=str(uuid4()),
                client_id=client_id,
                user_id="",
                redirect_uri=redirect_uri,
                state=state,
                scope=scope,
                expires_at=now + timedelta(minutes=10),
                revoked=False,
                consumed=False,
                created_at=now,
            )
        )
        await session.commit()
    return LOGIN_PAGE.format(
        client_id=_safe_template(client_id),
        redirect_uri=_safe_template(redirect_uri),
        state=_safe_template(state),
        scope=_safe_template(scope),
        flow_token=_safe_template(flow_token),
    )


@router.post("/authorize", dependencies=[Depends(oauth_authorize_post_limit)])
async def authorize_submit(
    session: Session,
    email: str = Form(default=""),
    password: str = Form(default=""),
    client_id: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    state: str = Form(default=""),
    scope: str = Form(default=SCOPE),
    consent: str = Form(default=""),
    flow_token: str = Form(default=""),
) -> RedirectResponse:
    if not _redirect_allowed(redirect_uri):
        raise _client_error("invalid_redirect_uri")
    flow = await session.scalar(
        update(OAuthGrantORM)
        .where(
            OAuthGrantORM.token_hash == _hash(flow_token),
            OAuthGrantORM.kind == "flow",
            OAuthGrantORM.consumed.is_(False),
            OAuthGrantORM.revoked.is_(False),
            OAuthGrantORM.expires_at > _now(),
            OAuthGrantORM.client_id == client_id,
            OAuthGrantORM.redirect_uri == redirect_uri,
            OAuthGrantORM.state == state,
            OAuthGrantORM.scope == scope,
        )
        .values(consumed=True)
        .returning(OAuthGrantORM)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    if not flow:
        raise _client_error("invalid_request")
    if not settings.YANDEX_CLIENT_ID or not hmac.compare_digest(client_id, settings.YANDEX_CLIENT_ID):
        raise _client_error("invalid_client", 401)
    if scope != SCOPE:
        await session.commit()
        return RedirectResponse(
            _with_query(redirect_uri, {"error": "unsupported_scope", "state": state}),
            status_code=302,
        )

    credentials_valid = bool(
        settings.YANDEX_DEMO_EMAIL
        and settings.YANDEX_DEMO_PASSWORD
        and hmac.compare_digest(email.strip().casefold(), settings.YANDEX_DEMO_EMAIL.strip().casefold())
        and hmac.compare_digest(password, settings.YANDEX_DEMO_PASSWORD)
    )
    if not credentials_valid or consent.lower() not in {"true", "on", "1"}:
        await session.commit()
        return RedirectResponse(
            _with_query(redirect_uri, {"error": "access_denied", "state": state}),
            status_code=302,
        )

    code = secrets.token_urlsafe(32)
    now = _now()
    session.add(
        OAuthGrantORM(
            token_hash=_hash(code),
            kind="code",
            family_id=str(uuid4()),
            client_id=client_id,
            user_id=email.strip().casefold(),
            redirect_uri=redirect_uri,
            state=state,
            scope=scope,
            expires_at=now + timedelta(seconds=AUTH_CODE_TTL_SECONDS),
            revoked=False,
            consumed=False,
            created_at=now,
        )
    )
    await session.commit()
    return RedirectResponse(
        _with_query(
            redirect_uri,
            {"code": code, "state": state, "client_id": client_id, "scope": scope},
        ),
        status_code=302,
    )


@router.post("/token", dependencies=[Depends(oauth_token_limit)])
async def token(
    request: Request,
    session: Session,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    try:
        if "application/json" in request.headers.get("content-type", ""):
            body = TokenRequest.model_validate(await request.json())
        else:
            form = await request.form()
            body = TokenRequest.model_validate({key: str(value) for key, value in form.items()})
    except (ValidationError, ValueError):
        raise _client_error("invalid_request") from None
    client_id = body.client_id
    client_secret = body.client_secret
    basic_credentials = _basic_client_credentials(authorization)
    if basic_credentials:
        client_id, client_secret = basic_credentials
    if not _configured_client(client_id, client_secret):
        raise _client_error("invalid_client", 401)

    grant_type = body.grant_type
    if grant_type == "authorization_code":
        code = body.code or ""
        redirect_uri = body.redirect_uri or ""
        grant = await session.scalar(
            update(OAuthGrantORM)
            .where(
                OAuthGrantORM.token_hash == _hash(code),
                OAuthGrantORM.kind == "code",
                OAuthGrantORM.revoked.is_(False),
                OAuthGrantORM.consumed.is_(False),
                OAuthGrantORM.expires_at > _now(),
                OAuthGrantORM.client_id == client_id,
                OAuthGrantORM.redirect_uri == redirect_uri,
            )
            .values(consumed=True)
            .returning(OAuthGrantORM)
            .execution_options(synchronize_session=False, populate_existing=True)
        )
        if not grant:
            raise _client_error("invalid_grant")
        access, refresh = await _issue_tokens(session, grant)
        await session.commit()
        return _token_response(access, refresh, grant.scope)

    if grant_type == "refresh_token":
        presented = body.refresh_token or ""
        grant = await session.scalar(
            select(OAuthGrantORM).where(OAuthGrantORM.token_hash == _hash(presented))
        )
        if not grant or grant.kind != "refresh" or grant.client_id != client_id:
            raise _client_error("invalid_grant")
        claimed = await session.scalar(
            update(OAuthGrantORM)
            .where(
                OAuthGrantORM.token_hash == _hash(presented),
                OAuthGrantORM.kind == "refresh",
                OAuthGrantORM.client_id == client_id,
                OAuthGrantORM.consumed.is_(False),
                OAuthGrantORM.revoked.is_(False),
                OAuthGrantORM.expires_at > _now(),
            )
            .values(consumed=True)
            .returning(OAuthGrantORM)
            .execution_options(synchronize_session=False, populate_existing=True)
        )
        if not claimed:
            if grant.consumed:
                await session.execute(
                    update(OAuthGrantORM)
                    .where(OAuthGrantORM.family_id == grant.family_id)
                    .values(revoked=True)
                )
                await session.commit()
            raise _client_error("invalid_grant")
        access, refresh = await _issue_tokens(session, claimed)
        await session.commit()
        return _token_response(access, refresh, grant.scope)

    raise _client_error("unsupported_grant_type")


async def _issue_tokens(
    session: AsyncSession, source: OAuthGrantORM
) -> tuple[str, str]:
    now = _now()
    access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    session.add_all(
        [
            OAuthGrantORM(
                token_hash=_hash(access), kind="access", family_id=source.family_id,
                client_id=source.client_id, user_id=source.user_id, redirect_uri="",
                scope=source.scope, expires_at=now + timedelta(seconds=ACCESS_TTL_SECONDS),
                revoked=False, consumed=False, created_at=now,
            ),
            OAuthGrantORM(
                token_hash=_hash(refresh), kind="refresh", family_id=source.family_id,
                client_id=source.client_id, user_id=source.user_id, redirect_uri="",
                scope=source.scope, expires_at=now + timedelta(days=30),
                revoked=False, consumed=False, created_at=now,
            ),
        ]
    )
    return access, refresh


def _token_response(access: str, refresh: str, scope: str) -> dict[str, object]:
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ACCESS_TTL_SECONDS,
        "refresh_token": refresh,
        "scope": scope,
    }


async def authenticate_access_token(
    session: AsyncSession, authorization: str | None
) -> OAuthGrantORM:
    scheme, _, token_value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token_value or len(token_value) > 2048:
        raise _client_error("invalid_token", 401)
    grant = await session.scalar(
        select(OAuthGrantORM).where(OAuthGrantORM.token_hash == _hash(token_value))
    )
    if (
        not grant
        or grant.kind != "access"
        or grant.revoked
        or _as_utc(grant.expires_at) <= _now()
    ):
        raise _client_error("invalid_token", 401)
    return grant


@router.post("/revoke", dependencies=[Depends(oauth_revoke_limit)])
async def revoke(
    request: Request,
    session: Session,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, bool]:
    try:
        if "application/json" in request.headers.get("content-type", ""):
            fields = RevokeRequest.model_validate(await request.json()).model_dump()
        else:
            fields = {key: str(value) for key, value in (await request.form()).items()}
    except (ValidationError, ValueError):
        raise _client_error("invalid_request") from None
    token = fields.get("token", "")
    client_id = fields.get("client_id")
    client_secret = fields.get("client_secret")
    basic_credentials = _basic_client_credentials(authorization)
    if basic_credentials:
        client_id, client_secret = basic_credentials
    if not _configured_client(client_id, client_secret):
        raise _client_error("invalid_client", 401)
    if token and len(token) <= 2048:
        grant = await session.scalar(
            select(OAuthGrantORM).where(OAuthGrantORM.token_hash == _hash(token))
        )
        if grant:
            await session.execute(
                update(OAuthGrantORM)
                .where(OAuthGrantORM.family_id == grant.family_id)
                .values(revoked=True)
            )
            await session.commit()
    return {"revoked": True}
