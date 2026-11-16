"""Единая блокировка операций, изменяющих состояние аудитории."""

from collections.abc import AsyncIterator

from app.api.errors import ApiError
from app.deps import engine
from app.mode_engine.exceptions import EngineError


async def mutation_guard() -> AsyncIterator[None]:
    try:
        async with engine.exclusive_mutation():
            yield
    except EngineError as exc:
        raise ApiError(exc.code, message=exc.message, details=exc.details) from exc
