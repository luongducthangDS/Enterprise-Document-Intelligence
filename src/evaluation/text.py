"""Chuẩn hoá text để so khớp trong eval (retrieval hit-check, fix ground truth).

Lịch sử: phát hiện qa_017 bị coi là "không nguyên văn" nhầm vì nguồn dùng dấu
ngoặc kép kiểu chữ (" ") còn ground_truth_context dùng dấu thẳng (" ") — 2 ký tự
Unicode khác nhau, whitespace-normalize thôi không đủ. Xem CLAUDE.md [2026-08-05].

Nằm ở src/ (không phải eval/scripts/) vì evaluation worker chạy trong container
agent, mà container không copy thư mục eval/ — xem .dockerignore.
eval/scripts/_text_utils.py re-export lại từ đây để mọi script eval và worker
dùng chung đúng một bản normalize.
"""

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
