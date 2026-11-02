from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.get("/link")
async def link_status() -> dict[str, Any]:
    return {
        "linked": False,
        "ya_user_id_masked": "",
        "linked_at": None,
        "access_token_expires_at": None,
        "refresh_rotated_at": None,
    }


@router.get("/devices")
async def published_devices() -> dict[str, Any]:
    return {"published": [], "blocked": [], "allowlist_version": "2026-10-27"}


@router.get("/voice-commands")
async def voice_commands(limit: int = 20) -> dict[str, Any]:
    return {"items": [], "total": 0}


@router.post("/link/revoke")
async def revoke_link() -> dict[str, Any]:
    return {"revoked": True, "ya_user_id_masked": ""}
