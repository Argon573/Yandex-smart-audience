from fastapi import APIRouter
from fastapi.responses import Response

from app.observability.metrics import render_metrics

router = APIRouter(tags=["observability"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
