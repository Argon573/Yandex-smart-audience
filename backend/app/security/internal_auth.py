from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from fastapi import Depends, Header
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.config import settings
from app.storage.db import get_session
from app.storage.models import OAuthGrantORM
from app.api.oauth import _as_utc, _hash

INTERNAL_CLIENT_ID = "smart-classroom-internal"
INTERNAL_SCOPE_PREFIX = "role:"


@dataclass(frozen=True)
class InternalUser:
    id: str
    email: str
    role: str
    family_id: str


def configured_internal_user(email: str, password: str) -> tuple[str, str] | None:
    expected_email = settings.APP_DEMO_EMAIL.strip().casefold()
    expected_password = settings.APP_DEMO_PASSWORD
    if not expected_email or not expected_password:
        return None
    valid_email = hmac.compare_digest(email.strip().casefold(), expected_email)
    valid_password = hmac.compare_digest(password, expected_password)
    if not (valid_email and valid_password):
        return None
    role = settings.APP_DEMO_ROLE.strip().lower()
    if role not in {"teacher", "operator", "admin"}:
        return None
    return expected_email, role


async def issue_internal_tokens(
    session: AsyncSession, email: str, role: str, *, family_id: str | None = None
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    family_id = family_id or str(uuid4())
    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(48)
    session.add_all(
        [
            OAuthGrantORM(
                token_hash=_hash(access_token),
                kind="app_access",
                family_id=family_id,
                client_id=INTERNAL_CLIENT_ID,
                user_id=email,
                redirect_uri="",
                state="",
                scope=f"{INTERNAL_SCOPE_PREFIX}{role}",
                expires_at=now + timedelta(seconds=settings.ACCESS_TTL),
                revoked=False,
                consumed=False,
                created_at=now,
            ),
            OAuthGrantORM(
                token_hash=_hash(refresh_token),
                kind="app_refresh",
                family_id=family_id,
                client_id=INTERNAL_CLIENT_ID,
                user_id=email,
                redirect_uri="",
                state="",
                scope=f"{INTERNAL_SCOPE_PREFIX}{role}",
                expires_at=now + timedelta(seconds=settings.REFRESH_TTL),
                revoked=False,
                consumed=False,
                created_at=now,
            ),
        ]
    )
    await session.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TTL,
        "user": {"id": email, "email": email, "display_name": email, "role": role},
    }


def _internal_user(grant: OAuthGrantORM) -> InternalUser:
    role = grant.scope.removeprefix(INTERNAL_SCOPE_PREFIX)
    return InternalUser(
        id=grant.user_id,
        email=grant.user_id,
        role=role,
        family_id=grant.family_id,
    )


async def get_current_internal_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> InternalUser:
    scheme, _, raw_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw_token or len(raw_token) > 2048:
        raise ApiError("unauthorized", "Требуется вход в панель аудитории.")
    grant = await session.scalar(
        select(OAuthGrantORM).where(OAuthGrantORM.token_hash == _hash(raw_token))
    )
    if (
        not grant
        or grant.kind != "app_access"
        or grant.client_id != INTERNAL_CLIENT_ID
        or grant.revoked
        or _as_utc(grant.expires_at) <= datetime.now(timezone.utc)
    ):
        raise ApiError("unauthorized", "Сессия истекла. Войдите снова.")
    return _internal_user(grant)


async def require_internal_user(
    _user: InternalUser = Depends(get_current_internal_user),
) -> None:
    return None


def require_roles(*roles: str) -> Callable[..., object]:
    async def dependency(
        user: InternalUser = Depends(get_current_internal_user),
    ) -> InternalUser:
        if user.role not in roles:
            raise ApiError("forbidden", "Недостаточно прав для этой операции.")
        return user

    return dependency


async def rotate_internal_refresh_token(
    session: AsyncSession, raw_token: str
) -> dict[str, object]:
    if not raw_token or len(raw_token) > 2048:
        raise ApiError("unauthorized", "Refresh-токен недействителен.")
    token_hash = _hash(raw_token)
    grant = await session.scalar(
        select(OAuthGrantORM).where(OAuthGrantORM.token_hash == token_hash)
    )
    if (
        not grant
        or grant.kind != "app_refresh"
        or grant.client_id != INTERNAL_CLIENT_ID
    ):
        raise ApiError("unauthorized", "Refresh-токен недействителен.")

    claimed = await session.scalar(
        update(OAuthGrantORM)
        .where(
            OAuthGrantORM.token_hash == token_hash,
            OAuthGrantORM.kind == "app_refresh",
            OAuthGrantORM.client_id == INTERNAL_CLIENT_ID,
            OAuthGrantORM.consumed.is_(False),
            OAuthGrantORM.revoked.is_(False),
            OAuthGrantORM.expires_at > datetime.now(timezone.utc),
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
        raise ApiError("unauthorized", "Refresh-токен недействителен или уже использован.")

    result = await issue_internal_tokens(
        session,
        grant.user_id,
        grant.scope.removeprefix(INTERNAL_SCOPE_PREFIX),
        family_id=grant.family_id,
    )
    await session.commit()
    return result


async def revoke_internal_family(session: AsyncSession, family_id: str) -> None:
    await session.execute(
        update(OAuthGrantORM)
        .where(OAuthGrantORM.family_id == family_id)
        .values(revoked=True)
    )
    await session.commit()
