"""Доменные исключения движка режимов.

Не импортируют app/api — API-слой маппит их в ApiError по code.
"""


class ModeNotFoundError(Exception):
    """Режим не найден в каталоге → API 404 not_found."""

    def __init__(self, mode_id: str) -> None:
        super().__init__(f"Режим «{mode_id}» не найден.")
        self.mode_id = mode_id
        self.code = "not_found"


class EngineError(Exception):
    """Ошибка применения режима с кодом из реестра Части 2, §1.2.

    code: preview_stale | warnings_unacked | precondition_failed |
          run_in_progress | idempotency_mismatch | adapter_unreachable | ...
    """

    def __init__(
        self,
        code: str,
        message: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.details = details or {}
