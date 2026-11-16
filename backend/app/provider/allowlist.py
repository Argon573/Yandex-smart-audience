from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings


@lru_cache(maxsize=1)
def load_allowlist(path: str | None = None) -> dict[str, Any]:
    """Загрузка allowlist (C-09). Пустой/битый конфиг — fail fast на старте."""
    allowlist_path = Path(path or settings.ALLOWLIST_PATH)
    if not allowlist_path.exists():
        raise ValueError("config_invalid: allowlist file not found")
    with allowlist_path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not data or not data.get("types"):
        raise ValueError("config_invalid: allowlist is empty")
    return data


def is_type_allowed(ya_type: str) -> bool:
    allowlist = load_allowlist()
    return ya_type in allowlist.get("types", [])


def is_capability_allowed(capability_type: str, instance: str) -> bool:
    section = {
        "devices.capabilities.on_off": "on_off",
        "devices.capabilities.range": "range",
        "devices.capabilities.mode": "mode",
        "devices.capabilities.toggle": "toggle",
    }.get(capability_type)
    return bool(section and instance in load_allowlist().get("capabilities", {}).get(section, {}).get("instances", []))


def is_property_allowed(property_type: str, instance: str) -> bool:
    section = {
        "devices.properties.float": "float",
        "devices.properties.event": "event",
    }.get(property_type)
    return bool(section and instance in load_allowlist().get("properties", {}).get(section, {}).get("instances", []))
