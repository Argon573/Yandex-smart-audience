from fastapi.testclient import TestClient


def _assert_envelope(response, code: str, status: int) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert "request_id" in error
    assert isinstance(error["retryable"], bool)
    return error


def _preview(client: TestClient, mode: str) -> dict:
    return client.post(f"/api/v1/classrooms/9f1b/modes/{mode}/preview").json()


def test_run_stale_hash_returns_409(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "hybrid", "preview_hash": "deadbeef", "ack_warnings": []},
    )
    error = _assert_envelope(response, "preview_stale", 409)
    assert error["details"]["actual_preview_hash"] == "deadbeef"
    assert error["details"]["expected_preview_hash"] != "deadbeef"
    assert len(error["details"]["expected_preview_hash"]) == 16


def test_run_unacked_warnings_returns_422(client: TestClient) -> None:
    """lecture: presence_absent без ack → 422 warnings_unacked."""
    preview = _preview(client, "lecture")
    assert any(w["code"] == "presence_absent" for w in preview["warnings"])
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "lecture", "preview_hash": preview["preview_hash"], "ack_warnings": []},
    )
    error = _assert_envelope(response, "warnings_unacked", 422)
    assert error["details"]["missing"] == ["presence_absent"]


def test_run_precondition_failed_read_check(client: TestClient) -> None:
    """hybrid: D02 недоступен → can_apply=false → 422 precondition_failed."""
    fault = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D02", "kind": "unavailable"},
    )
    assert fault.status_code == 201

    preview = _preview(client, "hybrid")
    assert preview["can_apply"] is False
    assert "read_check_failed" in preview["blocking_reasons"]

    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={
            "mode_id": "hybrid",
            "preview_hash": preview["preview_hash"],
            "ack_warnings": [],
        },
    )
    error = _assert_envelope(response, "precondition_failed", 422)
    assert "read_check_failed" in error["details"]["blocking_reasons"]


def test_idempotency_mismatch_returns_409(client: TestClient) -> None:
    key = "aaaaaaaa-4c11-4e0a-9a77-0b93d0c2a1f0"
    p1 = _preview(client, "arrival")
    first = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"Idempotency-Key": key},
        json={"mode_id": "arrival", "preview_hash": p1["preview_hash"], "ack_warnings": []},
    )
    assert first.status_code == 201

    p2 = _preview(client, "break")
    second = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"Idempotency-Key": key},
        json={"mode_id": "break", "preview_hash": p2["preview_hash"], "ack_warnings": []},
    )
    _assert_envelope(second, "idempotency_mismatch", 409)


def test_unknown_mode_on_run_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "party", "preview_hash": "x", "ack_warnings": []},
    )
    _assert_envelope(response, "not_found", 404)


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
        json={"mode_id": "hybrid", "preview_hash": "a91f3c8e", "ack_warnings": []},
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
