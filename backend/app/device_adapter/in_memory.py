from datetime import datetime, timezone
from typing import Sequence

from app.device_adapter.dto import (
    AdapterInfo,
    CapabilitySpec,
    CommandResult,
    DeviceDescriptor,
    DeviceState,
    PropertySpec,
)

SEED_TS = datetime(2026, 10, 27, 10, 14, 52, tzinfo=timezone.utc)

SEED_ZONES: list[dict[str, str]] = [
    {
        "id": "Z1",
        "code": "Z1",
        "name": "Преподавательская",
        "purpose": "Подсветка доски, проектор, экран, аудиосистема",
    },
    {
        "id": "Z2",
        "code": "Z2",
        "name": "Студенческая",
        "purpose": "Свет в рядах, жалюзи, кондиционер, датчики",
    },
    {
        "id": "Z3",
        "code": "Z3",
        "name": "Сервисная",
        "purpose": "Датчики присутствия и двери",
    },
]


def _on_off() -> CapabilitySpec:
    return CapabilitySpec(type="devices.capabilities.on_off", instance="on")


def _range(instance: str, minimum: int, maximum: int, unit: str) -> CapabilitySpec:
    return CapabilitySpec(
        type="devices.capabilities.range",
        instance=instance,
        parameters={"min": minimum, "max": maximum, "precision": 1, "unit": unit},
    )


def _mode(instance: str, modes: list[str]) -> CapabilitySpec:
    return CapabilitySpec(
        type="devices.capabilities.mode",
        instance=instance,
        parameters={"supported_modes": modes},
    )


def _toggle(instance: str) -> CapabilitySpec:
    return CapabilitySpec(type="devices.capabilities.toggle", instance=instance)


def _prop(instance: str, prop_type: str = "devices.properties.float") -> PropertySpec:
    return PropertySpec(type=prop_type, instance=instance)


def _descriptor(
    device_id: str,
    zone_id: str,
    name: str,
    ya_type: str,
    capabilities: list[CapabilitySpec] | None = None,
    properties: list[PropertySpec] | None = None,
    managability: str = "controllable",
) -> DeviceDescriptor:
    return DeviceDescriptor(
        id=device_id,
        zone_id=zone_id,
        name=name,
        ya_type=ya_type,
        managability=managability,  # type: ignore[arg-type]
        capabilities=capabilities or [],
        properties=properties or [],
    )


def seed_descriptors() -> list[DeviceDescriptor]:
    """12 приборов аудитории D01–D12 (Часть 3, §4.2)."""
    light_caps = [_on_off(), _range("brightness", 1, 100, "unit.percent")]
    return [
        _descriptor("D01", "Z1", "Подсветка доски", "devices.types.light", light_caps),
        _descriptor("D02", "Z1", "Проектор", "devices.types.media_device", [_on_off()]),
        _descriptor(
            "D03",
            "Z1",
            "Проекционный экран",
            "devices.types.openable.curtain",
            [_on_off(), _range("open", 0, 100, "unit.percent")],
        ),
        _descriptor(
            "D04",
            "Z1",
            "Аудиосистема",
            "devices.types.media_device",
            [_on_off(), _range("volume", 1, 100, "unit.percent"), _toggle("mute")],
        ),
        _descriptor("D05", "Z2", "Свет ряд 1", "devices.types.light", light_caps),
        _descriptor("D06", "Z2", "Свет ряд 2", "devices.types.light", light_caps),
        _descriptor(
            "D07",
            "Z2",
            "Жалюзи",
            "devices.types.openable.curtain",
            [_on_off(), _range("open", 0, 100, "unit.percent")],
        ),
        _descriptor(
            "D08",
            "Z2",
            "Кондиционер",
            "devices.types.thermostat.ac",
            [
                _on_off(),
                _range("temperature", 16, 30, "temperature.unit.celsius"),
                _mode("thermostat", ["auto", "cool", "heat", "fan_only", "dry", "eco"]),
                _mode("fan_speed", ["auto", "high", "low", "medium", "quiet", "turbo"]),
            ],
        ),
        _descriptor(
            "D09",
            "Z2",
            "Датчик климата",
            "devices.types.sensor.climate",
            properties=[_prop("temperature"), _prop("humidity")],
            managability="readonly",
        ),
        _descriptor(
            "D10",
            "Z2",
            "Датчик освещенности",
            "devices.types.sensor.illumination",
            properties=[_prop("illumination")],
            managability="readonly",
        ),
        _descriptor(
            "D11",
            "Z3",
            "Датчик присутствия",
            "devices.types.sensor.motion",
            properties=[_prop("motion", "devices.properties.event")],
            managability="readonly",
        ),
        _descriptor(
            "D12",
            "Z3",
            "Датчик двери",
            "devices.types.sensor.open",
            properties=[_prop("open", "devices.properties.event")],
            managability="readonly",
        ),
    ]


def seed_states() -> dict[str, DeviceState]:
    """Начальные состояния приборов (детерминированные, для моков фронта)."""
    raw: dict[str, dict[str, object]] = {
        "D01": {"on": False, "brightness": 60},
        "D02": {"on": False},
        "D03": {"on": False, "open": 0},
        "D04": {"on": False, "volume": 40, "mute": False},
        "D05": {"on": True, "brightness": 60},
        "D06": {"on": True, "brightness": 60},
        "D07": {"on": True, "open": 50},
        "D08": {"on": True, "temperature": 22, "thermostat_mode": "auto", "fan_speed": "auto"},
        "D09": {"temperature": 22.4, "humidity": 45},
        "D10": {"illumination": 320},
        "D11": {"motion": "not_detected"},
        "D12": {"open": "closed"},
    }
    return {
        device_id: DeviceState(
            device_id=device_id,
            state=state,
            reachable=True,
            updated_at=SEED_TS,
            source="simulator",
            state_version=1,
        )
        for device_id, state in raw.items()
    }


class InMemoryAdapter:
    """Реализация ClassroomDeviceAdapter с seed-данными (12 приборов D01–D12)."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceDescriptor] = {
            d.id: d for d in seed_descriptors()
        }
        self._states: dict[str, DeviceState] = seed_states()

    async def describe(self) -> Sequence[DeviceDescriptor]:
        return list(self._devices.values())

    async def read(self, device_ids: Sequence[str] | None = None) -> dict[str, DeviceState]:
        if device_ids is None:
            return dict(self._states)
        return {
            device_id: self._states[device_id]
            for device_id in device_ids
            if device_id in self._states
        }

    async def execute(
        self,
        device_id: str,
        target: DeviceState,
        *,
        timeout_ms: int | None = None,
    ) -> CommandResult:
        return CommandResult(
            device_id=device_id,
            current=dict(target.state),
            applied=False,
            source=target.source,
        )

    async def health(self) -> AdapterInfo:
        return AdapterInfo(adapter="in_memory", status="ok", checked_at=SEED_TS)

    async def reset(self, *, initial_state_ref: str | None = None) -> dict[str, DeviceState]:
        self._states = seed_states()
        return dict(self._states)


in_memory_adapter = InMemoryAdapter()
