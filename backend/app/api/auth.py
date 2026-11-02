from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login() -> dict[str, Any]:
    return {
        "access_token": "stub_access_token",
        "expires_in": 900,
        "user": {"id": "", "display_name": "", "role": "teacher"},
    }


@router.post("/refresh")
async def refresh() -> dict[str, Any]:
    return {"access_token": "stub_access_token", "expires_in": 900}


@router.post("/logout", status_code=204)
async def logout() -> None:
    return None


@router.get("/me")
async def me() -> dict[str, Any]:
    return {"id": "", "email": "", "display_name": "", "role": "teacher", "scopes": []}
