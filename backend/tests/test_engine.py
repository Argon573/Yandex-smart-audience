"""Доменные тесты ClassroomEngine: preview-diff, предусловия, run, идемпотентность."""

from datetime import datetime, timezone

import pytest

from app.device_adapter.dto import DeviceState
from app.device_adapter.in_memory import InMemoryAdapter
from app.mode_engine.engine import ClassroomEngine, compute_preview_hash
from app.mode_engine.exceptions import EngineError, ModeNotFoundError


@pytest.fixture()
def local_engine() -> ClassroomEngine:
    """Изолированный движок на свежем адаптере (без глобального синглтона)."""
    adapter = InMemoryAdapter()
    return ClassroomEngine(adapter)


def _target(device_id: str, state: dict[str, object]) -> DeviceState:
    return DeviceState(
        device_id=device_id,
        state=state,
        updated_at=datetime.now(timezone.utc),
        source="manual",
    )


@pytest.mark.asyncio
async def test_unknown_mode_raises(local_engine: ClassroomEngine) -> None:
    with pytest.raises(ModeNotFoundError) as exc:
        await local_engine.preview("party")
    assert exc.value.mode_id == "party"


@pytest.mark.asyncio
async def test_preview_has_8_steps_and_hash(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("hybrid")
    assert len(preview.steps) == 8
    assert preview.preview_hash == compute_preview_hash(preview.state_version, "hybrid")
    assert preview.can_apply is True
    assert preview.expires_at is not None


@pytest.mark.asyncio
async def test_preview_delta_and_already_in_state(local_engine: ClassroomEngine) -> None:
    # D07 seed open=50, hybrid target open=20 → will_change
    preview = await local_engine.preview("hybrid")
    d07 = next(s for s in preview.steps if s.device_id == "D07")
    assert d07.status == "will_change"
    assert d07.delta == "open: 50 → 20"

    # после apply все skipped
    await local_engine.run(
        "hybrid", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
    )
    preview2 = await local_engine.preview("hybrid")
    assert all(s.status == "already_in_state" for s in preview2.steps)
    assert preview2.summary["will_change"] == 0


@pytest.mark.asyncio
async def test_preview_critical_flags(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("hybrid")
    critical = {s.device_id for s in preview.steps if s.critical}
    assert critical == {"D02", "D03", "D04"}


@pytest.mark.asyncio
async def test_lecture_presence_warning(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("lecture")
    assert any(w.code == "presence_absent" for w in preview.warnings)


@pytest.mark.asyncio
async def test_finish_motion_quiet_warning(local_engine: ClassroomEngine) -> None:
    # seed: not_detected, presence_minutes=0 → тишина < 5 мин → warning
    preview = await local_engine.preview("finish")
    assert any(w.code == "motion_not_quiet" for w in preview.warnings)

    # оператор подтверждает «тихие» 6 минут → warning исчезает
    local_engine._adapter.presence_minutes = 6  # type: ignore[attr-defined]
    preview2 = await local_engine.preview("finish")
    assert not any(w.code == "motion_not_quiet" for w in preview2.warnings)


@pytest.mark.asyncio
async def test_hybrid_read_check_blocks(local_engine: ClassroomEngine) -> None:
    local_engine._adapter.inject_fault("D02", "unavailable")  # type: ignore[attr-defined]
    preview = await local_engine.preview("hybrid")
    assert preview.can_apply is False
    assert "read_check_failed" in preview.blocking_reasons

    with pytest.raises(EngineError) as exc:
        await local_engine.run(
            "hybrid", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
        )
    assert exc.value.code == "precondition_failed"


@pytest.mark.asyncio
async def test_run_applies_steps_and_counters(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("break")
    run, created = await local_engine.run(
        "break", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
    )
    assert created is True
    assert run.status == "applied"
    assert run.counters.error == 0
    assert run.counters.applied >= 1
    assert run.outcome_message
    assert len(run.steps) == 8
    # порядок sequence обязан совпасть со спецификацией §11
    assert [s.sequence for s in run.steps] == list(range(1, 9))


@pytest.mark.asyncio
async def test_run_stale_hash(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("arrival")
    # меняем состояние мимо preview
    await local_engine._adapter.execute(  # type: ignore[attr-defined]
        "D05", _target("D05", {"brightness": 10})
    )
    with pytest.raises(EngineError) as exc:
        await local_engine.run(
            "arrival", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
        )
    assert exc.value.code == "preview_stale"
    assert exc.value.details["expected_preview_hash"] != preview.preview_hash


@pytest.mark.asyncio
async def test_run_idempotency_mismatch(local_engine: ClassroomEngine) -> None:
    key = "k-1"
    p1 = await local_engine.preview("arrival")
    await local_engine.run(
        "arrival", "c1", preview_hash=p1.preview_hash, ack_warnings=[], idempotency_key=key
    )
    with pytest.raises(EngineError) as exc:
        await local_engine.run(
            "break", "c1", preview_hash="whatever", ack_warnings=[], idempotency_key=key
        )
    assert exc.value.code == "idempotency_mismatch"


@pytest.mark.asyncio
async def test_run_idempotent_same_body_returns_existing(
    local_engine: ClassroomEngine,
) -> None:
    key = "k-2"
    p1 = await local_engine.preview("arrival")
    run1, created1 = await local_engine.run(
        "arrival", "c1", preview_hash=p1.preview_hash, ack_warnings=[], idempotency_key=key
    )
    run2, created2 = await local_engine.run(
        "arrival", "c1", preview_hash=p1.preview_hash, ack_warnings=[], idempotency_key=key
    )
    assert created1 is True
    assert created2 is False
    assert run2.id == run1.id


@pytest.mark.asyncio
async def test_run_partial_failure_on_fault(local_engine: ClassroomEngine) -> None:
    """unavailable на D05 (шаг изменится): break без read_check → partial failure."""
    local_engine._adapter.inject_fault("D05", "unavailable")  # type: ignore[attr-defined]
    preview = await local_engine.preview("break")
    assert preview.can_apply is True
    assert any(w.code == "device_unreachable" for w in preview.warnings)

    run, _ = await local_engine.run(
        "break",
        "c1",
        preview_hash=preview.preview_hash,
        ack_warnings=["device_unreachable"],
    )
    assert run.status == "failed"
    assert run.counters.error >= 1
    error_steps = [s for s in run.steps if s.status == "error"]
    assert error_steps[0].device_id == "D05"
    assert error_steps[0].error_code == "device_unavailable"
    # остальные приборы применены (G5 изоляция)
    assert run.counters.applied >= 1


@pytest.mark.asyncio
async def test_run_all_skipped_when_already_in_state(
    local_engine: ClassroomEngine,
) -> None:
    preview = await local_engine.preview("arrival")
    await local_engine.run(
        "arrival", "c1", preview_hash=preview.preview_hash, ack_warnings=[]
    )
    preview2 = await local_engine.preview("arrival")
    run2, _ = await local_engine.run(
        "arrival", "c1", preview_hash=preview2.preview_hash, ack_warnings=[]
    )
    assert run2.status == "applied"
    assert run2.counters.applied == 0
    assert run2.counters.skipped == 8
    assert "целевом состоянии" in (run2.outcome_message or "")


@pytest.mark.asyncio
async def test_get_and_list_runs(local_engine: ClassroomEngine) -> None:
    preview = await local_engine.preview("break")
    run, _ = await local_engine.run(
        "break", "class-a", preview_hash=preview.preview_hash, ack_warnings=[]
    )
    assert local_engine.get_run(run.id) is run
    assert local_engine.get_run("nope") is None
    items, total = local_engine.list_runs(mode_id="break")
    assert total == 1 and items[0].id == run.id
    _, total_other = local_engine.list_runs(mode_id="lecture")
    assert total_other == 0
