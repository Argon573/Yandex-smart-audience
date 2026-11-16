from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings


class TransportSecurityMiddleware(BaseHTTPMiddleware):
    """Reject cleartext requests to APIs carrying credentials or bearer tokens."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        path = request.url.path
        protected = path.startswith(("/oauth/", "/v1.0/", "/api/v1/"))
        if settings.ENFORCE_HTTPS and protected and request.url.scheme != "https":
            if path.startswith("/oauth/"):
                return JSONResponse(
                    status_code=426,
                    content={"error": "https_required"},
                    headers={"Upgrade": "TLS/1.2"},
                )
            return JSONResponse(
                status_code=426,
                content={"detail": "HTTPS is required for this API."},
                headers={"Upgrade": "TLS/1.2"},
            )

        response = await call_next(request)
        if settings.ENFORCE_HTTPS and protected and request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
