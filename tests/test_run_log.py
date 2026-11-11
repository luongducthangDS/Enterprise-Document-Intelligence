import asyncio
import json

from src.config import get_settings
from src.observability import run_log

STATE = {
    "request_id": "r1",
    "tenant_id": "nexatech",
    "user_id": "u1",
    "department": "HR",
    "user_role": "EMPLOYEE",
    "query": "Tôi là a@b.com, nghỉ phép mấy ngày?",
    "response": "12 ngày, liên hệ 0912345678",
    "agent_steps": [
        {"tool": "search_policies", "args": {"query": "nghỉ phép a@b.com"}, "result": "- [T] ...", "chunk_ids": ["c1"], "latency_ms": 40},
        {"tool": "calculate_annual_leave", "args": {"raw": "{}"}, "result": "x", "error": "Tham số không hợp lệ", "latency_ms": 0},
    ],
    "citations": [{"source_file": "07_chinh-sach-nghi-phep.md"}],
}
CALLS = [
    {"kind": "chat", "model": "gemini-2.5-flash-lite", "duration_ms": 300, "attempts": 2, "prompt_tokens": 1_000_000, "completion_tokens": 0},
    {"kind": "chat", "model": "gemini-2.5-flash", "duration_ms": 900, "attempts": 1, "prompt_tokens": 0, "completion_tokens": 1_000_000},
    {"kind": "chat", "model": "DeepSeek-V4-Flash", "duration_ms": 100, "attempts": 1, "prompt_tokens": 10, "completion_tokens": 5},
]


def test_default_record_has_no_content(monkeypatch):
    monkeypatch.setattr(get_settings(), "run_log_content", False)
    r = run_log.build_record(STATE, CALLS, 1234, "ANSWERED", None)
    text = json.dumps(r, ensure_ascii=False)
    assert "a@b.com" not in text and "nghỉ phép mấy" not in text and "input" not in r
    assert r["trajectory"][0]["args"] == ["query"]  # chỉ giữ tên khóa
    assert r["tool_errors"] == 1 and r["sources"] == ["07_chinh-sach-nghi-phep.md"]


def test_content_mode_redacts_pii(monkeypatch):
    monkeypatch.setattr(get_settings(), "run_log_content", True)
    r = run_log.build_record(STATE, CALLS, 1234, "ANSWERED", None)
    assert "a@b.com" not in json.dumps(r, ensure_ascii=False)
    assert r["input"].startswith("Tôi là ") and "0912345678" not in r["output"]
    assert r["trajectory"][0]["args"]["query"].startswith("nghỉ phép ")


def test_cost_by_model_and_unpriced_tokens():
    u = run_log.llm_usage(CALLS)
    assert u["cost_usd"] == round(0.10 + 2.50, 6)  # 1M input flash-lite + 1M output flash
    assert u["unpriced_tokens"] == 15 and u["retries"] == 1 and u["chat_calls"] == 3


def test_answer_error_is_logged_then_raised(monkeypatch, tmp_path):
    from src.agents import service

    path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(get_settings(), "run_log_path", str(path))

    async def boom(state):
        raise TimeoutError("tool timeout")

    monkeypatch.setattr(service.agent, "ainvoke", boom)
    try:
        asyncio.run(service.answer("hỏi", identity={"user_id": "u1", "request_id": "r9"}))
    except TimeoutError:
        pass
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["run_id"] == "r9" and rec["status"] == "ERROR" and "tool timeout" in rec["error"]


def test_write_never_raises_on_cp1252_console(monkeypatch, tmp_path):
    import io
    import sys

    cp1252 = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", cp1252)
    path = tmp_path / "r.jsonl"
    monkeypatch.setattr(get_settings(), "run_log_path", str(path))
    run_log.write({"run_id": "x", "input": "thời hạn nộp hồ sơ"})  # không được ném lỗi
    assert json.loads(path.read_text(encoding="utf-8"))["input"] == "thời hạn nộp hồ sơ"


def test_stage_timers_are_not_counted_as_model_calls():
    calls = [
        {"kind": "retrieval_prep", "model": "embed+acl+bm25", "duration_ms": 900},
        {"kind": "embedding", "model": "gemini-embedding-001", "duration_ms": 800, "prompt_tokens": 10},
        {"kind": "vector_search", "model": "chroma_cloud", "duration_ms": 20},
    ]
    assert list(run_log.llm_usage(calls)["by_model"]) == ["gemini-embedding-001"]
