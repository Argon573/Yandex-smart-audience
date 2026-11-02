from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError, simulate_error
from app.api.mocks import build_preview_mock
from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import DeviceDescriptor, DeviceState
from app.device_adapter.in_memory import SEED_ZONES, in_memory_adapter
from app.mode_engine.catalog import MODES

router = APIRouter(prefix="/api/v1", tags=["control-plane"])


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
    descriptors = await adapter.describe()
    states = await adapter.read()

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
        "state_version": 1,
        "adapter_health": "ok",
        "updated_at": max(updated_ats).isoformat() if updated_ats else None,
        "zones": zones,
        "device_count": len(descriptors),
        "readonly_count": sum(
            1 for d in descriptors if d.managability == "readonly"
        ),
    }


@router.get("/room")
async def get_room() -> dict[str, Any]:
    """План аудории для фронта: зоны Z1–Z3 и все приборы D01–D12 (seed)."""
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


@router.post("/classrooms/{classroomId}/devices/{deviceId}/commands")
async def device_command(
    classroomId: str,
    deviceId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    states = await in_memory_adapter.read([deviceId])
    state = states.get(deviceId)
    if state is None:
        raise ApiError("not_found", details={"device_id": deviceId})
    return {
        "device_id": deviceId,
        "state": dict(state.state),
        "state_version": state.state_version,
        "updated_at": state.updated_at.isoformat(),
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
    mode = next((m for m in MODES if m.id == modeId), None)
    if mode is None:
        raise ApiError("not_found", details={"mode_id": modeId})
    return {
        "id": mode.id,
        "title": mode.title,
        "description": mode.description,
        "steps": [s.model_dump() for s in mode.steps],
        "critical_device_ids": mode.critical_device_ids,
        "enabled": mode.enabled,
    }


@router.post("/classrooms/{classroomId}/modes/{modeId}/preview")
async def preview_mode(
    classroomId: str,
    modeId: str,
    _simulate: None = Depends(simulate_error),
) -> dict[str, Any]:
    """Мок preview (S4): захардкоженный успешный результат.

    Для отработки алертов ошибок фронтом используй заголовок
    X-Simulate-Error: <code> (например preview_stale, adapter_unreachable).
    """
    return build_preview_mock(modeId)
