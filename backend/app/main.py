"""FastAPI app: CORS, request-id, обработчики ошибок, lifespan (init_db)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, assistant, auth, control_plane, oauth, operator, provider_api, runs
from app.api.errors import (
    ApiError,
    api_error_handler,
    error_responses,
    http_exception_handler,
    validation_error_handler,
)
from app.config import settings
from app.deps import engine
from app.observability.middleware import RequestIdMiddleware
from app.observability.routes import router as observability_router

DESCRIPTION = """
Control Plane API проекта «Умная аудитория» (Smart Classroom).

**Формат ошибок** — один на весь API (Часть 2, §1.1):

```json
{"error": {"code": "preview_stale", "message": "...", "details": {},
           "request_id": "...", "retryable": false}}
```

`request_id` дублируется в заголовке `X-Request-Id`.

**X-Simulate-Error: `<code>`** — заголовок для отладки UI: принудительно
возвращает конверт ошибки с любым кодом реестра (`preview_stale`,
`run_in_progress`, `invalid_value`, `adapter_unreachable`, `device_timeout`,
`not_found`, `unauthorized`, …).

**Idempotency-Key** — заголовок `POST /api/v1/classrooms/{id}/runs`:
повтор с тем же телом → 200 + тот же run, с другим телом → 409
`idempotency_mismatch`.

**SSE** — `GET /api/v1/runs/{runId}/events` в Swagger не отрабатывает
(браузер не показывает поток). Проверка:

```bash
curl -N http://localhost:8000/api/v1/runs/<runId>/events
```
"""

OPENAPI_TAGS = [
    {
        "name": "control-plane",
        "description": (
            "C-01: план аудитории, приборы, каталог режимов, "
            "preview (S4) и ручное управление (S2)."
        ),
    },
    {
        "name": "runs",
        "description": (
            "C-01/C-02: подтверждение запуска (S4→S5), опрос run, "
            "журнал шагов и SSE-поток прогресса."
        ),
    },
    {
        "name": "operator",
        "description": (
            "C-06: инъекция отказов, занятость D11, сброс симулятора, "
            "health адаптера и сводка (S7–S9)."
        ),
    },
    {"name": "auth", "description": "C-07: login/refresh/logout/me (заглушки для MVP)."},
    {"name": "admin", "description": "Управление пользователями (заглушки)."},
    {"name": "assistant", "description": "Связка с Алисой: link, устройства, голосовые команды."},
    {
        "name": "oauth",
        "description": "C-05: авторизационный код Яндекса (authorize/token/revoke).",
    },
    {
        "name": "provider",
        "description": (
            "C-04: Device Adapter для облачного API Яндекса "
            "(/v1.0/user/devices, query, action, unlink)."
        ),
    },
    {"name": "observability", "description": "C-08: /healthz, /readyz, /metrics."},
]

#: Базовый конверт ошибок для всех API-роутеров (описание — в DESCRIPTION).
BASE_ERROR_RESPONSES = error_responses(
    "validation_error", "not_found", "internal_error"
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Старт: создание таблиц журнала runs/run_steps (Task 1, БД)."""
    await engine.init_db()
    await engine.recover_interrupted_runs()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
	"http://199.242.186.36:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(observability_router)
app.include_router(control_plane.router, responses=BASE_ERROR_RESPONSES)
app.include_router(runs.router, responses=BASE_ERROR_RESPONSES)
app.include_router(auth.router, responses=BASE_ERROR_RESPONSES)
app.include_router(operator.router, responses=BASE_ERROR_RESPONSES)
app.include_router(assistant.router, responses=BASE_ERROR_RESPONSES)
app.include_router(admin.router, responses=BASE_ERROR_RESPONSES)
app.include_router(oauth.router, responses=BASE_ERROR_RESPONSES)
app.include_router(provider_api.router, responses=BASE_ERROR_RESPONSES)
