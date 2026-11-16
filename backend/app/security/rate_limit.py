from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque

from fastapi import HTTPException, Request

from app.api.errors import ApiError

_lock = Lock()
_requests: dict[str, Deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    with _lock:
        _requests.clear()


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    max_requests: int,
    window_seconds: int,
    subject: str = "",
    by_ip: bool = True,
) -> None:
    """Process-local sliding-window limit; never trust client-supplied XFF."""
    client_ip = request.client.host if request.client else "unknown"
    key = (
        f"{bucket}:{client_ip}:{subject.casefold()}"
        if by_ip
        else f"{bucket}:{subject.casefold()}"
    )
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        timestamps = _requests[key]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
        else:
            timestamps.append(now)
            retry_after = 0

        # Prevent unbounded growth when many distinct IPs hit the service.
        if len(_requests) > 10_000:
            for old_key in [key for key, values in _requests.items() if not values or values[-1] <= cutoff]:
                _requests.pop(old_key, None)

    if not retry_after:
        return
    headers = {"Retry-After": str(retry_after)}
    if request.url.path.startswith("/oauth/"):
        raise HTTPException(
            status_code=429,
            detail={"error": "slow_down"},
            headers=headers,
        )
    raise ApiError(
        "rate_limited",
        details={"retry_after": retry_after},
        headers=headers,
    )


async def oauth_authorize_get_limit(request: Request) -> None:
    enforce_rate_limit(
        request, bucket="oauth-authorize-get", max_requests=20, window_seconds=60
    )


async def oauth_authorize_post_limit(request: Request) -> None:
    form = await request.form()
    email = str(form.get("email", ""))[:254]
    enforce_rate_limit(
        request,
        bucket="oauth-authorize-post",
        max_requests=5,
        window_seconds=60,
    )
    if email:
        enforce_rate_limit(
            request,
            bucket="oauth-authorize-account",
            max_requests=5,
            window_seconds=60,
            subject=email,
            by_ip=False,
        )


async def oauth_token_limit(request: Request) -> None:
    enforce_rate_limit(request, bucket="oauth-token", max_requests=30, window_seconds=60)


async def oauth_revoke_limit(request: Request) -> None:
    enforce_rate_limit(request, bucket="oauth-revoke", max_requests=30, window_seconds=60)


async def app_login_limit(request: Request) -> None:
    try:
        body = await request.json()
    except ValueError:
        body = {}
    email = str(body.get("email", ""))[:254] if isinstance(body, dict) else ""
    enforce_rate_limit(
        request,
        bucket="app-login",
        max_requests=5,
        window_seconds=60,
    )
    if email:
        enforce_rate_limit(
            request,
            bucket="app-login-account",
            max_requests=5,
            window_seconds=60,
            subject=email,
            by_ip=False,
        )


async def app_refresh_limit(request: Request) -> None:
    enforce_rate_limit(request, bucket="app-refresh", max_requests=20, window_seconds=60)
