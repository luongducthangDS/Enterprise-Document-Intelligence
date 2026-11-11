"""Một bản ghi cho mỗi lần agent chạy: trajectory, tool + tham số, kết quả,
token theo model, latency, lỗi/retry, chi phí ước tính.

Ghi ra stdout (dòng `[run] {...}`, đọc được bằng log aggregator của Render/Docker)
và, nếu đặt `RUN_LOG_PATH`, thêm vào file JSONL để eval/notebook đọc lại.

Nội dung câu hỏi/câu trả lời mặc định KHÔNG ghi (giữ quyết định của `_log_audit`:
audit trail không được thành nơi chứa PII). `RUN_LOG_CONTENT=true` thì ghi bản đã
che PII bằng `redact_pii`. Khi tắt, tham số tool chỉ giữ tên khóa.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from src.agents.guardrails import redact_pii
from src.config import get_settings

# ponytail: bảng giá tham chiếu USD / 1M token (Gemini API trả phí, tra 11/2026).
# Model không có trong bảng thì cost = None và token đi vào `unpriced_tokens`,
# không đoán. Đổi giá/model thì sửa ở đây.
PRICES_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-embedding-001": (0.15, 0.0),
}

_lock = threading.Lock()


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_pii(value)[0]
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def llm_usage(calls: list[dict]) -> dict:
    by_model: dict[str, dict] = {}
    for c in calls:
        m = by_model.setdefault(c["model"], {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "ms": 0, "retries": 0})
        m["calls"] += 1
        m["prompt_tokens"] += c.get("prompt_tokens") or 0
        m["completion_tokens"] += c.get("completion_tokens") or 0
        m["ms"] += c.get("duration_ms") or 0
        m["retries"] += max((c.get("attempts") or 1) - 1, 0)
    cost, unpriced = 0.0, 0
    for model, m in by_model.items():
        price = PRICES_PER_1M.get(model)
        if price is None:
            unpriced += m["prompt_tokens"] + m["completion_tokens"]
            continue
        cost += m["prompt_tokens"] / 1e6 * price[0] + m["completion_tokens"] / 1e6 * price[1]
    return {
        "chat_calls": sum(1 for c in calls if c.get("kind") == "chat"),
        "prompt_tokens": sum(m["prompt_tokens"] for m in by_model.values()),
        "completion_tokens": sum(m["completion_tokens"] for m in by_model.values()),
        "retries": sum(m["retries"] for m in by_model.values()),
        "by_model": by_model,
        # Chỉ tính phần có giá; unpriced_tokens > 0 nghĩa là cost_usd là cận dưới.
        "cost_usd": round(cost, 6),
        "unpriced_tokens": unpriced,
    }


def build_record(state: dict, calls: list[dict], latency_ms: int, status: str | None, reason_code: str | None) -> dict:
    settings = get_settings()
    content = settings.run_log_content
    steps = []
    for s in state.get("agent_steps") or []:
        args = s.get("args") or {}
        steps.append(
            {
                "tool": s.get("tool"),
                "args": _redact(args) if content else sorted(args),
                "result": _redact(s.get("result")) if content else None,
                "chunk_ids": s.get("chunk_ids") or [],
                "latency_ms": s.get("latency_ms"),
                **({"error": s["error"]} if s.get("error") else {}),
            }
        )
    record = {
        "run_id": state.get("request_id") or uuid.uuid4().hex,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": settings.agent_mode,
        "tenant_id": state.get("tenant_id"),
        "user_id": state.get("user_id"),
        "department": state.get("department"),
        "role": state.get("user_role"),
        "intent": state.get("intent"),
        "status": status,
        "reason_code": reason_code,
        "escalate_reason": state.get("escalate_reason"),
        "trajectory": steps,
        "tool_errors": sum(1 for s in steps if "error" in s),
        "sources": sorted({c.get("source_file") for c in state.get("citations", []) if c.get("source_file")}),
        "latency_ms": latency_ms,
        "llm": llm_usage(calls),
    }
    if content:
        record["input"] = redact_pii(state.get("query") or "")[0]
        record["output"] = redact_pii(state.get("response") or "")[0]
    return record


def write(record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False, default=str)
    print(f"[run] {line}")
    path = get_settings().run_log_path
    if path:
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
