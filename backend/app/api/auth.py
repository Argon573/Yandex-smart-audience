from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.config import settings
from app.security.internal_auth import (
    InternalUser,
    configured_internal_user,
    get_current_internal_user,
    issue_internal_tokens,
    revoke_internal_family,
    rotate_internal_refresh_token,
)
from app.security.rate_limit import app_login_limit, app_refresh_limit
from app.storage.db import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=2048)


@router.post("/login", dependencies=[Depends(app_login_limit)])
async def login(
    body: LoginBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not settings_configured():
        raise ApiError("service_not_ready", "Учётная запись панели не настроена.")
    identity = configured_internal_user(body.email, body.password)
    if identity is None:
        raise ApiError("unauthorized", "Неверный email или пароль.")
    email, role = identity
    return await issue_internal_tokens(session, email, role)


@router.post("/refresh", dependencies=[Depends(app_refresh_limit)])
async def refresh(
    body: RefreshBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await rotate_internal_refresh_token(session, body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    user: InternalUser = Depends(get_current_internal_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await revoke_internal_family(session, user.family_id)


@router.get("/me")
async def me(
    user: InternalUser = Depends(get_current_internal_user),
) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.email,
        "role": user.role,
        "scopes": [f"role:{user.role}"],
    }


def settings_configured() -> bool:
    return bool(
        settings.APP_DEMO_EMAIL.strip()
        and settings.APP_DEMO_PASSWORD
        and settings.APP_DEMO_ROLE.strip().lower() in {"teacher", "operator", "admin"}
    )
