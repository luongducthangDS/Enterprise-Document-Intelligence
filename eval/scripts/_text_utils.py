"""Chuẩn hoá text dùng chung cho các script eval — nay là lớp re-export mỏng.

Bản gốc đã chuyển sang src/evaluation/text.py để evaluation worker trong
container agent (không copy eval/, xem .dockerignore) dùng chung đúng một bản
normalize với các script eval. Giữ module này để mọi script đang
`from _text_utils import normalize_for_match` chạy như cũ.
"""

from src.evaluation.text import normalize_for_match

__all__ = ["normalize_for_match"]
