from app.device_adapter.contract import ClassroomDeviceAdapter
from app.mode_engine.models import PreviewResult, Run


class ClassroomEngine:
    """Движок режимов. Заглушка: preview/execute возвращают пустые результаты."""

    def __init__(self, adapter: ClassroomDeviceAdapter) -> None:
        self._adapter = adapter

    async def preview(self, mode_id: str) -> PreviewResult:
        return PreviewResult(mode_id=mode_id)

    async def execute(
        self,
        mode_id: str,
        classroom_id: str,
        *,
        preview_hash: str = "",
        idempotency_key: str | None = None,
    ) -> Run:
        return Run(
            id="",
            mode_id=mode_id,
            classroom_id=classroom_id,
            preview_hash=preview_hash,
            idempotency_key=idempotency_key,
        )
