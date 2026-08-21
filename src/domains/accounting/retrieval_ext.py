"""Retrieval extensions cho domain Phòng Kế toán & Tài chính.

Bao gồm:
  - G1: Nhận diện query kế toán (_is_accounting_query)
  - G2: Bộ từ điển mở rộng Query Expansion (_expand_accounting_query)
  - G3: Dynamic Top-K Expansion (_get_accounting_top_k)
"""
from __future__ import annotations

import re

# ─── G1: Nhận diện query kế toán ─────────────────────────────────────────────
_ACCOUNTING_KEYWORD_PATTERN = re.compile(
    r"\b(?:tạm ứng|hoàn ứng|duyệt chi|mua sắm|báo giá|hóa đơn|kế toán"
    r"|thuế|gtgt|vat|po|pr|cba|avl|tiền mặt|chuyển khoản|thanh toán"
    r"|ngân sách|chi phí|quyết toán|phiếu chi|phiếu thu|sop-tckt|sop-ms"
    r"|13/qđ-abc|13-qd-abc|qc-ltk|bbgn|đntt|dntt|chứng từ)\b",
    re.IGNORECASE,
)
_ACCOUNTING_CATEGORY_PREFIX = ("accounting", "finance", "procurement", "internal_expense", "payroll_and_compensation", "advance_and_payment")


def _is_accounting_query(query: str, category: str | None = None) -> bool:
    """Xác định xem truy vấn có thuộc phạm vi Kế toán / Tài chính / Mua sắm không."""
    if category:
        cat_lower = category.lower()
        if any(cat_lower.startswith(p) for p in _ACCOUNTING_CATEGORY_PREFIX):
            return True
    return bool(_ACCOUNTING_KEYWORD_PATTERN.search(query))


# ─── G2: Query Expansion ─────────────────────────────────────────────────────
_ACCOUNTING_EXPANSION_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\b(?:tách đơn|chia nhỏ|lách luật|né hạn mức)\b", re.IGNORECASE),
        "nghiêm cấm hành vi cố ý chia nhỏ khoản chi tách hợp đồng thẩm quyền phê duyệt",
    ),
    (
        re.compile(
            r"\b(?:hóa đơn giấy|hóa đơn viết tay|hóa đơn không hợp lệ|không tra cứu được)\b",
            re.IGNORECASE,
        ),
        "hóa đơn GTGT điện tử hợp pháp hợp lệ tra cứu hệ thống Tổng cục Thuế từ chối thanh toán",
    ),
    (
        re.compile(r"\b(?:duyệt chi|ai duyệt|thẩm quyền ký|hạn mức duyệt)\b", re.IGNORECASE),
        "thẩm quyền phê duyệt hạn mức duyệt chi Giám đốc Trưởng phòng Kế toán trưởng",
    ),
    (
        re.compile(r"\b(?:mua sắm khẩn cấp|mua gấp|sự cố đột xuất)\b", re.IGNORECASE),
        "mua sắm khẩn cấp bất khả kháng gián đoạn kinh doanh bổ sung hồ sơ 48 giờ",
    ),
    (
        re.compile(
            r"\b(?:quá hạn hoàn ứng|chậm thanh toán tạm ứng|quên hoàn ứng)\b", re.IGNORECASE
        ),
        "thời hạn hoàn ứng quá hạn 15 ngày tự động khấu trừ vào lương",
    ),
]


def _expand_accounting_query(query: str) -> str:
    """Mở rộng từ đồng nghĩa và cụm từ quy chế đặc thù kế toán."""
    matched: list[str] = []
    for pattern, extra_terms in _ACCOUNTING_EXPANSION_RULES:
        if pattern.search(query):
            matched.append(extra_terms)
    if not matched:
        return query
    return f"{query}\nNgữ cảnh quy chế Kế toán: {' | '.join(matched)}"


# ─── G3: Dynamic Top-K Multi-source ──────────────────────────────────────────
_MULTI_DOC_PATTERN = re.compile(
    r"(?:giữa|và|với|đồng thời|đối chiếu|so sánh|theo cả).*?"
    r"(?:SOP|QĐ|QC|PO|PR|BC|Hóa đơn|Biên bản)"
    r"|(?:SOP|QĐ|QC)[\w\-]*.*?(?:và|với).*?(?:SOP|QĐ|QC)[\w\-]*",
    re.IGNORECASE,
)
ACCOUNTING_MULTI_DOC_TOP_K = 15


def _get_accounting_top_k(query: str, default_k: int) -> int:
    """Tự động mở rộng Top-K lên 15 nếu câu hỏi cần đối chiếu giữa nhiều văn bản."""
    if _MULTI_DOC_PATTERN.search(query):
        return max(default_k, ACCOUNTING_MULTI_DOC_TOP_K)
    return default_k
