from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CapabilitySpec(BaseModel):
    type: str
    instance: str
    retrievable: bool = True
    parameters: dict[str, Any] | None = None


class PropertySpec(BaseModel):
    type: str
    instance: str
    parameters: dict[str, Any] | None = None


class DeviceDescriptor(BaseModel):
    id: str
    zone_id: str
    name: str
    ya_type: str
    managability: Literal["controllable", "readonly"] = "controllable"
    capabilities: list[CapabilitySpec] = Field(default_factory=list)
    properties: list[PropertySpec] = Field(default_factory=list)
    enabled: bool = True


class DeviceState(BaseModel):
    device_id: str
    state: dict[str, Any] = Field(default_factory=dict)
    reachable: bool = True
    updated_at: datetime
    source: Literal["mode_run", "voice", "manual", "simulator"] = "simulator"
    state_version: int = 0


class Command(BaseModel):
    device_id: str
    target: dict[str, Any]
    idempotency_key: str | None = None


class CommandResult(BaseModel):
    device_id: str
    current: dict[str, Any] = Field(default_factory=dict)
    applied: bool = False
    latency_ms: int = 0
    source: Literal["mode_run", "voice", "manual", "simulator"] = "simulator"


class AdapterInfo(BaseModel):
    adapter: str = "in_memory"
    status: Literal["ok", "degraded", "unreachable"] = "ok"
    checked_at: datetime | None = None
    devices: list[dict[str, Any]] = Field(default_factory=list)


class AdapterError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        device_id: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        manual_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.device_id = device_id
        self.details = details or {}
        self.retryable = retryable
        self.manual_hint = manual_hint


class Fault(BaseModel):
    """Инъекция отказа оператором (Часть 3, §7; Часть 2, §7.1)."""

    id: str
    device_id: str
    kind: Literal["unavailable", "latency", "error"]
    value_ms: int | None = None
    error_code: str | None = None
    expires_at: datetime | None = None
    active: bool = True
    created_at: datetime | None = None
    created_by: str | None = None
    comment: str | None = None
