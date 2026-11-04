"""SQLAlchemy ORM-модели журнала запусков (таблицы runs, run_steps)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class RunORM(Base):
    """Строка запуска режима (переживает перезапуск сервера)."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    classroom_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    preview_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    policy: Mapped[str] = mapped_column(String(32), nullable=False, default="continue_on_error")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    counters_applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counters_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counters_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requested_by: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    steps: Mapped[list["RunStepORM"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunStepORM.sequence",
        lazy="selectin",
    )


class RunStepORM(Base):
    """Шаг журнала запуска (C-02)."""

    __tablename__ = "run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[str] = mapped_column(String(16), nullable=False)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[RunORM] = relationship(back_populates="steps")
