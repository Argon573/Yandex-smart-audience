"""RunRepository: сохранение/чтение журнала запусков в SQLite (Часть 2, C-02)."""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mode_engine.models import Counters, Run, RunStep, RunWarning
from app.storage.db import SessionLocal, init_db
from app.storage.models import RunORM, RunStepORM


class RunRepository:
    """CRUD журнала Run/RunStep поверх async SQLAlchemy.

    save_run — вставка при старте (status=running);
    update_run — обновление итога (counters/status/steps) по завершении;
    get_run/list_runs — сборка Pydantic Run из строк БД.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or SessionLocal

    async def init_db(self) -> None:
        """Создание таблиц при старте приложения (lifespan)."""
        await init_db()

    async def save_run(self, run: Run) -> None:
        """Вставить run и все его шаги (идемпотентно по id: replace)."""
        async with self._session_factory() as session:
            await session.execute(delete(RunORM).where(RunORM.id == run.id))
            await session.execute(delete(RunStepORM).where(RunStepORM.run_id == run.id))
            session.add(self._to_orm(run))
            await session.commit()

    async def update_run(self, run: Run) -> None:
        """Обновить статус, counters, итог и шаги существующего run."""
        async with self._session_factory() as session:
            existing = await session.get(RunORM, run.id)
            if existing is None:
                session.add(self._to_orm(run))
                await session.commit()
                return

            self._apply_run_fields(existing, run)
            await session.execute(delete(RunStepORM).where(RunStepORM.run_id == run.id))
            for step in run.steps:
                session.add(self._step_to_orm(run.id, step))
            await session.commit()

    async def get_run(self, run_id: str) -> Run | None:
        """Собрать Run со шагами из БД; None, если не найден."""
        async with self._session_factory() as session:
            row = await session.get(RunORM, run_id)
            if row is None:
                return None
            # форсируем загрузку steps (selectin)
            _ = list(row.steps)
            return self._to_domain(row)

    async def get_by_idempotency_key(self, key: str) -> Run | None:
        """Найти сохранённый запуск для повторного запроса после рестарта."""
        async with self._session_factory() as session:
            query = (
                select(RunORM)
                .where(RunORM.idempotency_key == key)
                .order_by(RunORM.created_at.desc())
                .limit(1)
            )
            row = (await session.execute(query)).scalars().first()
            return self._to_domain(row) if row is not None else None

    async def list_running_runs(self) -> list[Run]:
        """Вернуть запуски, которые процесс не успел завершить."""
        async with self._session_factory() as session:
            query = (
                select(RunORM)
                .where(RunORM.status == "running")
                .order_by(RunORM.created_at)
            )
            rows = (await session.execute(query)).scalars().all()
            return [self._to_domain(row) for row in rows]

    async def list_runs(
        self,
        *,
        classroom_id: str | None = None,
        mode_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Run], int]:
        """Пагинация с фильтрами; возвращает (items, total)."""
        async with self._session_factory() as session:
            query = select(RunORM)
            count_query = select(func.count()).select_from(RunORM)

            if classroom_id is not None:
                query = query.where(RunORM.classroom_id == classroom_id)
                count_query = count_query.where(RunORM.classroom_id == classroom_id)
            if mode_id is not None:
                query = query.where(RunORM.mode_id == mode_id)
                count_query = count_query.where(RunORM.mode_id == mode_id)
            if status is not None:
                query = query.where(RunORM.status == status)
                count_query = count_query.where(RunORM.status == status)

            total = int((await session.execute(count_query)).scalar_one())
            query = (
                query.order_by(RunORM.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(query)).scalars().all()
            return [self._to_domain(row) for row in rows], total

    async def clear_all(self) -> int:
        """Удалить все runs (каскадно steps). Возвращает число удалённых runs."""
        # таблиц может ещё не быть (до первого lifespan) — сначала create_all
        await self.init_db()
        async with self._session_factory() as session:
            result = await session.execute(delete(RunORM))
            await session.commit()
            return int(result.rowcount or 0)

    # --- маппинг ---

    def _to_orm(self, run: Run) -> RunORM:
        row = RunORM(id=run.id)
        self._apply_run_fields(row, run)
        for step in run.steps:
            row.steps.append(self._step_to_orm(run.id, step))
        return row

    @staticmethod
    def _apply_run_fields(row: RunORM, run: Run) -> None:
        row.mode_id = run.mode_id
        row.classroom_id = run.classroom_id
        row.status = run.status
        row.preview_hash = run.preview_hash
        row.state_version = run.state_version
        row.policy = run.policy
        row.error_code = run.error_code
        row.outcome_message = run.outcome_message
        row.counters_applied = run.counters.applied
        row.counters_skipped = run.counters.skipped
        row.counters_error = run.counters.error
        row.idempotency_key = run.idempotency_key
        row.requested_by = dict(run.requested_by) if run.requested_by else None
        row.warnings = [w.model_dump() for w in run.warnings]
        row.created_at = run.created_at
        row.started_at = run.started_at
        row.finished_at = run.finished_at
        row.duration_ms = run.duration_ms

    @staticmethod
    def _step_to_orm(run_id: str, step: RunStep) -> RunStepORM:
        return RunStepORM(
            run_id=run_id,
            sequence=step.sequence,
            device_id=step.device_id,
            device_name=step.device_name,
            target=dict(step.target),
            before=dict(step.before) if step.before is not None else None,
            after=dict(step.after) if step.after is not None else None,
            status=step.status,
            error_code=step.error_code,
            error_text=step.error_text,
            manual_hint=step.manual_hint,
            attempts=step.attempts,
            duration_ms=step.duration_ms,
            started_at=step.started_at,
            finished_at=step.finished_at,
        )

    @staticmethod
    def _to_domain(row: RunORM) -> Run:
        steps = [
            RunStep(
                run_id=s.run_id,
                sequence=s.sequence,
                device_id=s.device_id,
                device_name=s.device_name,
                target=dict(s.target or {}),
                before=dict(s.before) if s.before is not None else None,
                after=dict(s.after) if s.after is not None else None,
                status=s.status,  # type: ignore[arg-type]
                error_code=s.error_code,
                error_text=s.error_text,
                manual_hint=s.manual_hint,
                attempts=s.attempts,
                duration_ms=s.duration_ms,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in sorted(row.steps, key=lambda x: x.sequence)
        ]
        warnings = [RunWarning(**w) for w in (row.warnings or [])]
        requested: dict[str, Any] | None = dict(row.requested_by) if row.requested_by else None
        return Run(
            id=row.id,
            mode_id=row.mode_id,
            classroom_id=row.classroom_id,
            status=row.status,  # type: ignore[arg-type]
            counters=Counters(
                applied=row.counters_applied,
                skipped=row.counters_skipped,
                error=row.counters_error,
            ),
            error_code=row.error_code,
            idempotency_key=row.idempotency_key,
            preview_hash=row.preview_hash,
            state_version=row.state_version,
            requested_by=requested,
            warnings=warnings,
            steps=steps,
            policy=row.policy,
            outcome_message=row.outcome_message,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration_ms=row.duration_ms,
        )
