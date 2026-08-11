"""Guardrail kỹ thuật — độc lập với việc model có "nghe lời" system prompt hay
không. Thuần regex/code, không gọi LLM (không thêm latency, không phụ thuộc
hành vi model) — cùng triết lý deterministic enforcement đã dùng ở
`confidence_node`/`grade_node` (src/agents/nodes/escalation.py,
src/agents/nodes/retrieval.py).

Hai lớp:
1. Input/context guardrail — phát hiện & CẮT BỎ câu chứa chỉ dẫn injection
   trong RAG chunk trước khi nó tới prompt của LLM (không chỉ dặn LLM "đừng
   nghe theo" — loại bỏ hẳn khỏi context là lớp chặn không phụ thuộc model).
2. Output guardrail — che PII lộ trong câu trả lời cuối trước khi trả cho user.

# ponytail: regex theo pattern injection/PII phổ biến, chưa phải NLP/NER đầy
# đủ — nếu eval sau này đo được false positive/negative đáng kể (vd văn bản
# luật có đoạn hợp lệ bị cắt oan, hoặc injection phrasing mới lọt qua), nâng
# cấp lên classifier riêng khi có ngân sách đo.
"""

import re

REDACTED_INJECTION_MARKER = "[ĐOẠN BỊ GUARDRAIL CHẶN — nghi vấn prompt injection]"

# Mỗi pattern yêu cầu CẢ CỤM động từ điều khiển ("bỏ qua"/"ignore"/"tiết lộ")
# LẪN đối tượng bị điều khiển ("hướng dẫn trước đó"/"system prompt"/"admin")
# trong cùng 1 câu — tránh false positive trên câu HR hợp lệ chỉ chứa 1 nửa cụm
# (vd "nhân viên bỏ qua quy định nghỉ phép có thể bị kỷ luật" không khớp vì
# thiếu "tất cả/mọi" + "hướng dẫn/chỉ thị/quy tắc/prompt").
_INJECTION_SENTENCE_PATTERNS = [
    re.compile(
        r"[^.\n]*\b(bỏ qua|quên đi)\b[^.\n]*\b(tất cả|mọi|toàn bộ)\b[^.\n]*"
        r"\b(hướng dẫn|chỉ thị|quy tắc|prompt)\b[^.\n]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"[^.\n]*\bignore\b[^.\n]*\b(all|any|previous|prior|above)\b[^.\n]*"
        r"\b(instructions?|rules?|prompt)\b[^.\n]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"[^.\n]*\bdisregard\b[^.\n]*\b(previous|above)\b[^.\n]*\b(instructions?|rules?)\b[^.\n]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"[^.\n]*\b(tiết lộ|reveal)\b[^.\n]*(\bsystem prompt\b|prompt hệ thống|chỉ thị hệ thống)[^.\n]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"[^.\n]*\b(coi|xem)\s+(bạn|mình)\s+(là|như)\s+(admin|quản trị viên|quản trị hệ thống)[^.\n]*",
        re.IGNORECASE,
    ),
]


def detect_injection(text: str) -> list[str]:
    """Trả về danh sách câu nghi vấn injection tìm thấy (rỗng nếu sạch). Chỉ
    phát hiện, không sửa text — dùng để audit trên user query (không nên tự ý
    cắt câu hỏi của chính người dùng, rủi ro false-positive ảnh hưởng UX cao
    hơn lợi ích)."""
    return [m.group(0).strip() for pat in _INJECTION_SENTENCE_PATTERNS for m in pat.finditer(text)]


def strip_injection(text: str) -> tuple[str, list[str]]:
    """Cắt bỏ câu nghi vấn injection, thay bằng marker cố định. Dùng cho nội
    dung RAG document (untrusted data — xem AI_SAFETY_GUARDRAILS.md mục 1) vì
    ở đó loại bỏ hẳn văn bản gốc không mất gì (không phải câu hỏi của user)."""
    hits: list[str] = []

    def _sub(match: re.Match) -> str:
        hits.append(match.group(0).strip())
        return REDACTED_INJECTION_MARKER

    cleaned = text
    for pat in _INJECTION_SENTENCE_PATTERNS:
        cleaned = pat.sub(_sub, cleaned)
    return cleaned, hits


_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    # Số điện thoại VN: 10 số bắt đầu 0 (hoặc +84) + đầu số di động hợp lệ.
    ("phone", re.compile(r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)")),
    # CCCD 12 số liên tục — không chồng lấn số điện thoại (đã xử lý ở bước
    # trước, ký tự đã bị thay bằng '*' nên không còn là \d).
    ("cccd", re.compile(r"(?<!\d)\d{12}(?!\d)")),
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Che PII (email/SĐT/CCCD) bằng '*' cùng độ dài. Trả về text đã che +
    danh sách loại PII tìm thấy (để audit log)."""
    found: list[str] = []
    redacted = text
    for label, pat in _PII_PATTERNS:

        def _sub(match: re.Match, label: str = label) -> str:
            found.append(label)
            return "*" * len(match.group(0))

        redacted = pat.sub(_sub, redacted)
    return redacted, found
