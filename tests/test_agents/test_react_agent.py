import asyncio
import json

from src.agents.nodes import react


def _call(name, **args):
    return {"id": name, "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def _chunk(cid, score):
    return {"chunk_id": cid, "text": cid, "title": "T", "source_file": "f", "score": score, "distance": 0.1}


def _run(monkeypatch, replies, search_results=None):
    replies = list(replies)
    seen_queries = []
    llm_messages = []

    def fake_llm(messages, **kw):
        assert kw["tools"] is react.TOOLS
        llm_messages.append(list(messages))
        return replies.pop(0)

    async def fake_search(state, query):
        seen_queries.append(query)
        assert state["user_id"] == "u1"  # danh tính lấy từ state, không từ tool args
        return (search_results or {}).get(query, {"retrieved_chunks": []})

    monkeypatch.setattr(react, "_post_chat_completion", fake_llm)
    monkeypatch.setattr(react, "_search", fake_search)
    state = {"query": "q", "condensed_query": "q", "user_id": "u1"}
    out = asyncio.run(react.react_node(state))
    return out, seen_queries, llm_messages


def test_multi_search_merges_and_dedups_chunks(monkeypatch):
    out, queries, msgs = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("search_policies", query="nghỉ phép"), _call("search_policies", query="thai sản")]},
            {"content": "DONE"},
        ],
        {
            "nghỉ phép": {"retrieved_chunks": [_chunk("a", 0.5), _chunk("b", 0.9)]},
            "thai sản": {"retrieved_chunks": [_chunk("b", 0.9), _chunk("c", 0.7)]},
        },
    )
    assert queries == ["nghỉ phép", "thai sản"]
    assert [c["chunk_id"] for c in out["retrieved_chunks"]] == ["b", "c", "a"]
    assert [m["role"] for m in msgs[1]][-2:] == ["tool", "tool"]  # kết quả tool được trả lại cho model
    assert react.route_after_react(out) == "generate"


def test_escalate_tool_routes_to_ticket(monkeypatch):
    out, _, _ = _run(monkeypatch, [{"tool_calls": [_call("escalate_to_human", kind="personal_data")]}])
    assert out["escalate_reason"] == "personal_data_required"
    assert react.route_after_react(out) == "escalate"


def test_no_tool_call_falls_back_to_single_search(monkeypatch):
    out, queries, _ = _run(
        monkeypatch, [{"content": "DONE"}], {"q": {"retrieved_chunks": [_chunk("a", 0.8)]}}
    )
    assert queries == ["q"]
    assert out["retrieved_chunks"][0]["chunk_id"] == "a"


def test_access_denied_without_chunks(monkeypatch):
    denied = {"retrieved_chunks": [], "access_denied_reason": "DEPARTMENT_SCOPE_DENIED", "denied_department": "ACCOUNTING"}
    out, _, _ = _run(
        monkeypatch,
        [{"tool_calls": [_call("search_policies", query="lương")]}, {"content": "DONE"}],
        {"lương": denied},
    )
    assert react.route_after_react(out) == "access_denied"


def test_graph_modes_compile():
    from src.agents.graph import build_graph

    assert "react" in build_graph("react").get_graph().nodes
    assert "react" not in build_graph("pipeline").get_graph().nodes


def test_missing_evidence_escalate_keeps_found_chunks(monkeypatch):
    out, _, _ = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("search_policies", query="trợ cấp thôi việc")]},
            {"tool_calls": [_call("escalate_to_human", kind="missing_evidence")]},
        ],
        {"trợ cấp thôi việc": {"retrieved_chunks": [_chunk("faq", 0.6)]}},
    )
    assert [c["chunk_id"] for c in out["retrieved_chunks"]] == ["faq"]
    assert react.route_after_react(out) == "generate"


def test_missing_evidence_escalate_without_chunks(monkeypatch):
    out, _, _ = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("search_policies", query="x")]},
            {"tool_calls": [_call("escalate_to_human", kind="missing_evidence")]},
        ],
    )
    assert out["escalate_reason"] == "low_confidence"
    assert react.route_after_react(out) == "escalate"
