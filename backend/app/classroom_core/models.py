from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Zone(BaseModel):
    id: str
    code: str
    name: str
    purpose: str = ""


class Device(BaseModel):
    id: str
    classroom_id: str
    zone_id: str
    display_name: str
    ya_type: str
    managability: Literal["controllable", "readonly"] = "controllable"
    specs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class Classroom(BaseModel):
    id: str
    name: str
    timezone: str = "Europe/Moscow"
    state_version: int = 0
    adapter_health: Literal["ok", "degraded", "unreachable"] = "ok"
    updated_at: datetime | None = None


class Occupancy(BaseModel):
    classroom_id: str
    detected: bool = False
    last_motion_at: datetime | None = None
    presence_minutes: int = 0


class User(BaseModel):
    id: str
    email: str
    display_name: str = ""
    role: Literal["teacher", "operator", "admin"] = "teacher"
    status: Literal["active", "disabled"] = "active"
