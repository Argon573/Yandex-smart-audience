"""Runs (C-01/C-02): подтверждение запуска, опрос, журнал, SSE-поток."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ApiError, error_responses, simulate_error
from app.config import settings
from app.deps import engine, run_repository
from app.device_adapter.in_memory import seed_descriptors, seed_states
from app.mode_engine.catalog import get_mode
from app.mode_engine.engine import compute_preview_hash
from app.mode_engine.exceptions import EngineError, ModeNotFoundError
from app.mode_engine.models import Counters, Run, RunStep

router = APIRouter(
    prefix="/api/v1",
    tags=["runs"],
    responses=error_responses(
        "validation_error", "not_found", "internal_error"
    ),
)


#: Пример тела POST .../runs: hash берётся из ответа preview (свежий seed).
_RUN_CREATE_EXAMPLE: dict[str, Any] = {
    "mode_id": "hybrid",
    "preview_hash": "43bd033f1041156e",
    "ack_warnings": ["presence_absent"],
}


class RunCreate(BaseModel):
    """Тело подтверждения запуска (C-01, S4→S5)."""

    model_config = ConfigDict(
        json_schema_extra={
            # example (Swagger UI) + examples (JSON Schema 2020-12, OpenAPI 3.1)
            "example": _RUN_CREATE_EXAMPLE,
            "examples": [_RUN_CREATE_EXAMPLE],
        }
    )

    mode_id: str = Field(description="Каталожный id режима: arrival|lecture|hybrid|break|finish.")
    preview_hash: str = Field(
        default="",
        description="Хэш из POST .../preview. Пустой строкой — без сверки (для отладки).",
    )
    ack_warnings: list[str] = Field(
        default_factory=list,
        description="Коды предупреждений, подтверждённые оператором (например presence_absent).",
    )


class RunStepPayload(BaseModel):
    """Один шаг журнала в контракте C-02 (Часть 2, §3.4)."""

    sequence: int
    device_id: str
    device_name: str = ""
    target: dict[str, Any]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    status: Literal["pending", "applied", "skipped", "error"]
    error_code: str | None = None
    error_text: str | None = None
    manual_hint: str | None = None
    attempts: int = 1
    duration_ms: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RunWarningPayload(BaseModel):
    code: str
    acknowledged: bool = True


class RunPayload(BaseModel):
    """Полный журнал запуска: status, counters, шаги, poll_url (C-02)."""

    id: str
    mode_id: str
    mode_title: str
    classroom_id: str
    status: Literal["running", "applied", "failed"]
    outcome_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    policy: str
    counters: Counters
    error_code: str | None = None
    warnings: list[RunWarningPayload]
    steps: list[RunStepPayload]
    counters_total: int
    preview_hash: str
    state_version: int
    requested_by: dict[str, Any] | None = None
    poll_url: str
    step_total: int


class RunListItem(BaseModel):
    id: str
    mode_id: str
    mode_title: str
    status: Literal["running", "applied", "failed"]
    requested_by: str | None = None
    duration_ms: int | None = None
    created_at: str | None = None
    counters: Counters


class RunList(BaseModel):
    items: list[RunListItem]
    total: int
    limit: int
    offset: int


class RunSteps(BaseModel):
    items: list[RunStepPayload]
    total: int


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


def _example_run_payload() -> dict[str, Any]:
    """Синтетический применённый run для /docs.

    Сериализуется тем же _run_payload, что и живой ответ, поэтому пример
    не расходится с контрактом C-02. Шаги — из каталога hybrid на свежем seed.
    """
    mode = get_mode("hybrid")
    if mode is None:
        raise RuntimeError("catalog: режим hybrid не найден")
    names = {d.id: d.name for d in seed_descriptors()}
    states = seed_states()
    base = datetime(2026, 11, 3, 16, 40, 0, tzinfo=timezone.utc)
    run_id = "run-01j8zk3m4n5p6q7r8s9t0v1w2x"

    steps: list[RunStep] = []
    for index, spec in enumerate(mode.steps, start=1):
        before = dict(states[spec.device_id].state)
        target = dict(spec.target_state)
        # G2 движка: уже в целевом состоянии → skipped, after = before
        already = all(before.get(key) == value for key, value in target.items())
        steps.append(
            RunStep(
                run_id=run_id,
                sequence=spec.sequence,
                device_id=spec.device_id,
                device_name=names.get(spec.device_id, spec.device_id),
                target=target,
                before=before,
                after=before if already else target,
                status="skipped" if already else "applied",
                attempts=1,
                duration_ms=1 if already else 35 + index * 6,
                started_at=base + timedelta(seconds=index),
                finished_at=base
                + timedelta(seconds=index, milliseconds=1 if already else 40),
            )
        )
    applied = sum(1 for s in steps if s.status == "applied")
    run = Run(
        id=run_id,
        mode_id="hybrid",
        classroom_id="9f1b6a2e-0000-4000-8000-000000000001",
        status="applied",
        counters=Counters(
            applied=applied,
            skipped=len(steps) - applied,
            error=0,
        ),
        preview_hash=compute_preview_hash(12, "hybrid"),
        state_version=12,
        requested_by={"id": "u1", "display_name": "Иванова М.С.", "role": "teacher"},
        policy=settings.RUN_POLICY,
        outcome_message=f"Режим «{mode.title}» применён: {applied} шагов.",
        created_at=base - timedelta(seconds=5),
        started_at=base,
        finished_at=base + timedelta(seconds=len(steps)),
        duration_ms=len(steps) * 1000,
        steps=steps,
    )
    return _run_payload(run)


_RUN_EXAMPLE = _example_run_payload()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Сформировать строку SSE: event + data (JSON, UTF-8)."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post(
    "/classrooms/{classroomId}/runs",
    status_code=201,
    responses={
        201: {
            "model": RunPayload,
            "description": "Запуск создан: status=applied|failed, шаги, counters, poll_url.",
            "content": {"application/json": {"example": _RUN_EXAMPLE}},
        },
        200: {
            "model": RunPayload,
            "description": "Идемпотентный повтор того же Idempotency-Key: тот же run.",
            "content": {"application/json": {"example": _RUN_EXAMPLE}},
        },
        **error_responses(
            "preview_stale",
            "warnings_unacked",
            "precondition_failed",
            "idempotency_mismatch",
            "run_in_progress",
        ),
    },
)
async def create_run(
    classroomId: str,
    body: RunCreate,
    response: Response,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description=(
            "Ключ идемпотентности (C-01, §3.3): повтор с тем же телом → 200 + тот же run, "
            "с другим телом → 409 idempotency_mismatch."
        ),
    ),
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


@router.get(
    "/runs/{runId}",
    responses={
        200: {
            "model": RunPayload,
            "description": "Итог/прогресс запуска из SQLite.",
            "content": {"application/json": {"example": _RUN_EXAMPLE}},
        }
    },
)
async def get_run(
    runId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Опрос прогресса/итога из SQLite (C-02, экран S5). 404, если не найден."""
    run = await run_repository.get_run(runId)
    if run is None:
        # fallback: только что созданный в этом процессе, БД ещё не видна
        run = engine.get_run(runId)
    if run is None:
        raise ApiError("not_found", details={"run_id": runId})
    return _run_payload(run)


@router.get(
    "/runs/{runId}/steps",
    responses={
        200: {
            "model": RunSteps,
            "description": "Только шаги журнала (без обёртки run).",
            "content": {
                "application/json": {
                    "example": {
                        "items": _RUN_EXAMPLE["steps"],
                        "total": _RUN_EXAMPLE["counters_total"],
                    }
                }
            },
        }
    },
)
async def get_run_steps(runId: str) -> dict[str, Any]:
    run = await run_repository.get_run(runId)
    if run is None:
        run = engine.get_run(runId)
    if run is None:
        raise ApiError("not_found", details={"run_id": runId})
    payload = _run_payload(run)
    return {"items": payload["steps"], "total": payload["counters_total"]}


@router.get(
    "/runs",
    responses={
        200: {
            "model": RunList,
            "description": "Журнал запусков с фильтрами classroom_id|mode_id|status.",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": _RUN_EXAMPLE["id"],
                                "mode_id": "hybrid",
                                "mode_title": "Гибридная презентация",
                                "status": "applied",
                                "requested_by": "Иванова М.С.",
                                "duration_ms": 8000,
                                "created_at": "2026-11-03T16:39:55+00:00",
                                "counters": {"applied": 6, "skipped": 2, "error": 0},
                            }
                        ],
                        "total": 1,
                        "limit": 50,
                        "offset": 0,
                    }
                }
            },
        }
    },
)
async def list_runs(
    classroom_id: str | None = None,
    mode_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Журнал запусков из SQLite с пагинацией и фильтрами."""
    items, total = await run_repository.list_runs(
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
                "mode_title": (
                    get_mode(run.mode_id).title if get_mode(run.mode_id) else run.mode_id
                ),
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


@router.get(
    "/runs/{runId}/events",
    responses={
        200: {
            "description": (
                "SSE-поток: run.current | step.updated | run.finished + heartbeat. "
                "В Swagger кнопка «Try it out» поток не показывает — "
                "проверяйте через curl: curl -N http://localhost:8000/api/v1/runs/<id>/events"
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def run_events(runId: str) -> StreamingResponse:
    """SSE-поток прогресса запуска (text/event-stream).

    События: step.updated (шаг), run.finished (итог, закрывает поток),
    heartbeat (:) при простое > 15 с. Текущее состояние — первым сообщением.
    """
    if not settings.SSE_ENABLED:
        raise ApiError("service_not_ready", "SSE отключён (SSE_ENABLED=false).")

    run = await run_repository.get_run(runId)
    if run is None:
        run = engine.get_run(runId)
    if run is None:
        raise ApiError("not_found", details={"run_id": runId})

    queue = engine.subscribe(runId)

    async def event_stream():
        try:
            # 1) текущее состояние сразу после подписки
            if run.status != "running":
                yield _sse_event("run.finished", _run_payload(run))
                return

            yield _sse_event("run.current", _run_payload(run))

            # 2) живые события от _notify / heartbeat
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except (asyncio.TimeoutError, TimeoutError):
                    yield ": heartbeat\n\n"
                    continue

                event_type = event.get("type")
                if event_type == "run.finished":
                    # данные уже в model_dump — нормализуем через payload, если можно
                    data = event.get("run")
                    if isinstance(data, dict) and "counters" in data:
                        yield _sse_event("run.finished", data)
                    else:
                        fresh = await run_repository.get_run(runId) or engine.get_run(runId)
                        yield _sse_event(
                            "run.finished",
                            _run_payload(fresh) if fresh else {"id": runId, "status": "unknown"},
                        )
                    return
                if event_type == "step.updated":
                    yield _sse_event("step.updated", event)
                else:
                    yield _sse_event(event_type or "message", event)
        finally:
            engine.unsubscribe(runId, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
