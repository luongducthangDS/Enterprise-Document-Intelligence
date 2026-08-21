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
"""
