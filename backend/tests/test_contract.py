from datetime import datetime, timezone

import pytest

from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import DeviceState
from app.device_adapter.in_memory import InMemoryAdapter

DEVICE_IDS = {f"D{i:02d}" for i in range(1, 13)}


@pytest.fixture()
def adapter() -> InMemoryAdapter:
    return InMemoryAdapter()


def test_adapter_satisfies_protocol(adapter: InMemoryAdapter) -> None:
    assert isinstance(adapter, ClassroomDeviceAdapter)


@pytest.mark.asyncio
async def test_describe_returns_12_devices(adapter: InMemoryAdapter) -> None:
    descriptors = await adapter.describe()
    assert {d.id for d in descriptors} == DEVICE_IDS
    assert all(d.ya_type.startswith("devices.types.") for d in descriptors)


@pytest.mark.asyncio
async def test_read_returns_all_states(adapter: InMemoryAdapter) -> None:
    states = await adapter.read()
    assert set(states) == DEVICE_IDS
    subset = await adapter.read(["D01", "D99"])
    assert set(subset) == {"D01"}


@pytest.mark.asyncio
async def test_execute_applies_and_read_returns_it(adapter: InMemoryAdapter) -> None:
    target = DeviceState(
        device_id="D05",
        state={"brightness": 35},
        updated_at=datetime.now(timezone.utc),
        source="manual",
    )
    result = await adapter.execute("D05", target)
    assert result.applied is True
    states = await adapter.read(["D05"])
    assert states["D05"].state["brightness"] == 35
    assert states["D05"].state["on"] is True  # merge не сбрасывает остальные ключи


@pytest.mark.asyncio
async def test_health_ok(adapter: InMemoryAdapter) -> None:
    info = await adapter.health()
    assert info.status == "ok"
