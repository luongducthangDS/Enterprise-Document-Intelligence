from unittest.mock import MagicMock

import pytest

from src.agents import llm
from src.config import get_settings
from src.services import fpt_client


@pytest.fixture
def gemini(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    return s


def test_models_map_by_role(gemini):
    assert llm.resolve_llm_endpoint()[0] == gemini.gemini_model
    assert llm.resolve_llm_endpoint(model=gemini.router_model)[0] == gemini.gemini_fast_model
    # Judge phải khác model agent (circular evaluation).
    assert llm.resolve_llm_endpoint(model=gemini.judge_model)[0] == gemini.gemini_judge_model
    assert llm.resolve_embedding_endpoint()[0] == gemini.gemini_embedding_model
    model, base, key = llm.resolve_reranker_endpoint()
    assert base == gemini.gemini_base_url and key == "test-key"


def _capture_post(monkeypatch, response_json):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, json=json)
        r = MagicMock()
        r.json.return_value = response_json
        r.raise_for_status.return_value = None
        return r

    monkeypatch.setattr(fpt_client._session, "post", fake_post)
    return sent


def test_chat_payload_uses_gemini_thinking_switch(gemini, monkeypatch):
    sent = _capture_post(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    fpt_client._post_chat_completion(
        [{"role": "user", "content": "x"}], model="gemini-2.5-flash", base_url=gemini.gemini_base_url,
        api_key="k", enable_thinking=False, tools=[{"type": "function"}],
    )
    assert "chat_template_kwargs" not in sent["json"]  # Gemini trả 400 với field lạ
    assert sent["json"]["reasoning_effort"] == "none"
    assert sent["json"]["tools"] == [{"type": "function"}]

    fpt_client._post_chat_completion(
        [{"role": "user", "content": "x"}], model="gemini-2.5-pro", base_url=gemini.gemini_base_url,
        api_key="k", enable_thinking=False,
    )
    assert "reasoning_effort" not in sent["json"]  # pro không tắt được thinking


def test_embedding_sends_dimensions(gemini, monkeypatch):
    sent = _capture_post(monkeypatch, {"data": [{"index": 0, "embedding": [0.1]}]})
    fpt_client.embed_batch(["x"], model="gemini-embedding-001", base_url=gemini.gemini_base_url, api_key="k")
    assert sent["json"]["dimensions"] == gemini.gemini_embedding_dimensions


def test_embedding_without_index_field_keeps_order(gemini, monkeypatch):
    # Gemini OpenAI-compatible trả data không có "index" (lỗi KeyError khi reindex 11/11).
    _capture_post(monkeypatch, {"data": [{"embedding": [1.0]}, {"embedding": [2.0]}]})
    vecs = fpt_client.embed_batch(["a", "b"], model="gemini-embedding-001", base_url=gemini.gemini_base_url, api_key="k")
    assert vecs == [[1.0], [2.0]]


def test_collection_suffix_applies_to_every_access(monkeypatch):
    from src.ingestion.indexer import get_collection

    monkeypatch.setattr(get_settings(), "chroma_collection_suffix", "_gemini")
    client = MagicMock()
    get_collection(client, "accounting_documents")
    assert client.get_or_create_collection.call_args.kwargs["name"] == "accounting_documents_gemini"
