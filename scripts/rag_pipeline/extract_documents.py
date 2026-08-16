#!/usr/bin/env python3
"""Trích xuất data/raw/**/* -> data/processed/*.md.

- PDF có text layer thật (đa số trang có đủ chữ): dùng pdfplumber, trích xuất
  trực tiếp, nhanh, không tốn API call.
- PDF dạng scan (không có/rất ít text layer): PHẢI qua VLM từng trang
  (src/ingestion/extractors) — KHÔNG được yêu cầu model "viết lại nội dung
  theo trí nhớ" cho cả file, đó là nguyên nhân gây thiếu/sai nội dung nghiêm
  trọng đã phát hiện ở nghi_dinh_145_2020, luat_an_toan_ve_sinh_lao_dong, v.v.
  (xem CLAUDE.md).
- DOCX: python-docx, lấy paragraph + table.
- MD trong raw/: copy thẳng.

File đã có output trong data/processed/ sẽ bị BỎ QUA trừ khi truyền --force
hoặc liệt kê tên file trong --only.

Chạy: python scripts/rag_pipeline/extract_documents.py [--force] [--only file1.pdf file2.pdf ...]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

# Logic trích xuất nằm ở src/ để ingestion worker (src/workers/ingestion.py) dùng
# lại được cho file Backend upload lên; script này chỉ còn phần quét thư mục.
from src.ingestion.extractors.documents import UnsupportedDocumentError, extract_document, has_real_text_layer

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"


def process_file(path: str, force: bool) -> None:
    stem = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    out_path = os.path.join(OUT_DIR, f"{stem}.md")

    if os.path.exists(out_path) and not force:
        print(f"[skip] {stem} — đã có output")
        return

    if ext == ".pdf" and not has_real_text_layer(path):
        print(f"[vlm] {stem} — PDF dạng scan, trích xuất qua VLM từng trang (có thể mất vài phút)...")

    try:
        content, method = extract_document(path, out_path)
    except UnsupportedDocumentError:
        print(f"[skip] {stem} — định dạng không hỗ trợ ({ext})")
        return

    print(f"[{method}] {out_path} ({len(content)} chars)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ghi đè output đã có")
    parser.add_argument("--only", nargs="*", help="Chỉ xử lý các file có tên khớp (vd nghi_dinh_145_2020_nd_cp.pdf)")
    args = parser.parse_args()

    for root, _dirs, files in os.walk(RAW_DIR):
        for fname in sorted(files):
            if args.only and fname not in args.only:
                continue
            process_file(os.path.join(root, fname), force=args.force or bool(args.only))


if __name__ == "__main__":
    main()
