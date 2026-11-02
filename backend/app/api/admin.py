from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users")
async def list_users(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.post("/users", status_code=201)
async def create_user() -> dict[str, Any]:
    return {"id": "", "email": "", "display_name": "", "role": "teacher", "status": "active"}


@router.patch("/users/{userId}/role")
async def change_role(userId: str) -> dict[str, Any]:
    return {"id": userId, "role": "teacher"}


@router.delete("/users/{userId}", status_code=204)
async def delete_user(userId: str) -> None:
    return None
