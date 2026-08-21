"""Node Đánh giá rủi ro và Điều hướng Human-in-the-Loop (HITL).

Nguyên tắc phân tầng rủi ro:
1. LOW RISK:
   - Tra cứu chính sách chung (Nghỉ phép, WFH, OT, Công tác phí cơ bản).
   - Tóm tắt tài liệu thông thường.
   -> Trả lời tự động kèm trích dẫn (Auto response).

2. HIGH RISK:
   - Trích xuất quyết định ràng buộc pháp lý / nghĩa vụ tài chính lớn.
   - Xử lý kỷ luật lao động / sa thải / khiếu nại.
   - Độ tin cậy trích xuất / retrieval thấp (confidence < 0.85).
   - Mâu thuẫn phát hiện giữa các văn bản quy định.
   -> Kích hoạt luồng HITL (Human-in-the-Loop Review) với payload phê duyệt có cấu trúc.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field

from src.agents.state import AgentState


class HITLReviewPayload(BaseModel):
    """Payload gửi tới người quản trị / chuyên viên phê duyệt HITL."""
    request_id: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    risk_factors: list[str] = Field(default_factory=list)
    action_type: Literal["AUTO_APPROVE", "REQUIRE_HUMAN_REVIEW", "REJECT"] = "AUTO_APPROVE"
    proposed_content: str = Field(description="Nội dung AI đề xuất hoặc quyết định trích xuất")
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = 1.0
    status: Literal["PENDING_REVIEW", "APPROVED", "EDITED", "REJECTED"] = "PENDING_REVIEW"
    reviewer_notes: str | None = None


def evaluate_risk(state: AgentState) -> HITLReviewPayload:
    """Đánh giá mức độ rủi ro của yêu cầu và quyết định có cần HITL hay không."""
    query = (state.get("query") or "").lower()
    request_id = state.get("request_id") or "req_default"
    chunks = state.get("reranked_chunks") or state.get("retrieved_chunks") or []
    generation = state.get("generation") or ""
    extraction = state.get("structured_extraction")

    risk_factors = []
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"

    # 1. Kiểm tra từ khóa nhạy cảm / rủi ro cao
    high_risk_keywords = [
        "sa thải", "kỷ luật", "đơn phương chấm dứt", "bồi thường", "khiếu nại",
        "trách nhiệm vật chất", "bí mật kinh doanh", "tố cáo", "tạm đình chỉ"
    ]
    for kw in high_risk_keywords:
        if kw in query or kw in generation.lower():
            risk_factors.append(f"Chứa từ khóa nhạy cảm / nghiệp vụ kỷ luật: '{kw}'")
            risk_level = "HIGH"

    # 2. Kiểm tra Structured Extraction có yêu cầu HITL
    if extraction and extraction.get("requires_hitl"):
        risk_factors.append("Trích xuất quyết định điều hành yêu cầu phê duyệt từ ban lãnh đạo.")
        risk_level = "HIGH"

    # 3. Kiểm tra độ tin cậy của Retrieval
    if not chunks:
        risk_factors.append("Không tìm thấy tài liệu dẫn chứng phù hợp trong phạm vi được cấp quyền.")
        risk_level = "MEDIUM"
    elif len(chunks) < 2 and risk_level != "LOW":
        risk_factors.append("Bằng chứng đối chiếu thưa thớt (dưới 2 nguồn đối chiếu).")

    action_type: Literal["AUTO_APPROVE", "REQUIRE_HUMAN_REVIEW", "REJECT"] = (
        "REQUIRE_HUMAN_REVIEW" if risk_level in ("HIGH", "CRITICAL") else "AUTO_APPROVE"
    )

    evidence_list = []
    for c in chunks[:4]:
        evidence_list.append({
            "source_file": c["source_file"],
            "title": c.get("title", ""),
            "section": c.get("heading_path", ""),
            "text_snippet": c["text"][:200] + "...",
        })

    return HITLReviewPayload(
        request_id=request_id,
        risk_level=risk_level,
        risk_factors=risk_factors,
        action_type=action_type,
        proposed_content=generation or (extraction.get("summary") if extraction else "N/A"),
        supporting_evidence=evidence_list,
        confidence_score=0.95 if risk_level == "LOW" else 0.75,
        status="PENDING_REVIEW" if action_type == "REQUIRE_HUMAN_REVIEW" else "APPROVED",
    )


async def risk_assessment_node(state: AgentState) -> dict[str, Any]:
    """LangGraph Node thực thi đánh giá rủi ro và sinh payload HITL."""
    hitl_payload = evaluate_risk(state)
    return {
        "hitl_payload": hitl_payload.model_dump(),
        "requires_human_review": hitl_payload.action_type == "REQUIRE_HUMAN_REVIEW",
    }
