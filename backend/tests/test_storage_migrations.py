import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.storage.db import ensure_oauth_state_column


@pytest.mark.asyncio
async def test_legacy_oauth_table_gets_state_column() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE oauth_grants "
                    "(token_hash VARCHAR(64) PRIMARY KEY, kind VARCHAR(16) NOT NULL)"
                )
            )
            await ensure_oauth_state_column(connection)
            columns = await connection.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in inspect(sync_conn).get_columns("oauth_grants")
                }
            )
            assert "state" in columns
    finally:
        await engine.dispose()
