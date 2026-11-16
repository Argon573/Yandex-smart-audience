from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.oauth import _as_utc
from app.storage.db import get_session
from app.storage.models import OAuthGrantORM
from app.security.internal_auth import require_internal_user, require_roles

router = APIRouter(
    prefix="/api/v1/assistant",
    tags=["assistant"],
    dependencies=[Depends(require_internal_user)],
)


@router.get("/link")
async def link_status(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    grants = list(
        (
            await session.scalars(
                select(OAuthGrantORM)
                .where(
                    OAuthGrantORM.kind.in_(["access", "refresh"]),
                    OAuthGrantORM.revoked.is_(False),
                )
                .order_by(OAuthGrantORM.created_at.desc())
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    active = [grant for grant in grants if _as_utc(grant.expires_at) > now]
    families = {grant.family_id for grant in active}
    access = [grant for grant in active if grant.kind == "access"]
    refresh = [grant for grant in active if grant.kind == "refresh"]
    latest = active[0] if active else None
    return {
        "linked": bool(families),
        "ya_user_id_masked": _mask_user_id(latest.user_id) if latest else "",
        "linked_at": min((_as_utc(item.created_at) for item in active), default=None),
        "access_token_expires_at": max(
            (_as_utc(item.expires_at) for item in access), default=None
        ),
        "refresh_rotated_at": max(
            (_as_utc(item.created_at) for item in refresh), default=None
        ),
    }


def _mask_user_id(user_id: str) -> str:
    if not user_id:
        return ""
    if len(user_id) <= 3:
        return f"{user_id[0]}***"
    return f"{user_id[:2]}***{user_id[-2:]}"


@router.get("/devices")
async def published_devices() -> dict[str, Any]:
    return {"published": [], "blocked": [], "allowlist_version": "2026-10-27"}


@router.get("/voice-commands")
async def voice_commands(
    request: Request, limit: int = Query(default=20, ge=1, le=1000)
) -> dict[str, Any]:
    history = getattr(request.app.state, "voice_commands", [])
    items = list(reversed(history[-limit:]))
    return {"items": items, "total": len(history)}


@router.post("/link/revoke")
async def revoke_link(
    request: Request,
    _operator: Any = Depends(require_roles("operator", "admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    grants = list(
        (
            await session.scalars(
                select(OAuthGrantORM).where(
                    OAuthGrantORM.kind.in_(["access", "refresh"]),
                    OAuthGrantORM.revoked.is_(False),
                )
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    active = [grant for grant in grants if _as_utc(grant.expires_at) > now]
    family_ids = {grant.family_id for grant in active}
    user_id = active[0].user_id if active else ""
    if family_ids:
        await session.execute(
            update(OAuthGrantORM)
            .where(OAuthGrantORM.family_id.in_(family_ids))
            .values(revoked=True)
        )
        await session.commit()
        audit = getattr(request.app.state, "oauth_audit_events", [])
        audit.append(
            {
                "event": "linking_revoked",
                "ts": now.isoformat(),
                "user_id_masked": _mask_user_id(user_id),
            }
        )
        request.app.state.oauth_audit_events = audit[-1000:]
    return {"revoked": True, "ya_user_id_masked": _mask_user_id(user_id)}
