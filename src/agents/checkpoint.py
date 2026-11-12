"""Task state bền cho agent: LangGraph checkpointer, bật bằng AGENT_CHECKPOINT_URL.

- `sqlite:///<path>` khi chạy local/test, `postgresql://...` (Supabase) ở production
  (Render free không có đĩa bền nên không dùng sqlite ở đó).
- Mỗi request một thread: `<tenant>:<user>:<request_id>`. Gắn cả danh tính đã
  xác thực vào thread_id để một người không resume được việc của người khác dù
  đoán được request_id.
- Backend retry cùng `request_id` (= chat_request_id):
    * lần trước dừng giữa chừng (LLM/tool lỗi, process chết) -> chạy tiếp từ
      node cuối đã xong, không gọi lại tool/LLM của các node trước;
    * lần trước đã xong nhưng phản hồi mất trên đường về -> trả lại kết quả đã
      lưu, không tốn thêm lời gọi LLM nào.

ponytail: chưa có TTL dọn thread cũ; thêm job xoá checkpoint quá N ngày khi bảng lớn.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

_runner: Any = None  # graph đã compile kèm checkpointer, đặt lúc app khởi động


@asynccontextmanager
async def open_checkpointer(url: str):
    if url.startswith("sqlite:///"):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(url.removeprefix("sqlite:///")) as saver:
            yield saver
    elif url.startswith(("postgres://", "postgresql://")):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(url) as saver:
            await saver.setup()  # tạo bảng checkpoint nếu chưa có, chạy lại an toàn
            yield saver
    else:
        raise ValueError("AGENT_CHECKPOINT_URL phải bắt đầu bằng sqlite:/// hoặc postgresql://")


def install(saver: BaseCheckpointSaver | None) -> None:
    """Gọi trong lifespan của app (và trong test). None = tắt checkpoint."""
    global _runner
    if saver is None:
        _runner = None
        return
    from src.agents.graph import build_graph

    _runner = build_graph(checkpointer=saver)


def thread_config(state: dict) -> dict | None:
    if _runner is None or not state.get("request_id"):
        return None
    thread = f"{state.get('tenant_id', '')}:{state.get('user_id', '')}:{state['request_id']}"
    return {"configurable": {"thread_id": thread}}


async def prepare(initial: dict, default_runner: Any) -> tuple[Any, Any, dict | None, str]:
    """Trả (runner, input, config, kind) với kind = "fresh" | "resumed" | "replayed".

    `input=None` nghĩa là LangGraph chạy tiếp từ checkpoint thay vì bắt đầu lại.
    """
    config = thread_config(initial)
    if config is None:
        return default_runner, initial, None, "fresh"
    snapshot = await _runner.aget_state(config)
    if not snapshot.values:
        return _runner, initial, config, "fresh"
    if snapshot.next:
        return _runner, None, config, "resumed"
    return _runner, None, config, "replayed"


async def load_memory(state: dict) -> list:
    """Chunk của lượt trước (previous_request_id) cùng tenant + user; rỗng nếu không có."""
    prev = state.get("previous_request_id")
    if _runner is None or not prev:
        return []
    config = thread_config({**state, "request_id": prev})
    snapshot = await _runner.aget_state(config)
    return list((snapshot.values or {}).get("retrieved_chunks") or [])
