"""Node trích xuất tri thức có cấu trúc & quyết định (Structured Decision & Knowledge Extraction).

Hỗ trợ các use case doanh nghiệp:
- Trích xuất quyết định từ biên bản họp / nghị quyết / chính sách.
- Gán người phụ trách (Owner), thời hạn (Deadline), mức độ ưu tiên (Priority).
- Đối chiếu bằng chứng nguyên văn (Evidence quote) và định vị nguồn (Citation).
- Phát hiện mâu thuẫn hoặc liên kết chéo giữa nhiều văn bản (Cross-document Intelligence).
"""

import json
from typing import Any, Literal
from pydantic import BaseModel, Field

from src.agents.llm import acall_llm
from src.agents.state import AgentState, RetrievedChunk
from src.config import get_settings
from src.observability import llm_trace


class DecisionItem(BaseModel):
    """Mục quyết định hoặc hạng mục hành động được trích xuất."""
    decision_id: str = Field(description="Mã định danh quyết định (vd: DEC-001)")
    title: str = Field(description="Tiêu đề hoặc tóm lược quyết định ngắn gọn")
    content: str = Field(description="Nội dung chi tiết quyết định / chỉ đạo")
    owner: str = Field(description="Cá nhân hoặc phòng ban chịu trách nhiệm thực hiện")
    department: str = Field(description="Phòng ban phụ trách chính")
    deadline: str | None = Field(default=None, description="Hạn chót hoàn thành (YYYY-MM-DD hoặc mốc thời gian)")
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(default="MEDIUM", description="Mức độ ưu tiên")
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "APPROVED"] = Field(default="PENDING")
    source_document: str = Field(description="Tên file tài liệu gốc chứa quyết định")
    section_or_article: str = Field(description="Điều khoản hoặc mục chứa quyết định")
    evidence_quote: str = Field(description="Đoạn văn bản trích dẫn nguyên văn làm bằng chứng")
    confidence: float = Field(default=1.0, description="Độ tin cậy của trích xuất (0.0 - 1.0)")


class StructuredExtractionResult(BaseModel):
    """Kết quả trích xuất tri thức doanh nghiệp."""
    summary: str = Field(description="Tóm tắt tổng quan tri thức / quyết định")
    decisions: list[DecisionItem] = Field(default_factory=list, description="Danh sách các quyết định và hạng mục hành động")
    key_takeaways: list[str] = Field(default_factory=list, description="Các điểm cốt lõi quan trọng")
    cross_document_insights: list[str] = Field(default_factory=list, description="Tổng hợp quan hệ / mâu thuẫn giữa các tài liệu")
    requires_hitl: bool = Field(default=False, description="Cần con người (HITL) phê duyệt trước khi ghi nhận")


EXTRACTION_SYSTEM_PROMPT = """Bạn là Chuyên gia Trích xuất Tri thức & Quyết định Doanh nghiệp (Enterprise Knowledge & Decision Intelligence).
Nhiệm vụ của bạn là đọc các đoạn trích tài liệu nội bộ được cung cấp và trích xuất cấu trúc thông tin chính xác theo định dạng JSON.

Quy tắc bắt buộc:
1. Độ trung thực tuyệt đối: Mọi quyết định/nội dung trích xuất BẮT BUỘC phải có `evidence_quote` là đoạn văn bản gốc và `source_document` cụ thể. Không suy diễn ngoài tài liệu.
2. Trích xuất đầy đủ: Xác định rõ Người chịu trách nhiệm (`owner`), Phòng ban (`department`), Hạn chót (`deadline`), Mức độ ưu tiên (`priority`).
3. Đánh giá rủi ro / HITL: Nếu quyết định liên quan đến kỷ luật, cam kết tài chính, hoặc có sự mâu thuẫn/không chắc chắn -> đánh dấu `requires_hitl = true`.

Định dạng JSON trả về:
{
  "summary": "Tóm tắt tổng quan ngắn gọn...",
  "decisions": [
    {
      "decision_id": "DEC-001",
      "title": "Tên quyết định",
      "content": "Nội dung chỉ đạo cụ thể",
      "owner": "Người / Bộ phận phụ trách",
      "department": "HR / FINANCE / ...",
      "deadline": "2025-12-31 hoặc 'Định kỳ hàng tháng'",
      "priority": "HIGH" | "MEDIUM" | "LOW",
      "status": "PENDING",
      "source_document": "tên_file.md",
      "section_or_article": "Điều 5...",
      "evidence_quote": "Trích dẫn nguyên văn từ tài liệu",
      "confidence": 0.95
    }
  ],
  "key_takeaways": ["Điểm 1...", "Điểm 2..."],
  "cross_document_insights": ["Liên kết giữa tài liệu A và B..."],
  "requires_hitl": true | false
}
Chỉ trả về JSON thuần túy, không kèm bất kỳ lời giải thích nào.
"""


async def extraction_node(state: AgentState) -> dict[str, Any]:
    """Node xử lý trích xuất tri thức có cấu trúc từ tập chunks đã truy xuất."""
    settings = get_settings()
    chunks: list[RetrievedChunk] = state.get("reranked_chunks") or state.get("retrieved_chunks") or []
    query: str = state.get("query", "")

    if not chunks:
        return {
            "structured_extraction": StructuredExtractionResult(
                summary="Không tìm thấy tài liệu phù hợp để trích xuất tri thức.",
                decisions=[],
                key_takeaways=[],
                requires_hitl=False,
            ).model_dump()
        }

    # Tổng hợp ngữ cảnh từ các chunk được cấp quyền
    context_blocks = []
    for i, c in enumerate(chunks[:8]):
        context_blocks.append(
            f"--- [Tài liệu {i+1}: {c['source_file']} | Mục: {c.get('heading_path') or 'Toàn văn'}] ---\n"
            f"{c['text']}\n"
        )
    context_text = "\n".join(context_blocks)

    user_prompt = (
        f"Yêu cầu trích xuất từ người dùng: {query}\n\n"
        f"Ngữ cảnh tài liệu nội bộ đã được xác thực quyền truy cập:\n"
        f"{context_text}"
    )

    with llm_trace.Timer("structured_extraction", "fpt_llm"):
        response_text = await acall_llm(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            settings=settings,
            temperature=0.0,
        )

    # Clean JSON markdown fences
    cleaned_json = response_text.strip()
    if cleaned_json.startswith("```json"):
        cleaned_json = cleaned_json[7:]
    if cleaned_json.startswith("```"):
        cleaned_json = cleaned_json[3:]
    if cleaned_json.endswith("```"):
        cleaned_json = cleaned_json[:-3]
    cleaned_json = cleaned_json.strip()

    try:
        parsed_data = json.loads(cleaned_json)
        extraction_res = StructuredExtractionResult(**parsed_data)
    except Exception as e:
        extraction_res = StructuredExtractionResult(
            summary=f"Tóm tắt sơ bộ từ tài liệu (Lỗi parse JSON chi tiết: {e})",
            decisions=[],
            key_takeaways=[response_text[:300]],
            requires_hitl=True,
        )

    return {
        "structured_extraction": extraction_res.model_dump(),
        "requires_hitl": extraction_res.requires_hitl,
    }
