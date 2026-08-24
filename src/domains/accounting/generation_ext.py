"""Generation guardrail cho domain Phòng Kế toán — G4: Numeric Grounding Lock.

Inject đoạn prompt bổ sung vào system prompt của generation node khi context
được nhận diện là tài liệu kế toán, ngăn LLM bịa số tiền VNĐ, % tỷ lệ, ngày hạn.
"""
from __future__ import annotations

ACCOUNTING_GENERATION_RULES = """
=== QUY TẮC BẮT BUỘC — DỮ LIỆU KẾ TOÁN & TÀI CHÍNH ===
1. KHÓA SỐ LIỆU TUYỆT ĐỐI: Mọi con số về tiền tệ (VNĐ), tỷ lệ phần trăm (%), thời hạn (ngày làm việc), định mức duyệt chi PHẢI được trích dẫn CHÍNH XÁC từng chữ số từ các đoạn trích [Nguồn N]. Tuyệt đối KHÔNG tự tính toán, KHÔNG ước lượng, KHÔNG làm tròn số tiền.
2. ABSTAIN KHI THIẾU SỐ LIỆU CỤ THỂ: Nếu context không nêu con số cụ thể cho câu hỏi về hạn mức/mức thanh toán/thời hạn, phát [KHÔNG_ĐỦ_THÔNG_TIN] và hướng dẫn liên hệ Phòng Kế toán — KHÔNG ước tính "khoảng X triệu".
3. PHÂN ĐỊNH THẨM QUYỀN DUYỆT CHI: Khi trả lời về duyệt chi, LUÔN nêu rõ cấp phê duyệt gắn với hạn mức cụ thể (VD: Trưởng phòng phê duyệt dưới 10 triệu; Giám đốc từ 15 triệu trở lên hoặc vượt ngân sách).
4. XỬ LÝ MÂU THUẪN GIỮA CÁC VĂN BẢN (G8 - Conflict-Aware Rule): Nếu trong các đoạn trích có sự khác nhau hoặc mâu thuẫn về cùng một quy định/thời hạn/hạn mức giữa các văn bản khác nhau (ví dụ: Quy chế chi tiêu ghi 03 ngày làm việc, nhưng SOP lại ghi 05 ngày làm việc), hãy trình bày ĐẦY ĐỦ CẢ HAI văn bản và ghi chú rõ ràng tên từng văn bản, đồng thời khuyến nghị người dùng kiểm tra lại với Phòng Kế toán. TUYỆT ĐỐI KHÔNG phát [KHÔNG_ĐỦ_THÔNG_TIN] khi đã có thông tin trong các đoạn trích dù có sự chênh lệch giữa các văn bản.
"""

# G11: Danh sách category tài liệu OCR/ảnh trong phân hệ kế toán.
# Các tài liệu này có reranker score thấp hơn chuẩn do chất lượng text OCR;
# khi phát hiện có chunk thuộc category này và câu hỏi rõ ràng trả lời được,
# ta nâng confidence floor để tránh escalate nhầm.
_ACCOUNTING_OCR_CATEGORIES = frozenset({
    "fixed_assets_management",
    "invoices_and_tax",
    "advance_and_payment_sop",   # DNTT, ĐNTT là ảnh PNG
})

# Ngưỡng floor confidence khi có OCR chunk — đặt ở mức VỪA đủ không escalate
# (cần > low_confidence_threshold mặc định 0.45 một chút để có buffer an toàn).
_OCR_CONFIDENCE_FLOOR = 0.52


def adjust_confidence_for_ocr_docs(
    confidence: float,
    chunks: list[dict],
    answerable: bool,
) -> float:
    """G11: Nâng confidence floor cho tài liệu OCR/ảnh kế toán.

    Chỉ áp dụng khi:
    - answerable=True (agent đã xác nhận có đủ thông tin trả lời)
    - Có ít nhất 1 chunk thuộc OCR category
    - confidence hiện tại thấp hơn floor (tức là bị OCR noise kéo xuống)
    """
    if not answerable:
        return confidence  # Không override khi agent tự đánh là không trả lời được
    has_ocr_chunk = any(
        c.get("category", "") in _ACCOUNTING_OCR_CATEGORIES
        for c in chunks
    )
    if has_ocr_chunk and confidence < _OCR_CONFIDENCE_FLOOR:
        return _OCR_CONFIDENCE_FLOOR
    return confidence
