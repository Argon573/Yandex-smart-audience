from typing import Protocol, Sequence, runtime_checkable

from app.device_adapter.dto import AdapterInfo, CommandResult, DeviceDescriptor, DeviceState


@runtime_checkable
class ClassroomDeviceAdapter(Protocol):
    """Сервисный контракт доступа к приборам аудитории (Часть 3, §3). Все методы — async."""

    async def describe(self) -> Sequence[DeviceDescriptor]:
        """Полный каталог приборов со СПЕКАМИ. Побочных эффектов нет, идемпотентен."""

    async def read(self, device_ids: Sequence[str] | None = None) -> dict[str, DeviceState]:
        """Состояния приборов batch-вызовом. device_ids=None → все приборы.

        Отсутствующий id не включается в результат и не бросает исключение;
        недоступный прибор → DeviceState(reachable=False).
        """

    async def execute(
        self,
        device_id: str,
        target: DeviceState,
        *,
        timeout_ms: int | None = None,
    ) -> CommandResult:
        """Применить целевое состояние прибора.

        Гарантии: G1 current == target после успеха; G2 повтор с тем же target →
        applied=False; G3 невалидный ключ/диапазон → AdapterError ДО изменения
        состояния; G4 состояние меняется атомарно; G5 отказ одного прибора не
        влияет на остальные.
        """

    async def health(self) -> AdapterInfo:
        """Состояние адаптера и reachability по каждому прибору. Побочных эффектов нет."""

    async def reset(self, *, initial_state_ref: str | None = None) -> dict[str, DeviceState]:
        """Привести аудиторию к эталонному состоянию, снять faults. Идемпотентен."""
