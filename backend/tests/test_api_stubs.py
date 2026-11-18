from fastapi.testclient import TestClient
from urllib.parse import parse_qs, urlsplit
import re
from tests.conftest import wait_for_run

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
    assert len(body["preview_hash"]) == 32
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
    assert first["state_version"] == second["state_version"]
    assert len(first["preview_hash"]) == len(second["preview_hash"]) == 32


def test_mode_detail_and_unknown_mode(client: TestClient) -> None:
    response = client.get("/api/v1/classrooms/9f1b/modes/hybrid")
    assert response.status_code == 200
    assert response.json()["id"] == "hybrid"
    assert len(response.json()["steps"]) == 8
    response = client.get("/api/v1/classrooms/9f1b/modes/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_preview_is_bound_to_classroom(client: TestClient) -> None:
    preview = client.post("/api/v1/classrooms/first/modes/break/preview").json()
    response = client.post("/api/v1/classrooms/second/runs", json={
        "mode_id": "break", "preview_hash": preview["preview_hash"], "ack_warnings": [],
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preview_stale"


def test_preview_expired_returns_410(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.mode_engine.engine.PREVIEW_TTL_MINUTES", -1)
    preview = client.post("/api/v1/classrooms/9f1b/modes/break/preview").json()
    response = client.post("/api/v1/classrooms/9f1b/runs", json={
        "mode_id": "break", "preview_hash": preview["preview_hash"], "ack_warnings": [],
    })
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "preview_expired"


def test_preview_signature_cannot_be_extended(client: TestClient) -> None:
    preview = client.post("/api/v1/classrooms/9f1b/modes/break/preview").json()
    token = preview["preview_hash"]
    extended = f"{int(token[:8], 16) + 3600:08x}{token[8:]}"
    response = client.post("/api/v1/classrooms/9f1b/runs", json={
        "mode_id": "break", "preview_hash": extended, "ack_warnings": [],
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preview_stale"


def test_malformed_unicode_preview_returns_stale(client: TestClient) -> None:
    response = client.post("/api/v1/classrooms/9f1b/runs", json={
        "mode_id": "break", "preview_hash": "а" * 32, "ack_warnings": [],
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preview_stale"


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
    assert body["status"] == "running"
    body = wait_for_run(client, body["id"])
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
    body = wait_for_run(client, created["id"])
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


def test_yandex_discovery_shape(client: TestClient, provider_auth: dict[str, str]) -> None:
    response = client.get(
        "/v1.0/user/devices", headers={**provider_auth, "X-Request-Id": "f0e1d2c3"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "f0e1d2c3"
    devices = body["payload"]["devices"]
    assert len(devices) == 12
    by_id = {device["id"]: device for device in devices}
    assert by_id["D01"]["type"] == "devices.types.light"
    assert by_id["D01"]["capabilities"]
    assert "properties" not in by_id["D01"]
    assert by_id["D09"]["properties"]
    assert "capabilities" not in by_id["D09"]
    assert by_id["D09"]["device_info"]["manufacturer"] == "Smart Classroom"
    assert by_id["D09"]["custom_data"]["classroom_id"]


def test_yandex_access_token_requires_control_scope(
    client: TestClient, provider_auth_wrong_scope: dict[str, str]
) -> None:
    response = client.get(
        "/v1.0/user/devices",
        headers={**provider_auth_wrong_scope, "X-Request-Id": "wrong-scope"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["details"]["error"] == "invalid_token"


def test_yandex_provider_api_is_rate_limited(
    client: TestClient, provider_auth: dict[str, str], monkeypatch
) -> None:
    from app.security import rate_limit

    monkeypatch.setattr(rate_limit, "PROVIDER_API_MAX_REQUESTS", 2)
    headers = {**provider_auth, "X-Request-Id": "provider-rate-limit"}
    for _ in range(2):
        assert client.get("/v1.0/user/devices", headers=headers).status_code == 200

    limited = client.get("/v1.0/user/devices", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"]


def test_yandex_query_and_action_shape(
    client: TestClient, provider_auth: dict[str, str]
) -> None:
    query = client.post(
        "/v1.0/user/devices/query",
        headers={**provider_auth, "X-Request-Id": "query-1"},
        json={"devices": [{"id": "D08"}, {"id": "D09"}, {"id": "not-real"}]},
    )
    assert query.status_code == 200
    assert query.json()["request_id"] == "query-1"
    states = query.json()["payload"]["devices"]
    assert states[0]["id"] == "D08"
    values = {item["state"]["instance"]: item["state"]["value"] for item in states[0]["capabilities"]}
    assert values["temperature"] == 22
    assert values["thermostat"] == "auto"
    assert states[1]["properties"]
    assert states[2]["error_code"] == "DEVICE_NOT_FOUND"

    action = client.post(
        "/v1.0/user/devices/action",
        headers={**provider_auth, "X-Request-Id": "action-empty"},
        json={"payload": {"devices": []}},
    )
    assert action.status_code == 200
    assert action.json()["payload"] == {"devices": []}


def test_yandex_voice_actions_mutate_simulator_and_are_logged(
    client: TestClient, provider_auth: dict[str, str]
) -> None:
    commands = [
        ("D01", "devices.capabilities.on_off", "on", True),
        ("D01", "devices.capabilities.range", "brightness", 75),
        ("D02", "devices.capabilities.on_off", "on", True),
        ("D04", "devices.capabilities.range", "volume", 65),
        ("D08", "devices.capabilities.range", "temperature", 24),
        ("D08", "devices.capabilities.mode", "thermostat", "cool"),
    ]
    for index, (device_id, capability_type, instance, value) in enumerate(commands):
        response = client.post(
            "/v1.0/user/devices/action",
            headers={**provider_auth, "X-Request-Id": f"voice-{index}"},
            json={
                "payload": {
                    "devices": [
                        {
                            "id": device_id,
                            "capabilities": [
                                {
                                    "type": capability_type,
                                    "state": {"instance": instance, "value": value},
                                }
                            ],
                        }
                    ]
                }
            },
        )
        assert response.status_code == 200
        result = response.json()["payload"]["devices"][0]["capabilities"][0]
        assert result["state"]["action_result"]["status"] == "DONE"

    queried = client.post(
        "/v1.0/user/devices/query",
        headers={**provider_auth, "X-Request-Id": "query-after-voice"},
        json={"devices": [{"id": "D01"}, {"id": "D08"}]},
    ).json()["payload"]["devices"]
    d01_values = {c["state"]["instance"]: c["state"]["value"] for c in queried[0]["capabilities"]}
    d08_values = {c["state"]["instance"]: c["state"]["value"] for c in queried[1]["capabilities"]}
    assert d01_values["on"] is True and d01_values["brightness"] == 75
    assert d08_values["temperature"] == 24 and d08_values["thermostat"] == "cool"

    log = client.get("/api/v1/assistant/voice-commands").json()
    assert log["total"] == 6
    assert len(log["items"]) == 6
    assert all(item["source"] == "voice" for item in log["items"])
    assert log["items"][0]["request_id"] == "voice-5"
    assert "provider_actions_total 6" in client.get("/metrics").text
    assert client.get("/api/v1/operator/summary").json()["voice"]["actions_total"] == 6


def test_yandex_action_returns_device_errors_without_mutation(
    client: TestClient, provider_auth: dict[str, str]
) -> None:
    def run(device_id: str, instance: str, value: object) -> dict:
        response = client.post(
            "/v1.0/user/devices/action",
            headers={**provider_auth, "X-Request-Id": "voice-error"},
            json={
                "payload": {
                    "devices": [
                        {
                            "id": device_id,
                            "capabilities": [
                                {
                                    "type": "devices.capabilities.on_off",
                                    "state": {"instance": instance, "value": value},
                                }
                            ],
                        }
                    ]
                }
            },
        )
        assert response.status_code == 200
        return response.json()["payload"]["devices"][0]["capabilities"][0]["state"]["action_result"]

    assert run("D09", "on", True)["error_code"] == "INVALID_ACTION"
    assert run("D02", "on", True)["status"] == "DONE"
    assert run("D02", "on", False)["status"] == "DONE"
    assert run("D01", "on", 99)["error_code"] == "INVALID_VALUE"
    before = client.get("/api/v1/classrooms/9f1b/devices/D02").json()["state"]["on"]
    fault = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D02", "kind": "unavailable"},
    )
    assert fault.status_code == 201
    assert run("D02", "on", not before)["error_code"] == "DEVICE_UNREACHABLE"
    after = client.get("/api/v1/classrooms/9f1b/devices/D02").json()["state"]["on"]
    assert after is before
    assert run("missing", "on", True)["error_code"] == "DEVICE_NOT_FOUND"


def test_yandex_invalid_request_shape_is_400(
    client: TestClient, provider_auth: dict[str, str]
) -> None:
    response = client.post(
        "/v1.0/user/devices/action",
        headers={**provider_auth, "X-Request-Id": "malformed"},
        json={"payload": {"devices": [{"id": "D01"}]}}
    )
    assert response.status_code == 400


def test_yandex_head_check(client: TestClient, provider_auth: dict[str, str]) -> None:
    response = client.head(
        "/v1.0/", headers={**provider_auth, "X-Request-Id": "head"}
    )
    assert response.status_code == 200


def test_oauth_token_shape(client: TestClient) -> None:
    redirect_uri = "http://localhost/callback"
    page = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "test-yandex-client",
            "redirect_uri": redirect_uri,
            "state": "nonce-123",
            "scope": "classroom:control",
        },
    )
    assert page.status_code == 200
    flow_token = re.search(r'name="flow_token" value="([^"]+)"', page.text)
    assert flow_token
    authorized = client.post(
        "/oauth/authorize",
        data={
            "email": "teacher@example.test",
            "password": "test-password",
            "client_id": "test-yandex-client",
            "redirect_uri": redirect_uri,
            "state": "nonce-123",
            "scope": "classroom:control",
            "consent": "true",
            "flow_token": flow_token.group(1),
        },
        follow_redirects=False,
    )
    assert authorized.status_code == 302
    callback = parse_qs(urlsplit(authorized.headers["location"]).query)
    assert callback["state"] == ["nonce-123"]
    assert callback["client_id"] == ["test-yandex-client"]
    code = callback["code"][0]

    response = client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": "test-yandex-client",
            "client_secret": "test-yandex-secret",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert "access_token" in body and "refresh_token" in body
    assert body["scope"] == "classroom:control"

    linked = client.get(
        "/v1.0/user/devices",
        headers={"X-Request-Id": "oauth-linked", "Authorization": f"Bearer {body['access_token']}"},
    )
    assert linked.status_code == 200
    assert linked.json()["payload"]["user_id"] == "teacher@example.test"
    assert linked.json()["payload"]["devices"]
    voice_action = client.post(
        "/v1.0/user/devices/action",
        headers={
            "X-Request-Id": "oauth-voice",
            "Authorization": f"Bearer {body['access_token']}",
        },
        json={
            "payload": {
                "devices": [
                    {
                        "id": "D02",
                        "capabilities": [
                            {
                                "type": "devices.capabilities.on_off",
                                "state": {"instance": "on", "value": True},
                            }
                        ],
                    }
                ]
            }
        },
    )
    assert voice_action.status_code == 200
    assert (
        voice_action.json()["payload"]["devices"][0]["capabilities"][0]["state"]["action_result"]["status"]
        == "DONE"
    )

    refreshed = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": body["refresh_token"],
            "client_id": "test-yandex-client",
            "client_secret": "test-yandex-secret",
        },
    )
    assert refreshed.status_code == 200
    next_tokens = refreshed.json()
    assert next_tokens["access_token"] != body["access_token"]

    link = client.get("/api/v1/assistant/link").json()
    assert link["linked"] is True
    assert link["ya_user_id_masked"]
    assert link["access_token_expires_at"]
    assert link["refresh_rotated_at"]

    replay = client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": body["refresh_token"],
            "client_id": "test-yandex-client",
            "client_secret": "test-yandex-secret",
        },
    )
    assert replay.status_code == 400
    revoked_access = client.get(
        "/v1.0/user/devices",
        headers={"X-Request-Id": "revoked", "Authorization": f"Bearer {next_tokens['access_token']}"},
    )
    assert revoked_access.status_code == 401

    unlink = client.post("/api/v1/assistant/link/revoke")
    assert unlink.status_code == 200
    assert unlink.json()["revoked"] is True
    assert "ya_user_id_masked" in unlink.json()
    assert client.get("/api/v1/assistant/link").json()["linked"] is False


def test_yandex_unlink_revokes_bearer_and_writes_audit(
    client: TestClient, provider_auth: dict[str, str]
) -> None:
    response = client.post(
        "/v1.0/user/unlink", headers={**provider_auth, "X-Request-Id": "unlink-1"}
    )
    assert response.status_code == 200
    assert response.json() == {"request_id": "unlink-1", "payload": {}}
    denied = client.get(
        "/v1.0/user/devices",
        headers={**provider_auth, "X-Request-Id": "after-unlink"},
    )
    assert denied.status_code == 401
    assert client.get("/api/v1/assistant/link").json()["linked"] is False


def test_oauth_rejects_missing_credentials_invalid_client_and_replayed_code(
    client: TestClient,
) -> None:
    no_credentials = client.get(
        "/v1.0/user/devices",
        headers={"X-Request-Id": "no-auth", "Authorization": ""},
    )
    assert no_credentials.status_code == 401

    invalid_client = client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": "not-a-code",
            "redirect_uri": "http://localhost/callback",
            "client_id": "test-yandex-client",
            "client_secret": "wrong-secret",
        },
    )
    assert invalid_client.status_code == 401
    assert invalid_client.json()["error"] == "invalid_client"

    page = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "test-yandex-client",
            "redirect_uri": "http://localhost/callback",
            "state": "state-replay",
            "scope": "classroom:control",
        },
    )
    flow_token = re.search(r'name="flow_token" value="([^"]+)"', page.text)
    assert flow_token
    response = client.post(
        "/oauth/authorize",
        data={
            "email": "teacher@example.test",
            "password": "test-password",
            "client_id": "test-yandex-client",
            "redirect_uri": "http://localhost/callback",
            "state": "state-replay",
            "scope": "classroom:control",
            "consent": "true",
            "flow_token": flow_token.group(1),
        },
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost/callback",
        "client_id": "test-yandex-client",
        "client_secret": "test-yandex-secret",
    }
    assert client.post("/oauth/token", json=token_payload).status_code == 200
    replay = client.post("/oauth/token", json=token_payload)
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"

    anonymous_revoke = client.post("/oauth/revoke", json={"token": "unknown-token"})
    assert anonymous_revoke.status_code == 401
    assert anonymous_revoke.json()["error"] == "invalid_client"
    client_authenticated_revoke = client.post(
        "/oauth/revoke",
        json={
            "token": "unknown-token",
            "client_id": "test-yandex-client",
            "client_secret": "test-yandex-secret",
        },
    )
    assert client_authenticated_revoke.status_code == 200
    assert client_authenticated_revoke.json() == {"revoked": True}


def test_internal_api_requires_bearer_and_enforces_operator_role(client: TestClient) -> None:
    unauthenticated = client.get("/api/v1/room", headers={"Authorization": ""})
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthorized"
    denied_global_unlink = client.post(
        "/api/v1/assistant/link/revoke", headers={"Authorization": ""}
    )
    assert denied_global_unlink.status_code == 401

    from app.config import settings

    settings.APP_DEMO_ROLE = "teacher"
    login = client.post(
        "/api/v1/auth/login",
        json={"email": settings.APP_DEMO_EMAIL, "password": settings.APP_DEMO_PASSWORD},
    )
    assert login.status_code == 200
    teacher_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/room", headers=teacher_headers).status_code == 200
    denied = client.get("/api/v1/operator/summary", headers=teacher_headers)
    assert denied.status_code == 403
    denied_revoke = client.post("/api/v1/assistant/link/revoke", headers=teacher_headers)
    assert denied_revoke.status_code == 403


def test_internal_refresh_rotation_replay_and_logout(client: TestClient) -> None:
    from app.config import settings

    login = client.post(
        "/api/v1/auth/login",
        json={"email": settings.APP_DEMO_EMAIL, "password": settings.APP_DEMO_PASSWORD},
    )
    assert login.status_code == 200
    original = login.json()
    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert rotated.status_code == 200
    updated = rotated.json()
    assert updated["refresh_token"] != original["refresh_token"]
    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert replay.status_code == 401
    revoked = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {updated['access_token']}"}
    )
    assert revoked.status_code == 401

    fresh = client.post(
        "/api/v1/auth/login",
        json={"email": settings.APP_DEMO_EMAIL, "password": settings.APP_DEMO_PASSWORD},
    ).json()
    logout = client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {fresh['access_token']}"}
    )
    assert logout.status_code == 204
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"}
    ).status_code == 401


def test_login_rate_limit_and_https_enforcement(client: TestClient) -> None:
    from app.config import settings
    from app.security.rate_limit import reset_rate_limits

    reset_rate_limits()
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": settings.APP_DEMO_EMAIL, "password": "incorrect"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": settings.APP_DEMO_EMAIL, "password": "incorrect"},
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"]

    settings.ENFORCE_HTTPS = True
    cleartext = client.get("/api/v1/room")
    assert cleartext.status_code == 426
    secure = client.get("https://testserver/api/v1/room")
    assert secure.status_code == 200
    assert secure.headers["strict-transport-security"].startswith("max-age=")


def test_oauth_login_rate_limit_returns_protocol_error(client: TestClient) -> None:
    from app.security.rate_limit import reset_rate_limits

    reset_rate_limits()
    form = {"email": "teacher@example.test"}
    for _ in range(5):
        response = client.post("/oauth/authorize", data=form, follow_redirects=False)
        assert response.status_code == 400
    limited = client.post("/oauth/authorize", data=form, follow_redirects=False)
    assert limited.status_code == 429
    assert limited.json() == {"error": "slow_down"}
    assert limited.headers["retry-after"]


def test_https_is_default_outside_local_environments() -> None:
    from app.config import Settings

    assert Settings(_env_file=None, APP_ENV="production").ENFORCE_HTTPS is True
    assert Settings(_env_file=None, APP_ENV="local").ENFORCE_HTTPS is False
