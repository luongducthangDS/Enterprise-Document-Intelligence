from unittest.mock import patch

from src.agents.llm import resolve_llm_endpoint
from src.config import Settings


def test_resolve_llm_endpoint_with_use_glm_on():
    settings = Settings(
        USE_GLM="ON",
        FPT_API_KEY="test-fpt-key",
        FPT_BASE_URL="https://mkp-api.fptcloud.com",
    )
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
    settings = Settings(
        USE_GLM="OFF",
        OPENAI_API_KEY="test-openai-key",
        OPENAI_BASE_URL="https://api.openai.com/v1",
    )
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
