import pytest
from fastapi.testclient import TestClient

from app.deps import engine
from app.main import app


@pytest.fixture(autouse=True)
def _reset_simulator_state():
    """Чистый старт: seed + без faults + пустой журнал runs (AC-02)."""
    engine._reset_all()
    yield
    engine._reset_all()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
