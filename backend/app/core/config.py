from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # ---- PostgreSQL Database ----
    postgres_user: str = "postgres"
    postgres_password: str = "postgres_password"
    postgres_db: str = "hr_ai_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres_password@localhost:5432/hr_ai_db"
    )

    # ---- JWT Authentication ----
    jwt_secret_key: str = (
        "super_secret_jwt_key_change_in_production_123456789"
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ---- External AI Agent REST Service ----
    ai_agent_service_url: str = "http://localhost:8001/api/v1/agent"
    ai_agent_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
