import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_production_requires_explicit_environment_jwt_secret():
    with pytest.raises(ValidationError, match="provided by the production environment"):
        Settings(app_env="production", _env_file=None)



@pytest.mark.parametrize(
    "secret",
    ["", "short", "12345678900aaa", "replace-with-a-long-random-secret"],
)
def test_production_rejects_missing_or_weak_jwt_secret(secret: str):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            app_env="production",
            jwt_secret_key=secret,
            _env_file=None,
        )


def test_production_accepts_strong_environment_jwt_secret():
    settings = Settings(
        app_env="production",
        jwt_secret_key="pilot-secret-with-at-least-32-random-characters",
        _env_file=None,
    )

    assert settings.jwt_secret_key.startswith("pilot-secret")
