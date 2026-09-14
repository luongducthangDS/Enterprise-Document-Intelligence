from unittest.mock import patch

from src.agents.llm import resolve_llm_endpoint
from src.config import Settings


def _settings(**overrides) -> Settings:
    """Settings hermetic cho unit test.

    Phải truyền kwargs theo đúng tên field (chữ thường). Settings đặt
    `extra="ignore"`, nên kwargs viết hoa kiểu `USE_GLM=` bị bỏ qua im lặng và
    test sẽ rơi về giá trị từ `.env`/biến môi trường của máy chạy.
    `_env_file=None` chặn `.env`; mọi field mà `resolve_llm_endpoint` đọc đều
    được set explicit để biến môi trường không đổi được kết quả.
    """
    base = {
        "use_glm": False,
        "llm_provider": "auto",
        "llm_model": "GLM-5.2",
        "router_model": "DeepSeek-V4-Flash",
        "fpt_api_key": "test-fpt-key",
        "fpt_base_url": "https://mkp-api.fptcloud.com",
        "openai_api_key": "test-openai-key",
        "openai_base_url": "https://api.openai.com/v1",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_settings_reject_uppercase_kwargs():
    """Chốt lại nguyên nhân gốc: kwargs viết hoa không set được field."""
    assert _settings().use_glm is False
    assert Settings(_env_file=None, use_glm="ON").use_glm is True


def test_resolve_llm_endpoint_with_use_glm_on():
    settings = _settings(use_glm=True)
    with patch("src.agents.llm.get_settings", return_value=settings):
        # Default model when USE_GLM is ON should be GLM-5.2
        model, base_url, api_key = resolve_llm_endpoint()
        assert model == "GLM-5.2"
        assert base_url == "https://mkp-api.fptcloud.com"
        assert api_key == "test-fpt-key"

        # Router model mapping
        model, base_url, api_key = resolve_llm_endpoint(model="gpt-4o-mini")
        assert model == "DeepSeek-V4-Flash"
        assert base_url == "https://mkp-api.fptcloud.com"


def test_resolve_llm_endpoint_with_use_glm_off():
    settings = _settings(use_glm=False)
    with patch("src.agents.llm.get_settings", return_value=settings):
        # Default model when USE_GLM is OFF should be gpt-4o
        model, base_url, api_key = resolve_llm_endpoint()
        assert model == "gpt-4o"
        assert base_url == "https://api.openai.com/v1"
        assert api_key == "test-openai-key"

        # GLM-5.2 should be mapped to gpt-4o
        model, base_url, api_key = resolve_llm_endpoint(model="GLM-5.2")
        assert model == "gpt-4o"
        assert base_url == "https://api.openai.com/v1"
