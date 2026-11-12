import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# Giá trị fallback trong code — không bao giờ được dùng ở production.
WEAK_JWT_SECRET_DEFAULT = "12345678900aaa"
# ponytail: Render CLI không sửa được env của service có sẵn; chuyển sang AI_AGENT_SERVICE_URL khi tiện.
DEMO_AGENT_SERVICE_URL = "https://p-153-agent-demo.onrender.com/api/v1/agent"


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
    # Bản demo public: bật POST /auth/demo và giới hạn lượt chat để bảo vệ quota model.
    demo_mode: bool = False
    # Mở cổng CREATE_CASE (MVP-2): chỉ scenario registry cho phép CREATE_CASE, không
    # HUMAN_FIRST/Critical, và người hỏi phải bấm xác nhận. Tắt = hành vi MVP-1.
    enable_create_case: bool = False
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
    database_pool_recycle_seconds: int = Field(default=60, ge=10)
    database_pool_pre_ping: bool = True
    database_echo: bool = False
    database_use_transaction_pooler: bool = True

    # ---- JWT Authentication ----
    # Production inject JWT_SECRET_KEY qua secret manager/environment.
    # Development/test dùng secret ngẫu nhiên theo process, không nhúng vào code.
    jwt_secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48), repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ---- External AI Agent REST Service ----
    ai_agent_service_url: str = "http://localhost:8001/api/v1/agent"
    ai_agent_timeout_seconds: float = 120.0
    ai_agent_service_token: str = ""
    ai_agent_max_history_turns: int = Field(default=8, ge=0, le=16)
    # Render free ngủ sau 15 phút; boot agent (import + warmup + provisioning) mất 30-50s,
    # nên ladder 6x5s=30s cũ không phủ hết một lần đánh thức.
    ai_agent_max_cold_retries: int = Field(default=10, ge=1, le=30)
    ai_agent_cold_retry_delay_seconds: float = Field(default=5.0, gt=0, le=30)

    # ---- Cloudinary CDN Storage ----
    cloudinary_cloud_name: str = Field(default="", description="Cloudinary Cloud Name")
    cloudinary_api_key: str = Field(default="", description="Cloudinary API Key")
    cloudinary_api_secret: str = Field(default="", description="Cloudinary API Secret", repr=False)

    @model_validator(mode="after")
    def use_demo_agent(self) -> "Settings":
        if self.demo_mode and self.app_env == "production":
            self.ai_agent_service_url = DEMO_AGENT_SERVICE_URL
        return self

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Chặn khởi động với secret mặc định/yếu khi chạy production.

        .env thật hiện đã dùng secret mạnh, nhưng giá trị fallback trong code
        vẫn tồn tại — một lần deploy quên .env sẽ mở khóa forge token admin.
        Dev/test vẫn chạy được để không cản trở làm việc local.
        """
        if self.app_env == "production":
            if "jwt_secret_key" not in self.model_fields_set:
                raise ValueError("JWT_SECRET_KEY must be provided by the production environment")
            secret = self.jwt_secret_key.strip()
            known_weak = {
                WEAK_JWT_SECRET_DEFAULT,
                "change_this_to_a_secure_random_secret_key_in_production",
                "replace-with-a-long-random-secret",
            }
            if len(secret) < 16 or secret.casefold() in known_weak:
                raise ValueError(
                    "JWT_SECRET_KEY must be a strong environment secret (>= 32 random chars) in production"
                )
            if not self.ai_agent_service_token.strip():
                raise ValueError("AI_AGENT_SERVICE_TOKEN bắt buộc khi chạy production.")
        elif self.jwt_secret_key == WEAK_JWT_SECRET_DEFAULT:
            print("[config] CẢNH BÁO: JWT_SECRET_KEY dùng giá trị mặc định yếu — chỉ chấp nhận cho dev/test.")
        return self

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
