"""Operator API (C-06): fault injection, занятость, сброс, health, summary (S7–S9)."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.errors import ApiError, api_error_from_adapter, error_responses, simulate_error
from app.config import settings
from app.deps import engine, in_memory_adapter
from app.device_adapter.dto import AdapterError, Fault

router = APIRouter(
    prefix="/api/v1/operator",
    tags=["operator"],
    responses=error_responses(
        "validation_error", "not_found", "internal_error"
    ),
)


class FaultCreate(BaseModel):
    """Тело инъекции отказа (Часть 2, §7.1)."""

    device_id: str
    kind: Literal["unavailable", "latency", "error"]
    value_ms: int | None = None
    error_code: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)
    comment: str | None = None


class OccupancyBody(BaseModel):
    """Занятость D11 — источник предусловия finish (Часть 2, §7.2)."""

    detected: bool
    presence_minutes: int = Field(default=0, ge=0)


class FaultList(BaseModel):
    """Активные faults + список «сломанных» приборов (S7)."""

    items: list[Fault]
    total: int
    limit: int
    offset: int
    broken_devices: list[str]


class FaultDeleted(BaseModel):
    id: str
    active: bool = Field(default=False, description="Всегда false: снятие идемпотентно.")


class OccupancyResult(BaseModel):
    device_id: str
    state: dict[str, Any]
    presence_minutes: int
    state_version: int
    updated_at: str


class ResetResult(BaseModel):
    """Чистый старт: seed + очистка faults и журнала (AC-02)."""

    restored: bool
    state_version: int
    restored_devices: int
    faults_cleared: int
    runs_cleared: int
    initial_state_ref: str


class HealthDevice(BaseModel):
    id: str
    reachable: bool
    last_error: str | None = None
    last_success_at: str | None = None


class AdapterHealthResult(BaseModel):
    adapter: str
    status: Literal["ok", "degraded", "unreachable"]
    checked_at: str | None
    devices: list[HealthDevice]
    broken_devices: list[str]


class SummaryRuns(BaseModel):
    applied: int
    failed: int
    running: int
    partial: int


class SummaryAdapter(BaseModel):
    p95_read_ms: int
    p95_execute_ms: int
    status: Literal["ok", "degraded", "unreachable"]


class SummaryError(BaseModel):
    ts: str | None = None
    device_id: str
    error_code: str
    run_id: str
    message: str | None = None


class OperatorSummary(BaseModel):
    """Сводка S8/S9 для панели оператора."""

    window: str
    runs: SummaryRuns
    adapter: SummaryAdapter
    errors: list[SummaryError]
    voice: dict[str, Any]
    energy: dict[str, Any]
    generated_at: str


@router.post(
    "/classrooms/{classroomId}/simulator/faults",
    status_code=201,
    responses={
        201: {
            "model": Fault,
            "description": "Активный fault создан.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "flt-01j8zk3m4n5p6q7r8s9t0v1w2x",
                        "device_id": "D02",
                        "kind": "unavailable",
                        "value_ms": None,
                        "error_code": None,
                        "expires_at": "2026-11-03T17:10:00+00:00",
                        "active": True,
                        "created_at": "2026-11-03T16:55:00+00:00",
                        "created_by": "operator@stand",
                        "comment": "Демо: проектор не отвечает",
                    }
                }
            },
        },
        **error_responses("not_found", "invalid_value"),
    },
)
async def inject_fault(
    classroomId: str,
    body: FaultCreate,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Создать активный fault (kind: unavailable | latency | error)."""
    try:
        fault = in_memory_adapter.inject_fault(
            body.device_id,
            body.kind,
            value_ms=body.value_ms,
            error_code=body.error_code,
            ttl_seconds=body.ttl_seconds,
            comment=body.comment,
            created_by="operator@stand",
        )
    except AdapterError as exc:
        raise api_error_from_adapter(exc) from exc
    return fault.model_dump(mode="json")


@router.get(
    "/classrooms/{classroomId}/simulator/faults",
    responses={200: {"model": FaultList, "description": "Активные faults и broken_devices."}},
)
async def list_faults(classroomId: str) -> dict[str, Any]:
    items = in_memory_adapter.list_faults()
    return {
        "items": [f.model_dump(mode="json") for f in items],
        "total": len(items),
        "limit": 50,
        "offset": 0,
        "broken_devices": in_memory_adapter.broken_devices,
    }


@router.delete(
    "/simulator/faults/{faultId}",
    responses={200: {"model": FaultDeleted, "description": "Снятие fault, идемпотентно."}},
)
async def delete_fault(faultId: str) -> dict[str, Any]:
    """Снять fault. Идемпотентно: неактивный/неизвестный → active=false."""
    in_memory_adapter.remove_fault(faultId)
    return {"id": faultId, "active": False}


@router.post(
    "/classrooms/{classroomId}/simulator/occupancy",
    responses={
        200: {
            "model": OccupancyResult,
            "description": "motion D11 + presence_minutes (предусловия finish).",
            "content": {
                "application/json": {
                    "example": {
                        "device_id": "D11",
                        "state": {"motion": "detected"},
                        "presence_minutes": 7,
                        "state_version": 2,
                        "updated_at": "2026-11-03T16:56:00+00:00",
                    }
                }
            },
        }
    },
)
async def set_occupancy(
    classroomId: str,
    body: OccupancyBody,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Установить motion D11 и presence_minutes (предусловия режимов)."""
    motion = "detected" if body.detected else "not_detected"
    in_memory_adapter.presence_minutes = body.presence_minutes
    try:
        state = await in_memory_adapter.set_state("D11", {"motion": motion})
    except AdapterError as exc:
        raise api_error_from_adapter(exc) from exc
    return {
        "device_id": "D11",
        "state": dict(state.state),
        "presence_minutes": body.presence_minutes,
        "state_version": state.state_version,
        "updated_at": state.updated_at.isoformat(),
    }


@router.post(
    "/classrooms/{classroomId}/simulator/reset",
    responses={200: {"model": ResetResult, "description": "Seed + очистка faults и runs."}},
)
async def reset_simulator(classroomId: str) -> dict[str, Any]:
    """Сброс seed + faults + журнал запусков (AC-02 «чистый старт»)."""
    faults_cleared = in_memory_adapter.clear_faults()
    restored_devices = len(await in_memory_adapter.reset())
    runs_cleared = await engine.aclear_runs()
    states = await in_memory_adapter.read()
    return {
        "restored": True,
        "state_version": sum(s.state_version for s in states.values()),
        "restored_devices": restored_devices,
        "faults_cleared": faults_cleared,
        "runs_cleared": runs_cleared,
        "initial_state_ref": f"seed-{settings.SIMULATOR_SEED}",
    }


@router.get(
    "/classrooms/{classroomId}/adapter/health",
    responses={
        200: {
            "model": AdapterHealthResult,
            "description": "degraded при активных faults; devices — только сломанные.",
            "content": {
                "application/json": {
                    "example": {
                        "adapter": "in_memory",
                        "status": "degraded",
                        "checked_at": "2026-11-03T16:57:00+00:00",
                        "devices": [
                            {
                                "id": "D02",
                                "reachable": False,
                                "last_error": "device_unavailable",
                                "last_success_at": "2026-11-03T16:40:00+00:00",
                            }
                        ],
                        "broken_devices": ["D02"],
                    }
                }
            },
        }
    },
)
async def adapter_health(classroomId: str) -> dict[str, Any]:
    """Health адаптера (S8): degraded при активных faults."""
    info = await in_memory_adapter.health()
    return {
        "adapter": info.adapter,
        "status": info.status,
        "checked_at": info.checked_at.isoformat() if info.checked_at else None,
        "devices": info.devices,
        "broken_devices": in_memory_adapter.broken_devices,
    }


@router.get(
    "/summary",
    responses={
        200: {
            "model": OperatorSummary,
            "description": "Агрегаты runs/adapter/errors за окно (window=1h|24h|7d).",
        }
    },
)
async def summary(window: str = "1h") -> dict[str, Any]:
    """Сводка S8/S9: runs, adapter, ошибки. Данные из журнала engine."""
    items, _ = engine.list_runs(limit=200)
    applied = sum(1 for r in items if r.status == "applied")
    failed = sum(1 for r in items if r.status == "failed")
    running = sum(1 for r in items if r.status == "running")
    partial = sum(
        1 for r in items if r.status == "failed" and r.counters.applied > 0
    )
    health = await in_memory_adapter.health()

    errors: list[dict[str, Any]] = []
    for run in items:
        for step in run.steps:
            if step.status == "error" and step.error_code:
                errors.append(
                    {
                        "ts": step.finished_at.isoformat() if step.finished_at else None,
                        "device_id": step.device_id,
                        "error_code": step.error_code,
                        "run_id": run.id,
                        "message": step.error_text,
                    }
                )

    return {
        "window": window,
        "runs": {"applied": applied, "failed": failed, "running": running, "partial": partial},
        "adapter": {
            "p95_read_ms": 12,
            "p95_execute_ms": 45,
            "status": health.status,
        },
        "errors": errors,
        "voice": {"actions_total": 0, "success_rate": 0.0},
        "energy": {"devices_off_after_finish": 0, "estimated_watts_saved": 0},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
