from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Precondition(BaseModel):
    kind: str
    device_id: str | None = None
    device_ids: list[str] = Field(default_factory=list)
    text: str = ""


class ModeStep(BaseModel):
    sequence: int
    device_id: str
    target_state: dict[str, Any] = Field(default_factory=dict)
    critical: bool = False
    description: str = ""


class Mode(BaseModel):
    id: str
    title: str
    description: str = ""
    preconditions: list[Precondition] = Field(default_factory=list)
    steps: list[ModeStep] = Field(default_factory=list)
    critical_device_ids: list[str] = Field(default_factory=list)
    enabled: bool = True


class Counters(BaseModel):
    applied: int = 0
    skipped: int = 0
    error: int = 0


RunStatus = Literal["running", "applied", "failed"]
StepStatus = Literal["pending", "applied", "skipped", "error"]


class RunStep(BaseModel):
    run_id: str
    sequence: int
    device_id: str
    target: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    status: StepStatus = "pending"
    error_code: str | None = None
    attempts: int = 1
    duration_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Run(BaseModel):
    id: str
    mode_id: str
    classroom_id: str
    status: RunStatus = "running"
    counters: Counters = Field(default_factory=Counters)
    error_code: str | None = None
    idempotency_key: str | None = None
    preview_hash: str = ""
    state_version: int = 0
    requested_by: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    finished_at: datetime | None = None


class StepDiff(BaseModel):
    sequence: int
    device_id: str
    before: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    delta: str | None = None
    status: Literal["will_change", "already_in_state"] = "will_change"
    critical: bool = False


class PreviewWarning(BaseModel):
    code: str
    severity: Literal["warning", "critical"] = "warning"
    text: str = ""


class PreviewResult(BaseModel):
    mode_id: str
    state_version: int = 0
    preview_hash: str = ""
    expires_at: datetime | None = None
    can_apply: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[PreviewWarning] = Field(default_factory=list)
    steps: list[StepDiff] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
