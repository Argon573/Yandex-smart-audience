"""ClassroomEngine: preview (diff + предусловия) и пошаговый run (C-01, C-02).

Побочных эффектов у preview нет. run() применяет шаги волнами (параллельно
независимые приборы) через ClassroomDeviceAdapter, пишет журнал RunStep,
переживает перезапуск через RunRepository, идемпотентен по Idempotency-Key.
Домен не импортирует FastAPI — ошибки: ModeNotFoundError / EngineError.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.config import settings
from app.device_adapter.contract import ClassroomDeviceAdapter
from app.device_adapter.dto import AdapterError, DeviceState
from app.mode_engine.catalog import get_mode
from app.mode_engine.exceptions import EngineError, ModeNotFoundError
from app.mode_engine.groups import build_execution_groups
from app.mode_engine.models import (
    Counters,
    Mode,
    ModeStep,
    PreviewResult,
    PreviewWarning,
    Run,
    RunStep,
    RunWarning,
    StepDiff,
)

if TYPE_CHECKING:
    from app.storage.run_repository import RunRepository

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
    """Движок режимов: каталог → preview → волновой apply шагов + persistence."""

    def __init__(
        self,
        adapter: ClassroomDeviceAdapter,
        repository: RunRepository | None = None,
    ) -> None:
        self._adapter = adapter
        self._repository = repository
        self._runs: dict[str, Run] = {}
        # Idempotency-Key → (fingerprint тела, run_id)
        self._idempotency: dict[str, tuple[tuple[Any, ...], str]] = {}
        self._run_lock = asyncio.Lock()
        self._active_run_id: str | None = None
        self._inflight_idempotency: dict[str, tuple[tuple[Any, ...], asyncio.Event]] = {}
        #: SSE: run_id → очереди подписчиков (шаги/итог в реальном времени)
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    async def init_db(self) -> None:
        """Создать таблицы журнала (lifespan при старте). No-op без репозитория."""
        if self._repository is not None:
            await self._repository.init_db()

    async def recover_interrupted_runs(self) -> int:
        """Закрыть запуски, оставшиеся running после остановки процесса."""
        if self._repository is None:
            return 0

        interrupted = await self._repository.list_running_runs()
        now = datetime.now(timezone.utc)
        for run in interrupted:
            for step in run.steps:
                if step.status != "pending":
                    continue
                step.status = "error"
                step.error_code = "run_interrupted"
                step.error_text = "Сервер перезапустился до завершения шага."
                step.manual_hint = "Проверьте состояние приборов и запустите режим заново."
                step.finished_at = now
                step.duration_ms = 0

            run.counters = Counters(
                applied=sum(step.status == "applied" for step in run.steps),
                skipped=sum(step.status == "skipped" for step in run.steps),
                error=sum(step.status == "error" for step in run.steps),
            )
            run.status = "failed"
            run.error_code = "run_interrupted"
            run.outcome_message = "Запуск прерван перезапуском сервера. Проверьте состояние аудитории."
            run.finished_at = now
            if run.started_at is not None:
                started_at = run.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                run.duration_ms = _elapsed_ms(started_at)
            else:
                run.duration_ms = 0

            await self._repository.update_run(run)
            self._runs[run.id] = run
            if run.idempotency_key:
                fingerprint = self._run_fingerprint(
                    run.classroom_id,
                    run.mode_id,
                    run.preview_hash,
                    [warning.code for warning in run.warnings],
                )
                self._idempotency[run.idempotency_key] = (fingerprint, run.id)
        return len(interrupted)

    # --- SSE подписки (C-02, поток /runs/{id}/events) ---

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Подписаться на события run_id; очередь получает _notify-данные."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Отписаться (идемпотентно). Вызывать в finally потока SSE."""
        subscribers = self._subscribers.get(run_id)
        if subscribers is None:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            del self._subscribers[run_id]

    def _notify(self, run_id: str, event: dict[str, Any]) -> None:
        """Разослать event всем подписчикам run_id (неблокирующе)."""
        for queue in self._subscribers.get(run_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

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

    @staticmethod
    def _run_fingerprint(
        classroom_id: str,
        mode_id: str,
        preview_hash: str,
        ack_warnings: list[str] | tuple[str, ...],
    ) -> tuple[Any, ...]:
        return (
            classroom_id,
            mode_id,
            preview_hash,
            tuple(sorted(set(ack_warnings))),
        )

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
        """Защитить запуск от гонок и сохранить семантику повторных запросов."""
        fingerprint = self._run_fingerprint(
            classroom_id, mode_id, preview_hash, ack_warnings or []
        )

        if idempotency_key:
            known = self._idempotency.get(idempotency_key)
            if known is not None:
                if known[0] != fingerprint:
                    raise EngineError(
                        "idempotency_mismatch",
                        "Тот же Idempotency-Key уже использован с другим телом запроса.",
                        {"idempotency_key": idempotency_key},
                    )
                existing_run = self._runs.get(known[1])
                if existing_run is not None:
                    return existing_run, False

            inflight = self._inflight_idempotency.get(idempotency_key)
            if inflight is not None:
                if inflight[0] != fingerprint:
                    raise EngineError(
                        "idempotency_mismatch",
                        "Тот же Idempotency-Key уже использован с другим телом запроса.",
                        {"idempotency_key": idempotency_key},
                    )
                await inflight[1].wait()
                known = self._idempotency.get(idempotency_key)
                if known is not None and known[0] == fingerprint:
                    existing_run = self._runs.get(known[1])
                    if existing_run is not None:
                        return existing_run, False

        if self._run_lock.locked():
            raise EngineError(
                "run_in_progress",
                "У аудитории уже выполняется запуск.",
                {"run_id": self._active_run_id} if self._active_run_id else {},
            )

        await self._run_lock.acquire()
        event: asyncio.Event | None = None
        try:
            # Повторная проверка закрывает окно между первым lookup и захватом lock.
            if idempotency_key:
                known = self._idempotency.get(idempotency_key)
                if known is not None:
                    if known[0] != fingerprint:
                        raise EngineError(
                            "idempotency_mismatch",
                            "Тот же Idempotency-Key уже использован с другим телом запроса.",
                            {"idempotency_key": idempotency_key},
                        )
                    existing_run = self._runs.get(known[1])
                    if existing_run is not None:
                        return existing_run, False
                event = asyncio.Event()
                self._inflight_idempotency[idempotency_key] = (fingerprint, event)

            return await self._run_locked(
                mode_id,
                classroom_id,
                preview_hash=preview_hash,
                ack_warnings=ack_warnings,
                idempotency_key=idempotency_key,
                requested_by=requested_by,
            )
        finally:
            if idempotency_key and event is not None:
                current = self._inflight_idempotency.get(idempotency_key)
                if current is not None and current[1] is event:
                    del self._inflight_idempotency[idempotency_key]
            self._active_run_id = None
            self._run_lock.release()
            if event is not None:
                event.set()

    async def _run_locked(
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
        fingerprint = self._run_fingerprint(
            classroom_id, mode_id, preview_hash, list(ack)
        )

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
                existing_run = self._runs.get(run_id)
                if existing_run is not None:
                    return existing_run, False

            if self._repository is not None:
                existing_run = await self._repository.get_by_idempotency_key(
                    idempotency_key
                )
                if existing_run is not None:
                    stored_fingerprint = self._run_fingerprint(
                        existing_run.classroom_id,
                        existing_run.mode_id,
                        existing_run.preview_hash,
                        [warning.code for warning in existing_run.warnings],
                    )
                    if stored_fingerprint != fingerprint:
                        raise EngineError(
                            "idempotency_mismatch",
                            "Тот же Idempotency-Key уже использован с другим телом запроса.",
                            {"idempotency_key": idempotency_key},
                        )
                    self._runs[existing_run.id] = existing_run
                    self._idempotency[idempotency_key] = (
                        fingerprint,
                        existing_run.id,
                    )
                    return existing_run, False

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
        """Волновой runner: параллельно независимые шаги, журнал по sequence.

        save_run (running) в начале, update_run (итог) в конце — SQLite переживает
        перезапуск. После каждого шага — _notify для SSE.
        """
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
        self._active_run_id = run.id

        descriptors = {d.id: d for d in await self._adapter.describe()}

        # журнал предзаполняется по sequence — порядок не зависит от параллелизма
        step_by_sequence: dict[int, RunStep] = {}
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
                started_at=None,
            )
            run.steps.append(step)
            step_by_sequence[spec.sequence] = step

        self._runs[run.id] = run
        if self._repository is not None:
            await self._repository.save_run(run)

        stop_requested = False
        groups = build_execution_groups(mode.steps)
        loop = asyncio.get_running_loop()
        run_deadline = loop.time() + max(0, settings.RUN_TIMEOUT_MS) / 1000

        for group in groups:
            if stop_requested:
                for spec in group:
                    step = step_by_sequence[spec.sequence]
                    step.status = "skipped"
                    step.finished_at = datetime.now(timezone.utc)
                    step.duration_ms = 0
                    self._notify(
                        run.id,
                        {"type": "step.updated", "step": step.model_dump(mode="json")},
                    )
                self._update_counters(run)
                if self._repository is not None:
                    await self._repository.update_run(run)
                continue

            coroutines = [
                self._execute_single_step(
                    spec,
                    step_by_sequence[spec.sequence],
                )
                for spec in group
            ]
            # return_exceptions: отказ одного прибора не роняет волну (G5)
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*coroutines, return_exceptions=True),
                    timeout=max(0, run_deadline - loop.time()),
                )
            except asyncio.TimeoutError:
                results = []
                stop_requested = True
                for spec in group:
                    step = step_by_sequence[spec.sequence]
                    if step.status != "pending":
                        continue
                    step.status = "error"
                    step.error_code = "device_timeout"
                    step.error_text = "Превышено общее время выполнения режима."
                    step.manual_hint = "Проверьте состояние приборов и повторите запуск."
                    step.finished_at = datetime.now(timezone.utc)
                    if step.started_at is not None:
                        step.duration_ms = _elapsed_ms(step.started_at)
                    else:
                        step.duration_ms = 0
                    self._notify(
                        run.id,
                        {"type": "step.updated", "step": step.model_dump(mode="json")},
                    )

            # Не оставлять шаг pending, если корутина завершилась нештатно
            # вне обработчика _execute_single_step (например, была отменена).
            for spec, result in zip(group, results):
                if isinstance(result, BaseException):
                    step = step_by_sequence[spec.sequence]
                    step.status = "error"
                    step.error_code = "internal_error"
                    step.error_text = (
                        f"Внутренняя ошибка выполнения шага ({type(result).__name__})."
                    )
                    step.manual_hint = "Проверьте журнал сервера и состояние прибора."
                    step.finished_at = datetime.now(timezone.utc)
                    if step.started_at is not None:
                        step.duration_ms = _elapsed_ms(step.started_at)
                    self._notify(
                        run.id,
                        {"type": "step.updated", "step": step.model_dump(mode="json")},
                    )

            for spec in group:
                step = step_by_sequence[spec.sequence]
                if (
                    step.status == "error"
                    and spec.critical
                    and settings.RUN_POLICY == "stop_on_critical"
                ):
                    stop_requested = True

            self._update_counters(run)
            if self._repository is not None:
                await self._repository.update_run(run)

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
        if self._repository is not None:
            await self._repository.update_run(run)

        self._notify(
            run.id,
            {"type": "run.finished", "run": run.model_dump(mode="json")},
        )
        return run

    @staticmethod
    def _update_counters(run: Run) -> None:
        run.counters = Counters(
            applied=sum(step.status == "applied" for step in run.steps),
            skipped=sum(step.status == "skipped" for step in run.steps),
            error=sum(step.status == "error" for step in run.steps),
        )

    async def _execute_single_step(
        self,
        spec: ModeStep,
        step: RunStep,
    ) -> RunStep:
        """Выполнить один шаг (read → skip/error/apply). Мутирует step, шлёт SSE."""
        step.started_at = datetime.now(timezone.utc)
        step_started = step.started_at

        try:
            before_states = await self._adapter.read([spec.device_id])
            before_state = before_states.get(spec.device_id)
            before = dict(before_state.state) if before_state else {}
            step.before = before

            # G2/домен: уже в целевом состоянии → skipped
            if spec.target_state and all(
                before.get(k) == v for k, v in spec.target_state.items()
            ):
                step.status = "skipped"
                step.after = before
                step.finished_at = datetime.now(timezone.utc)
                step.duration_ms = _elapsed_ms(step_started)
                return step

            if before_state is not None and not before_state.reachable:
                step.status = "error"
                step.error_code = "device_unavailable"
                step.error_text = f"{step.device_name}: прибор недоступен."
                step.manual_hint = (
                    f"Проверьте питание/связь «{step.device_name}» и повторите."
                )
                step.finished_at = datetime.now(timezone.utc)
                step.duration_ms = _elapsed_ms(step_started)
                return step

            result = await self._execute_with_retries(
                spec.device_id, spec.target_state, step
            )
            if result is not None:
                step.status = "applied"
                step.after = dict(result)
            # status=error уже выставлен внутри _execute_with_retries

            step.finished_at = datetime.now(timezone.utc)
            step.duration_ms = _elapsed_ms(step_started)
            return step
        except AdapterError as exc:
            step.status = "error"
            step.error_code = exc.code
            step.error_text = exc.message
            step.manual_hint = exc.manual_hint
            step.finished_at = datetime.now(timezone.utc)
            step.duration_ms = _elapsed_ms(step_started)
            return step
        except Exception as exc:
            step.status = "error"
            step.error_code = "internal_error"
            step.error_text = (
                f"Внутренняя ошибка выполнения шага ({type(exc).__name__})."
            )
            step.manual_hint = "Проверьте журнал сервера и состояние прибора."
            step.finished_at = datetime.now(timezone.utc)
            step.duration_ms = _elapsed_ms(step_started)
            return step
        finally:
            self._notify(
                step.run_id,
                {"type": "step.updated", "step": step.model_dump(mode="json")},
            )

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
        """Сброс журнала в памяти (тесты/симулятор). DB чистит run_repository."""
        count = len(self._runs)
        self._runs.clear()
        self._idempotency.clear()
        self._subscribers.clear()
        return count

    async def aclear_runs(self) -> int:
        """Сброс журнала: память + SQLite. Возвращает число удалённых runs."""
        count = self.clear_runs()
        if self._repository is not None:
            await self._repository.clear_all()
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
