"""Тестовые фикстуры: чистый seed + пустой журнал (память и SQLite)."""

import asyncio
import os
import tempfile
import time

# Принудительно изолировать БД до импорта app: фикстуры удаляют журнал.
_test_db_dir = tempfile.TemporaryDirectory(prefix="smart-classroom-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_dir.name}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.deps import engine, run_repository
from app.main import app


def _clear_run_db() -> None:
    """Очистить таблицы runs/run_steps синхронно (нет running loop в pytest)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_repository.clear_all())
    else:
        # не должно случаться в sync-фикстуре; fallback — отдельный loop
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run_repository.clear_all())
        finally:
            loop.close()


@pytest.fixture(autouse=True)
def _reset_simulator_state():
    """Чистый старт: seed + без faults + пустой журнал в памяти и в БД (AC-02)."""
    engine._reset_all()
    _clear_run_db()
    yield
    engine._reset_all()
    _clear_run_db()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def wait_for_run(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] != "running":
            return run
        time.sleep(0.01)
    raise AssertionError(f"Run {run_id} did not finish")
