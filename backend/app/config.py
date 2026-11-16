from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "local"
    APP_NAME: str = "Smart Classroom Control Plane API"
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    JWT_SECRET: str = "change-me-in-secret-storage"
    ACCESS_TTL: int = 900
    REFRESH_TTL: int = 604800
    APP_DEMO_EMAIL: str = ""
    APP_DEMO_PASSWORD: str = ""
    APP_DEMO_ROLE: str = "operator"
    ENFORCE_HTTPS: bool | None = None

    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    YANDEX_REDIRECT_URIS: str = "https://social.yandex.net/broker/redirect"
    YANDEX_DEMO_EMAIL: str = ""
    YANDEX_DEMO_PASSWORD: str = ""
    YANDEX_PROVIDER_BASE_URL: str = "http://localhost:8000/v1.0"

    POLL_INTERVAL_MS: int = 2000
    STEP_TIMEOUT_MS: int = 3000
    STEP_RETRIES: int = 2
    RUN_TIMEOUT_MS: int = 60000
    RUN_POLICY: str = "continue_on_error"

    ALLOWLIST_VERSION: str = "2026-10-27"
    ALLOWLIST_PATH: str = "config/yandex_allowlist.yaml"
    SIMULATOR_SEED: int = 42

    #: SSE-поток /runs/{id}/events (Server-Sent Events для прогресса S5)
    SSE_ENABLED: bool = True

    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def set_secure_transport_default(self) -> "Settings":
        if self.ENFORCE_HTTPS is None:
            self.ENFORCE_HTTPS = self.APP_ENV.strip().lower() not in {
                "local",
                "test",
                "development",
            }
        return self


settings = Settings()
