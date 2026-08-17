"""Thu thập chi tiết từng lệnh gọi LLM/embedding/rerank trong phạm vi một request.

Chỉ phục vụ profiling — MẶC ĐỊNH TẮT. Khi không ai gọi `capture()`, mọi hàm ở
đây là no-op và không tốn gì ngoài một lần đọc ContextVar.

Vì sao dùng ContextVar chứ không phải biến module: agent chạy async và nhiều
request có thể đan xen nhau trên cùng event loop. Biến module sẽ trộn lệnh gọi
của các request khác nhau vào một rổ, làm sai đúng thứ cần đo là "một request
tốn bao nhiêu".
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_calls: ContextVar[list[dict] | None] = ContextVar("_llm_trace_calls", default=None)


@contextmanager
def capture():
    """Bật thu thập cho đúng khối lệnh bên trong. Trả về list các call đã ghi."""
    collected: list[dict] = []
    token = _calls.set(collected)
    try:
        yield collected
    finally:
        _calls.reset(token)


def is_active() -> bool:
    return _calls.get() is not None


def record(
    kind: str,
    model: str,
    duration_ms: int,
    *,
    usage: dict[str, Any] | None = None,
    enable_thinking: bool | None = None,
    attempts: int = 1,
    started_at: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Ghi một lệnh gọi mạng. No-op nếu không trong phạm vi `capture()`.

    `attempts` > 1 nghĩa là đã phải retry (429/5xx) — cần tách khỏi latency
    thuần của model, nếu không một lần backoff 9s sẽ bị đọc nhầm thành "model
    chậm".
    """
    collected = _calls.get()
    if collected is None:
        return
    usage = usage or {}
    collected.append(
        {
            "kind": kind,
            "model": model,
            # Mốc perf_counter lúc BẮT ĐẦU gọi. Cần để gán từng lệnh gọi vào
            # đúng node phát sinh ra nó: condense/generate/hallucination_check
            # dùng chung một model và cùng thiết lập thinking, nên không thể
            # phân biệt bằng metadata của lệnh gọi — chỉ phân biệt được bằng
            # thời điểm nó xảy ra so với mốc kết thúc của từng node.
            "started_at": started_at,
            "duration_ms": duration_ms,
            "attempts": attempts,
            "enable_thinking": enable_thinking,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            # Gateway FPT gộp reasoning vào completion_tokens và KHÔNG trả
            # trường riêng; giữ chỗ để nếu sau này có thì không phải đổi schema.
            "reasoning_tokens": usage.get("reasoning_tokens"),
            **(extra or {}),
        }
    )


class Timer:
    """Đo một lệnh gọi rồi ghi vào trace. Dùng như context manager."""

    def __init__(self, kind: str, model: str, **fields: Any) -> None:
        self.kind = kind
        self.model = model
        # `enable_thinking` là tham số có tên riêng của record(); mọi field khác
        # (n_documents, n_texts, top_n...) đi vào `extra` để record() không phải
        # biết trước từng loại call có metadata gì.
        self.enable_thinking = fields.pop("enable_thinking", None)
        self.extra = fields
        self.usage: dict[str, Any] | None = None
        self.attempts = 1
        self._t0 = 0.0

    def __enter__(self) -> Timer:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        record(
            self.kind,
            self.model,
            round((time.perf_counter() - self._t0) * 1000),
            usage=self.usage,
            enable_thinking=self.enable_thinking,
            attempts=self.attempts,
            started_at=self._t0,
            extra=self.extra,
        )
