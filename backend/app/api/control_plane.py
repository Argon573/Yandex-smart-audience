"""Control Plane (C-01): план аудитории, карточки приборов, modes, preview, команды."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.errors import (
    ApiError,
    api_error_from_adapter,
    error_responses,
    simulate_error,
)
from app.deps import engine, in_memory_adapter
from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import AdapterError, DeviceDescriptor, DeviceState
from app.device_adapter.in_memory import SEED_ZONES, seed_descriptors, seed_states
from app.mode_engine.catalog import MODES, get_mode
from app.mode_engine.exceptions import ModeNotFoundError
from app.mode_engine.models import PreviewResult

router = APIRouter(
    prefix="/api/v1",
    tags=["control-plane"],
    responses=error_responses(
        "validation_error", "not_found", "internal_error"
    ),
)

# instance capability → ключ state (обратный алиас thermostat_mode)
_INSTANCE_TO_STATE_KEY: dict[str, str] = {"thermostat": "thermostat_mode"}


# --- Модели ответов для OpenAPI (/docs) -------------------------------------
# Только документация: рантайм-сериализация осталась dict, response_model не включён.


class DevicePayload(BaseModel):
    """Карточка прибора в плане аудитории (C-01, §2.1)."""

    id: str
    name: str
    ya_type: str
    managability: Literal["controllable", "readonly"]
    state: dict[str, Any] = Field(description="Текущее состояние прибора.")
    state_version: int
    updated_at: str
    source: Literal["mode_run", "voice", "manual", "simulator"]
    status: Literal["on", "off", "unavailable"]


class ZonePayload(BaseModel):
    """Зона аудитории (Z1–Z3) с приборами."""

    id: str
    code: str
    name: str
    purpose: str
    devices: list[DevicePayload]


class RoomPlan(BaseModel):
    """План аудитории: зоны, приборы, сводные счётчики (S1)."""

    id: str
    name: str
    state_version: int
    adapter_health: Literal["ok", "degraded", "unreachable"]
    updated_at: str | None
    zones: list[ZonePayload]
    device_count: int
    readonly_count: int


class ClassroomRef(BaseModel):
    id: str
    name: str
    state_version: int


class ClassroomList(BaseModel):
    items: list[ClassroomRef]
    total: int
    limit: int
    offset: int


class StateDevice(BaseModel):
    id: str
    state: dict[str, Any]
    source: Literal["mode_run", "voice", "manual", "simulator"]
    updated_at: str | None


class ClassroomState(BaseModel):
    """Инкрементальное состояние (since_version) для опроса фронта."""

    changed: bool
    state_version: int
    adapter_health: Literal["ok", "degraded", "unreachable"]
    devices: list[StateDevice]


class DeviceSpecs(BaseModel):
    capabilities: list[dict[str, Any]]
    properties: list[dict[str, Any]]


class DeviceDetail(BaseModel):
    """Полная карточка прибора: specs, доступные команды, история (S2)."""

    id: str
    zone_id: str
    name: str
    ya_type: str
    managability: Literal["controllable", "readonly"]
    state: dict[str, Any]
    specs: DeviceSpecs
    commands_available: bool
    history: list[dict[str, Any]]
    state_version: int
    updated_at: str | None


class DeviceHistory(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class CommandItem(BaseModel):
    """Одна команда ручного управления (Часть 2, §2.5)."""

    type: str
    instance: str
    value: Any


class DeviceCommandBody(BaseModel):
    commands: list[CommandItem] = Field(default_factory=list)


class DeviceCommandResult(BaseModel):
    """Ответ ручного управления (S2): новое состояние прибора."""

    device_id: str
    state: dict[str, Any]
    state_version: int
    updated_at: str
    source: Literal["mode_run", "voice", "manual", "simulator"] = "manual"


class ModeSummary(BaseModel):
    id: str
    title: str
    description: str
    step_count: int
    critical_device_ids: list[str]
    enabled: bool
    preconditions: list[dict[str, Any]]


class ModeList(BaseModel):
    items: list[ModeSummary]


class ModeDetail(BaseModel):
    """Полный каталог режима: шаги + предусловия (§11)."""

    id: str
    title: str
    description: str
    steps: list[dict[str, Any]]
    critical_device_ids: list[str]
    enabled: bool
    preconditions: list[dict[str, Any]]


def _ui_status(state: DeviceState) -> str:
    if not state.reachable:
        return "unavailable"
    if "on" in state.state:
        return "on" if state.state["on"] else "off"
    return "on"


def _device_payload(
    descriptor: DeviceDescriptor, state: DeviceState | None
) -> dict[str, Any]:
    return {
        "id": descriptor.id,
        "name": descriptor.name,
        "ya_type": descriptor.ya_type,
        "managability": descriptor.managability,
        "state": dict(state.state) if state else {},
        "state_version": state.state_version if state else 0,
        "updated_at": (state.updated_at if state else datetime.now(timezone.utc)).isoformat(),
        "source": state.source if state else "simulator",
        "status": _ui_status(state) if state else "unavailable",
    }


async def build_room_plan(adapter: ClassroomDeviceAdapter) -> dict[str, Any]:
    """План S1: зоны + приборы; state_version = сумма версий, health с faults."""
    descriptors = await adapter.describe()
    states = await adapter.read()
    health = await adapter.health()

    zones: list[dict[str, Any]] = []
    for zone in SEED_ZONES:
        zone_devices = [
            _device_payload(d, states.get(d.id))
            for d in descriptors
            if d.zone_id == zone["id"]
        ]
        zones.append({**zone, "devices": zone_devices})

    updated_ats = [s.updated_at for s in states.values()]
    return {
        "id": "9f1b6a2e-0000-4000-8000-000000000001",
        "name": "Аудитория 301",
        "state_version": sum(s.state_version for s in states.values()),
        "adapter_health": health.status,
        "updated_at": max(updated_ats).isoformat() if updated_ats else None,
        "zones": zones,
        "device_count": len(descriptors),
        "readonly_count": sum(
            1 for d in descriptors if d.managability == "readonly"
        ),
    }


def _example_room_plan() -> dict[str, Any]:
    """Пример плана для /docs: собирается из seed, в зоне 1–2 прибора вместо всех."""
    descriptors = {d.id: d for d in seed_descriptors()}
    states = seed_states()
    sample = {"Z1": ["D01", "D02"], "Z2": ["D05", "D08"], "Z3": ["D11"]}
    zones = [
        {
            **zone,
            "devices": [
                _device_payload(descriptors[device_id], states[device_id])
                for device_id in sample[zone["id"]]
            ],
        }
        for zone in SEED_ZONES
    ]
    return {
        "id": "9f1b6a2e-0000-4000-8000-000000000001",
        "name": "Аудитория 301",
        "state_version": sum(s.state_version for s in states.values()),
        "adapter_health": "ok",
        "updated_at": "2026-10-27T10:14:52+00:00",
        "zones": zones,
        "device_count": len(descriptors),
        "readonly_count": sum(d.managability == "readonly" for d in descriptors.values()),
    }


_ROOM_EXAMPLE = _example_room_plan()

_ROOM_200 = {
    "model": RoomPlan,
    "description": "3 зоны и 12 приборов D01–D12 (пример сокращён до 1–2 приборов в зоне).",
    "content": {"application/json": {"example": _ROOM_EXAMPLE}},
}

_CLASSROOM_LIST_EXAMPLE = {
    "items": [
        {
            "id": "9f1b6a2e-0000-4000-8000-000000000001",
            "name": "Аудитория 301",
            "state_version": _ROOM_EXAMPLE["state_version"],
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0,
}


@router.get("/room", responses={200: _ROOM_200})
async def get_room() -> dict[str, Any]:
    """План аудитории для фронта: зоны Z1–Z3 и все приборы D01–D12 (seed)."""
    return await build_room_plan(in_memory_adapter)


@router.get(
    "/classrooms",
    responses={
        200: {
            "model": ClassroomList,
            "content": {"application/json": {"example": _CLASSROOM_LIST_EXAMPLE}},
        }
    },
)
async def list_classrooms() -> dict[str, Any]:
    room = await build_room_plan(in_memory_adapter)
    return {
        "items": [{"id": room["id"], "name": room["name"], "state_version": room["state_version"]}],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }


@router.get("/classrooms/{classroomId}", responses={200: _ROOM_200})
async def get_classroom(classroomId: str) -> dict[str, Any]:
    return await build_room_plan(in_memory_adapter)


@router.get(
    "/classrooms/{classroomId}/state", responses={200: {"model": ClassroomState}}
)
async def get_classroom_state(
    classroomId: str, since_version: int | None = Query(default=None)
) -> dict[str, Any]:
    room = await build_room_plan(in_memory_adapter)
    devices = [
        {"id": d["id"], "state": d["state"], "source": d["source"], "updated_at": d["updated_at"]}
        for zone in room["zones"]
        for d in zone["devices"]
    ]
    return {
        "changed": since_version != room["state_version"],
        "state_version": room["state_version"],
        "adapter_health": room["adapter_health"],
        "devices": devices,
    }


@router.get(
    "/classrooms/{classroomId}/devices/{deviceId}",
    responses={200: {"model": DeviceDetail}},
)
async def get_device(classroomId: str, deviceId: str) -> dict[str, Any]:
    descriptors = await in_memory_adapter.describe()
    states = await in_memory_adapter.read()
    descriptor = next((d for d in descriptors if d.id == deviceId), None)
    if descriptor is None:
        raise ApiError("not_found", details={"device_id": deviceId})
    state = states.get(deviceId)
    return {
        "id": descriptor.id,
        "zone_id": descriptor.zone_id,
        "name": descriptor.name,
        "ya_type": descriptor.ya_type,
        "managability": descriptor.managability,
        "state": dict(state.state) if state else {},
        "specs": {
            "capabilities": [c.model_dump() for c in descriptor.capabilities],
            "properties": [p.model_dump() for p in descriptor.properties],
        },
        "commands_available": descriptor.managability == "controllable",
        "history": [],
        "state_version": state.state_version if state else 0,
        "updated_at": state.updated_at.isoformat() if state else None,
    }


@router.get(
    "/classrooms/{classroomId}/devices/{deviceId}/history",
    responses={200: {"model": DeviceHistory}},
)
async def get_device_history(
    classroomId: str,
    deviceId: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.post(
    "/classrooms/{classroomId}/devices/{deviceId}/commands",
    responses={
        200: {"model": DeviceCommandResult},
        **error_responses(
            "readonly_device",
            "invalid_value",
            "unsupported_capability",
            "adapter_unreachable",
            "device_timeout",
        ),
    },
)
async def device_command(
    classroomId: str,
    deviceId: str,
    body: DeviceCommandBody,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Ручное управление (S2): execute через адаптер, ошибки → конверт §1.1."""
    states = await in_memory_adapter.read([deviceId])
    if deviceId not in states:
        raise ApiError("not_found", details={"device_id": deviceId})

    target: dict[str, Any] = {}
    for command in body.commands:
        key = _INSTANCE_TO_STATE_KEY.get(command.instance, command.instance)
        target[key] = command.value
    if not target:
        raise ApiError(
            "validation_error",
            "Пустой список commands.",
            {"path": "commands"},
        )

    try:
        result = await in_memory_adapter.execute(
            deviceId,
            DeviceState(
                device_id=deviceId,
                state=target,
                updated_at=datetime.now(timezone.utc),
                source="manual",
            ),
        )
    except AdapterError as exc:
        raise api_error_from_adapter(exc) from exc

    fresh = (await in_memory_adapter.read([deviceId]))[deviceId]
    return {
        "device_id": deviceId,
        "state": dict(result.current),
        "state_version": fresh.state_version,
        "updated_at": fresh.updated_at.isoformat(),
        "source": "manual",
    }


@router.get("/classrooms/{classroomId}/modes", responses={200: {"model": ModeList}})
async def list_modes(classroomId: str) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": mode.id,
                "title": mode.title,
                "description": mode.description,
                "step_count": len(mode.steps),
                "critical_device_ids": mode.critical_device_ids,
                "enabled": mode.enabled,
                "preconditions": [
                    p.model_dump(exclude_none=True) for p in mode.preconditions
                ],
            }
            for mode in MODES
        ]
    }


@router.get(
    "/classrooms/{classroomId}/modes/{modeId}", responses={200: {"model": ModeDetail}}
)
async def get_mode(classroomId: str, modeId: str) -> dict[str, Any]:
    mode = get_mode(modeId)
    if mode is None:
        raise ApiError("not_found", details={"mode_id": modeId})
    return {
        "id": mode.id,
        "title": mode.title,
        "description": mode.description,
        "steps": [s.model_dump() for s in mode.steps],
        "critical_device_ids": mode.critical_device_ids,
        "enabled": mode.enabled,
        "preconditions": [p.model_dump(exclude_none=True) for p in mode.preconditions],
    }


# Пример ответа preview на свежем seed (state_version=12, mode=hybrid):
# preview_hash = sha256("12:hybrid")[:16] — детерминирован, пока состояние не менялось.
_PREVIEW_EXAMPLE: dict[str, Any] = {
    "mode_id": "hybrid",
    "state_version": 12,
    "preview_hash": "43bd033f1041156e",
    "expires_at": "2026-11-03T16:45:00+00:00",
    "can_apply": True,
    "blocking_reasons": [],
    "warnings": [],
    "steps": [
        {
            "sequence": 1,
            "device_id": "D07",
            "device_name": "Жалюзи",
            "before": {"on": True, "open": 50},
            "target": {"on": True, "open": 20},
            "delta": "open: 50 → 20",
            "status": "will_change",
            "critical": False,
        },
        {
            "sequence": 5,
            "device_id": "D03",
            "device_name": "Проекционный экран",
            "before": {"on": False, "open": 0},
            "target": {"on": True, "open": 100},
            "delta": "on: false → true, open: 0 → 100",
            "status": "will_change",
            "critical": True,
        },
        {
            "sequence": 8,
            "device_id": "D08",
            "device_name": "Кондиционер",
            "before": {
                "on": True,
                "temperature": 22,
                "thermostat_mode": "auto",
                "fan_speed": "auto",
            },
            "target": {"on": True, "thermostat_mode": "auto", "temperature": 22},
            "delta": None,
            "status": "already_in_state",
            "critical": False,
        },
    ],
    "summary": {"will_change": 6, "already_in_state": 2, "critical_total": 3},
}


@router.post(
    "/classrooms/{classroomId}/modes/{modeId}/preview",
    responses={
        200: {
            "model": PreviewResult,
            "description": "Diff before→target, preview_hash (16 hex), TTL 15 мин.",
            "content": {
                "application/json": {"example": _PREVIEW_EXAMPLE}
            },
        },
        **error_responses(
            "preview_stale", "run_in_progress", "adapter_unreachable", "device_timeout"
        ),
    },
)
async def preview_mode(
    classroomId: str,
    modeId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Preview (S4): реальный diff + предусловия, без команд адаптеру.

    Естественные ошибки: X-Simulate-Error: <code> (preview_stale, adapter_unreachable…).
    can_apply=false → 200 с blocking_reasons (кнопка «Применить» скрыта).
    warnings: presence_absent (lecture), motion_not_quiet (finish), device_unreachable.
    """
    try:
        preview = await engine.preview(modeId)
    except ModeNotFoundError:
        raise ApiError("not_found", details={"mode_id": modeId}) from None
    return preview.model_dump(mode="json")
