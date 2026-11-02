"""Runs (C-01/C-02): подтверждение запуска, опрос прогресса, журнал."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field

from app.api.errors import ApiError, simulate_error
from app.deps import engine
from app.mode_engine.catalog import get_mode
from app.mode_engine.exceptions import EngineError, ModeNotFoundError
from app.mode_engine.models import Run

router = APIRouter(prefix="/api/v1", tags=["runs"])


class RunCreate(BaseModel):
    mode_id: str
    preview_hash: str = ""
    ack_warnings: list[str] = Field(default_factory=list)


def _run_payload(run: Run) -> dict[str, Any]:
    """Сериализация Run в контракт C-02 (Часть 2, §3.4)."""
    mode = get_mode(run.mode_id)
    return {
        "id": run.id,
        "mode_id": run.mode_id,
        "mode_title": mode.title if mode else run.mode_id,
        "classroom_id": run.classroom_id,
        "status": run.status,
        "outcome_message": run.outcome_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "policy": run.policy,
        "counters": run.counters.model_dump(),
        "error_code": run.error_code,
        "warnings": [w.model_dump() for w in run.warnings],
        "steps": [
            {
                "sequence": s.sequence,
                "device_id": s.device_id,
                "device_name": s.device_name,
                "target": s.target,
                "before": s.before,
                "after": s.after,
                "status": s.status,
                "error_code": s.error_code,
                "error_text": s.error_text,
                "manual_hint": s.manual_hint,
                "attempts": s.attempts,
                "duration_ms": s.duration_ms,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in run.steps
        ],
        "counters_total": len(run.steps),
        "preview_hash": run.preview_hash,
        "state_version": run.state_version,
        "requested_by": run.requested_by,
        "poll_url": f"/api/v1/runs/{run.id}",
        "step_total": len(run.steps),
    }


@router.post("/classrooms/{classroomId}/runs", status_code=201)
async def create_run(
    classroomId: str,
    body: RunCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Подтверждение запуска (S4→S5).

    Естественные ошибки для алертов фронта:
    - preview_hash ≠ живого preview → 409 preview_stale;
    - warnings без ack_warnings → 422 warnings_unacked;
    - can_apply=false → 422 precondition_failed;
    - тот же Idempotency-Key с другим телом → 409 idempotency_mismatch.
    Повтор того же Idempotency-Key → 200 + существующий run.
    Или принудительно: X-Simulate-Error: <code>.
    """
    requested_by = {"id": "u1", "display_name": "Иванова М.С.", "role": "teacher"}
    try:
        run, created = await engine.run(
            body.mode_id,
            classroomId,
            preview_hash=body.preview_hash,
            ack_warnings=body.ack_warnings,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
        )
    except ModeNotFoundError:
        raise ApiError("not_found", details={"mode_id": body.mode_id}) from None
    except EngineError as exc:
        raise ApiError(exc.code, message=exc.message, details=exc.details) from exc

    if not created:
        response.status_code = 200  # идемпотентный повтор (Часть 2, §1, §3.3)
    return _run_payload(run)


@router.get("/runs/{runId}")
async def get_run(
    runId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Опрос прогресса/итога запуска (C-02, экран S5). 404, если не найден."""
    run = engine.get_run(runId)
    if run is None:
        raise ApiError("not_found", details={"run_id": runId})
    return _run_payload(run)


@router.get("/runs/{runId}/steps")
async def get_run_steps(runId: str) -> dict[str, Any]:
    run = engine.get_run(runId)
    if run is None:
        raise ApiError("not_found", details={"run_id": runId})
    payload = _run_payload(run)
    return {"items": payload["steps"], "total": payload["counters_total"]}


@router.get("/runs")
async def list_runs(
    classroom_id: str | None = None,
    mode_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    items, total = engine.list_runs(
        classroom_id=classroom_id,
        mode_id=mode_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                "id": run.id,
                "mode_id": run.mode_id,
                "mode_title": (get_mode(run.mode_id).title if get_mode(run.mode_id) else run.mode_id),
                "status": run.status,
                "requested_by": (run.requested_by or {}).get("display_name"),
                "duration_ms": run.duration_ms,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "counters": run.counters.model_dump(),
            }
            for run in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
