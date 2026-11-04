"""Async SQLAlchemy: engine, session factory, create_all (SQLite/aiosqlite)."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base для ORM-моделей storage."""


# NullPool: соединение не переиспользуется между event loop'ами
# (pytest fixture и loop TestClient) — важно для SQLite + aiosqlite в тестах.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """DI-фабрика сессий для Depends(get_session)."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Создать таблицы (checkfirst). Вызывается из lifespan при старте."""
    # импорт моделей обязателен, чтобы Base.metadata был заполнен
    from app.storage import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
