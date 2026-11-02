"""Composition root: единые синглтоны адаптера и движка для всего приложения.

Зависимости собираются здесь (Часть 1, §3.1: api → module → domain/ports → storage).
Один InMemoryAdapter на процесс — /room, preview, runs и operator видят одно состояние.
"""

from app.device_adapter.in_memory import in_memory_adapter
from app.mode_engine.engine import ClassroomEngine

engine = ClassroomEngine(in_memory_adapter)

__all__ = ["engine", "in_memory_adapter"]
