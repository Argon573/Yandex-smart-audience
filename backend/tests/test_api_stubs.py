from fastapi.testclient import TestClient

MODE_IDS = {"arrival", "lecture", "hybrid", "break", "finish"}


def test_list_classrooms(client: TestClient) -> None:
    response = client.get("/api/v1/classrooms")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Аудитория 301"


def test_list_modes(client: TestClient) -> None:
    response = client.get("/api/v1/classrooms/9f1b/modes")
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["id"] for item in items} == MODE_IDS
    assert all("step_count" in item and "critical_device_ids" in item for item in items)


def test_preview_mode_mock(client: TestClient) -> None:
    response = client.post("/api/v1/classrooms/9f1b/modes/hybrid/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["mode_id"] == "hybrid"
    assert body["can_apply"] is True
    assert body["preview_hash"] == "a91f3c8e"
    assert len(body["steps"]) == 7
    assert body["warnings"][0]["code"] == "presence_absent"
    assert body["summary"]["will_change"] >= 1


def test_create_run_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"Idempotency-Key": "1d7f22ab-4c11-4e0a-9a77-0b93d0c2a1f0"},
        json={"mode_id": "hybrid", "preview_hash": "a91f3c8e", "ack_warnings": ["presence_absent"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "running"
    assert body["step_total"] == 7
    assert body["poll_url"].startswith("/api/v1/runs/")


def test_get_run_finished_mock(client: TestClient) -> None:
    response = client.get("/api/v1/runs/7a3e")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["counters"] == {"applied": 5, "skipped": 1, "error": 1}
    assert "частично" in body["outcome_message"]


def test_yandex_discovery_shape(client: TestClient) -> None:
    response = client.get("/v1.0/user/devices", headers={"X-Request-Id": "f0e1d2c3"})
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "f0e1d2c3"
    assert body["payload"]["devices"] == []


def test_yandex_query_and_action_shape(client: TestClient) -> None:
    query = client.post("/v1.0/user/devices/query", json={"devices": []})
    assert query.status_code == 200
    assert query.json()["payload"] == {"devices": []}

    action = client.post("/v1.0/user/devices/action", json={"payload": {"devices": []}})
    assert action.status_code == 200
    assert action.json()["payload"] == {"devices": []}


def test_yandex_head_check(client: TestClient) -> None:
    response = client.head("/v1.0/")
    assert response.status_code == 200


def test_oauth_token_shape(client: TestClient) -> None:
    response = client.post("/oauth/token", data={"grant_type": "authorization_code"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert "access_token" in body and "refresh_token" in body
