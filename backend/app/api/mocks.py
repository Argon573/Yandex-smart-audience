from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

PREVIEW_HASH = "a91f3c8e"

_WARNING = {
    "code": "presence_absent",
    "severity": "warning",
    "text": "Датчик присутствия не видит движения. Продолжить?",
}


def build_preview_mock(mode_id: str) -> dict[str, Any]:
    """Успешный preview (S4) на захардкоженных данных гибридного режима."""
    now = datetime.now(timezone.utc)
    steps: list[dict[str, Any]] = [
        {
            "sequence": 1,
            "device_id": "D07",
            "device_name": "Жалюзи",
            "before": {"on": True, "open": 50},
            "target": {"on": True, "open": 20},
            "delta": "open: 50 → 20",
            "status": "will_change",
            "critical": False,
        },
        {
            "sequence": 2,
            "device_id": "D05",
            "device_name": "Свет ряд 1",
            "before": {"on": True, "brightness": 60},
            "target": {"on": True, "brightness": 40},
            "delta": "brightness: 60 → 40",
            "status": "will_change",
            "critical": False,
        },
        {
            "sequence": 3,
            "device_id": "D06",
            "device_name": "Свет ряд 2",
            "before": {"on": True, "brightness": 60},
            "target": {"on": True, "brightness": 60},
            "delta": None,
            "status": "already_in_state",
            "critical": False,
        },
        {
            "sequence": 4,
            "device_id": "D03",
            "device_name": "Проекционный экран",
            "before": {"on": False, "open": 0},
            "target": {"on": True, "open": 100},
            "delta": "on: false → true, open: 0 → 100",
            "status": "will_change",
            "critical": True,
        },
        {
            "sequence": 5,
            "device_id": "D02",
            "device_name": "Проектор",
            "before": {"on": False},
            "target": {"on": True},
            "delta": "on: false → true",
            "status": "will_change",
            "critical": True,
        },
        {
            "sequence": 6,
            "device_id": "D04",
            "device_name": "Аудиосистема",
            "before": {"on": False, "volume": 40, "mute": False},
            "target": {"on": True, "volume": 55},
            "delta": "on: false → true, volume: 40 → 55",
            "status": "will_change",
            "critical": True,
        },
        {
            "sequence": 7,
            "device_id": "D08",
            "device_name": "Кондиционер",
            "before": {"on": True, "temperature": 22, "thermostat_mode": "auto"},
            "target": {"on": True, "temperature": 22, "thermostat_mode": "auto"},
            "delta": None,
            "status": "already_in_state",
            "critical": False,
        },
    ]
    will_change = sum(1 for s in steps if s["status"] == "will_change")
    return {
        "mode_id": mode_id,
        "state_version": 1,
        "preview_hash": PREVIEW_HASH,
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "can_apply": True,
        "blocking_reasons": [],
        "warnings": [_WARNING],
        "steps": steps,
        "summary": {
            "will_change": will_change,
            "already_in_state": len(steps) - will_change,
            "critical_total": sum(1 for s in steps if s["critical"]),
        },
    }


def build_run_mock(classroom_id: str, mode_id: str) -> dict[str, Any]:
    """Успешный ответ POST /runs (201, status=running)."""
    run_id = str(uuid4())
    preview = build_preview_mock(mode_id)
    steps = [
        {"sequence": s["sequence"], "device_id": s["device_id"], "status": "pending"}
        for s in preview["steps"]
    ]
    return {
        "id": run_id,
        "mode_id": mode_id,
        "classroom_id": classroom_id,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": {"id": "u1", "display_name": "Иванова М.С."},
        "preview_hash": PREVIEW_HASH,
        "step_total": len(steps),
        "steps": steps,
        "poll_url": f"/api/v1/runs/{run_id}",
    }


def build_run_finished_mock(run_id: str) -> dict[str, Any]:
    """Мок GET /runs/{id} для опроса (C-02): частичный успех для верстки S5."""
    return {
        "id": run_id,
        "mode_id": "hybrid",
        "mode_title": "Гибридная презентация",
        "classroom_id": "9f1b6a2e-0000-4000-8000-000000000001",
        "status": "failed",
        "outcome_message": "Применено частично: 6 из 7 шагов. Проектор недоступен — включите его вручную.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 4820,
        "policy": "continue_on_error",
        "counters": {"applied": 5, "skipped": 1, "error": 1},
        "error_code": "device_unavailable",
        "warnings": [{"code": "presence_absent", "acknowledged": True}],
        "steps": [
            {
                "sequence": 1,
                "device_id": "D07",
                "device_name": "Жалюзи",
                "target": {"on": True, "open": 20},
                "before": {"on": True, "open": 50},
                "after": {"on": True, "open": 20},
                "status": "applied",
                "attempts": 1,
                "duration_ms": 240,
            },
            {
                "sequence": 5,
                "device_id": "D02",
                "device_name": "Проектор",
                "target": {"on": True},
                "before": {"on": False},
                "after": None,
                "status": "error",
                "error_code": "device_unavailable",
                "error_text": "Прибор недоступен. Проверьте питание проектора.",
                "manual_hint": "Включите проектор пультом и повторите режим.",
                "attempts": 3,
                "duration_ms": 3001,
            },
        ],
        "counters_total": 7,
    }
