import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.api.oauth import authenticate_access_token
from app.device_adapter.dto import AdapterError, DeviceDescriptor, DeviceState
from app.deps import in_memory_adapter
from app.observability.metrics import record_failed_provider_action, record_provider_action
from app.provider.allowlist import is_capability_allowed, is_property_allowed, is_type_allowed
from app.provider.mapping import (
    to_yandex_action_capability,
    to_yandex_device,
    to_yandex_query_state,
)
from app.security.rate_limit import provider_api_limit
from app.storage.db import get_session
from app.storage.models import OAuthGrantORM
router = APIRouter(prefix="/v1.0", tags=["provider"])
CLASSROOM_ID = "9f1b6a2e-0000-4000-8000-000000000001"
_STATE_KEY_ALIASES = {"thermostat": "thermostat_mode"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryDevice(StrictModel):
    id: str
    custom_data: dict[str, Any] = Field(default_factory=dict)


class QueryRequest(StrictModel):
    devices: list[QueryDevice]


class ActionState(StrictModel):
    instance: str
    value: Any


class ActionCapability(StrictModel):
    type: str
    state: ActionState


class ActionDevice(StrictModel):
    id: str
    custom_data: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[ActionCapability] = Field(min_length=1)


class ActionPayload(StrictModel):
    devices: list[ActionDevice]


class ActionRequest(StrictModel):
    payload: ActionPayload


def _request_id(request: Request) -> str:
    return request.state.request_id or request.headers.get("X-Request-Id") or str(uuid.uuid4())


async def _require_request_id(
    x_request_id: str = Header(..., alias="X-Request-Id", min_length=1),
) -> str:
    if not x_request_id.strip():
        raise ApiError(
            "validation_error",
            "X-Request-Id обязателен.",
            {"path": "header.X-Request-Id"},
        )
    return x_request_id


async def _provider_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> OAuthGrantORM:
    return await authenticate_access_token(session, authorization)


async def _descriptors() -> dict[str, DeviceDescriptor]:
    return {device.id: device for device in await in_memory_adapter.describe()}


def _published(descriptor: DeviceDescriptor) -> bool:
    if not descriptor.enabled or not is_type_allowed(descriptor.ya_type):
        return False
    return any(
        is_capability_allowed(spec.type, spec.instance)
        for spec in descriptor.capabilities
    ) or any(
        is_property_allowed(spec.type, spec.instance)
        for spec in descriptor.properties
    )


def _public_descriptor(descriptor: DeviceDescriptor) -> DeviceDescriptor:
    result = descriptor.model_copy(deep=True)
    result.capabilities = [
        spec
        for spec in result.capabilities
        if is_capability_allowed(spec.type, spec.instance)
    ]
    result.properties = [
        spec
        for spec in result.properties
        if is_property_allowed(spec.type, spec.instance)
    ]
    return result


@router.head("/", dependencies=[Depends(provider_api_limit)])
async def check(
    _required_request_id: str = Depends(_require_request_id),
    _identity: OAuthGrantORM = Depends(_provider_identity),
) -> Response:
    return Response(status_code=200)


@router.get("/user/devices", dependencies=[Depends(provider_api_limit)])
async def discovery(
    request: Request,
    _required_request_id: str = Depends(_require_request_id),
    identity: OAuthGrantORM = Depends(_provider_identity),
) -> dict[str, Any]:
    descriptors = await in_memory_adapter.describe()
    devices = []
    for descriptor in descriptors:
        if not _published(descriptor):
            continue
        public_descriptor = _public_descriptor(descriptor)
        devices.append(to_yandex_device(public_descriptor, CLASSROOM_ID))
    return {
        "request_id": _request_id(request),
        "payload": {"user_id": identity.user_id, "devices": devices},
    }


@router.post("/user/devices/query", dependencies=[Depends(provider_api_limit)])
async def query(
    request: Request,
    body: QueryRequest,
    _required_request_id: str = Depends(_require_request_id),
    _identity: OAuthGrantORM = Depends(_provider_identity),
) -> dict[str, Any]:
    descriptors = await _descriptors()
    requested = [device.id for device in body.devices]
    states = await in_memory_adapter.read(requested)
    devices: list[dict[str, Any]] = []
    for device_id in requested:
        descriptor = descriptors.get(device_id)
        if descriptor is None or not _published(descriptor):
            devices.append({"id": device_id, "error_code": "DEVICE_NOT_FOUND"})
            continue
        state = states.get(device_id)
        if state is None:
            devices.append({"id": device_id, "error_code": "DEVICE_UNREACHABLE"})
            continue
        devices.append(to_yandex_query_state(state, _public_descriptor(descriptor)))
    return {"request_id": _request_id(request), "payload": {"devices": devices}}


@router.post("/user/devices/action", dependencies=[Depends(provider_api_limit)])
async def action(
    request: Request,
    body: ActionRequest,
    _required_request_id: str = Depends(_require_request_id),
    _identity: OAuthGrantORM = Depends(_provider_identity),
) -> dict[str, Any]:
    descriptors = await _descriptors()
    results: list[dict[str, Any]] = []
    for requested in body.payload.devices:
        descriptor = descriptors.get(requested.id)
        if descriptor is None or not _published(descriptor):
            results.append(_failed_capabilities(requested, "DEVICE_NOT_FOUND"))
            continue

        state = await in_memory_adapter.read([requested.id])
        if requested.id not in state:
            results.append(_failed_capabilities(requested, "DEVICE_UNREACHABLE"))
            continue

        target: dict[str, Any] = {}
        failure: str | None = None
        for capability in requested.capabilities:
            instance = capability.state.instance
            spec = next(
                (
                    item
                    for item in descriptor.capabilities
                    if item.type == capability.type
                    and item.instance == instance
                    and is_capability_allowed(item.type, item.instance)
                ),
                None,
            )
            if descriptor.managability == "readonly" or spec is None:
                failure = "INVALID_ACTION"
                break
            key = _STATE_KEY_ALIASES.get(instance, instance)
            target[key] = capability.state.value

        if failure:
            results.append(_failed_capabilities(requested, failure))
            continue
        if not target:
            results.append(_failed_capabilities(requested, "INVALID_ACTION"))
            continue

        try:
            result = await in_memory_adapter.execute(
                requested.id,
                DeviceState(
                    device_id=requested.id,
                    state=target,
                    updated_at=state[requested.id].updated_at,
                    source="voice",
                ),
            )
        except AdapterError as exc:
            results.append(_failed_capabilities(requested, _platform_error(exc)))
            continue
        except Exception:
            results.append(_failed_capabilities(requested, "INTERNAL_ERROR"))
            continue

        fresh = (await in_memory_adapter.read([requested.id]))[requested.id]
        _record_voice_action(request, requested.id, target, fresh)
        results.append(
            {
                "id": requested.id,
                "capabilities": [
                    to_yandex_action_capability(
                        capability.type,
                        capability.state.instance,
                        result.current.get(
                            _STATE_KEY_ALIASES.get(capability.state.instance, capability.state.instance),
                            capability.state.value,
                        ),
                        status="DONE",
                        updated_at=fresh.updated_at.isoformat(timespec="milliseconds").replace(
                            "+00:00", "Z"
                        ),
                    )
                    for capability in requested.capabilities
                ],
            }
        )

    return {"request_id": _request_id(request), "payload": {"devices": results}}


def _failed_capabilities(device: ActionDevice, error_code: str) -> dict[str, Any]:
    record_failed_provider_action()
    return {
        "id": device.id,
        "capabilities": [
            to_yandex_action_capability(
                capability.type,
                capability.state.instance,
                capability.state.value,
                status="ERROR",
                error_code=error_code,
            )
            for capability in device.capabilities
        ],
    }


def _platform_error(exc: AdapterError) -> str:
    if exc.code == "device_unavailable":
        return "DEVICE_UNREACHABLE"
    if exc.code == "device_busy":
        return "DEVICE_BUSY"
    if exc.code == "invalid_value":
        return "INVALID_VALUE"
    if exc.code == "readonly_device":
        return "INVALID_ACTION"
    return "INTERNAL_ERROR"


def _record_voice_action(
    request: Request, device_id: str, target: dict[str, Any], state: DeviceState
) -> None:
    history = getattr(request.app.state, "voice_commands", None)
    if history is None:
        history = []
        request.app.state.voice_commands = history
    history.append(
        {
            "ts": state.updated_at.isoformat(),
            "source": "voice",
            "device_id": device_id,
            "state": dict(state.state),
            "command": dict(target),
            "request_id": _request_id(request),
        }
    )
    del history[:-1000]
    record_provider_action()


@router.post("/user/unlink", dependencies=[Depends(provider_api_limit)])
async def unlink(
    request: Request,
    _required_request_id: str = Depends(_require_request_id),
    identity: OAuthGrantORM = Depends(_provider_identity),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await session.execute(
        update(OAuthGrantORM)
        .where(OAuthGrantORM.family_id == identity.family_id)
        .values(revoked=True)
    )
    await session.commit()
    audit = getattr(request.app.state, "oauth_audit_events", [])
    audit.append(
        {
            "event": "linking_revoked",
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id_masked": f"{identity.user_id[:2]}***{identity.user_id[-2:]}"
            if len(identity.user_id) > 3
            else "***",
        }
    )
    request.app.state.oauth_audit_events = audit[-1000:]
    return {"request_id": _request_id(request), "payload": {}}
