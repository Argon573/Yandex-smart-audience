import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(prefix="/v1.0", tags=["provider"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@router.head("/")
async def check() -> Response:
    return Response(status_code=200)


@router.get("/user/devices")
async def discovery(request: Request) -> dict[str, Any]:
    return {
        "request_id": _request_id(request),
        "payload": {"user_id": "stub-user", "devices": []},
    }


@router.post("/user/devices/query")
async def query(request: Request) -> dict[str, Any]:
    return {
        "request_id": _request_id(request),
        "payload": {"devices": []},
    }


@router.post("/user/devices/action")
async def action(request: Request) -> dict[str, Any]:
    return {
        "request_id": _request_id(request),
        "payload": {"devices": []},
    }


@router.post("/user/unlink")
async def unlink(request: Request) -> dict[str, Any]:
    return {"request_id": _request_id(request), "payload": {}}
