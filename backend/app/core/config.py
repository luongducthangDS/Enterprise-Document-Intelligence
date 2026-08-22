from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App Config ----
    app_name: str = "HR AI Backend Service"
    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    active_tenant: str = Field(default="nexatech", min_length=1, max_length=64)
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # ---- PostgreSQL Database ----
    postgres_user: str = "postgres"
    postgres_password: str = "postgres_password"
    postgres_db: str = "hr_ai_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://postgres:postgres_password@localhost:5432/hr_ai_db"
    database_pool_size: int = Field(default=5, ge=1, le=10)
    database_max_overflow: int = Field(default=0, ge=0, le=10)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    database_pool_recycle_seconds: int = Field(default=300, ge=30)
    database_pool_pre_ping: bool = False
    database_echo: bool = False
    database_use_transaction_pooler: bool = True

    # ---- JWT Authentication ----
    jwt_secret_key: str = "12345678900aaa"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ---- External AI Agent REST Service ----
    ai_agent_service_url: str = "http://localhost:8001/api/v1/agent"
    ai_agent_timeout_seconds: float = 60.0
    ai_agent_service_token: str = ""
    ai_agent_max_history_turns: int = Field(default=8, ge=0, le=16)

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)

        parsed = make_url(url)
        if (
            self.database_use_transaction_pooler
            and parsed.host
            and parsed.host.endswith(".pooler.supabase.com")
            and parsed.port == 5432
        ):
            parsed = parsed.set(port=6543)
        return parsed.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
