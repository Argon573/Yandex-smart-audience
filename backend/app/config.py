from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "local"
    APP_NAME: str = "Smart Classroom Control Plane API"
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    JWT_SECRET: str = "change-me-in-secret-storage"
    ACCESS_TTL: int = 900
    REFRESH_TTL: int = 604800

    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    YANDEX_PROVIDER_BASE_URL: str = "http://localhost:8000/v1.0"

    POLL_INTERVAL_MS: int = 2000
    STEP_TIMEOUT_MS: int = 3000
    STEP_RETRIES: int = 2
    RUN_TIMEOUT_MS: int = 60000
    RUN_POLICY: str = "continue_on_error"

    ALLOWLIST_VERSION: str = "2026-10-27"
    ALLOWLIST_PATH: str = "config/yandex_allowlist.yaml"
    SIMULATOR_SEED: int = 42

    LOG_LEVEL: str = "INFO"


settings = Settings()
