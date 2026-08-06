#!/usr/bin/env python3
"""Gate tự động cho data/processed/: so mật độ ký tự với số trang PDF gốc để
bắt sớm kiểu hồi quy "model viết lại nội dung theo trí nhớ thay vì trích xuất
thật" đã gặp ở nghi_dinh_145_2020 và 5 file khác (xem CLAUDE.md, entry
"[2026-08-04] Review kỹ data/raw/"). Bản cũ chỉ liệt kê char/line count, không
có ngưỡng nên không bắt được lỗi đó — các file lỗi vẫn có vài KB nội dung nghe
hợp lý, chỉ thiếu so với số trang gốc.

- PDF: mở lại file gốc ở data/raw/<category>/<source_file> để đếm số trang
  thật, so với char_count của .md tương ứng — cảnh báo nếu dưới
  MIN_CHARS_PER_PAGE ký tự/trang.
- DOCX/MD: không có khái niệm "trang" — chỉ check ngưỡng ký tự tuyệt đối tối
  thiểu MIN_CHARS_NO_PAGE.

Exit code 1 nếu có file dưới ngưỡng — dùng làm gate trước khi chạy
build_chunks.py.

Chạy: python scripts/verify_processed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import pdfplumber

from src.ingestion.metadata import load_registry

RAW_DIR = "data/raw"
MIN_CHARS_PER_PAGE = 500
MIN_CHARS_NO_PAGE = 300


def pdf_page_count(path: str) -> int | None:
    try:
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception:
        return None


def main() -> None:
    rows = [r for r in load_registry() if r.status == "processed"]
    problems: list[str] = []

    for row in rows:
        if not os.path.exists(row.processed_path):
            print(f"[MISSING] {row.source_file} — processed_path không tồn tại: {row.processed_path}")
            problems.append(f"{row.source_file}: processed_path không tồn tại ({row.processed_path})")
            continue

        with open(row.processed_path, encoding="utf-8") as f:
            n_chars = len(f.read())

        is_pdf = row.source_file.lower().endswith(".pdf")
        raw_path = os.path.join(RAW_DIR, row.category, row.source_file)
        n_pages = pdf_page_count(raw_path) if is_pdf and os.path.exists(raw_path) else None

        if n_pages:
            density = n_chars / n_pages
            ok = density >= MIN_CHARS_PER_PAGE
            tag = "OK" if ok else "CẢNH BÁO"
            print(f"[{tag}] {row.source_file:<70} {n_chars:>8} chars / {n_pages:>4} trang = {density:>8.0f} chars/trang")
            if not ok:
                problems.append(
                    f"{row.source_file}: {density:.0f} chars/trang < ngưỡng {MIN_CHARS_PER_PAGE} "
                    f"— nghi thiếu nội dung, kiểm tra lại (có thể bị 'viết lại theo trí nhớ' thay vì trích xuất thật)"
                )
        else:
            ok = n_chars >= MIN_CHARS_NO_PAGE
            tag = "OK" if ok else "CẢNH BÁO"
            note = "" if not is_pdf else " (không tìm thấy PDF gốc để đối chiếu số trang)"
            print(f"[{tag}] {row.source_file:<70} {n_chars:>8} chars{note}")
            if not ok:
                problems.append(f"{row.source_file}: chỉ {n_chars} chars < ngưỡng {MIN_CHARS_NO_PAGE}")

    print()
    print(f"=== {len(rows)} file processed, {len(problems)} cảnh báo ===")
    if problems:
        print("\nChi tiết cảnh báo:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)


if __name__ == "__main__":
    main()
