from app.mode_engine.models import Mode, ModeStep

MODES: list[Mode] = [
    Mode(
        id="arrival",
        title="Приход",
        description="Базовый свет и комфортный климат",
        critical_device_ids=["D05", "D06"],
        steps=[ModeStep(sequence=i + 1, device_id="D05") for i in range(7)],
    ),
    Mode(
        id="lecture",
        title="Лекция",
        description="Рабочий свет, проекция для аудитории",
        critical_device_ids=["D02", "D03"],
        steps=[ModeStep(sequence=i + 1, device_id="D05") for i in range(7)],
    ),
    Mode(
        id="hybrid",
        title="Гибридная презентация",
        description="Приглушённый свет, экран и звук включены",
        critical_device_ids=["D02", "D03", "D04"],
        steps=[ModeStep(sequence=i + 1, device_id="D05") for i in range(7)],
    ),
    Mode(
        id="break",
        title="Перерыв",
        description="Безопасный свет, техника презентации приостановлена",
        critical_device_ids=["D05", "D06"],
        steps=[ModeStep(sequence=i + 1, device_id="D05") for i in range(7)],
    ),
    Mode(
        id="finish",
        title="Завершение/энергосбережение",
        description="Свет и медиатехника выключены, климат — экономичный профиль",
        critical_device_ids=[],
        steps=[ModeStep(sequence=i + 1, device_id="D05") for i in range(6)],
    ),
]
