"""Control Plane (C-01): план аудитории, карточки приборов, modes, preview, команды."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.errors import (
    ApiError,
    api_error_from_adapter,
    simulate_error,
)
from app.deps import engine, in_memory_adapter
from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import AdapterError, DeviceDescriptor, DeviceState
from app.device_adapter.in_memory import SEED_ZONES
from app.mode_engine.catalog import MODES, get_mode
from app.mode_engine.exceptions import ModeNotFoundError

router = APIRouter(prefix="/api/v1", tags=["control-plane"])

# instance capability → ключ state (обратный алиас thermostat_mode)
_INSTANCE_TO_STATE_KEY: dict[str, str] = {"thermostat": "thermostat_mode"}


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


@router.get("/room")
async def get_room() -> dict[str, Any]:
    """План аудитории для фронта: зоны Z1–Z3 и все приборы D01–D12 (seed)."""
    return await build_room_plan(in_memory_adapter)


@router.get("/classrooms")
async def list_classrooms() -> dict[str, Any]:
    room = await build_room_plan(in_memory_adapter)
    return {
        "items": [{"id": room["id"], "name": room["name"], "state_version": room["state_version"]}],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }


@router.get("/classrooms/{classroomId}")
async def get_classroom(classroomId: str) -> dict[str, Any]:
    return await build_room_plan(in_memory_adapter)


@router.get("/classrooms/{classroomId}/state")
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


@router.get("/classrooms/{classroomId}/devices/{deviceId}")
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


@router.get("/classrooms/{classroomId}/devices/{deviceId}/history")
async def get_device_history(
    classroomId: str,
    deviceId: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


class CommandItem(BaseModel):
    """Одна команда ручного управления (Часть 2, §2.5)."""

    type: str
    instance: str
    value: Any


class DeviceCommandBody(BaseModel):
    commands: list[CommandItem] = Field(default_factory=list)


@router.post("/classrooms/{classroomId}/devices/{deviceId}/commands")
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


@router.get("/classrooms/{classroomId}/modes")
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


@router.get("/classrooms/{classroomId}/modes/{modeId}")
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


@router.post("/classrooms/{classroomId}/modes/{modeId}/preview")
async def preview_mode(
    classroomId: str,
    modeId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Preview (S4): реальный diff + предусловия, без команд адаптеру.

    Естественные ошибки: X-Simulate-Error: <code> (preview_stale, adapter_unreachable…).
    can_apply=false → 200 с blocking_reasons (кнопка «Применить» скрыта).
    """
    try:
        preview = await engine.preview(modeId)
    except ModeNotFoundError:
        raise ApiError("not_found", details={"mode_id": modeId}) from None
    return preview.model_dump(mode="json")
