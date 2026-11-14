"""Проверки фонового запуска и конкурирующих операций через HTTP."""

import asyncio
import json

import httpx
import pytest

from app.deps import engine, in_memory_adapter, run_repository
from app.main import app


@pytest.mark.asyncio
async def test_background_run_blocks_mutations_and_allows_idempotent_retry(monkeypatch):
    await engine.init_db()
    started = asyncio.Event()
    release = asyncio.Event()
    original = engine._execute_steps

    async def delayed(run, mode):
        started.set()
        await release.wait()
        return await original(run, mode)

    monkeypatch.setattr(engine, "_execute_steps", delayed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        preview = (await client.post("/api/v1/classrooms/9f1b/modes/arrival/preview")).json()
        body = {"mode_id": "arrival", "preview_hash": preview["preview_hash"], "ack_warnings": []}
        headers = {"Idempotency-Key": "background-test"}
        try:
            response = await client.post("/api/v1/classrooms/9f1b/runs", json=body, headers=headers)
            assert response.status_code == 201
            run_id = response.json()["id"]
            assert response.json()["status"] == "running"
            await asyncio.wait_for(started.wait(), 2)
            stored = await run_repository.get_run(run_id)
            assert stored is not None and stored.status == "running"

            repeat = await client.post("/api/v1/classrooms/9f1b/runs", json=body, headers=headers)
            assert repeat.status_code == 200 and repeat.json()["id"] == run_id
            other = await client.post("/api/v1/classrooms/9f1b/runs", json=body)
            assert other.status_code == 409
            operations = [
                ("/api/v1/operator/classrooms/9f1b/simulator/reset", None),
                ("/api/v1/operator/classrooms/9f1b/simulator/occupancy", {"detected": True, "presence_minutes": 0}),
                ("/api/v1/operator/classrooms/9f1b/simulator/faults", {"device_id": "D05", "kind": "unavailable"}),
                ("/api/v1/classrooms/9f1b/devices/D05/commands", {"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": True}]}),
            ]
            for url, payload in operations:
                conflict = await client.post(url, json=payload)
                assert conflict.status_code == 409, conflict.text
                assert conflict.json()["error"]["code"] == "run_in_progress"
            release.set()
            await asyncio.wait_for(asyncio.gather(*list(engine._tasks)), 3)
            assert (await run_repository.get_run(run_id)).status == "applied"
            assert (await client.post("/api/v1/operator/classrooms/9f1b/simulator/reset")).status_code == 200
        finally:
            release.set()
            await engine.shutdown()


@pytest.mark.asyncio
async def test_sse_snapshot_does_not_miss_completion_during_db_lookup(monkeypatch):
    await engine.init_db()
    execute_release = asyncio.Event()
    lookup_started = asyncio.Event()
    lookup_release = asyncio.Event()
    original_execute = engine._execute_steps
    original_get = run_repository.get_run

    async def delayed_execution(run, mode):
        await execute_release.wait()
        return await original_execute(run, mode)

    async def delayed_lookup(run_id):
        stale = await original_get(run_id)
        lookup_started.set()
        await lookup_release.wait()
        return stale

    monkeypatch.setattr(engine, "_execute_steps", delayed_execution)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        preview = (await client.post("/api/v1/classrooms/9f1b/modes/arrival/preview")).json()
        response = await client.post("/api/v1/classrooms/9f1b/runs", json={
            "mode_id": "arrival", "preview_hash": preview["preview_hash"], "ack_warnings": [],
        })
        run_id = response.json()["id"]
        monkeypatch.setattr(run_repository, "get_run", delayed_lookup)
        request = asyncio.create_task(client.get(f"/api/v1/runs/{run_id}/events"))
        try:
            await asyncio.wait_for(lookup_started.wait(), 2)
            execute_release.set()
            await asyncio.wait_for(asyncio.gather(*list(engine._tasks)), 3)
            lookup_release.set()
            events = await asyncio.wait_for(request, 2)
            assert "event: run.finished" in events.text
            data = next(line[6:] for line in events.text.splitlines() if line.startswith("data: "))
            assert json.loads(data)["status"] == "applied"
            assert run_id not in engine._subscribers
        finally:
            execute_release.set()
            lookup_release.set()
            if not request.done():
                request.cancel()
                await asyncio.gather(request, return_exceptions=True)
            await engine.shutdown()


@pytest.mark.asyncio
async def test_background_error_closes_run_and_releases_lock(monkeypatch):
    await engine.init_db()

    async def fail(run, mode):
        raise RuntimeError("test failure")

    monkeypatch.setattr(engine, "_execute_steps", fail)
    preview = await engine.preview("arrival", "9f1b")
    run, _ = await engine.run("arrival", "9f1b", preview_hash=preview.preview_hash, background=True)
    await asyncio.wait_for(asyncio.gather(*list(engine._tasks)), 3)
    persisted = await run_repository.get_run(run.id)
    assert persisted.status == "failed"
    assert persisted.error_code == "internal_error"
    assert all(step.status == "error" for step in persisted.steps)
    async with engine.exclusive_mutation():
        pass


@pytest.mark.asyncio
async def test_manual_command_blocks_run_until_command_finishes(monkeypatch):
    await engine.init_db()
    started, release = asyncio.Event(), asyncio.Event()
    original = in_memory_adapter.execute

    async def delayed(*args, **kwargs):
        started.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(in_memory_adapter, "execute", delayed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        preview = (await client.post("/api/v1/classrooms/9f1b/modes/arrival/preview")).json()
        command = asyncio.create_task(client.post(
            "/api/v1/classrooms/9f1b/devices/D05/commands",
            json={"commands": [{"type": "devices.capabilities.on_off", "instance": "on", "value": False}]},
        ))
        try:
            await asyncio.wait_for(started.wait(), 2)
            response = await client.post("/api/v1/classrooms/9f1b/runs", json={
                "mode_id": "arrival", "preview_hash": preview["preview_hash"], "ack_warnings": [],
            })
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "run_in_progress"
            release.set()
            assert (await asyncio.wait_for(command, 2)).status_code == 200
        finally:
            release.set()
            await asyncio.gather(command, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_background_run_is_recorded(monkeypatch):
    await engine.init_db()
    started = asyncio.Event()

    async def blocked(run, mode):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(engine, "_execute_steps", blocked)
    preview = await engine.preview("arrival", "9f1b")
    run, _ = await engine.run("arrival", "9f1b", preview_hash=preview.preview_hash, background=True)
    await asyncio.wait_for(started.wait(), 2)
    task = next(iter(engine._tasks))
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    persisted = await run_repository.get_run(run.id)
    assert persisted.status == "failed"
    assert persisted.error_code == "run_interrupted"
    assert not engine._run_lock.locked()
