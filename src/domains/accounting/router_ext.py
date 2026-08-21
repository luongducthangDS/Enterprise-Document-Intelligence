"""Router guardrail cho domain Phòng Kế toán — G5: ABSTAIN Trigger.

Chặn các câu hỏi tra cứu dữ liệu sổ sách cá nhân thời gian thực hoặc
tra cứu lương/thu nhập cá nhân riêng lẻ mà hệ thống RAG tĩnh không thể
trả lời chính xác (không kết nối ERP live).
"""
from __future__ import annotations

import re

_ACCOUNTING_PERSONAL_PATTERNS: list[re.Pattern] = [
    # "tôi/em/mình còn nợ...", "số dư tạm ứng của tôi..."
    re.compile(
        r"\b(?:tôi|em|mình)\b.{0,30}"
        r"\b(?:còn nợ|nợ bao nhiêu|đã tạm ứng bao nhiêu|chưa hoàn ứng|số dư tạm ứng)\b",
        re.IGNORECASE,
    ),
    # "lương của anh/chị X...", "thu nhập của Trưởng phòng..."
    re.compile(
        r"\b(?:lương|thu nhập|thưởng|hoa hồng)\b.{0,20}\bcủa\b.{0,30}"
        r"\b(?:anh|chị|ông|bà|trưởng phòng|giám đốc|đồng nghiệp|nhân viên)\b",
        re.IGNORECASE,
    ),
    # "tra cứu/xem sổ nợ của tôi..."
    re.compile(
        r"\b(?:tra cứu|kiểm tra|xem)\b.{0,30}"
        r"\b(?:sổ nợ|công nợ cá nhân|bảng lương tháng này của tôi)\b",
        re.IGNORECASE,
    ),
]


def check_accounting_personal_data(query: str) -> tuple[bool, str]:
    """Kiểm tra xem câu hỏi có thuộc nhóm dữ liệu cá nhân sống kế toán hay không.

    Returns:
        (is_personal_data_query, reason_code)
    """
    for pat in _ACCOUNTING_PERSONAL_PATTERNS:
        if pat.search(query):
            return True, "requires_live_accounting_erp_data"
    return False, ""
