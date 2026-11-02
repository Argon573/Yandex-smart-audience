from fastapi.testclient import TestClient

DEVICE_IDS = {f"D{i:02d}" for i in range(1, 13)}


def test_room_returns_full_plan(client: TestClient) -> None:
    response = client.get("/api/v1/room")
    assert response.status_code == 200
    body = response.json()

    assert body["name"] == "Аудитория 301"
    assert body["device_count"] == 12
    assert body["readonly_count"] == 4
    assert body["adapter_health"] == "ok"

    zone_ids = {z["id"] for z in body["zones"]}
    assert zone_ids == {"Z1", "Z2", "Z3"}

    device_ids = {d["id"] for z in body["zones"] for d in z["devices"]}
    assert device_ids == DEVICE_IDS


def test_room_device_fields_for_frontend(client: TestClient) -> None:
    body = client.get("/api/v1/room").json()
    d05 = next(d for z in body["zones"] for d in z["devices"] if d["id"] == "D05")
    assert d05["name"] == "Свет ряд 1"
    assert d05["ya_type"] == "devices.types.light"
    assert d05["managability"] == "controllable"
    assert d05["state"] == {"on": True, "brightness": 60}
    assert d05["status"] == "on"
    assert d05["updated_at"]

    d11 = next(d for z in body["zones"] for d in z["devices"] if d["id"] == "D11")
    assert d11["managability"] == "readonly"
    assert d11["state"] == {"motion": "not_detected"}


def test_room_zone_grouping(client: TestClient) -> None:
    body = client.get("/api/v1/room").json()
    zones = {z["id"]: z for z in body["zones"]}
    assert {d["id"] for d in zones["Z1"]["devices"]} == {"D01", "D02", "D03", "D04"}
    assert {d["id"] for d in zones["Z2"]["devices"]} == {"D05", "D06", "D07", "D08", "D09", "D10"}
    assert {d["id"] for d in zones["Z3"]["devices"]} == {"D11", "D12"}
    for zone in body["zones"]:
        assert zone["name"] and zone["purpose"]


def test_device_card_has_specs(client: TestClient) -> None:
    response = client.get("/api/v1/classrooms/x/devices/D08")
    assert response.status_code == 200
    body = response.json()
    assert body["zone_id"] == "Z2"
    cap_types = {c["type"] for c in body["specs"]["capabilities"]}
    assert "devices.capabilities.on_off" in cap_types
    assert body["commands_available"] is True


def test_device_not_found_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/classrooms/x/devices/D99")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
