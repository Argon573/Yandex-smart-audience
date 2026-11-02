from datetime import datetime, timezone

import pytest

from app.device_adapter.dto import AdapterError, DeviceState
from app.device_adapter.in_memory import InMemoryAdapter


def _target(device_id: str, state: dict[str, object], source: str = "manual") -> DeviceState:
    return DeviceState(
        device_id=device_id,
        state=state,
        updated_at=datetime.now(timezone.utc),
        source=source,
    )


@pytest.fixture()
def adapter() -> InMemoryAdapter:
    return InMemoryAdapter()


@pytest.mark.asyncio
async def test_execute_changes_state_and_read_returns_it(adapter: InMemoryAdapter) -> None:
    result = await adapter.execute("D05", _target("D05", {"brightness": 35}))
    assert result.applied is True
    assert result.current["brightness"] == 35

    states = await adapter.read(["D05"])
    assert states["D05"].state["brightness"] == 35
    assert states["D05"].source == "manual"
    assert states["D05"].state_version == 2


@pytest.mark.asyncio
async def test_execute_merge_keeps_other_keys(adapter: InMemoryAdapter) -> None:
    await adapter.execute("D01", _target("D01", {"on": True}))
    states = await adapter.read(["D01"])
    assert states["D01"].state == {"on": True, "brightness": 60}


@pytest.mark.asyncio
async def test_execute_idempotent(adapter: InMemoryAdapter) -> None:
    target = _target("D05", {"brightness": 35})
    first = await adapter.execute("D05", target)
    second = await adapter.execute("D05", target)
    assert first.applied is True
    assert second.applied is False
    states = await adapter.read(["D05"])
    assert states["D05"].state_version == 2  # версия выросла один раз


@pytest.mark.asyncio
async def test_execute_invalid_range_does_not_change_state(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D05", _target("D05", {"brightness": 0}))
    assert exc_info.value.code == "invalid_value"

    states = await adapter.read(["D05"])
    assert states["D05"].state["brightness"] == 60  # G3: состояние не тронуто
    assert states["D05"].state_version == 1


@pytest.mark.asyncio
async def test_execute_unknown_key_rejected(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D05", _target("D05", {"color": "red"}))
    assert exc_info.value.code == "invalid_value"
    assert exc_info.value.details["key"] == "color"


@pytest.mark.asyncio
async def test_execute_wrong_type_rejected(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D05", _target("D05", {"on": "yes"}))
    assert exc_info.value.code == "invalid_value"


@pytest.mark.asyncio
async def test_execute_readonly_device_rejected(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D11", _target("D11", {"motion": "detected"}))
    assert exc_info.value.code == "readonly_device"


@pytest.mark.asyncio
async def test_execute_unknown_device_rejected(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D99", _target("D99", {"on": True}))
    assert exc_info.value.code == "invalid_value"


@pytest.mark.asyncio
async def test_execute_mode_value_validated(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError) as exc_info:
        await adapter.execute("D08", _target("D08", {"thermostat_mode": "banana"}))
    assert exc_info.value.code == "invalid_value"

    ok = await adapter.execute("D08", _target("D08", {"thermostat_mode": "cool"}))
    assert ok.applied is True


@pytest.mark.asyncio
async def test_execute_temperature_range(adapter: InMemoryAdapter) -> None:
    with pytest.raises(AdapterError):
        await adapter.execute("D08", _target("D08", {"temperature": 99}))
    ok = await adapter.execute("D08", _target("D08", {"temperature": 25}))
    assert ok.current["temperature"] == 25


@pytest.mark.asyncio
async def test_execute_failure_does_not_affect_other_devices(adapter: InMemoryAdapter) -> None:
    # G5: изоляция отказов — ошибка D05 не влияет на D06
    with pytest.raises(AdapterError):
        await adapter.execute("D05", _target("D05", {"brightness": 0}))
    ok = await adapter.execute("D06", _target("D06", {"brightness": 30}))
    assert ok.applied is True
    states = await adapter.read(["D05", "D06"])
    assert states["D05"].state["brightness"] == 60
    assert states["D06"].state["brightness"] == 30


@pytest.mark.asyncio
async def test_read_returns_copies_not_references(adapter: InMemoryAdapter) -> None:
    states = await adapter.read(["D05"])
    states["D05"].state["brightness"] = 1  # попытка мимо execute
    fresh = await adapter.read(["D05"])
    assert fresh["D05"].state["brightness"] == 60


@pytest.mark.asyncio
async def test_reset_restores_seed(adapter: InMemoryAdapter) -> None:
    await adapter.execute("D05", _target("D05", {"brightness": 35}))
    await adapter.reset()
    states = await adapter.read(["D05"])
    assert states["D05"].state["brightness"] == 60
    assert states["D05"].state_version == 1
