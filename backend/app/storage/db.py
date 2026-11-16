"""Async SQLAlchemy: engine, session factory, create_all (SQLite/aiosqlite)."""

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncConnection,
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
        await ensure_oauth_state_column(conn)


async def ensure_oauth_state_column(connection: AsyncConnection) -> None:
    """Upgrade DBs created before OAuth state binding was added."""
    table_names = await connection.run_sync(
        lambda sync_conn: inspect(sync_conn).get_table_names()
    )
    if "oauth_grants" not in table_names:
        return
    columns = await connection.run_sync(
        lambda sync_conn: {
            column["name"]
            for column in inspect(sync_conn).get_columns("oauth_grants")
        }
    )
    if "state" not in columns:
        await connection.execute(
            text(
                "ALTER TABLE oauth_grants "
                "ADD COLUMN state VARCHAR(1024) NOT NULL DEFAULT ''"
            )
        )
