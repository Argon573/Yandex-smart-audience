"""Seed каталога режимов: матрицы из Части 3, §11.

Один ModeStep = один прибор, sequence 1..N уникальны (пары вида
«D05 и D06 в одном пункте матрицы» разворачиваются в два шага подряд).
Датчики D09–D12 шагами не управляются — только читаются как предусловия.
"""

from app.mode_engine.models import Mode, ModeStep, Precondition


def _steps(
    items: list[tuple[str, dict[str, object], str]],
    critical_device_ids: list[str],
) -> list[ModeStep]:
    """Собрать шаги: (device_id, target_state, description) → sequence 1..N."""
    return [
        ModeStep(
            sequence=index + 1,
            device_id=device_id,
            target_state=target,
            critical=device_id in critical_device_ids,
            description=description,
        )
        for index, (device_id, target, description) in enumerate(items)
    ]


def _mode(
    mode_id: str,
    title: str,
    description: str,
    critical_device_ids: list[str],
    items: list[tuple[str, dict[str, object], str]],
    preconditions: list[Precondition] | None = None,
) -> Mode:
    return Mode(
        id=mode_id,
        title=title,
        description=description,
        critical_device_ids=critical_device_ids,
        steps=_steps(items, critical_device_ids),
        preconditions=preconditions or [],
    )


MODES: list[Mode] = [
    _mode(
        "arrival",
        "Приход",
        "Базовый свет и комфортный климат",
        ["D05", "D06"],
        [
            ("D08", {"on": True, "thermostat_mode": "auto", "temperature": 22}, "Климат: auto, 22°C"),
            ("D05", {"on": True, "brightness": 60}, "Свет ряд 1: 60%"),
            ("D06", {"on": True, "brightness": 60}, "Свет ряд 2: 60%"),
            ("D07", {"on": True, "open": 50}, "Жалюзи: 50%"),
            ("D02", {"on": False}, "Проектор: off"),
            ("D03", {"on": False, "open": 0}, "Экран: свернуть"),
            ("D04", {"on": False}, "Аудиосистема: off"),
            ("D01", {"on": False}, "Подсветка доски: off"),
        ],
    ),
    _mode(
        "lecture",
        "Лекция",
        "Рабочий свет, проекция для аудитории",
        ["D02", "D03"],
        [
            ("D07", {"on": True, "open": 50}, "Жалюзи: 50%"),
            ("D05", {"on": True, "brightness": 70}, "Свет ряд 1: 70%"),
            ("D06", {"on": True, "brightness": 70}, "Свет ряд 2: 70%"),
            ("D01", {"on": True, "brightness": 80}, "Подсветка доски: 80%"),
            ("D03", {"on": True, "open": 100}, "Экран: развернуть"),
            ("D02", {"on": True}, "Проектор: on"),
            ("D04", {"on": True, "volume": 40}, "Аудиосистема: volume 40"),
            ("D08", {"on": True, "thermostat_mode": "auto", "temperature": 22}, "Климат: auto, 22°C"),
        ],
        [
            Precondition(
                kind="presence_warning",
                device_id="D11",
                text="В аудитории никого нет — вы подтвердите запуск",
            ),
        ],
    ),
    _mode(
        "hybrid",
        "Гибридная презентация",
        "Приглушённый свет, экран и звук включены",
        ["D02", "D03", "D04"],
        [
            ("D07", {"on": True, "open": 20}, "Жалюзи: 20%"),
            ("D05", {"on": True, "brightness": 40}, "Свет ряд 1: 40%"),
            ("D06", {"on": True, "brightness": 60}, "Свет ряд 2: 60%"),
            ("D01", {"on": True, "brightness": 50}, "Подсветка доски: 50%"),
            ("D03", {"on": True, "open": 100}, "Экран: развернуть"),
            ("D02", {"on": True}, "Проектор: on"),
            ("D04", {"on": True, "volume": 55}, "Аудиосистема: volume 55"),
            ("D08", {"on": True, "thermostat_mode": "auto", "temperature": 22}, "Климат: auto, 22°C"),
        ],
        [
            Precondition(
                kind="read_check",
                device_ids=["D02", "D04"],
                text="Проектор и аудиосистема должны отвечать на чтение",
            ),
        ],
    ),
    _mode(
        "break",
        "Перерыв",
        "Безопасный свет, техника презентации приостановлена",
        ["D05", "D06"],
        [
            ("D02", {"on": False}, "Проектор: off"),
            ("D04", {"on": False}, "Аудиосистема: off"),
            ("D03", {"on": False, "open": 0}, "Экран: свернуть"),
            ("D05", {"on": True, "brightness": 100}, "Свет ряд 1: 100%"),
            ("D06", {"on": True, "brightness": 100}, "Свет ряд 2: 100%"),
            ("D01", {"on": False}, "Подсветка доски: off"),
            ("D07", {"on": True, "open": 50}, "Жалюзи: 50%"),
            ("D08", {"on": True, "thermostat_mode": "auto", "temperature": 23}, "Климат: auto, 23°C"),
        ],
    ),
    _mode(
        "finish",
        "Завершение/энергосбережение",
        "Свет и медиатехника выключены, климат — экономичный профиль",
        [],
        [
            ("D02", {"on": False}, "Проектор: off"),
            ("D03", {"on": False, "open": 0}, "Экран: свернуть"),
            ("D04", {"on": False}, "Аудиосистема: off"),
            ("D01", {"on": False}, "Подсветка доски: off"),
            ("D05", {"on": False}, "Свет ряд 1: off"),
            ("D06", {"on": False}, "Свет ряд 2: off"),
            ("D08", {"on": False}, "Климат: off"),
            ("D07", {"on": False, "open": 0}, "Жалюзи: закрыть"),
        ],
        [
            Precondition(
                kind="motion_quiet_5min",
                device_id="D11",
                text="Нужно 5 минут без движения в аудитории, иначе подтвердите запуск",
            ),
        ],
    ),
]


def get_mode(mode_id: str) -> Mode | None:
    """Найти режим по id; None, если неизвестен (вызывающий маппит в not_found)."""
    return next((m for m in MODES if m.id == mode_id), None)
