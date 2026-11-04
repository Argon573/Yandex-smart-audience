"""Composition root: единые синглтоны адаптера, репозитория и движка.

Зависимости собираются здесь (Часть 1, §3.1: api → module → domain/ports → storage).
Один InMemoryAdapter на процесс — /room, preview, runs и operator видят одно состояние.
"""

from app.device_adapter.in_memory import in_memory_adapter
from app.mode_engine.engine import ClassroomEngine
from app.storage.run_repository import RunRepository

run_repository = RunRepository()
engine = ClassroomEngine(in_memory_adapter, repository=run_repository)

__all__ = ["engine", "in_memory_adapter", "run_repository"]
