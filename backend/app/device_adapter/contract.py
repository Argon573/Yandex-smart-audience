from typing import Protocol, Sequence, runtime_checkable

from app.device_adapter.dto import AdapterInfo, CommandResult, DeviceDescriptor, DeviceState


@runtime_checkable
class ClassroomDeviceAdapter(Protocol):
    """Сервисный контракт доступа к приборам аудитории. Все методы — async."""

    async def describe(self) -> Sequence[DeviceDescriptor]: ...

    async def read(self, device_ids: Sequence[str] | None = None) -> dict[str, DeviceState]: ...

    async def execute(
        self,
        device_id: str,
        target: DeviceState,
        *,
        timeout_ms: int | None = None,
    ) -> CommandResult: ...

    async def health(self) -> AdapterInfo: ...

    async def reset(self, *, initial_state_ref: str | None = None) -> dict[str, DeviceState]: ...
