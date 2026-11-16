"""Тестовые фикстуры: чистый seed + пустой журнал (память и SQLite)."""

import asyncio
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Принудительно изолировать БД до импорта app: фикстуры удаляют журнал.
_test_db_dir = tempfile.TemporaryDirectory(prefix="smart-classroom-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_dir.name}/test.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.deps import engine, run_repository
from app.main import app
from app.observability.metrics import reset_provider_actions
from app.security.rate_limit import reset_rate_limits
from app.config import settings
from app.storage.db import SessionLocal
from app.storage.models import OAuthGrantORM


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


def _clear_oauth_db() -> None:
    async def clear() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(OAuthGrantORM))
            await session.commit()

    asyncio.run(clear())


def _create_test_access_token() -> str:
    import hashlib
    import secrets

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    async def create() -> None:
        async with SessionLocal() as session:
            session.add(
                OAuthGrantORM(
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    kind="access",
                    family_id=str(uuid4()),
                    client_id=settings.YANDEX_CLIENT_ID,
                    user_id="teacher@example.test",
                    redirect_uri="",
                    state="",
                    scope="classroom:control",
                    expires_at=now + timedelta(hours=1),
                    revoked=False,
                    consumed=False,
                    created_at=now,
                )
            )
            await session.commit()

    asyncio.run(create())
    return token


def _create_test_yandex_access_token() -> str:
    import hashlib
    import secrets

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    async def create() -> None:
        async with SessionLocal() as session:
            session.add(
                OAuthGrantORM(
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    kind="access",
                    family_id=str(uuid4()),
                    client_id=settings.YANDEX_CLIENT_ID,
                    user_id="teacher@example.test",
                    redirect_uri="",
                    state="",
                    scope="classroom:control",
                    expires_at=now + timedelta(hours=1),
                    revoked=False,
                    consumed=False,
                    created_at=now,
                )
            )
            await session.commit()

    asyncio.run(create())
    return token


@pytest.fixture(autouse=True)
def _reset_simulator_state():
    """Чистый старт: seed + без faults + пустой журнал в памяти и в БД (AC-02)."""
    engine._reset_all()
    reset_provider_actions()
    app.state.voice_commands = []
    _clear_run_db()
    old_settings = (
        settings.YANDEX_CLIENT_ID,
        settings.YANDEX_CLIENT_SECRET,
        settings.YANDEX_DEMO_EMAIL,
        settings.YANDEX_DEMO_PASSWORD,
        settings.YANDEX_REDIRECT_URIS,
        settings.APP_DEMO_EMAIL,
        settings.APP_DEMO_PASSWORD,
        settings.APP_DEMO_ROLE,
        settings.ENFORCE_HTTPS,
    )
    settings.YANDEX_CLIENT_ID = "test-yandex-client"
    settings.YANDEX_CLIENT_SECRET = "test-yandex-secret"
    settings.YANDEX_DEMO_EMAIL = "teacher@example.test"
    settings.YANDEX_DEMO_PASSWORD = "test-password"
    settings.YANDEX_REDIRECT_URIS = "https://social.yandex.net/broker/redirect,http://localhost/callback"
    settings.APP_DEMO_EMAIL = "operator@example.test"
    settings.APP_DEMO_PASSWORD = "internal-test-password"
    settings.APP_DEMO_ROLE = "operator"
    settings.ENFORCE_HTTPS = False
    reset_rate_limits()
    _clear_oauth_db()
    yield
    _clear_oauth_db()
    (
        settings.YANDEX_CLIENT_ID,
        settings.YANDEX_CLIENT_SECRET,
        settings.YANDEX_DEMO_EMAIL,
        settings.YANDEX_DEMO_PASSWORD,
        settings.YANDEX_REDIRECT_URIS,
        settings.APP_DEMO_EMAIL,
        settings.APP_DEMO_PASSWORD,
        settings.APP_DEMO_ROLE,
        settings.ENFORCE_HTTPS,
    ) = old_settings
    engine._reset_all()
    reset_provider_actions()
    app.state.voice_commands = []
    _clear_run_db()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        login = test_client.post(
            "/api/v1/auth/login",
            json={"email": settings.APP_DEMO_EMAIL, "password": settings.APP_DEMO_PASSWORD},
        )
        assert login.status_code == 200, login.text
        test_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield test_client


@pytest.fixture()
def provider_auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_create_test_yandex_access_token()}"}


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
