from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, assistant, auth, control_plane, oauth, operator, provider_api, runs
from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    validation_error_handler,
)
from app.config import settings
from app.observability.middleware import RequestIdMiddleware
from app.observability.routes import router as observability_router

app = FastAPI(title=settings.APP_NAME)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(observability_router)
app.include_router(control_plane.router)
app.include_router(runs.router)
app.include_router(auth.router)
app.include_router(operator.router)
app.include_router(assistant.router)
app.include_router(admin.router)
app.include_router(oauth.router)
app.include_router(provider_api.router)
