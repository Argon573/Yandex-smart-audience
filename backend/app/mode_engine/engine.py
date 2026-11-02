"""ClassroomEngine: preview (diff + предусловия) и пошаговый run (C-01, C-02).

Побочных эффектов у preview нет. run() применяет шаги последовательно через
ClassroomDeviceAdapter, пишет журнал RunStep, идемпотентен по Idempotency-Key.
Домен не импортирует FastAPI/БД — ошибки возвращаются как ModeNotFoundError/EngineError.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.config import settings
from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import AdapterError, DeviceState
from app.mode_engine.catalog import get_mode
from app.mode_engine.exceptions import EngineError, ModeNotFoundError
from app.mode_engine.models import (
    Counters,
    Mode,
    PreviewResult,
    PreviewWarning,
    Run,
    RunStep,
    RunWarning,
    StepDiff,
)

PREVIEW_TTL_MINUTES = 15


def _fmt(value: object) -> str:
    """Человекочитаемое значение для delta (bool → true/false)."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _delta(before: dict[str, Any], target: dict[str, Any]) -> str | None:
    """«open: 50 → 20, on: false → true» или None, если менять нечего."""
    parts: list[str] = []
    for key, new in target.items():
        old = before.get(key)
        if old != new:
            parts.append(f"{key}: {_fmt(old)} → {_fmt(new)}")
    return ", ".join(parts) if parts else None


def _state_version_sum(states: dict[str, DeviceState]) -> int:
    """Сумма state_version всех приборов — версия состояния аудитории."""
    return sum(s.state_version for s in states.values())


def compute_preview_hash(state_version: int, mode_id: str) -> str:
    """Стабильный hash preview: sha256(version:mode)[:16] (идемпотентен по состоянию)."""
    raw = f"{state_version}:{mode_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


class ClassroomEngine:
    """Движок режимов: каталог → preview → последовательный apply шагов."""

    def __init__(self, adapter: ClassroomDeviceAdapter) -> None:
        self._adapter = adapter
        self._runs: dict[str, Run] = {}
        # Idempotency-Key → (fingerprint тела, run_id)
        self._idempotency: dict[str, tuple[tuple[Any, ...], str]] = {}

    # --- preview (S4) ---

    async def preview(self, mode_id: str) -> PreviewResult:
        """Diff before→target + предусловия. Без команд адаптеру (побочек нет)."""
        mode = self._require_mode(mode_id)
        descriptors = {d.id: d for d in await self._adapter.describe()}
        states = await self._adapter.read()

        steps: list[StepDiff] = []
        blocking: list[str] = []
        warnings: list[PreviewWarning] = []
        presence_absent = False
        motion_quiet_ok: bool | None = None
        read_check_failed = False
        unreachable_devices: list[str] = []

        for step in mode.steps:
            before_state = states.get(step.device_id)
            before = dict(before_state.state) if before_state else {}
            descriptor = descriptors.get(step.device_id)
            diff = StepDiff(
                sequence=step.sequence,
                device_id=step.device_id,
                device_name=descriptor.name if descriptor else step.device_id,
                before=before,
                target=dict(step.target_state),
                critical=step.critical,
            )
            delta = _delta(before, step.target_state)
            if delta is None:
                diff.status = "already_in_state"
                diff.delta = None
            else:
                diff.status = "will_change"
                diff.delta = delta
            steps.append(diff)

            # недоступный прибор не блокирует сам по себе (continue_on_error →
            # partial); блок даёт только предусловие read_check (§11 hybrid)
            if before_state is not None and not before_state.reachable:
                if step.device_id not in unreachable_devices:
                    unreachable_devices.append(step.device_id)

        # предусловия каталога (Часть 3, §11)
        for precondition in mode.preconditions:
            if precondition.kind == "presence_warning":
                motion = (states.get("D11") or DeviceState(
                    device_id="D11", updated_at=datetime.now(timezone.utc)
                )).state.get("motion")
                if motion != "detected":
                    presence_absent = True
            elif precondition.kind == "read_check":
                for device_id in precondition.device_ids:
                    state = states.get(device_id)
                    if state is None or not state.reachable:
                        read_check_failed = True
            elif precondition.kind == "motion_quiet_5min":
                motion = (states.get("D11") or DeviceState(
                    device_id="D11", updated_at=datetime.now(timezone.utc)
                )).state.get("motion")
                presence_minutes = getattr(self._adapter, "presence_minutes", 0)
                # тихо ≥ 5 мин при motion=not_detected → можно без подтверждения
                motion_quiet_ok = motion != "detected" and presence_minutes >= 5

        if read_check_failed and "read_check_failed" not in blocking:
            blocking.append("read_check_failed")

        if unreachable_devices:
            names = ", ".join(unreachable_devices)
            warnings.append(
                PreviewWarning(
                    code="device_unreachable",
                    severity="warning",
                    text=f"Приборы недоступны: {names}. Шаги по ним завершатся ошибкой.",
                )
            )

        if presence_absent:
            warnings.append(
                PreviewWarning(
                    code="presence_absent",
                    severity="warning",
                    text="Датчик присутствия не видит движения. Продолжить?",
                )
            )
        if motion_quiet_ok is False:
            warnings.append(
                PreviewWarning(
                    code="motion_not_quiet",
                    severity="warning",
                    text="Движение в аудитории не прекращалось 5 минут. Продолжить?",
                )
            )

        state_version = _state_version_sum(states)
        now = datetime.now(timezone.utc)
        will_change = sum(1 for s in steps if s.status == "will_change")
        return PreviewResult(
            mode_id=mode_id,
            state_version=state_version,
            preview_hash=compute_preview_hash(state_version, mode_id),
            expires_at=now + timedelta(minutes=PREVIEW_TTL_MINUTES),
            can_apply=not blocking,
            blocking_reasons=blocking,
            warnings=warnings,
            steps=steps,
            summary={
                "will_change": will_change,
                "already_in_state": len(steps) - will_change,
                "critical_total": sum(1 for s in steps if s.critical),
            },
        )

    # --- run / apply (S4→S5) ---

    async def run(
        self,
        mode_id: str,
        classroom_id: str,
        *,
        preview_hash: str,
        ack_warnings: list[str] | None = None,
        idempotency_key: str | None = None,
        requested_by: dict[str, Any] | None = None,
    ) -> tuple[Run, bool]:
        """Подтверждённый запуск. Возвращает (run, created).

        created=False → повтор того же Idempotency-Key (HTTP 200).
        Ошибки валидации → EngineError с кодом §1.2; неизвестный режим → ModeNotFoundError.
        """
        mode = self._require_mode(mode_id)
        ack = set(ack_warnings or [])
        fingerprint = (mode_id, preview_hash, tuple(sorted(ack)))

        # 1) идемпотентность — повтор того же тела → существующий run
        if idempotency_key:
            known = self._idempotency.get(idempotency_key)
            if known is not None:
                stored_fingerprint, run_id = known
                if stored_fingerprint != fingerprint:
                    raise EngineError(
                        "idempotency_mismatch",
                        "Тот же Idempotency-Key уже использован с другим телом запроса.",
                        {"idempotency_key": idempotency_key},
                    )
                return self._runs[run_id], False

        # 2) параллельный запуск (в MVP один — проверка на всякий случай)
        for run in self._runs.values():
            if run.status == "running":
                raise EngineError(
                    "run_in_progress",
                    "У аудитории уже выполняется запуск.",
                    {"run_id": run.id},
                )

        # 3) preview на ЖИВОМ состоянии — hash должен совпасть с присланным
        preview = await self.preview(mode_id)
        if preview.preview_hash != preview_hash:
            raise EngineError(
                "preview_stale",
                "Состояние аудитории изменилось после предпросмотра. Обновите предпросмотр.",
                {
                    "expected_preview_hash": preview.preview_hash,
                    "actual_preview_hash": preview_hash,
                },
            )

        # 4) can_apply=false → precondition_failed (blocking_reasons в details)
        # раньше warnings: нет смысла просить ack, если apply в целом запрещён
        if not preview.can_apply:
            raise EngineError(
                "precondition_failed",
                "Предусловие режима не выполнено и не подтверждено.",
                {"blocking_reasons": preview.blocking_reasons},
            )

        # 5) предупреждения должны быть подтверждены (US-08)
        warning_codes = {w.code for w in preview.warnings}
        missing = sorted(warning_codes - ack)
        if missing:
            raise EngineError(
                "warnings_unacked",
                "Есть предупреждения без подтверждения.",
                {"missing": missing},
            )

        # 6) здоровье адаптера до старта
        health = await self._adapter.health()
        if health.status == "unreachable":
            raise EngineError(
                "adapter_unreachable",
                "Адаптер недоступен, запуск не начат.",
                {"adapter": health.adapter},
            )

        run = await self._execute_steps(
            mode=mode,
            classroom_id=classroom_id,
            preview=preview,
            ack=ack,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
        )

        if idempotency_key:
            self._idempotency[idempotency_key] = (fingerprint, run.id)
        return run, True

    async def _execute_steps(
        self,
        *,
        mode: Mode,
        classroom_id: str,
        preview: PreviewResult,
        ack: set[str],
        idempotency_key: str | None,
        requested_by: dict[str, Any] | None,
    ) -> Run:
        """Пошаговый runner: apply/skip/error, counters, stop_on_critical, итог."""
        now = datetime.now(timezone.utc)
        run = Run(
            id=str(uuid4()),
            mode_id=mode.id,
            classroom_id=classroom_id,
            status="running",
            preview_hash=preview.preview_hash,
            state_version=preview.state_version,
            requested_by=requested_by,
            warnings=[
                RunWarning(code=code, acknowledged=True) for code in sorted(ack)
            ],
            policy=settings.RUN_POLICY,
            idempotency_key=idempotency_key,
            created_at=now,
            started_at=now,
        )

        descriptors = {d.id: d for d in await self._adapter.describe()}
        stop_requested = False

        for spec in mode.steps:
            device_name = (
                descriptors[spec.device_id].name
                if spec.device_id in descriptors
                else spec.device_id
            )
            step = RunStep(
                run_id=run.id,
                sequence=spec.sequence,
                device_id=spec.device_id,
                device_name=device_name,
                target=dict(spec.target_state),
                status="pending",
                started_at=datetime.now(timezone.utc),
            )
            run.steps.append(step)

            if stop_requested:
                step.status = "skipped"
                step.finished_at = datetime.now(timezone.utc)
                step.duration_ms = 0
                continue

            step_started = datetime.now(timezone.utc)
            before_states = await self._adapter.read([spec.device_id])
            before_state = before_states.get(spec.device_id)
            before = dict(before_state.state) if before_state else {}
            step.before = before

            # G2/домен: уже в целевом состоянии → skipped (идемпотентный повтор)
            if spec.target_state and all(
                before.get(k) == v for k, v in spec.target_state.items()
            ):
                step.status = "skipped"
                step.after = before
                step.finished_at = datetime.now(timezone.utc)
                step.duration_ms = _elapsed_ms(step_started)
                continue

            if before_state is not None and not before_state.reachable:
                step.status = "error"
                step.error_code = "device_unavailable"
                step.error_text = f"{device_name}: прибор недоступен."
                step.manual_hint = f"Проверьте питание/связь «{device_name}» и повторите."
                step.finished_at = datetime.now(timezone.utc)
                step.duration_ms = _elapsed_ms(step_started)
                if spec.critical and settings.RUN_POLICY == "stop_on_critical":
                    stop_requested = True
                continue

            result = await self._execute_with_retries(spec.device_id, spec.target_state, step)
            if result is not None:
                step.status = "applied"
                step.after = dict(result)
            # status=error уже выставлен внутри _execute_with_retries

            step.finished_at = datetime.now(timezone.utc)
            step.duration_ms = _elapsed_ms(step_started)

            if step.status == "error" and spec.critical and settings.RUN_POLICY == "stop_on_critical":
                stop_requested = True

        # итог
        counters = Counters(
            applied=sum(1 for s in run.steps if s.status == "applied"),
            skipped=sum(1 for s in run.steps if s.status == "skipped"),
            error=sum(1 for s in run.steps if s.status == "error"),
        )
        run.counters = counters
        finished = datetime.now(timezone.utc)
        run.finished_at = finished
        run.duration_ms = _elapsed_ms(now)
        run.outcome_message = _outcome_message(run, mode)
        first_error = next((s for s in run.steps if s.status == "error"), None)
        run.error_code = first_error.error_code if first_error else None
        run.status = "failed" if counters.error > 0 else "applied"

        states = await self._adapter.read()
        run.state_version = _state_version_sum(states)

        self._runs[run.id] = run
        return run

    async def _execute_with_retries(
        self,
        device_id: str,
        target: dict[str, Any],
        step: RunStep,
    ) -> dict[str, Any] | None:
        """Один шаг: retry при retryable (backoff 200/600 мс), иначе error."""
        attempts = 0
        max_attempts = 1 + max(0, settings.STEP_RETRIES)
        last_error: AdapterError | None = None
        backoffs = [0.2, 0.6]

        while attempts < max_attempts:
            attempts += 1
            step.attempts = attempts
            try:
                result = await self._adapter.execute(
                    device_id,
                    DeviceState(
                        device_id=device_id,
                        state=dict(target),
                        updated_at=datetime.now(timezone.utc),
                        source="mode_run",
                    ),
                    timeout_ms=settings.STEP_TIMEOUT_MS,
                )
                return dict(result.current)
            except AdapterError as exc:
                last_error = exc
                if exc.retryable and attempts < max_attempts:
                    delay = backoffs[min(attempts - 1, len(backoffs) - 1)]
                    # в стендовом моке backoff сокращён, чтобы тесты не спали
                    await asyncio.sleep(min(delay, 0.01))
                    continue
                break

        assert last_error is not None
        step.status = "error"
        step.error_code = last_error.code
        step.error_text = last_error.message
        step.manual_hint = last_error.manual_hint
        return None

    # --- журнал / опрос (C-02) ---

    def get_run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_runs(
        self,
        *,
        classroom_id: str | None = None,
        mode_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Run], int]:
        items = sorted(self._runs.values(), key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if classroom_id is not None:
            items = [r for r in items if r.classroom_id == classroom_id]
        if mode_id is not None:
            items = [r for r in items if r.mode_id == mode_id]
        if status is not None:
            items = [r for r in items if r.status == status]
        total = len(items)
        return items[offset : offset + limit], total

    def clear_runs(self) -> int:
        """Сброс журнала запусков (тесты/симулятор)."""
        count = len(self._runs)
        self._runs.clear()
        self._idempotency.clear()
        return count

    def _reset_all(self) -> None:
        """Полный сброс движка + адаптера (autouse-фикстура в tests)."""
        self.clear_runs()
        reset = getattr(self._adapter, "_reset_all", None)
        if callable(reset):
            reset()

    def _require_mode(self, mode_id: str) -> Mode:
        mode = get_mode(mode_id)
        if mode is None:
            raise ModeNotFoundError(mode_id)
        return mode


def _elapsed_ms(since: datetime) -> int:
    return max(0, int((datetime.now(timezone.utc) - since).total_seconds() * 1000))


def _outcome_message(run: Run, mode: Mode) -> str:
    """Серверное итоговое сообщение (Часть 2, §3.4)."""
    total = len(run.steps)
    applied = run.counters.applied
    error = run.counters.error
    hint = next((s.manual_hint for s in run.steps if s.status == "error" and s.manual_hint), None)

    if error == 0:
        if applied == 0:
            return f"Уже в целевом состоянии: {total} шагов."
        return f"Режим «{mode.title}» применён: {applied} шагов."
    if applied > 0:
        message = f"Применено частично: {applied} из {total} шагов."
        if hint:
            message = f"{message} {hint}"
        return message
    message = f"Не выполнено: {error} ошибок из {total} шагов."
    if hint:
        message = f"{message} {hint}"
    return message
