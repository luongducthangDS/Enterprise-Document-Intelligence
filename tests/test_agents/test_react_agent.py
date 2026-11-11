import asyncio
import dataclasses
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


def test_annual_leave_days_matches_policy_table():
    # 07_chinh-sach-nghi-phep.md mục 4.2: bình thường 5-<10 năm = 13, 20+ năm = 16
    assert react.annual_leave_days("normal", 4.9)[0] == 12
    assert react.annual_leave_days("normal", 7)[0] == 13
    assert react.annual_leave_days("normal", 20)[0] == 16
    assert react.annual_leave_days("heavy_or_hazardous", 7)[0] == 15
    assert react.annual_leave_days("very_heavy_or_hazardous", 10)[0] == 18
    import pytest
    with pytest.raises(ValueError):
        react.annual_leave_days("normal", 0.5)


def test_calculator_needs_policy_evidence(monkeypatch):
    policy = {**_chunk("p", 0.8), "source_file": react._LEAVE_POLICY_FILE}
    out, _, _ = _run(
        monkeypatch,
        [{"tool_calls": [_call("calculate_annual_leave", job_type="heavy_or_hazardous", years_of_service=7)]}, {"content": "DONE"}],
        {"số ngày nghỉ phép năm tiêu chuẩn và ngày tăng thêm theo thâm niên": {"retrieved_chunks": [policy]}},
    )
    computed = [c for c in out["retrieved_chunks"] if c["chunk_id"].startswith("computed:")]
    assert len(computed) == 1 and "= 15 ngày" in computed[0]["text"]
    assert any(c["chunk_id"] == "p" for c in out["retrieved_chunks"])  # nguồn thật đi kèm

    # Không lấy được chính sách (vd không có quyền) -> không có con số nào.
    out, _, _ = _run(
        monkeypatch,
        [{"tool_calls": [_call("calculate_annual_leave", job_type="normal", years_of_service=7)]}, {"content": "DONE"}],
    )
    assert not any(c["chunk_id"].startswith("computed:") for c in out.get("retrieved_chunks", []))


def test_repeated_query_hits_cache_and_tells_model(monkeypatch):
    out, queries, msgs = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("search_policies", query="nghỉ phép")]},
            {"tool_calls": [_call("search_policies", query="  Nghỉ  PHÉP ")]},
            {"content": "DONE"},
        ],
        {"nghỉ phép": {"retrieved_chunks": [_chunk("a", 0.5)]}},
    )
    assert queries == ["nghỉ phép"]  # lần 2 trùng (khác hoa/thường, khoảng trắng) không gọi retrieval
    assert "đã tìm ở bước trước" in msgs[2][-1]["content"]
    assert [c["chunk_id"] for c in out["retrieved_chunks"]] == ["a"]


def test_no_new_chunk_is_flagged(monkeypatch):
    _, _, msgs = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("search_policies", query="phép năm")]},
            {"tool_calls": [_call("search_policies", query="nghỉ hằng năm")]},
            {"content": "DONE"},
        ],
        {"phép năm": {"retrieved_chunks": [_chunk("a", 0.5)]}, "nghỉ hằng năm": {"retrieved_chunks": [_chunk("a", 0.5)]}},
    )
    assert msgs[2][-1]["content"].startswith("Không có đoạn trích mới")


def test_same_turn_searches_run_concurrently(monkeypatch):
    running, peak = 0, 0

    async def slow_search(state, query):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return {"retrieved_chunks": [_chunk(query, 0.5)]}

    replies = [
        {"tool_calls": [_call("search_policies", query=q) for q in ("qa", "qb", "qc")]},
        {"content": "DONE"},
    ]
    monkeypatch.setattr(react, "_post_chat_completion", lambda m, **kw: replies.pop(0))
    monkeypatch.setattr(react, "_search", slow_search)
    out = asyncio.run(react.react_node({"query": "q", "condensed_query": "q", "user_id": "u1"}))
    assert peak == 3
    assert {c["chunk_id"] for c in out["retrieved_chunks"]} == {"qa", "qb", "qc"}


def test_invalid_args_go_back_to_model_and_do_not_run(monkeypatch):
    out, queries, msgs = _run(
        monkeypatch,
        [
            {"tool_calls": [_call("calculate_annual_leave", job_type="office", years_of_service=-3)]},
            {"tool_calls": [_call("search_policies", query="nghỉ phép")]},
            {"content": "DONE"},
        ],
        {"nghỉ phép": {"retrieved_chunks": [_chunk("a", 0.5)]}},
    )
    bad = out["agent_steps"][0]
    assert bad["error"].startswith("Tham số calculate_annual_leave không hợp lệ")
    assert "job_type" in bad["error"] and "years_of_service" in bad["error"]
    assert "đúng schema" in msgs[1][-1]["content"]  # model nhận lỗi để sửa
    assert queries == ["nghỉ phép"]


def test_unknown_tool_is_reported(monkeypatch):
    out, _, _ = _run(monkeypatch, [{"tool_calls": [_call("delete_all")]}, {"content": "DONE"}])
    assert "Tool không tồn tại" in out["agent_steps"][0]["error"]


def test_search_timeout_becomes_tool_error_and_is_not_cached(monkeypatch):
    from src.agents import tools

    calls = []

    async def hang_then_ok(state, query):
        calls.append(query)
        if len(calls) == 1:
            await asyncio.sleep(1)
        return {"retrieved_chunks": [_chunk("a", 0.5)]}

    monkeypatch.setitem(tools.REGISTRY, "search_policies", dataclasses.replace(tools.REGISTRY["search_policies"], timeout_s=0.05))
    replies = [
        {"tool_calls": [_call("search_policies", query="nghỉ phép")]},
        {"tool_calls": [_call("search_policies", query="nghỉ phép")]},
        {"content": "DONE"},
    ]
    monkeypatch.setattr(react, "_post_chat_completion", lambda m, **kw: replies.pop(0))
    monkeypatch.setattr(react, "_search", hang_then_ok)
    out = asyncio.run(react.react_node({"query": "q", "condensed_query": "q", "user_id": "u1"}))
    first, second = out["agent_steps"][:2]
    assert "quá thời gian" in first["error"]
    assert "error" not in second and second["chunk_ids"] == ["a"]  # lần 2 chạy lại, không lấy lỗi từ cache


def test_registry_schema_is_what_model_sees():
    from src.agents import tools

    leave = next(t for t in react.TOOLS if t["function"]["name"] == "calculate_annual_leave")["function"]["parameters"]
    assert leave["properties"]["job_type"]["enum"] == list(tools.LEAVE_JOB_TYPES)
    assert "title" not in json.dumps(react.TOOLS)


def _planner_run(monkeypatch, plan_content, n_search_turns):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "react_planner", True)
    monkeypatch.setattr(get_settings(), "react_max_steps", 2)
    seen = []

    def fake_llm(messages, **kw):
        seen.append((messages[0]["content"], kw.get("tools")))
        if kw.get("tools") is None:  # lời gọi planner
            return {"content": plan_content}
        turns = sum(1 for m in messages if m["role"] == "assistant")
        if turns < n_search_turns:
            return {"tool_calls": [_call("search_policies", query=f"bước số {turns}")]}
        return {"content": "DONE"}

    async def fake_search(state, query):
        return {"retrieved_chunks": [_chunk(query, 0.5)]}

    monkeypatch.setattr(react, "_post_chat_completion", fake_llm)
    monkeypatch.setattr(react, "_search", fake_search)
    out = asyncio.run(react.react_node({"query": "q", "condensed_query": "q", "user_id": "u1"}))
    return out, seen


def test_planner_plan_goes_into_prompt_and_extends_step_budget(monkeypatch):
    plan = json.dumps({"steps": [{"goal": f"việc {i}", "tool": "search_policies"} for i in range(4)] + [
        {"goal": "không có tool này", "tool": "send_email"}], "deliverable": "action_checklist"}, ensure_ascii=False)
    out, seen = _planner_run(monkeypatch, plan, n_search_turns=10)
    assert "KẾ HOẠCH" in seen[1][0] and "việc 3" in seen[1][0]
    assert len(out["plan"]["steps"]) == 4  # bước dùng tool lạ bị bỏ
    assert out["deliverable"] == "action_checklist"
    assert len(out["agent_steps"]) == 5  # react_max_steps=2 nhưng kế hoạch 4 bước -> 4+1 lượt


def test_planner_budget_is_capped(monkeypatch):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "react_planner_max_steps", 3)
    plan = json.dumps({"steps": [{"goal": f"việc {i}", "tool": "search_policies"} for i in range(6)]}, ensure_ascii=False)
    out, _ = _planner_run(monkeypatch, plan, n_search_turns=10)
    assert len(out["agent_steps"]) == 3


def test_bad_plan_falls_back_to_plain_react(monkeypatch):
    out, seen = _planner_run(monkeypatch, "không phải JSON", n_search_turns=1)
    assert "plan" not in out and "deliverable" not in out
    assert "KẾ HOẠCH" not in seen[1][0]
    assert [s["tool"] for s in out["agent_steps"]] == ["search_policies"]


def test_every_plan_deliverable_has_a_generate_format():
    import typing

    from src.agents.nodes.generation import _DELIVERABLE_FORMAT

    kinds = set(typing.get_args(react.Plan.model_fields["deliverable"].annotation)) - {"answer"}
    assert kinds == set(_DELIVERABLE_FORMAT)


def test_memory_chunks_seed_evidence_and_skip_fallback_search(monkeypatch):
    seen = []

    def fake_llm(messages, **kw):
        seen.append(messages[0]["content"])
        return {"content": "DONE"}

    async def no_search(state, query):
        raise AssertionError("đã có bằng chứng lượt trước và model trả DONE: không search lại")

    monkeypatch.setattr(react, "_post_chat_completion", fake_llm)
    monkeypatch.setattr(react, "_search", no_search)
    mem = [_chunk("prev1", 0.7), {**_chunk("calc", 1.0), "category": "computed"}]
    state = {"query": "Nếu nộp trễ thì sao?", "condensed_query": "nộp trễ", "user_id": "u1", "memory_chunks": mem}
    out = asyncio.run(react.react_node(state))
    assert "BẰNG CHỨNG ĐÃ CÓ TỪ LƯỢT TRƯỚC" in seen[0] and "prev1" in seen[0]
    assert [c["chunk_id"] for c in out["retrieved_chunks"]] == ["prev1"]  # chunk computed lượt trước không mang sang
    assert out["agent_steps"] == []
