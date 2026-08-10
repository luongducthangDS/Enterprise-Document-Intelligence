"""Chuẩn hoá text dùng chung cho các script eval (retrieval hit-check, fix ground
truth) — tránh mỗi script tự viết 1 bản _normalize() lệch nhau.

Lịch sử: phát hiện qa_017 bị coi là "không nguyên văn" nhầm vì nguồn dùng dấu
ngoặc kép kiểu chữ (" ") còn ground_truth_context dùng dấu thẳng (" ") — 2 ký tự
Unicode khác nhau, whitespace-normalize thôi không đủ. Xem CLAUDE.md [2026-08-05]."""
import re
import unicodedata

_QUOTE_MAP = str.maketrans({
    "“": '"', "”": '"',  # “ ”
    "‘": "'", "’": "'",  # ‘ ’
    "–": "-", "—": "-",  # – —
})


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_QUOTE_MAP)
    text = re.sub(r"\*\*|__", "", text)  # markdown bold
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()
