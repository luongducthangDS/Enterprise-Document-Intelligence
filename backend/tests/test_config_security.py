"""Khóa hành vi security-hardening của backend Settings (TASK-014 / Addendum I).

Ràng buộc:
1. Production đòi hỏi JWT secret đến từ môi trường (không phải default code).
2. Production + JWT secret yếu/mặc định (<32 ký tự hoặc nằm trong known-weak) -> từ chối khởi động.
3. Production + thiếu AI_AGENT_SERVICE_TOKEN -> từ chối khởi động.
4. Dev/test vẫn khởi động được với default (không cản trở làm việc local).
"""

import pytest
from app.core.config import WEAK_JWT_SECRET_DEFAULT, Settings
from pydantic import ValidationError

STRONG_SECRET = "pilot-secret-with-at-least-32-random-characters"


def test_production_requires_explicit_environment_jwt_secret():
    with pytest.raises(ValidationError, match="provided by the production environment"):
        Settings(app_env="production", _env_file=None)


@pytest.mark.parametrize(
    "secret",
    ["", "short", WEAK_JWT_SECRET_DEFAULT, "replace-with-a-long-random-secret"],
)
def test_production_rejects_missing_or_weak_jwt_secret(secret: str):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", jwt_secret_key=secret, _env_file=None)


def test_production_rejects_missing_agent_service_token():
    with pytest.raises(ValidationError, match="AI_AGENT_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            jwt_secret_key=STRONG_SECRET,
            ai_agent_service_token="",
            _env_file=None,
        )


def test_production_accepts_strong_environment_secrets():
    settings = Settings(
        app_env="production",
        jwt_secret_key=STRONG_SECRET,
        ai_agent_service_token="t" * 32,
        _env_file=None,
    )
    assert settings.app_env == "production"


def test_development_tolerates_default_secret():
    settings = Settings(app_env="development", jwt_secret_key=WEAK_JWT_SECRET_DEFAULT, _env_file=None)
    assert settings.jwt_secret_key == WEAK_JWT_SECRET_DEFAULT
