from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_request_id_echo(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-Id": "req-123"})
    assert response.headers["X-Request-Id"] == "req-123"
