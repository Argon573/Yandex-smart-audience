from typing import Any

from app.device_adapter.dto import DeviceDescriptor, DeviceState

_ROOM_NAMES = {
    "Z1": "Преподавательская",
    "Z2": "Студенческая",
    "Z3": "Сервисная",
}


def to_yandex_device(descriptor: DeviceDescriptor, classroom_id: str = "") -> dict[str, Any]:
    """Маппинг DeviceDescriptor → устройство discovery-ответа Яндекса (Часть 2 §5.1)."""
    device: dict[str, Any] = {
        "id": descriptor.id,
        "name": descriptor.name,
        "type": descriptor.ya_type,
        "status_info": {"reportable": True},
        "device_info": {"manufacturer": "Smart Classroom", "model": descriptor.id},
        "room": _ROOM_NAMES.get(descriptor.zone_id, descriptor.zone_id),
        "custom_data": {"classroom_id": classroom_id, "zone_id": descriptor.zone_id},
    }
    if descriptor.capabilities:
        device["capabilities"] = [
            {
                "type": capability.type,
                "retrievable": capability.retrievable,
                **(
                    {"parameters": {"instance": capability.instance, **capability.parameters}}
                    if capability.parameters
                    else {"parameters": {"instance": capability.instance}}
                ),
            }
            for capability in descriptor.capabilities
        ]
    if descriptor.properties:
        device["properties"] = [
            {
                "type": prop.type,
                **({"parameters": prop.parameters} if prop.parameters else {}),
            }
            for prop in descriptor.properties
        ]
    return device


def _timestamp(state: DeviceState) -> str:
    return state.updated_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_yandex_query_state(
    state: DeviceState, descriptor: DeviceDescriptor
) -> dict[str, Any]:
    """Маппинг актуального состояния в формат query Yandex Smart Home."""
    capabilities: list[dict[str, Any]] = []
    for spec in descriptor.capabilities:
        key = "thermostat_mode" if spec.instance == "thermostat" else spec.instance
        if key not in state.state:
            continue
        capabilities.append(
            {
                "type": spec.type,
                "state": {
                    "instance": spec.instance,
                    "value": state.state[key],
                    "updated_at": _timestamp(state),
                },
            }
        )

    properties: list[dict[str, Any]] = []
    for spec in descriptor.properties:
        if spec.instance not in state.state:
            continue
        properties.append(
            {
                "type": spec.type,
                "state": {
                    "instance": spec.instance,
                    "value": state.state[spec.instance],
                    "updated_at": _timestamp(state),
                },
            }
        )
    result: dict[str, Any] = {"id": state.device_id}
    if capabilities:
        result["capabilities"] = capabilities
    if properties:
        result["properties"] = properties
    if not state.reachable:
        result["error_code"] = "DEVICE_UNREACHABLE"
    return result


def to_yandex_action_capability(
    capability_type: str,
    instance: str,
    value: Any,
    *,
    status: str,
    error_code: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {"instance": instance, "value": value}
    if updated_at:
        state["updated_at"] = updated_at
    action_result: dict[str, Any] = {"status": status}
    if error_code:
        action_result["error_code"] = error_code
    state["action_result"] = action_result
    return {"type": capability_type, "state": state}


def to_yandex_action_result(device_id: str, applied: bool) -> dict[str, Any]:
    """Compatibility helper retained for callers from the initial scaffold."""
    status = "DONE" if applied else "ERROR"
    return {
        "id": device_id,
        "capabilities": [
            to_yandex_action_capability(
                "devices.capabilities.on_off", "on", applied, status=status
            )
        ],
    }
