from typing import Any, Protocol, runtime_checkable

from app.device_adapter.dto import DeviceState


@runtime_checkable
class ModeRepository(Protocol):
    async def get(self, mode_id: str) -> Any: ...

    async def list_public(self) -> list[Any]: ...


@runtime_checkable
class RunRepository(Protocol):
    async def create(self, run: Any) -> Any: ...

    async def get(self, run_id: str) -> Any: ...

    async def append_step(self, step: Any) -> None: ...

    async def finish(self, run_id: str, outcome: str) -> None: ...


@runtime_checkable
class StateSnapshotPort(Protocol):
    async def snapshot(self, classroom_id: str) -> dict[str, DeviceState]: ...

    async def version(self, classroom_id: str) -> int: ...
