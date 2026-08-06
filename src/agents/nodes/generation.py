from src.agents.llm import acall_llm
from src.agents.state import AgentState, Citation, RetrievedChunk

# Model phải phát ra ĐÚNG chuỗi này khi context không trả lời được câu hỏi.
# Prompt cũ chỉ dặn "nói rõ là chưa đủ thông tin" nên model diễn đạt tự do —
# không có cách nào bắt được bằng máy, và 10/29 câu in_scope fail là trường hợp
# retrieval sai mà agent vẫn tự tin sinh nội dung (xem eval/results/EVAL_REVIEW.md).
INSUFFICIENT_MARKER = "[KHÔNG_ĐỦ_THÔNG_TIN]"

_GENERATE_SYSTEM = f"""Bạn là trợ lý HR nội bộ, CHỈ trả lời dựa trên các đoạn trích tài liệu được cung cấp — không bịa thêm số liệu/điều khoản không có trong đó. Trả lời ngắn gọn, tiếng Việt, trích rõ [Nguồn N] cho từng ý lấy từ tài liệu.

KHI ĐOẠN TRÍCH KHÔNG ĐỦ: chỉ dùng chuỗi {INSUFFICIENT_MARKER} (bắt đầu câu trả lời bằng đúng chuỗi này rồi mới nói rõ thiếu gì) khi CHỦ ĐỀ của câu hỏi hoàn toàn KHÔNG được đoạn trích nào nhắc tới, hoặc đoạn trích chỉ nói về một chủ đề khác gần giống nhưng không trả lời đúng câu hỏi. TUYỆT ĐỐI KHÔNG dùng chuỗi này chỉ vì đoạn trích không cho một con số cố định — nhiều chính sách hợp lệ trả lời kiểu "mức cụ thể do doanh nghiệp quyết định" hoặc "tuỳ từng trường hợp", đó LÀ câu trả lời đầy đủ và đúng, không phải thiếu thông tin. Nếu đoạn trích có nhắc tới đúng chủ đề được hỏi, hãy trả lời bằng đúng những gì đoạn trích nói, kể cả khi không có số liệu chính xác.

KHI CÁC NGUỒN NÓI KHÁC NHAU VỀ CÙNG MỘT SỰ KIỆN CỤ THỂ (vd cùng nói mức phụ cấp X nhưng cho 2 con số khác nhau): ưu tiên (1) chính sách nội bộ chính thức, (2) văn bản pháp luật, (3) template/synthetic, VÀ nói rõ là có nguồn khác quy định khác — không im lặng chọn một bên. Quy tắc này CHỈ áp dụng khi các nguồn thực sự MÂU THUẪN về cùng một điều khoản cụ thể. QUAN TRỌNG: đoạn trích ĐÚNG TRỌNG TÂM câu hỏi nhất (dù là template/synthetic) luôn phải được dùng làm câu trả lời chính — thứ tự ưu tiên trên KHÔNG có nghĩa là bỏ qua đoạn trích sát câu hỏi để dùng một đoạn trích "chính thức" nhưng chỉ liên quan chung chung. Nếu chỉ có nguồn template/synthetic, phải nói rõ đây là tài liệu tham khảo, không phải quy định chính thức của công ty."""

_HALLUCINATION_SYSTEM = """Bạn kiểm tra xem câu trả lời có bám sát HOÀN TOÀN vào các đoạn trích nguồn hay không — không có số liệu/điều khoản nào bị bịa thêm ngoài đoạn trích. Chỉ trả lời đúng 1 từ: "PASS" nếu câu trả lời có căn cứ đầy đủ từ đoạn trích (hoặc câu trả lời chỉ nói "chưa đủ thông tin"), "FAIL" nếu có nội dung không xuất hiện trong đoạn trích."""


_SOURCE_LABEL = {
    "official_policy": "chính sách nội bộ chính thức",
    "government_law": "văn bản pháp luật",
    "public_article": "bài viết tham khảo công khai — không phải quy định công ty",
    "public_template": "template công khai — không phải quy định công ty",
    "synthetic": "tài liệu mẫu/synthetic — không phải quy định công ty",
}


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Đánh số [Nguồn N] theo ĐÚNG thứ tự relevance đã nhận (reranker/dense) —
    KHÔNG sắp xếp lại theo source_type.

    Từng thử sort ưu tiên chính sách chính thức lên trước (A3 bản đầu) và đo
    được nó phản tác dụng: LLM bám rất mạnh vào vị trí "Nguồn 1", nên khi một
    chunk KHÔNG liên quan sát câu hỏi (vd VinFast, chính sách kỷ luật chung,
    score 0.15) bị đẩy lên trước một chunk liên quan trực tiếp (vd tài liệu
    "thông báo quy định nghỉ phép" đúng tên trong câu hỏi, score 0.95) chỉ vì
    is_official_policy=True, model trả lời theo nguồn sai (xem CLAUDE.md
    [2026-08-06], qa_117/qa_113/qa_017 — cả 3 đều regressed từ chunk đúng
    trọng tâm nhưng ưu tiên thấp bị nguồn "chính thức" nhưng lạc đề lấn át).
    Quy tắc ưu tiên nguồn khi có mâu thuẫn thật vẫn tồn tại — nhưng chỉ ở dạng
    văn bản trong _GENERATE_SYSTEM (mỗi nguồn có nhãn origin), không can thiệp
    vào thứ tự vật lý.
    """
    parts = []
    for i, c in enumerate(chunks, start=1):
        page = f", trang {c['page_start']}" if c.get("page_start") else ""
        origin = _SOURCE_LABEL.get(
            c.get("source_type") or "",
            "chính sách chính thức" if c["is_official_policy"] else "template/synthetic — không phải chính sách công ty thật",
        )
        parts.append(f"[Nguồn {i}] {c['title']} ({c['source_file']}{page}, {origin})\n{c['text']}")
    return "\n\n".join(parts) if parts else "(không tìm thấy đoạn trích liên quan)"


async def generate_node(state: AgentState) -> dict:
    query = state.get("query", "")
    chunks = state.get("retrieved_chunks", [])
    context = _build_context_block(chunks)
    user_prompt = f"Câu hỏi: {query}\n\nCác đoạn trích:\n{context}"

    answer = (await acall_llm(_GENERATE_SYSTEM, user_prompt, temperature=0.2)).strip()

    answerable = INSUFFICIENT_MARKER not in answer
    if not answerable:
        # Bỏ marker khỏi câu trả lời hiển thị cho user — nó là tín hiệu điều
        # khiển nội bộ, phần giải thích "thiếu gì" phía sau vẫn giữ nguyên.
        answer = answer.replace(INSUFFICIENT_MARKER, "").strip()

    citations: list[Citation] = [
        Citation(
            chunk_id=c["chunk_id"],
            source_file=c["source_file"],
            title=c["title"],
            category=c["category"],
            page_start=c.get("page_start"),
            page_end=c.get("page_end"),
            is_official_policy=c["is_official_policy"],
        )
        for c in chunks
    ]
    return {"generated_answer": answer, "citations": citations, "answerable": answerable}


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
