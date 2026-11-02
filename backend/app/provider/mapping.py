from typing import Any

from app.device_adapter.dto import DeviceDescriptor, DeviceState


def to_yandex_device(descriptor: DeviceDescriptor, classroom_id: str = "") -> dict[str, Any]:
    """Маппинг DeviceDescriptor → устройство discovery-ответа Яндекса (Часть 2 §5.1)."""
    return {
        "id": descriptor.id,
        "name": descriptor.name,
        "type": descriptor.ya_type,
        "status_info": {"reportable": True},
        "capabilities": [],
        "properties": [],
        "custom_data": {"classroom_id": classroom_id, "zone_id": descriptor.zone_id},
    }


def to_yandex_query_state(state: DeviceState) -> dict[str, Any]:
    """Маппинг DeviceState → элемент query-ответа (Часть 2 §5.2)."""
    return {"id": state.device_id, "capabilities": [], "properties": []}


def to_yandex_action_result(device_id: str, applied: bool) -> dict[str, Any]:
    """Маппинг CommandResult → элемент action-ответа (Часть 2 §5.3)."""
    status = "DONE" if applied else "ERROR"
    return {
        "id": device_id,
        "capabilities": [
            {
                "type": "devices.capabilities.on_off",
                "state": {
                    "instance": "on",
                    "value": applied,
                    "action_result": {"status": status},
                },
            }
        ],
    }
