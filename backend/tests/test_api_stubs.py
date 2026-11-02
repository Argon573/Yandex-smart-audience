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
    # реальные матрицы: 8 шагов на прибор (Часть 3, §11)
    by_id = {item["id"]: item for item in items}
    assert by_id["hybrid"]["step_count"] == 8
    assert by_id["finish"]["step_count"] == 8


def test_list_modes_preconditions(client: TestClient) -> None:
    items = client.get("/api/v1/classrooms/9f1b/modes").json()["items"]
    by_id = {item["id"]: item for item in items}
    lecture_pre = by_id["lecture"]["preconditions"]
    assert lecture_pre and lecture_pre[0]["kind"] == "presence_warning"
    hybrid_pre = by_id["hybrid"]["preconditions"]
    assert hybrid_pre and hybrid_pre[0]["kind"] == "read_check"
    assert hybrid_pre[0]["device_ids"] == ["D02", "D04"]


def test_preview_mode_real(client: TestClient) -> None:
    """Реальный preview hybrid: diff, hash из состояния, presence_absent без движения."""
    response = client.post("/api/v1/classrooms/9f1b/modes/hybrid/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["mode_id"] == "hybrid"
    assert body["can_apply"] is True
    assert len(body["preview_hash"]) == 16
    assert len(body["steps"]) == 8
    assert body["summary"]["will_change"] >= 1
    assert body["summary"]["critical_total"] == 3  # D02, D03, D04
    # D07: 50 → 20
    d07 = next(s for s in body["steps"] if s["device_id"] == "D07")
    assert d07["status"] == "will_change"
    assert d07["delta"] == "open: 50 → 20"
    assert d07["device_name"] == "Жалюзи"


def test_preview_lecture_presence_warning(client: TestClient) -> None:
    response = client.post("/api/v1/classrooms/9f1b/modes/lecture/preview")
    body = response.json()
    codes = [w["code"] for w in body["warnings"]]
    assert "presence_absent" in codes
    assert body["can_apply"] is True  # warning ≠ blocking


def test_preview_unknown_mode_404(client: TestClient) -> None:
    response = client.post("/api/v1/classrooms/9f1b/modes/nope/preview")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_preview_idempotent_hash(client: TestClient) -> None:
    first = client.post("/api/v1/classrooms/9f1b/modes/break/preview").json()
    second = client.post("/api/v1/classrooms/9f1b/modes/break/preview").json()
    assert first["preview_hash"] == second["preview_hash"]
    assert first["state_version"] == second["state_version"]


def test_create_run_success(client: TestClient) -> None:
    """Apply hybrid: preview → run 201, шаги применены, status applied."""
    preview = client.post("/api/v1/classrooms/9f1b/modes/hybrid/preview").json()
    response = client.post(
        "/api/v1/classrooms/9f1b/runs",
        headers={"Idempotency-Key": "1d7f22ab-4c11-4e0a-9a77-0b93d0c2a1f0"},
        json={
            "mode_id": "hybrid",
            "preview_hash": preview["preview_hash"],
            "ack_warnings": preview_warnings(preview),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "applied"
    assert body["step_total"] == 8
    assert body["counters"]["error"] == 0
    assert body["poll_url"].startswith("/api/v1/runs/")
    assert body["mode_title"] == "Гибридная презентация"

    # состояние реально изменилось: D07 open 20
    room = client.get("/api/v1/room").json()
    d07 = next(d for z in room["zones"] for d in z["devices"] if d["id"] == "D07")
    assert d07["state"]["open"] == 20


def test_create_run_idempotent_repeat(client: TestClient) -> None:
    preview = client.post("/api/v1/classrooms/9f1b/modes/arrival/preview").json()
    payload = {
        "mode_id": "arrival",
        "preview_hash": preview["preview_hash"],
        "ack_warnings": [],
    }
    key = "2d7f22ab-4c11-4e0a-9a77-0b93d0c2a1f0"
    first = client.post(
        "/api/v1/classrooms/9f1b/runs", headers={"Idempotency-Key": key}, json=payload
    )
    second = client.post(
        "/api/v1/classrooms/9f1b/runs", headers={"Idempotency-Key": key}, json=payload
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_get_run_finished(client: TestClient) -> None:
    preview = client.post("/api/v1/classrooms/9f1b/modes/break/preview").json()
    created = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={
            "mode_id": "break",
            "preview_hash": preview["preview_hash"],
            "ack_warnings": [],
        },
    ).json()
    response = client.get(f"/api/v1/runs/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("applied", "failed")
    assert body["counters_total"] == 8
    assert len(body["steps"]) == 8
    assert body["outcome_message"]


def test_get_run_unknown_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/7a3e-does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_runs_journal(client: TestClient) -> None:
    preview = client.post("/api/v1/classrooms/9f1b/modes/finish/preview").json()
    client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={
            "mode_id": "finish",
            "preview_hash": preview["preview_hash"],
            "ack_warnings": ["motion_not_quiet"],
        },
    )
    response = client.get("/api/v1/runs?mode_id=finish")
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["mode_id"] == "finish"
    assert body["items"][0]["counters"]


def preview_warnings(preview: dict) -> list[str]:
    return [w["code"] for w in preview.get("warnings", [])]


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
