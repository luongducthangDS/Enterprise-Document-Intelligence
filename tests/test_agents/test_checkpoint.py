import asyncio
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from src.agents import checkpoint


class S(TypedDict, total=False):
    query: str
    request_id: str
    tenant_id: str
    user_id: str
    tools_done: bool
    response: str


def _tiny_graph(saver, calls, fail_once):
    async def tools(state):
        calls.append("tools")
        return {"tools_done": True}

    async def generate(state):
        calls.append("generate")
        if fail_once:
            fail_once.pop()
            raise TimeoutError("LLM timeout")
        return {"response": "ok"}

    g = StateGraph(S)
    g.add_node("tools", tools)
    g.add_node("generate", generate)
    g.set_entry_point("tools")
    g.add_edge("tools", "generate")
    g.add_edge("generate", END)
    return g.compile(checkpointer=saver)


async def _scenario(db_path):
    calls, fail_once = [], [True]
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        checkpoint._runner = _tiny_graph(saver, calls, fail_once)
        try:
            req = {"query": "q", "request_id": "r1", "tenant_id": "t", "user_id": "u1"}
            kinds = []

            async def run(initial):
                runner, inp, config, kind = await checkpoint.prepare(initial, default_runner=None)
                kinds.append(kind)
                return await runner.ainvoke(inp, config)

            try:
                await run(req)
            except TimeoutError:
                pass
            after_fail = list(calls)
            second = await run(req)  # retry cùng request_id
            after_resume = list(calls)
            third = await run(req)  # phản hồi lần trước bị mất, backend gọi lại
            other_user = await checkpoint.prepare({**req, "user_id": "u2"}, default_runner=None)
            return after_fail, after_resume, list(calls), kinds, second, third, other_user[3]
        finally:
            checkpoint._runner = None


def test_resume_after_failure_skips_finished_nodes_and_replays_finished_run(tmp_path):
    after_fail, after_resume, final, kinds, second, third, other_kind = asyncio.run(_scenario(tmp_path / "cp.db"))
    assert after_fail == ["tools", "generate"]
    assert after_resume == ["tools", "generate", "generate"]  # tools KHÔNG chạy lại
    assert final == after_resume  # replay không chạy node nào
    assert kinds == ["fresh", "resumed", "replayed"]
    assert second["response"] == third["response"] == "ok"
    assert other_kind == "fresh"  # user khác cùng request_id không thấy thread của u1


def test_disabled_checkpoint_uses_default_runner():
    checkpoint._runner = None
    sentinel = object()
    runner, inp, config, kind = asyncio.run(checkpoint.prepare({"request_id": "r"}, default_runner=sentinel))
    assert runner is sentinel and config is None and kind == "fresh" and inp == {"request_id": "r"}


def test_bad_url_is_rejected():
    import pytest

    async def open_bad():
        async with checkpoint.open_checkpointer("redis://x"):
            pass

    with pytest.raises(ValueError):
        asyncio.run(open_bad())


def test_service_answer_resumes_through_checkpoint(tmp_path, monkeypatch):
    import json

    from src.agents import service
    from src.config import get_settings

    log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(get_settings(), "run_log_path", str(log))

    async def scenario():
        calls, fail_once = [], [True]
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cp.db")) as saver:
            checkpoint._runner = _tiny_graph(saver, calls, fail_once)
            try:
                ident = {"request_id": "r7", "tenant_id": "t", "user_id": "u1"}
                try:
                    await service.answer("q", identity=ident)
                except TimeoutError:
                    pass
                a = await service.answer("q", identity=ident)
                return calls, a
            finally:
                checkpoint._runner = None

    calls, answer = asyncio.run(scenario())
    assert calls == ["tools", "generate", "generate"]
    assert answer.response == "ok"
    kinds = [json.loads(line).get("run_kind") for line in log.read_text(encoding="utf-8").splitlines()]
    assert kinds[-1] == "resumed"


def test_load_memory_reads_previous_request_of_same_user_only(tmp_path):
    class M(TypedDict, total=False):
        query: str
        request_id: str
        tenant_id: str
        user_id: str
        retrieved_chunks: list

    async def retrieve(state):
        return {"retrieved_chunks": [{"chunk_id": "c1", "text": "x"}]}

    async def scenario():
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "m.db")) as saver:
            g = StateGraph(M)
            g.add_node("retrieve", retrieve)
            g.set_entry_point("retrieve")
            g.add_edge("retrieve", END)
            checkpoint._runner = g.compile(checkpointer=saver)
            try:
                first = {"query": "q1", "request_id": "r1", "tenant_id": "t", "user_id": "u1"}
                await checkpoint._runner.ainvoke(first, checkpoint.thread_config(first))
                mine = await checkpoint.load_memory({"request_id": "r2", "previous_request_id": "r1", "tenant_id": "t", "user_id": "u1"})
                other = await checkpoint.load_memory({"request_id": "r9", "previous_request_id": "r1", "tenant_id": "t", "user_id": "u2"})
                none = await checkpoint.load_memory({"request_id": "r2", "tenant_id": "t", "user_id": "u1"})
                return mine, other, none
            finally:
                checkpoint._runner = None

    mine, other, none = asyncio.run(scenario())
    assert [c["chunk_id"] for c in mine] == ["c1"]
    assert other == [] and none == []
