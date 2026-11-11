"""Tool-calling agent (AGENT_MODE=react) thay cho đoạn cố định
knowledge_lookup -> retrieve -> grade -> rewrite của pipeline.

LLM tự quyết gọi tool nào, mấy lần, với query gì (tách câu hỏi nhiều ý, thử
lại bằng từ khóa khác, hoặc chuyển người). Nó KHÔNG viết câu trả lời cuối:
chunk gom được đi tiếp vào generate -> confidence -> hallucination_check ->
finalize như pipeline, nên citation, chống ảo giác và che PII giữ nguyên.

Danh tính/ACL lấy từ state (đã xác thực ở API), không bao giờ từ tham số tool:
model chỉ chọn câu truy vấn, không chọn được mình là ai.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Literal

from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from src.agents import doc_tools
from src.agents.llm import resolve_llm_endpoint, thinking_arg
from src.agents.nodes.knowledge_lookup import knowledge_lookup_node
from src.agents.nodes.retrieval import grade_node, retrieval_node
from src.agents.state import AgentState, RetrievedChunk
from src.agents.tools import LEAVE_JOB_TYPES, REGISTRY, ToolArgsError, openai_tools, parse_call
from src.config import get_settings
from src.services.fpt_client import _post_chat_completion

logger = logging.getLogger(__name__)

# ponytail: hằng số chép từ 07_chinh-sach-nghi-phep.md mục 4.1 (mức nền) và 4.2
# (+1 ngày mỗi 5 năm). Đổi chính sách thì đổi ở đây; tool chỉ chạy khi search
# lấy được đúng file này, nên kết quả luôn kèm nguồn thật.
_LEAVE_POLICY_FILE = "07_chinh-sach-nghi-phep.md"
_LEAVE_BASE = {
    "normal": (12, "công việc bình thường"),
    "heavy_or_hazardous": (14, "công việc nặng nhọc, độc hại, nguy hiểm"),
    "minor_or_disabled": (14, "người dưới 18 tuổi hoặc người khuyết tật"),
    "very_heavy_or_hazardous": (16, "công việc đặc biệt nặng nhọc, độc hại, nguy hiểm"),
}


def annual_leave_days(job_type: str, years_of_service: float) -> tuple[int, str]:
    """Trả (tổng ngày, diễn giải). Dưới 1 năm: Điều 113.2 tính theo tỷ lệ tháng, không tính tự động."""
    base, label = _LEAVE_BASE[job_type]
    if years_of_service < 1:
        raise ValueError("Chưa đủ 12 tháng: số ngày phép tính theo tỷ lệ số tháng làm việc, cần HR xác nhận.")
    extra = int(years_of_service // 5)
    total = base + extra
    return total, (
        f"Mức nền {base} ngày ({label}, mục 4.1) + {extra} ngày thâm niên "
        f"({years_of_service:g} năm, cứ 5 năm thêm 1 ngày, mục 4.2) = {total} ngày phép năm."
    )


TOOLS = openai_tools()
assert set(_LEAVE_BASE) == set(LEAVE_JOB_TYPES), "enum job_type trong registry lệch bảng chính sách"


_SYSTEM = (
    "Bạn là agent tra cứu tài liệu nội bộ doanh nghiệp. Nhiệm vụ: thu thập ĐỦ bằng chứng để trả lời câu hỏi, "
    "bằng cách gọi tool. Không tự trả lời từ kiến thức riêng.\n"
    "- Câu hỏi nhiều ý: gọi search_policies riêng cho từng ý.\n"
    "- Kết quả rỗng/lạc đề: thử lại với từ khóa khác (tối đa 2 lần cho một ý).\n"
    "- Định mức khách sạn/công tác phí: thử lookup_structured_policy trước.\n"
    "- Đoạn trích chưa đủ (cần cả quy trình/bảng): get_document với tên file từ kết quả search.\n"
    "- Hỏi so sánh hai chính sách/quy định: tìm tên file của từng cái rồi compare_documents.\n"
    "- Cần nhiều con số/mốc cụ thể từ một tài liệu (hạn, mức, người duyệt): extract_structured.\n"
    "- Cần dữ liệu cá nhân hoặc tài liệu không có: escalate_to_human.\n"
    "Khi đã đủ bằng chứng, trả lời đúng một chữ: DONE."
)


class PlanStep(BaseModel):
    goal: str = Field(min_length=2, max_length=300)
    tool: str


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=6)
    deliverable: Literal["answer", "comparison_table", "action_checklist"] = "answer"

    def as_prompt(self) -> str:
        lines = [f"{i}. {s.goal} (dự kiến: {s.tool})" for i, s in enumerate(self.steps, 1)]
        return (
            "KẾ HOẠCH (đã lập trước, làm lần lượt; bước độc lập thì gọi tool cùng lượt; "
            "kết quả một bước làm thay đổi bước sau thì điều chỉnh):\n" + "\n".join(lines)
        )


_PLAN_SYSTEM = (
    "Bạn lập kế hoạch cho agent tra cứu tài liệu nội bộ. Tool có: "
    + ", ".join(f"{n} ({t.description[:90]})" for n, t in REGISTRY.items())
    + ". Trả về DUY NHẤT JSON: "
    '{"steps": [{"goal": "<việc cần làm>", "tool": "<tên tool>"}], '
    '"deliverable": "answer" | "comparison_table" | "action_checklist"}. '
    "Câu hỏi một ý: 1 bước. Yêu cầu nhiều việc (tìm, đọc, so sánh, trích, rồi tổng hợp): tách bước theo thứ tự, tối đa 6. "
    "deliverable: comparison_table khi được yêu cầu so sánh; action_checklist khi được yêu cầu danh sách việc cần làm/checklist; "
    "còn lại answer."
)


async def make_plan(question: str, model: str, base_url: str, api_key: str) -> Plan | None:
    """1 lời gọi LLM. Lỗi hoặc JSON sai thì None: agent chạy như không có planner."""
    try:
        msg = await asyncio.to_thread(
            _post_chat_completion,
            [{"role": "system", "content": _PLAN_SYSTEM}, {"role": "user", "content": question}],
            model=model, base_url=base_url, api_key=api_key, temperature=0.0, timeout=30, retries=1,
        )
        m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
        plan = Plan.model_validate_json(m.group(0)) if m else None
    except Exception as e:  # noqa: BLE001
        logger.warning("planner failed, run without plan: %r", e)
        return None
    if plan:
        plan.steps = [s for s in plan.steps if s.tool in REGISTRY] or plan.steps[:1]
    return plan


_STATUS = {
    "plan": "Đã lập kế hoạch: {q}",
    "search_policies": "Đang tìm trong tài liệu: {q}",
    "lookup_structured_policy": "Đang tra bảng định mức: {q}",
    "calculate_annual_leave": "Đang tính số ngày phép năm...",
    "escalate_to_human": "Đang chuẩn bị chuyển yêu cầu cho người phụ trách...",
}


def _emit_status(name: str, query: str) -> None:
    """Phát tiến trình từng tool call ra SSE (custom stream của LangGraph).
    Chỉ là metadata, không chứa nội dung câu trả lời. Ngoài astream (ainvoke,
    test gọi trực tiếp) writer là no-op hoặc không có context: bỏ qua."""
    try:
        get_stream_writer()({"type": "status", "value": _STATUS.get(name, name).format(q=query[:80])})
    except Exception:  # noqa: BLE001
        pass


def _summarize(chunks: list[RetrievedChunk], limit: int = 5) -> str:
    if not chunks:
        return "Không tìm thấy đoạn trích liên quan."
    lines = []
    for c in chunks[:limit]:
        where = c.get("heading_path") or c.get("source_file", "")
        lines.append(f"- [{c.get('title', '')} · {where}] (file: {c.get('source_file', '')}) {c.get('text', '')[:600]}")
    return "\n".join(lines)


async def _guard(name: str, coro):
    return await asyncio.wait_for(coro, REGISTRY[name].timeout_s)


def _tool_error(name: str, e: BaseException) -> str:
    logger.warning("tool %s failed: %r", name, e)
    kind = "quá thời gian" if isinstance(e, asyncio.TimeoutError) else f"lỗi {type(e).__name__}"
    return f"Tool {name} {kind}; thử lại hoặc dùng tool khác."


def _norm(query: str) -> str:
    return " ".join(query.lower().split())


async def _search(state: AgentState, query: str) -> dict:
    retrieved = await retrieval_node({**state, "rewritten_query": query})
    if retrieved.get("access_denied_reason"):
        return retrieved
    return grade_node({**state, **retrieved})


async def _calculate_leave(state: AgentState, args: dict) -> tuple[str, dict | None]:
    try:
        total, explanation = annual_leave_days(str(args.get("job_type")), float(args.get("years_of_service")))
    except (KeyError, TypeError, ValueError) as e:
        return f"Không tính được: {e}", None
    res = await _search(state, "số ngày nghỉ phép năm tiêu chuẩn và ngày tăng thêm theo thâm niên")
    evidence = [c for c in res.get("retrieved_chunks", []) if c.get("source_file") == _LEAVE_POLICY_FILE]
    if not evidence:
        # Không lấy được chính sách (không có quyền / đã gỡ) thì không đưa ra con số.
        return "Không tìm thấy chính sách nghỉ phép để làm căn cứ; không tính.", None
    computed = {
        **evidence[0],
        "chunk_id": f"computed:annual_leave:{args.get('job_type')}:{args.get('years_of_service')}",
        "text": f"Phép tính tất định theo Chính sách Nghỉ phép: {explanation}",
        "heading_path": "4.1–4.2 · phép tính",
        "category": "computed",
        "score": 1.0,
        "distance": 0.0,
        "_evidence": evidence,
    }
    return explanation, computed


async def _tool_get_document(state: AgentState, args: dict, question: str) -> tuple[str, list[RetrievedChunk]]:
    chunks = await doc_tools.get_document(state, args["source_file"])
    if not chunks:
        return doc_tools.NOT_AVAILABLE, []
    # Đưa cả tài liệu cho model đọc, nhưng chỉ mấy mục sát câu hỏi đi tiếp vào generate.
    return doc_tools.doc_text(chunks, 6000), doc_tools.top_sections(chunks, question, k=4)


async def _tool_compare(state: AgentState, args: dict, question: str) -> tuple[str, list[RetrievedChunk]]:
    docs = await asyncio.gather(*(doc_tools.get_document(state, f) for f in args["source_files"]))
    parts, evidence = [], []
    for name, chunks in zip(args["source_files"], docs):
        if not chunks:
            parts.append(f"## {name}\n{doc_tools.NOT_AVAILABLE}")
            continue
        top = doc_tools.top_sections(chunks, args["aspect"], k=2)
        evidence += top
        parts.append(f"## {chunks[0].get('title') or name} (file: {name})\n" + doc_tools.doc_text(top, 2500))
    if not evidence:
        return "Không đọc được tài liệu nào để so sánh.", []
    return f"Các mục liên quan đến '{args['aspect']}':\n\n" + "\n\n".join(parts), evidence


async def _tool_extract(state: AgentState, args: dict, question: str) -> tuple[str, list[RetrievedChunk]]:
    chunks = await doc_tools.get_document(state, args["source_file"])
    if not chunks:
        return doc_tools.NOT_AVAILABLE, []
    data = await doc_tools.extract_structured(chunks, args["fields"])
    grounded = {k: v["value"] for k, v in data.items() if v["grounded"]}
    if not grounded:
        return "Không trích được trường nào có căn cứ trong tài liệu.", []
    quotes = [doc_tools.norm_ws(v["quote"]) for v in data.values() if v["grounded"]]
    evidence = [c for c in chunks if any(q in doc_tools.norm_ws(c.get("text", "")) for q in quotes)] or chunks[:2]
    computed = {
        **evidence[0],
        "chunk_id": f"computed:extract:{args['source_file']}:{','.join(sorted(grounded))}",
        "text": "Dữ liệu trích từ tài liệu (mỗi giá trị có câu trích làm căn cứ): " + json.dumps(data, ensure_ascii=False),
        "category": "computed",
        "score": 1.0,
        "distance": 0.0,
    }
    missing = [k for k, v in data.items() if not v["grounded"]]
    note = f" Không có căn cứ cho: {', '.join(missing)}." if missing else ""
    return json.dumps(grounded, ensure_ascii=False) + note, [computed, *evidence]


_DOC_TOOLS = {"get_document": _tool_get_document, "compare_documents": _tool_compare, "extract_structured": _tool_extract}


async def react_node(state: AgentState) -> dict:
    settings = get_settings()
    question = state.get("condensed_query") or state.get("query", "")
    model, base_url, api_key = resolve_llm_endpoint(model=settings.router_model or None)
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": question}]
    plan = await make_plan(question, model, base_url, api_key) if settings.react_planner else None
    max_steps = settings.react_max_steps
    if plan:
        messages[0]["content"] += "\n\n" + plan.as_prompt()
        # Mỗi bước kế hoạch cần ít nhất 1 lượt tool, +1 lượt để dừng; có trần để không chạy vô hạn.
        max_steps = min(max(max_steps, len(plan.steps) + 1), settings.react_planner_max_steps)
        _emit_status("plan", f"{len(plan.steps)} bước")

    found: dict[str, RetrievedChunk] = {}
    steps: list[dict] = []
    denied: dict = {}
    # ponytail: cache theo query đã chuẩn hoá (lower + gộp khoảng trắng), chỉ sống trong 1 câu hỏi.
    # Query diễn đạt khác nhưng cùng ý vẫn chạy lại; muốn bắt cả loại đó thì so embedding.
    search_cache: dict[str, dict] = {}

    stop = False
    for _ in range(max_steps):
        if stop:
            break
        try:
            msg = await asyncio.to_thread(
                _post_chat_completion,
                messages,
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=0.0,
                timeout=30,
                retries=1,
                enable_thinking=thinking_arg(settings.thinking_router),
                tools=TOOLS,
            )
        except Exception as e:  # noqa: BLE001 — model lỗi thì rơi về 1 lần search như pipeline
            logger.warning("react_node LLM failed, fallback to single search: %s", e)
            break
        calls = msg.get("tool_calls") or []
        if not calls:
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})

        parsed = []
        for call in calls:
            name = call["function"]["name"]
            try:
                _, model_args = parse_call(name, call["function"].get("arguments"))
                args, err = model_args.model_dump(), None
            except ToolArgsError as e:
                args, err = {"raw": call["function"].get("arguments")}, str(e)
            query = str(args.get("query") or question)
            parsed.append((call, name, args, query, err))
            if not err:
                _emit_status(name, query)

        # Các search trong cùng lượt độc lập nhau: chạy song song thay vì lần lượt.
        # Search lỗi/timeout không vào cache, để lượt sau model thử lại được.
        fresh = [k for k in dict.fromkeys(_norm(q) for _, n, _, q, e in parsed if n == "search_policies" and not e) if k not in search_cache]
        fresh_q = {_norm(q): q for _, n, _, q, e in parsed if n == "search_policies" and not e}
        cached_before = set(search_cache)
        failed: dict[str, str] = {}
        results = await asyncio.gather(*(_guard("search_policies", _search(state, fresh_q[k])) for k in fresh), return_exceptions=True)
        for key, res in zip(fresh, results):
            if isinstance(res, BaseException):
                failed[key] = _tool_error("search_policies", res)
            else:
                search_cache[key] = res

        for call, name, args, query, err in parsed:
            chunk_ids: list[str] = []
            t0 = time.perf_counter()
            error = err

            if err:
                result = f"{err}. Gọi lại với tham số đúng schema."
            elif name == "escalate_to_human":
                if args.get("kind") != "personal_data" and found:
                    # Model chỉ thấy bản tóm tắt chunk nên không đủ căn cứ để vứt
                    # bằng chứng đã gom (qa_029: chunk FAQ có đáp án nằm sau đoạn
                    # bị cắt). Dừng gọi tool, để generate + confidence quyết định.
                    steps.append({"tool": name, "args": args, "result": "deferred_to_generate"})
                    stop = True
                    break
                steps.append({"tool": name, "args": args, "result": "escalated"})
                logger.info("react steps=%s", steps)
                reason = "personal_data_required" if args.get("kind") == "personal_data" else "low_confidence"
                return {"agent_steps": steps, "escalate": True, "escalate_reason": reason}
            elif name == "lookup_structured_policy":
                try:
                    res = await _guard(name, knowledge_lookup_node({**state, "condensed_query": query}))
                except Exception as e:  # noqa: BLE001
                    res, error = {}, _tool_error(name, e)
                if res.get("skip_retrieval"):
                    steps.append({"tool": name, "args": args, "result": "resolved"})
                    logger.info("react steps=%s", steps)
                    return {**res, "agent_steps": steps}
                result = error or "Không tra được trong bảng định mức; hãy dùng search_policies."
            elif name == "calculate_annual_leave":
                try:
                    result, computed = await _guard(name, _calculate_leave(state, args))
                except Exception as e:  # noqa: BLE001
                    result, computed = _tool_error(name, e), None
                    error = result
                if computed:
                    found.setdefault(computed["chunk_id"], computed)
                    for c in computed.pop("_evidence"):
                        found.setdefault(c["chunk_id"], c)
            elif name in _DOC_TOOLS:
                try:
                    result, extra = await _guard(name, _DOC_TOOLS[name](state, args, question))
                except Exception as e:  # noqa: BLE001
                    result, extra = _tool_error(name, e), []
                    error = result
                for c in extra:
                    found.setdefault(c["chunk_id"], c)
                chunk_ids = [c["chunk_id"] for c in extra]
            else:  # search_policies
                key = _norm(query)
                res = search_cache.get(key)
                if res is None:
                    result = error = failed.get(key, "search không chạy")
                elif res.get("access_denied_reason"):
                    denied = res
                    result = "Người dùng không có quyền xem tài liệu của phòng ban này."
                elif key in cached_before:
                    result = "Câu truy vấn này đã tìm ở bước trước, kết quả không đổi. Đổi từ khóa, hoặc trả DONE nếu đã đủ."
                else:
                    new = res.get("retrieved_chunks", [])
                    unseen = [c for c in new if c["chunk_id"] not in found]
                    for c in new:
                        found.setdefault(c["chunk_id"], c)
                    result = _summarize(new)
                    if new and not unseen:
                        result = "Không có đoạn trích mới so với các lần tìm trước. Nếu đã đủ bằng chứng, trả DONE.\n" + result
                    chunk_ids = [c["chunk_id"] for c in new]

            step = {"tool": name, "args": args, "result": result[:200], "chunk_ids": chunk_ids, "latency_ms": int((time.perf_counter() - t0) * 1000)}
            if error:
                step["error"] = error
            steps.append(step)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    if not steps:
        # ponytail: model không gọi tool nào (hoặc lỗi) -> hành xử như pipeline: 1 lần search câu gốc.
        res = await _search(state, question)
        if res.get("access_denied_reason"):
            denied = res
        for c in res.get("retrieved_chunks", []):
            found.setdefault(c["chunk_id"], c)
        steps.append({"tool": "search_policies", "args": {"query": question}, "result": "fallback"})

    logger.info("react steps=%s chunks=%d", [(s["tool"], s["args"]) for s in steps], len(found))
    chunks = sorted(found.values(), key=lambda c: -c["score"] if c.get("score") is not None else c.get("distance", 0.0))[: max(settings.rerank_top_k, 8)]
    if not chunks and denied:
        return {**denied, "agent_steps": steps}
    # rewrite_count = max để hallucination retry không quay về vòng rewrite của pipeline.
    out = {"retrieved_chunks": chunks, "agent_steps": steps, "rewrite_count": settings.max_rewrite_retries}
    if plan:
        out |= {"plan": plan.model_dump(), "deliverable": plan.deliverable}
    return out


def route_after_react(state: AgentState) -> str:
    if state.get("skip_retrieval"):
        return "finalize"
    if state.get("escalate"):
        return "escalate"
    if state.get("access_denied_reason") == "DEPARTMENT_SCOPE_DENIED" and not state.get("retrieved_chunks"):
        return "access_denied"
    return "generate"
