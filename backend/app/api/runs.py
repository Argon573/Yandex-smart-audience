from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.api.errors import ApiError, simulate_error
from app.api.mocks import PREVIEW_HASH, build_run_finished_mock, build_run_mock

router = APIRouter(prefix="/api/v1", tags=["runs"])


class RunCreate(BaseModel):
    mode_id: str
    preview_hash: str = ""
    ack_warnings: list[str] = Field(default_factory=list)


@router.post("/classrooms/{classroomId}/runs", status_code=201)
async def create_run(
    classroomId: str,
    body: RunCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Мок apply (S4→S5).

    Естественные ошибки для отработки алертов фронтом:
    - preview_hash != preview_hash из preview → 409 preview_stale;
    - warnings из preview не подтверждены в ack_warnings → 422 warnings_unacked.
    Или принудительно: заголовок X-Simulate-Error: <code>.
    """
    if body.preview_hash != PREVIEW_HASH:
        raise ApiError(
            "preview_stale",
            details={
                "expected_preview_hash": PREVIEW_HASH,
                "actual_preview_hash": body.preview_hash,
            },
        )
    preview_warnings = {"presence_absent"}
    missing = preview_warnings - set(body.ack_warnings)
    if missing:
        raise ApiError("warnings_unacked", details={"missing": sorted(missing)})
    return build_run_mock(classroomId, body.mode_id)


@router.get("/runs/{runId}")
async def get_run(
    runId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Мок прогресса/итога запуска (C-02, экран S5)."""
    return build_run_finished_mock(runId)


@router.get("/runs/{runId}/steps")
async def get_run_steps(runId: str) -> dict[str, Any]:
    run = build_run_finished_mock(runId)
    return {"items": run["steps"], "total": run["counters_total"]}


@router.get("/runs")
async def list_runs(
    classroom_id: str | None = None,
    mode_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    run = build_run_finished_mock("7a3e0b41-0000-4000-8000-000000000000")
    return {
        "items": [
            {
                "id": run["id"],
                "mode_id": run["mode_id"],
                "mode_title": run["mode_title"],
                "status": run["status"],
                "requested_by": "Иванова М.С.",
                "duration_ms": run["duration_ms"],
                "created_at": run["created_at"],
                "counters": run["counters"],
            }
        ],
        "total": 1,
        "limit": limit,
        "offset": offset,
    }
