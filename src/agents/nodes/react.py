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

from langgraph.config import get_stream_writer

from src.agents.llm import resolve_llm_endpoint, thinking_arg
from src.agents.nodes.knowledge_lookup import knowledge_lookup_node
from src.agents.nodes.retrieval import grade_node, retrieval_node
from src.agents.state import AgentState, RetrievedChunk
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


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": (
                "Tìm đoạn trích trong kho tài liệu nội bộ (HR, Kế toán, Sản phẩm) mà người dùng được phép xem. "
                "Gọi nhiều lần với query khác nhau nếu câu hỏi có nhiều ý hoặc lần đầu không thấy kết quả."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Câu truy vấn tiếng Việt, cụ thể"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_structured_policy",
            "description": (
                "Tra bảng định mức có cấu trúc (hiện có: định mức khách sạn/công tác phí theo địa điểm và chức danh). "
                "Trả về con số chính xác nếu tra được."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_annual_leave",
            "description": (
                "Tính số ngày phép năm cho một trường hợp cụ thể (loại công việc + số năm thâm niên). "
                "Dùng khi người hỏi nêu thâm niên/loại công việc của họ; không tự cộng nhẩm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_type": {"type": "string", "enum": list(_LEAVE_BASE)},
                    "years_of_service": {"type": "number", "description": "Số năm làm việc"},
                },
                "required": ["job_type", "years_of_service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Chuyển cho người phụ trách khi câu hỏi cần dữ liệu cá nhân, quyết định của con người, "
                "hoặc đã tìm mà tài liệu không có."
            ),
            "parameters": {
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": ["personal_data", "missing_evidence"]}},
                "required": ["kind"],
            },
        },
    },
]

_SYSTEM = (
    "Bạn là agent tra cứu tài liệu nội bộ doanh nghiệp. Nhiệm vụ: thu thập ĐỦ bằng chứng để trả lời câu hỏi, "
    "bằng cách gọi tool. Không tự trả lời từ kiến thức riêng.\n"
    "- Câu hỏi nhiều ý: gọi search_policies riêng cho từng ý.\n"
    "- Kết quả rỗng/lạc đề: thử lại với từ khóa khác (tối đa 2 lần cho một ý).\n"
    "- Định mức khách sạn/công tác phí: thử lookup_structured_policy trước.\n"
    "- Cần dữ liệu cá nhân hoặc tài liệu không có: escalate_to_human.\n"
    "Khi đã đủ bằng chứng, trả lời đúng một chữ: DONE."
)


_STATUS = {
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
        lines.append(f"- [{c.get('title', '')} · {where}] {c.get('text', '')[:600]}")
    return "\n".join(lines)


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


async def react_node(state: AgentState) -> dict:
    settings = get_settings()
    question = state.get("condensed_query") or state.get("query", "")
    model, base_url, api_key = resolve_llm_endpoint(model=settings.router_model or None)
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": question}]

    found: dict[str, RetrievedChunk] = {}
    steps: list[dict] = []
    denied: dict = {}

    stop = False
    for _ in range(settings.react_max_steps):
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

        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            query = str(args.get("query") or question)
            _emit_status(name, query)
            chunk_ids: list[str] = []

            if name == "escalate_to_human":
                if args.get("kind") != "personal_data" and found:
                    # Model chỉ thấy bản tóm tắt chunk nên không đủ căn cứ để vứt
                    # bằng chứng đã gom (qa_029: chunk FAQ có đáp án nằm sau đoạn
                    # bị cắt). Dừng gọi tool, để generate + confidence quyết định.
                    steps.append({"tool": name, "args": args, "result": "deferred_to_generate"})
                    stop = True
                    break
                steps.append({"tool": name, "args": args, "result": "escalated"})
                print(f"[REACT] steps={steps}")
                reason = "personal_data_required" if args.get("kind") == "personal_data" else "low_confidence"
                return {"agent_steps": steps, "escalate": True, "escalate_reason": reason}

            if name == "lookup_structured_policy":
                res = await knowledge_lookup_node({**state, "condensed_query": query})
                if res.get("skip_retrieval"):
                    steps.append({"tool": name, "args": args, "result": "resolved"})
                    print(f"[REACT] steps={steps}")
                    return {**res, "agent_steps": steps}
                result = "Không tra được trong bảng định mức; hãy dùng search_policies."
            elif name == "calculate_annual_leave":
                result, computed = await _calculate_leave(state, args)
                if computed:
                    found.setdefault(computed["chunk_id"], computed)
                    for c in computed.pop("_evidence"):
                        found.setdefault(c["chunk_id"], c)
            elif name == "search_policies":
                res = await _search(state, query)
                if res.get("access_denied_reason"):
                    denied = res
                    result = "Người dùng không có quyền xem tài liệu của phòng ban này."
                else:
                    new = res.get("retrieved_chunks", [])
                    for c in new:
                        found.setdefault(c["chunk_id"], c)
                    result = _summarize(new)
                    chunk_ids = [c["chunk_id"] for c in new]
            else:
                result = f"Tool không tồn tại: {name}"

            steps.append({"tool": name, "args": args, "result": result[:200], "chunk_ids": chunk_ids})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    if not steps:
        # ponytail: model không gọi tool nào (hoặc lỗi) -> hành xử như pipeline: 1 lần search câu gốc.
        res = await _search(state, question)
        if res.get("access_denied_reason"):
            denied = res
        for c in res.get("retrieved_chunks", []):
            found.setdefault(c["chunk_id"], c)
        steps.append({"tool": "search_policies", "args": {"query": question}, "result": "fallback"})

    print(f"[REACT] steps={[(s['tool'], s['args']) for s in steps]} chunks={len(found)}")
    chunks = sorted(found.values(), key=lambda c: -c["score"] if c.get("score") is not None else c.get("distance", 0.0))[: max(settings.rerank_top_k, 8)]
    if not chunks and denied:
        return {**denied, "agent_steps": steps}
    # rewrite_count = max để hallucination retry không quay về vòng rewrite của pipeline.
    return {"retrieved_chunks": chunks, "agent_steps": steps, "rewrite_count": settings.max_rewrite_retries}


def route_after_react(state: AgentState) -> str:
    if state.get("skip_retrieval"):
        return "finalize"
    if state.get("escalate"):
        return "escalate"
    if state.get("access_denied_reason") == "DEPARTMENT_SCOPE_DENIED" and not state.get("retrieved_chunks"):
        return "access_denied"
    return "generate"
