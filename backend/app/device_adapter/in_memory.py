from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from app.device_adapter.dto import (
    AdapterError,
    AdapterInfo,
    CapabilitySpec,
    CommandResult,
    DeviceDescriptor,
    DeviceState,
    Fault,
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


# Ключ состояния → instance capability (термостат назван иначе в state и в спеке)
_STATE_KEY_ALIASES: dict[str, str] = {"thermostat_mode": "thermostat"}


def _spec_for_key(descriptor: DeviceDescriptor, key: str) -> CapabilitySpec | PropertySpec | None:
    instance = _STATE_KEY_ALIASES.get(key, key)
    for cap in descriptor.capabilities:
        if cap.instance == instance:
            return cap
    for prop in descriptor.properties:
        if prop.instance == instance:
            return prop
    return None


def _validate_value(spec: CapabilitySpec | PropertySpec, key: str, value: object, device_id: str) -> None:
    """G3: валидация значения ДО изменения состояния."""
    def fail(message: str, details: dict[str, object]) -> None:
        raise AdapterError("invalid_value", message, device_id, details=details)

    if not spec.type.startswith("devices.capabilities."):
        return  # properties — только чтение, execute по ним отсекается раньше
    if spec.type in ("devices.capabilities.on_off", "devices.capabilities.toggle"):
        if not isinstance(value, bool):
            fail(f"«{key}» ожидает bool, получено {value!r}.", {"key": key, "value": value})
    elif spec.type == "devices.capabilities.range":
        params = spec.parameters or {}
        minimum, maximum = params.get("min"), params.get("max")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail(f"«{key}» ожидает число, получено {value!r}.", {"key": key, "value": value})
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            fail(
                f"«{key}» вне диапазона {minimum}..{maximum}: {value}.",
                {"key": key, "value": value, "min": minimum, "max": maximum},
            )
    elif spec.type == "devices.capabilities.mode":
        allowed = (spec.parameters or {}).get("supported_modes", [])
        if value not in allowed:
            fail(
                f"«{key}» вне списка режимов {allowed}: {value!r}.",
                {"key": key, "value": value, "supported_modes": allowed},
            )


class InMemoryAdapter:
    """Реализация ClassroomDeviceAdapter с seed-данными (12 приборов D01–D12).

    Состояния хранятся в self._states; execute() реально их меняет
    (merge целевых ключей, валидация до записи, идемпотентность).

    Fault injection (Часть 3, §7): инъекция только через inject_fault/remove_fault
    (Operator API). Приоритет при execute: unavailable → device_unavailable;
    latency → device_timeout при value_ms > timeout_ms; error → error_code из §5.
    read() при активном unavailable возвращает reachable=False без исключений.
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceDescriptor] = {
            d.id: d for d in seed_descriptors()
        }
        self._states: dict[str, DeviceState] = seed_states()
        self._faults: dict[str, Fault] = {}
        #: минуты с последнего «движения» D11 — источник предусловия finish
        self.presence_minutes: int = 0

    async def describe(self) -> Sequence[DeviceDescriptor]:
        return list(self._devices.values())

    async def read(self, device_ids: Sequence[str] | None = None) -> dict[str, DeviceState]:
        ids = device_ids if device_ids is not None else list(self._states)
        # копии: внешний код не может мутировать состояние мимо execute()
        result: dict[str, DeviceState] = {}
        for device_id in ids:
            state = self._states.get(device_id)
            if state is None:
                continue
            copy = state.model_copy(deep=True)
            fault = self._active_fault(device_id)
            if fault is not None and fault.kind == "unavailable":
                # контракт read(): недоступный прибор → reachable=False, без исключения
                copy.reachable = False
            result[device_id] = copy
        return result

    async def execute(
        self,
        device_id: str,
        target: DeviceState,
        *,
        timeout_ms: int | None = None,
    ) -> CommandResult:
        descriptor = self._devices.get(device_id)
        if descriptor is None:
            raise AdapterError(
                "invalid_value",
                f"Прибор {device_id} не найден в адаптере.",
                device_id,
                details={"device_id": device_id},
            )

        # faults приоритетны до readonly/валидации (Часть 3, §7)
        fault = self._active_fault(device_id)
        if fault is not None:
            self._raise_for_fault(fault, device_id, timeout_ms)

        if descriptor.managability == "readonly":
            raise AdapterError(
                "readonly_device",
                f"{descriptor.name}: прибор только для чтения.",
                device_id,
                details={"device_id": device_id},
            )
        current = self._states.get(device_id)
        if current is None:
            raise AdapterError(
                "device_unavailable",
                f"Состояние прибора {device_id} недоступно.",
                device_id,
                details={"device_id": device_id},
            )

        # G3: валидация всех ключей/значений ДО записи
        for key, value in target.state.items():
            spec = _spec_for_key(descriptor, key)
            if spec is None:
                raise AdapterError(
                    "invalid_value",
                    f"Ключ «{key}» не входит в спецификацию прибора {device_id}.",
                    device_id,
                    details={"key": key, "value": value, "device_id": device_id},
                )
            _validate_value(spec, key, value, device_id)

        # merge: отсутствующие ключи не сбрасываются (Часть 3, §4.2)
        merged = {**current.state, **target.state}
        if merged == current.state:
            # G2: идемпотентность — состояние уже равно target
            return CommandResult(
                device_id=device_id,
                current=merged,
                applied=False,
                latency_ms=0,
                source=target.source,
            )

        # G4: атомарная замена состояния одной записью в dict
        self._states[device_id] = current.model_copy(
            update={
                "state": merged,
                "reachable": True,
                "updated_at": datetime.now(timezone.utc),
                "source": target.source,
                "state_version": current.state_version + 1,
            }
        )
        return CommandResult(
            device_id=device_id,
            current=merged,
            applied=True,
            latency_ms=0,
            source=target.source,
        )

    async def health(self) -> AdapterInfo:
        """Статус адаптера и reachability по приборам с активными faults (S8)."""
        broken = self.broken_devices
        devices: list[dict[str, object]] = []
        for device_id in sorted(self._states):
            fault = self._active_fault(device_id)
            if fault is None:
                continue
            devices.append(
                {
                    "id": device_id,
                    "reachable": fault.kind != "unavailable",
                    "last_error": _fault_error_code(fault),
                    "last_success_at": self._states[device_id].updated_at.isoformat(),
                }
            )
        status = "degraded" if broken else "ok"
        return AdapterInfo(
            adapter="in_memory",
            status=status,  # type: ignore[arg-type]
            checked_at=datetime.now(timezone.utc),
            devices=devices,
        )

    async def reset(self, *, initial_state_ref: str | None = None) -> dict[str, DeviceState]:
        """Эталон seed + снятие faults. Идемпотентен (Часть 3, §3, reset)."""
        self._reset_all()
        return dict(self._states)

    # --- fault injection / simulator (Operator API, не входит в Protocol) ---

    @property
    def broken_devices(self) -> list[str]:
        """Приборы с активным fault kind=unavailable («сломанные» для фронта)."""
        return sorted(
            f.device_id for f in self._faults.values() if f.active and f.kind == "unavailable"
        )

    def inject_fault(
        self,
        device_id: str,
        kind: str,
        *,
        value_ms: int | None = None,
        error_code: str | None = None,
        ttl_seconds: int | None = None,
        comment: str | None = None,
        created_by: str | None = None,
    ) -> Fault:
        """Создать активный fault; неизвестный device_id → AdapterError invalid_value."""
        if device_id not in self._devices:
            raise AdapterError(
                "invalid_value",
                f"Прибор {device_id} не найден в адаптере.",
                device_id,
                details={"device_id": device_id},
            )
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        fault = Fault(
            id=str(uuid4()),
            device_id=device_id,
            kind=kind,  # type: ignore[arg-type]
            value_ms=value_ms,
            error_code=error_code,
            expires_at=expires_at,
            active=True,
            created_at=now,
            created_by=created_by,
            comment=comment,
        )
        self._faults[fault.id] = fault
        return fault

    def remove_fault(self, fault_id: str) -> bool:
        """Снять fault. Возвращает True, если был активен (идемпотентен)."""
        fault = self._faults.get(fault_id)
        if fault is None or not fault.active:
            return False
        fault.active = False
        return True

    def list_faults(self) -> list[Fault]:
        """Активные неистёкшие faults (expired снимаются лениво)."""
        self._expire_faults()
        return [f for f in self._faults.values() if f.active]

    def clear_faults(self) -> int:
        """Снять все активные faults. Возвращает число снятых."""
        cleared = 0
        for fault in self._faults.values():
            if fault.active:
                fault.active = False
                cleared += 1
        return cleared

    async def set_state(
        self,
        device_id: str,
        state: dict[str, object],
        *,
        source: str = "simulator",
    ) -> DeviceState:
        """Прямая установка состояния симулятором (занятость D11, дверь D12).

        Не проходит execute()-валидацию: нужен для операторской occupancy.
        """
        current = self._states.get(device_id)
        if current is None:
            raise AdapterError(
                "invalid_value",
                f"Прибор {device_id} не найден в адаптере.",
                device_id,
                details={"device_id": device_id},
            )
        merged = {**current.state, **state}
        updated = current.model_copy(
            update={
                "state": merged,
                "reachable": True,
                "updated_at": datetime.now(timezone.utc),
                "source": source,  # type: ignore[arg-type]
                "state_version": current.state_version + 1,
            }
        )
        self._states[device_id] = updated
        return updated.model_copy(deep=True)

    def _reset_all(self) -> None:
        """Синхронный полный сброс seed + faults + presence (для tests/симулятора)."""
        self._states = seed_states()
        self._faults.clear()
        self.presence_minutes = 0

    def _expire_faults(self) -> None:
        now = datetime.now(timezone.utc)
        for fault in self._faults.values():
            if fault.active and fault.expires_at is not None and fault.expires_at <= now:
                fault.active = False

    def _active_fault(self, device_id: str) -> Fault | None:
        self._expire_faults()
        for fault in self._faults.values():
            if fault.active and fault.device_id == device_id:
                return fault
        return None

    def _raise_for_fault(
        self, fault: Fault, device_id: str, timeout_ms: int | None
    ) -> None:
        """Приоритет faults при execute (Часть 3, §7)."""
        name = self._devices[device_id].name
        if fault.kind == "unavailable":
            raise AdapterError(
                "device_unavailable",
                f"{name}: прибор недоступен (инъекция отказа).",
                device_id,
                details={"device_id": device_id, "fault_id": fault.id},
                retryable=True,
                manual_hint=f"Проверьте питание/связь «{name}» и повторите.",
            )
        if fault.kind == "latency":
            value = fault.value_ms or 0
            limit = timeout_ms if timeout_ms is not None else 3000
            if value > limit:
                raise AdapterError(
                    "device_timeout",
                    f"{name}: превышен таймаут {limit} мс (симуляция {value} мс).",
                    device_id,
                    details={
                        "device_id": device_id,
                        "fault_id": fault.id,
                        "value_ms": value,
                        "timeout_ms": limit,
                    },
                    retryable=True,
                    manual_hint=f"«{name}» не ответил вовремя — повторите шаг.",
                )
            return  # латентность в пределах таймаута — execute проходит
        # kind == "error"
        code = fault.error_code or "internal_error"
        raise AdapterError(
            code,
            f"{name}: симулируемая ошибка {code}.",
            device_id,
            details={"device_id": device_id, "fault_id": fault.id, "error_code": code},
            retryable=code in ("device_timeout", "rate_limited"),
        )


def _fault_error_code(fault: Fault) -> str:
    """Код last_error для health() по kind fault."""
    if fault.kind == "unavailable":
        return "device_unavailable"
    if fault.kind == "latency":
        return "device_timeout"
    return fault.error_code or "internal_error"


in_memory_adapter = InMemoryAdapter()
