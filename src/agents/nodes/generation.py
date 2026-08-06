from src.agents.llm import acall_llm
from src.agents.state import AgentState, Citation, RetrievedChunk

_GENERATE_SYSTEM = """Bạn là trợ lý HR nội bộ, CHỈ trả lời dựa trên các đoạn trích tài liệu được cung cấp — không bịa thêm số liệu/điều khoản không có trong đó. Nếu đoạn trích không đủ để trả lời, hãy nói rõ là chưa đủ thông tin thay vì đoán. Trả lời ngắn gọn, tiếng Việt, trích rõ [Nguồn N] cho từng ý lấy từ tài liệu."""

_HALLUCINATION_SYSTEM = """Bạn kiểm tra xem câu trả lời có bám sát HOÀN TOÀN vào các đoạn trích nguồn hay không — không có số liệu/điều khoản nào bị bịa thêm ngoài đoạn trích. Chỉ trả lời đúng 1 từ: "PASS" nếu câu trả lời có căn cứ đầy đủ từ đoạn trích (hoặc câu trả lời chỉ nói "chưa đủ thông tin"), "FAIL" nếu có nội dung không xuất hiện trong đoạn trích."""


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        page = f", trang {c['page_start']}" if c.get("page_start") else ""
        origin = "chính sách chính thức" if c["is_official_policy"] else "template/synthetic — không phải chính sách công ty thật"
        parts.append(f"[Nguồn {i}] {c['title']} ({c['source_file']}{page}, {origin})\n{c['text']}")
    return "\n\n".join(parts) if parts else "(không tìm thấy đoạn trích liên quan)"


async def generate_node(state: AgentState) -> dict:
    query = state.get("query", "")
    chunks = state.get("retrieved_chunks", [])
    context = _build_context_block(chunks)
    user_prompt = f"Câu hỏi: {query}\n\nCác đoạn trích:\n{context}"

    answer = (await acall_llm(_GENERATE_SYSTEM, user_prompt, temperature=0.2)).strip()

    citations: list[Citation] = [
        Citation(
            chunk_id=c["chunk_id"],
            source_file=c["source_file"],
            title=c["title"],
            page_start=c.get("page_start"),
            page_end=c.get("page_end"),
            is_official_policy=c["is_official_policy"],
        )
        for c in chunks
    ]
    return {"generated_answer": answer, "citations": citations}


async def hallucination_check_node(state: AgentState) -> dict:
    chunks = state.get("retrieved_chunks", [])
    answer = state.get("generated_answer", "")
    context = _build_context_block(chunks)
    user_prompt = f"Đoạn trích:\n{context}\n\nCâu trả lời cần kiểm tra:\n{answer}"

    verdict = await acall_llm(_HALLUCINATION_SYSTEM, user_prompt, temperature=0.0)
    passed = "PASS" in verdict.upper()

    retry_count = state.get("hallucination_retry_count", 0)
    if not passed:
        retry_count += 1
    return {"hallucination_passed": passed, "hallucination_retry_count": retry_count}


def finalize_node(state: AgentState) -> dict:
    """Ghép câu trả lời cuối + danh sách nguồn tham khảo — chạy sau khi confidence
    đủ cao (không escalate)."""
    answer = state.get("generated_answer", "")
    citations = state.get("citations", [])
    if citations:
        lines = []
        for c in citations:
            page = f" (trang {c['page_start']})" if c.get("page_start") else ""
            caveat = "" if c["is_official_policy"] else " [nguồn tham khảo/template, không phải chính sách công ty thật]"
            lines.append(f"- {c['title']}{page}{caveat}")
        answer = f"{answer}\n\nNguồn tham khảo:\n" + "\n".join(lines)
    return {"response": answer}
