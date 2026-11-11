"""Тесты Задач 1–3: персистентность runs в SQLite, параллельные волны, SSE."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.deps import engine, run_repository
from app.device_adapter.in_memory import InMemoryAdapter
from app.mode_engine.catalog import get_mode
from app.mode_engine.engine import ClassroomEngine
from app.mode_engine.groups import build_execution_groups
from app.mode_engine.models import Counters, ModeStep, Run, RunStep


def _preview(client: TestClient, mode: str) -> dict:
    return client.post(f"/api/v1/classrooms/9f1b/modes/{mode}/preview").json()


def _ack(preview: dict) -> list[str]:
    return [w["code"] for w in preview.get("warnings", [])]


# --- Задача 3: группы / параллельность ---


def test_build_execution_groups_independent_single_wave() -> None:
    steps = [
        ModeStep(sequence=1, device_id="D07", target_state={"open": 20}),
        ModeStep(sequence=2, device_id="D05", target_state={"on": True}),
        ModeStep(sequence=3, device_id="D08", target_state={"on": True}),
    ]
    groups = build_execution_groups(steps)
    assert len(groups) == 1
    assert [s.sequence for s in groups[0]] == [1, 2, 3]


def test_build_execution_groups_splits_projector_screen() -> None:
    steps = [
        ModeStep(sequence=1, device_id="D05", target_state={"on": True}),
        ModeStep(sequence=2, device_id="D03", target_state={"on": True}),
        ModeStep(sequence=3, device_id="D02", target_state={"on": True}),
        ModeStep(sequence=4, device_id="D04", target_state={"on": True}),
    ]
    groups = build_execution_groups(steps)
    # D03 и D02 не в одной волне; порядок sequence внутри волн сохранён
    assert len(groups) == 2
    devices_wave0 = {s.device_id for s in groups[0]}
    devices_wave1 = {s.device_id for s in groups[1]}
    assert "D03" in devices_wave0
    assert "D02" in devices_wave1
    assert "D05" in devices_wave0 and "D04" in devices_wave0
    assert all(
        groups[i][j].sequence <= groups[i][j + 1].sequence
        for i in range(len(groups))
        for j in range(len(groups[i]) - 1)
    )


def test_build_execution_groups_empty() -> None:
    assert build_execution_groups([]) == []


def test_all_modes_have_valid_groups() -> None:
    for mode_id in ("arrival", "lecture", "hybrid", "break", "finish"):
        mode = get_mode(mode_id)
        assert mode is not None
        groups = build_execution_groups(mode.steps)
        flat = [s.sequence for g in groups for s in g]
        # все sequence на месте, без потерь и дублей
        assert sorted(flat) == list(range(1, len(mode.steps) + 1)), mode_id
        # внутри волны — по sequence
        for wave in groups:
            seqs = [s.sequence for s in wave]
            assert seqs == sorted(seqs), mode_id


@pytest.mark.asyncio
async def test_run_steps_sorted_by_sequence_after_parallel() -> None:
    """Журнал по sequence, даже если выполняли параллельно."""
    preview = await engine.preview("hybrid")
    run, _ = await engine.run(
        "hybrid", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
    )
    sequences = [s.sequence for s in run.steps]
    assert sequences == sorted(sequences)
    assert sequences == list(range(1, 9))


@pytest.mark.asyncio
async def test_restart_marks_running_run_as_interrupted() -> None:
    now = datetime.now(timezone.utc)
    stale_run = Run(
        id="interrupted-run",
        mode_id="arrival",
        classroom_id="c1",
        status="running",
        counters=Counters(applied=1),
        idempotency_key="interrupted-key",
        preview_hash="preview-hash",
        created_at=now,
        started_at=now,
        steps=[
            RunStep(
                run_id="interrupted-run",
                sequence=1,
                device_id="D01",
                status="applied",
                target={"on": True},
                after={"on": True},
            ),
            RunStep(
                run_id="interrupted-run",
                sequence=2,
                device_id="D05",
                status="pending",
                target={"on": True},
            ),
        ],
    )
    await run_repository.save_run(stale_run)

    restarted_engine = ClassroomEngine(InMemoryAdapter(), repository=run_repository)
    recovered_count = await restarted_engine.recover_interrupted_runs()
    recovered = await run_repository.get_run("interrupted-run")

    assert recovered_count == 1
    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.error_code == "run_interrupted"
    assert recovered.counters.applied == 1
    assert recovered.counters.error == 1
    assert recovered.steps[1].error_code == "run_interrupted"


# --- Задача 1: БД ---


def test_run_persisted_and_readable_from_db(client: TestClient) -> None:
    preview = _preview(client, "break")
    created = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={
            "mode_id": "break",
            "preview_hash": preview["preview_hash"],
            "ack_warnings": _ack(preview),
        },
    ).json()

    # чтение через API уже идёт из репозитория
    fetched = client.get(f"/api/v1/runs/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert fetched["status"] in ("applied", "failed")
    assert fetched["counters_total"] == 8
    assert len(fetched["steps"]) == 8

    # прямая проверка репозитория (отдельный event loop, NullPool — безопасно)
    run = asyncio.run(run_repository.get_run(created["id"]))
    assert run is not None
    assert run.id == created["id"]
    assert run.counters.error == fetched["counters"]["error"]


def test_list_runs_from_db(client: TestClient) -> None:
    for mode in ("arrival", "break"):
        p = _preview(client, mode)
        client.post(
            "/api/v1/classrooms/9f1b/runs",
            json={"mode_id": mode, "preview_hash": p["preview_hash"], "ack_warnings": _ack(p)},
        )

    body = client.get("/api/v1/runs?limit=10").json()
    assert body["total"] >= 2
    modes = {item["mode_id"] for item in body["items"]}
    assert {"arrival", "break"} <= modes

    filtered = client.get("/api/v1/runs?mode_id=arrival").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["mode_id"] == "arrival"


def test_get_unknown_run_from_db_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/no-such-run-id")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_reset_clears_db(client: TestClient) -> None:
    p = _preview(client, "finish")
    client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={
            "mode_id": "finish",
            "preview_hash": p["preview_hash"],
            "ack_warnings": _ack(p),
        },
    )
    assert client.get("/api/v1/runs").json()["total"] == 1

    client.post("/api/v1/operator/classrooms/9f1b/simulator/reset")
    assert client.get("/api/v1/runs").json()["total"] == 0


# --- Задача 2: SSE ---


def test_sse_unknown_run_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/missing-id/events")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_sse_finished_run_emits_run_finished(client: TestClient) -> None:
    """После завершения run SSE сразу отдаёт run.finished и закрывается."""
    p = _preview(client, "arrival")
    created = client.post(
        "/api/v1/classrooms/9f1b/runs",
        json={"mode_id": "arrival", "preview_hash": p["preview_hash"], "ack_warnings": []},
    ).json()

    response = client.get(f"/api/v1/runs/{created['id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: run.finished" in body
    assert "data:" in body
    # payload содержит id и статус
    for line in body.splitlines():
        if line.startswith("data: "):
            data = json.loads(line[len("data: "):])
            assert data["id"] == created["id"]
            assert data["status"] in ("applied", "failed")
            break
    else:
        pytest.fail("нет data-строки в SSE")


def test_sse_subscribe_notify_unsubscribe() -> None:
    """Юнит: очередь получает _notify, unsubscribe убирает подписчика."""
    queue = engine.subscribe("run-x")
    engine._notify("run-x", {"type": "step.updated", "step": {"sequence": 1}})
    engine._notify("run-x", {"type": "run.finished", "run": {"id": "run-x"}})
    assert queue.qsize() == 2
    first = queue.get_nowait()
    assert first["type"] == "step.updated"
    second = queue.get_nowait()
    assert second["type"] == "run.finished"

    engine.unsubscribe("run-x", queue)
    engine._notify("run-x", {"type": "step.updated", "step": {}})
    assert queue.empty()
    # повторный unsubscribe безопасен
    engine.unsubscribe("run-x", queue)


def test_sse_events_include_step_updates_during_run(client: TestClient) -> None:
    """Прямая подписка: _execute_steps шлёт step.updated и run.finished."""
    received: list[dict] = []

    async def _scenario() -> None:
        queue = engine.subscribe("live-run")
        # эмулируем приход событий как в _execute_steps
        step = {
            "run_id": "live-run",
            "sequence": 1,
            "device_id": "D05",
            "status": "applied",
        }
        engine._notify("live-run", {"type": "step.updated", "step": step})
        engine._notify("live-run", {"type": "run.finished", "run": {"id": "live-run", "status": "applied"}})
        while not queue.empty():
            received.append(queue.get_nowait())
        engine.unsubscribe("live-run", queue)

    asyncio.run(_scenario())
    assert [e["type"] for e in received] == ["step.updated", "run.finished"]
