"""Operator API (C-06): faults, occupancy, reset, health, ручное управление."""

from fastapi.testclient import TestClient


def _assert_envelope(response, code: str, status: int) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    return error


def test_inject_and_list_faults(client: TestClient) -> None:
    created = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D02", "kind": "unavailable", "ttl_seconds": 600, "comment": "US-05"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["device_id"] == "D02"
    assert body["kind"] == "unavailable"
    assert body["active"] is True
    assert body["created_by"] == "operator@stand"
    assert body["expires_at"] is not None

    listed = client.get("/api/v1/operator/classrooms/9f1b/simulator/faults").json()
    assert listed["total"] == 1
    assert listed["broken_devices"] == ["D02"]


def test_delete_fault(client: TestClient) -> None:
    created = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D05", "kind": "latency", "value_ms": 4000},
    ).json()
    deleted = client.delete(f"/api/v1/operator/simulator/faults/{created['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["active"] is False
    listed = client.get("/api/v1/operator/classrooms/9f1b/simulator/faults").json()
    assert listed["total"] == 0


def test_fault_unknown_device_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D99", "kind": "unavailable"},
    )
    _assert_envelope(response, "invalid_value", 422)


def test_fault_unavailable_blocks_execute_and_read(client: TestClient) -> None:
    client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D05", "kind": "unavailable"},
    )
    # read → reachable=false
    room = client.get("/api/v1/room").json()
    d05 = next(d for z in room["zones"] for d in z["devices"] if d["id"] == "D05")
    assert d05["status"] == "unavailable"

    # команда → 502 adapter_unreachable (device_unavailable)
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D05/commands",
        json={"commands": [{"type": "devices.capabilities.range", "instance": "brightness", "value": 30}]},
    )
    error = _assert_envelope(response, "adapter_unreachable", 502)
    assert error["details"]["adapter_code"] == "device_unavailable"

    health = client.get("/api/v1/operator/classrooms/9f1b/adapter/health").json()
    assert health["status"] == "degraded"
    assert health["broken_devices"] == ["D05"]
    assert health["devices"][0]["id"] == "D05"
    assert health["devices"][0]["reachable"] is False


def test_fault_latency_timeout_on_command(client: TestClient) -> None:
    client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D06", "kind": "latency", "value_ms": 4000},
    )
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D06/commands",
        json={"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": False}]},
    )
    error = _assert_envelope(response, "device_timeout", 504)
    assert error["details"]["value_ms"] == 4000


def test_fault_error_kind(client: TestClient) -> None:
    client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D07", "kind": "error", "error_code": "invalid_value"},
    )
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D07/commands",
        json={"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": False}]},
    )
    _assert_envelope(response, "invalid_value", 422)


def test_occupancy_sets_motion(client: TestClient) -> None:
    response = client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/occupancy",
        json={"detected": True, "presence_minutes": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "D11"
    assert body["state"]["motion"] == "detected"

    # lecture: движение есть → нет presence_absent
    preview = client.post("/api/v1/classrooms/9f1b/modes/lecture/preview").json()
    codes = [w["code"] for w in preview["warnings"]]
    assert "presence_absent" not in codes

    # finish: движение есть → motion_not_quiet
    preview_f = client.post("/api/v1/classrooms/9f1b/modes/finish/preview").json()
    assert any(w["code"] == "motion_not_quiet" for w in preview_f["warnings"])


def test_occupancy_quiet_finish_no_warning(client: TestClient) -> None:
    client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/occupancy",
        json={"detected": False, "presence_minutes": 6},
    )
    preview = client.post("/api/v1/classrooms/9f1b/modes/finish/preview").json()
    assert not any(w["code"] == "motion_not_quiet" for w in preview["warnings"])
    assert preview["can_apply"] is True


def test_reset_restores_seed_and_clears_faults(client: TestClient) -> None:
    client.post(
        "/api/v1/operator/classrooms/9f1b/simulator/faults",
        json={"device_id": "D02", "kind": "unavailable"},
    )
    # портим состояние
    client.post(
        "/api/v1/classrooms/9f1b/devices/D05/commands",
        json={"commands": [{"type": "devices.capabilities.range", "instance": "brightness", "value": 15}]},
    )

    response = client.post("/api/v1/operator/classrooms/9f1b/simulator/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["restored"] is True
    assert body["restored_devices"] == 12
    assert body["faults_cleared"] == 1
    assert body["initial_state_ref"] == "seed-42"

    room = client.get("/api/v1/room").json()
    d05 = next(d for z in room["zones"] for d in z["devices"] if d["id"] == "D05")
    assert d05["state"] == {"on": True, "brightness": 60}
    assert d05["status"] == "on"
    health = client.get("/api/v1/operator/classrooms/9f1b/adapter/health").json()
    assert health["status"] == "ok"


def test_manual_command_applies(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D01/commands",
        json={"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": True}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["device_id"] == "D01"
    assert body["state"]["on"] is True
    assert body["source"] == "manual"
    assert body["state_version"] == 2


def test_manual_command_readonly_409(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D11/commands",
        json={"commands": [{"type": "devices.properties.event", "instance": "motion", "value": "detected"}]},
    )
    _assert_envelope(response, "readonly_device", 409)


def test_manual_command_invalid_value_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D05/commands",
        json={"commands": [{"type": "devices.capabilities.range", "instance": "brightness", "value": 0}]},
    )
    _assert_envelope(response, "invalid_value", 422)


def test_manual_command_unknown_device_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classrooms/9f1b/devices/D99/commands",
        json={"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": True}]},
    )
    _assert_envelope(response, "not_found", 404)


def test_summary_shape(client: TestClient) -> None:
    response = client.get("/api/v1/operator/summary?window=1h")
    assert response.status_code == 200
    body = response.json()
    assert set(body["runs"]) == {"applied", "failed", "running", "partial"}
    assert body["adapter"]["status"] in ("ok", "degraded", "unreachable")
    assert isinstance(body["errors"], list)
