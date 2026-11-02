from fastapi.testclient import TestClient


def _assert_envelope(response, code: str, status: int) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert "request_id" in error
    assert isinstance(error["retryable"], bool)
    return error


def test_run_stale_hash_returns_409(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "hybrid", "preview_hash": "deadbeef", "ack_warnings": ["presence_absent"]},
    )
    error = _assert_envelope(response, "preview_stale", 409)
    assert error["details"]["expected_preview_hash"] == "a91f3c8e"
    assert error["details"]["actual_preview_hash"] == "deadbeef"


def test_run_unacked_warnings_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "hybrid", "preview_hash": "a91f3c8e", "ack_warnings": []},
    )
    error = _assert_envelope(response, "warnings_unacked", 422)
    assert error["details"]["missing"] == ["presence_absent"]


def test_simulate_error_header_on_preview(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/modes/hybrid/preview",
        headers={"X-Simulate-Error": "adapter_unreachable"},
    )
    _assert_envelope(response, "adapter_unreachable", 502)


def test_simulate_error_header_on_run(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"X-Simulate-Error": "run_in_progress"},
        json={"mode_id": "hybrid", "preview_hash": "a91f3c8e", "ack_warnings": ["presence_absent"]},
    )
    _assert_envelope(response, "run_in_progress", 409)


def test_simulate_error_on_get_run(client: TestClient) -> None:
    response = client.get(
        "/api/v1/runs/x", headers={"X-Simulate-Error": "device_timeout"}
    )
    _assert_envelope(response, "device_timeout", 504)


def test_validation_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/classrooms/9f1b/runs", json={"preview_hash": "a91f3c8e"})
    error = _assert_envelope(response, "validation_error", 400)
    assert error["details"]["path"] == "mode_id"


def test_request_id_echoed_in_error(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"X-Request-Id": "req-42"},
        json={"mode_id": "hybrid", "preview_hash": "bad"},
    )
    assert response.json()["error"]["request_id"] == "req-42"
    assert response.headers["X-Request-Id"] == "req-42"


def test_unknown_route_returns_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    _assert_envelope(response, "not_found", 404)
