"""Группировка шагов режима в волны для параллельного выполнения.

Независимые приборы (свет, жалюзи, климат, аудио) выполняются одновременно
(asyncio.gather). Зависимая пара D03↔D02 (экран и проектор) не параллелится:
идёт в разных волнах с сохранением порядка sequence.
"""

from app.mode_engine.models import ModeStep

#: жёсткая зависимая пара приборов — нельзя выполнять одновременно
DEPENDENT_PAIR: tuple[str, str] = ("D02", "D03")


def build_execution_groups(steps: list[ModeStep]) -> list[list[ModeStep]]:
    """Разбить шаги на волны: внутри волны — gather, между волнами — порядок.

    Правила:
    - каждый прибор не более одного раза на режим (каталог §11);
    - независимые приборы → level 0 (одна параллельная волна);
    - D02 и D03 → уровни 0 и 1 по порядку sequence (кто раньше — тот в волне 0);
    - волны возвращаются по возрастанию level, внутри — по sequence.

    Порядок записи в run.steps определяется sequence (журнал), а не порядком
    выполнения — вызывающий обязан сортировать/предзаполнять шаги по sequence.
    """
    if not steps:
        return []

    ordered = sorted(steps, key=lambda s: s.sequence)
    pair_devices = set(DEPENDENT_PAIR)
    pair_steps = [s for s in ordered if s.device_id in pair_devices]
    # первый по sequence из пары — level 0, второй — level 1
    pair_level = {s.device_id: index for index, s in enumerate(pair_steps)}

    waves: dict[int, list[ModeStep]] = {}
    for step in ordered:
        level = pair_level.get(step.device_id, 0)
        waves.setdefault(level, []).append(step)

    max_level = max(waves)
    return [waves[level] for level in range(max_level + 1)]
