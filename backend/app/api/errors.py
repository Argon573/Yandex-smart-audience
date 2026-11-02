from typing import Any

from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Реестр кодов (Часть 2, §1.2): code -> (HTTP статус, сообщение по умолчанию, retryable)
ERROR_REGISTRY: dict[str, tuple[int, str, bool]] = {
    "validation_error": (400, "Нарушена схема тела или параметров запроса.", False),
    "unauthorized": (401, "Нет или просрочен access-токен.", False),
    "forbidden": (403, "Недостаточно роли для выполнения операции.", False),
    "not_found": (404, "Сущность не найдена.", False),
    "preview_stale": (
        409,
        "Состояние аудитории изменилось после предпросмотра. Обновите предпросмотр.",
        False,
    ),
    "run_in_progress": (409, "У аудитории уже выполняется запуск.", False),
    "idempotency_mismatch": (
        409,
        "Тот же Idempotency-Key уже использован с другим телом запроса.",
        False,
    ),
    "readonly_device": (409, "Команда датчику: прибор только для чтения.", False),
    "preview_expired": (410, "Предпросмотр старше 15 минут.", False),
    "warnings_unacked": (422, "Есть предупреждения без подтверждения.", False),
    "precondition_failed": (422, "Предусловие режима не выполнено и не подтверждено.", False),
    "unsupported_capability": (422, "Команда вне спецификации прибора.", False),
    "invalid_value": (422, "Значение вне диапазона или enum.", False),
    "rate_limited": (429, "Превышен лимит запросов.", True),
    "internal_error": (500, "Непредвиденное исключение сервера.", False),
    "adapter_unreachable": (502, "Адаптер недоступен, запуск не начат.", True),
    "service_not_ready": (503, "База данных или схема недоступны.", True),
    "device_timeout": (504, "Таймаут шага: прибор не ответил вовремя.", True),
}

_STATUS_TO_CODE = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "run_in_progress",
    422: "invalid_value",
    429: "rate_limited",
    500: "internal_error",
    503: "service_not_ready",
}


class ApiError(Exception):
    """Типизированная ошибка API: падает в хендлере → конверт из §1.1."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code not in ERROR_REGISTRY:
            code = "internal_error"
        status, default_message, retryable = ERROR_REGISTRY[code]
        super().__init__(message or default_message)
        self.code = code
        self.status_code = status
        self.message = message or default_message
        self.details = details or {}
        self.retryable = retryable


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request.headers.get(
        "X-Request-Id", ""
    )


def _envelope(
    request: Request,
    code: str,
    message: str,
    details: dict[str, Any],
    retryable: bool,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": _request_id(request),
            "retryable": retryable,
        }
    }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    _, default_message, _ = ERROR_REGISTRY[exc.code]
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            request, exc.code, exc.message or default_message, exc.details, exc.retryable
        ),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    path = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    _, message, retryable = ERROR_REGISTRY["validation_error"]
    return JSONResponse(
        status_code=400,
        content=_envelope(
            request,
            "validation_error",
            message,
            {"path": path, "errors": [{"path": path, "msg": first.get("msg", "")}]},
            retryable,
        ),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "internal_error")
    status, default_message, retryable = ERROR_REGISTRY[code]
    message = exc.detail if isinstance(exc.detail, str) else default_message
    details: dict[str, Any] = {}
    if not isinstance(exc.detail, str) and isinstance(exc.detail, dict):
        details = exc.detail
    return JSONResponse(
        status_code=status,
        content=_envelope(request, code, message, details, retryable),
    )


async def simulate_error(request: Request) -> None:
    """
        Зависимость: заголовок X-Simulate-Error: <code> принудительно отдаёт ошибку.
    """
    code = request.headers.get("X-Simulate-Error")
    if code:
        raise ApiError(code)


# Коды адаптера (Часть 3, §5) → коды API-реестра (Часть 2, §1.2)
_ADAPTER_TO_API: dict[str, str] = {
    "device_unavailable": "adapter_unreachable",  # 502 — прибор/адаптер недоступен
    "device_timeout": "device_timeout",  # 504
    "invalid_value": "invalid_value",  # 422
    "readonly_device": "readonly_device",  # 409
    "unsupported_capability": "unsupported_capability",  # 422
    "device_busy": "run_in_progress",  # 409 — ближайший семантический код
    "rate_limited": "rate_limited",  # 429
    "permission_denied": "forbidden",  # 403
    "internal_error": "internal_error",  # 500
}


def api_error_from_adapter(exc: Exception) -> ApiError:
    """Маппинг AdapterError → ApiError с конвертом §1.1.

    device_unavailable по контракту ручного управления → 502 adapter_unreachable
    (Часть 2, §2.5). Прочие коды адаптера проходят как есть, если есть в реестре.
    """
    code = getattr(exc, "code", None) or "internal_error"
    message = getattr(exc, "message", None) or None
    details = dict(getattr(exc, "details", None) or {})
    device_id = getattr(exc, "device_id", None)
    if device_id:
        details.setdefault("device_id", device_id)
    details.setdefault("adapter_code", code)
    api_code = _ADAPTER_TO_API.get(code, code if code in ERROR_REGISTRY else "internal_error")
    return ApiError(api_code, message=message, details=details)
