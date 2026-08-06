from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.router import _get_router_system, clarify_node, direct_node, router_node
from src.config import get_settings


class TestRouterNode:
    def test_get_router_system_includes_internal_names(self):
        settings = get_settings()
        settings.internal_company_names = ["vingroup", "vinfast"]
        prompt = _get_router_system()
        assert "vingroup, vinfast" in prompt
        assert "VinFast" not in prompt # just to ensure we check what is rendered
    @pytest.mark.asyncio
    async def test_parses_valid_intent_from_llm_output(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")):
            result = await router_node({"query": "Tôi được nghỉ mấy ngày phép?"})
        assert result["intent"] == "hr_question"

    @pytest.mark.asyncio
    async def test_parses_intent_case_insensitively_with_extra_text(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="  Ambiguous.\n")):
            result = await router_node({"query": "Tôi muốn nghỉ"})
        assert result["intent"] == "ambiguous"

    @pytest.mark.asyncio
    async def test_unparseable_output_falls_back_to_hr_question(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="không rõ")):
            result = await router_node({"query": "abc"})
        assert result["intent"] == "hr_question"


class TestDirectNode:
    @pytest.mark.asyncio
    async def test_returns_llm_response_as_response(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="  Chào bạn!  ")):
            result = await direct_node({"query": "Chào bạn"})
        assert result["response"] == "Chào bạn!"


class TestClarifyNode:
    @pytest.mark.asyncio
    async def test_sets_needs_clarification_and_response(self):
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"),
        ):
            result = await clarify_node({"query": "Tôi muốn nghỉ"})
        assert result["needs_clarification"] is True
        assert result["clarifying_question"] == "Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"
        assert result["response"] == result["clarifying_question"]
