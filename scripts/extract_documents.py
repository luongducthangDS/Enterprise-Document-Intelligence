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

Chạy: python scripts/extract_documents.py [--force] [--only file1.pdf file2.pdf ...]
"""
import argparse
import os
import sys

import docx
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.ingestion.extractors import extract_pdf

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"

# Trang được coi là "có text layer thật" nếu pdfplumber đọc được > 200 ký tự.
# PDF được coi là scan (cần VLM) nếu số trang có text layer < 50% tổng số trang.
TEXT_LAYER_MIN_CHARS_PER_PAGE = 200
TEXT_LAYER_MIN_RATIO = 0.5


def has_real_text_layer(pdf_path: str) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        if n == 0:
            return False
        pages_with_text = sum(
            1 for p in pdf.pages if len(p.extract_text() or "") >= TEXT_LAYER_MIN_CHARS_PER_PAGE
        )
        return (pages_with_text / n) >= TEXT_LAYER_MIN_RATIO


def extract_pdf_text_layer(pdf_path: str, out_path: str) -> None:
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = []
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages_text.append(f"<!-- page {i} -->\n\n{text}")
    full_text = "\n\n---\n\n".join(pages_text)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {stem}\n\n{full_text}")
    print(f"[text-layer] {out_path} ({len(full_text)} chars, {len(pages_text)} trang)")


def extract_docx(docx_path: str, out_path: str) -> None:
    d = docx.Document(docx_path)
    paragraphs = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    table_lines = []
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells if c.text.strip()]
            if cells:
                table_lines.append(" | ".join(cells))

    full_text = "\n\n".join(paragraphs)
    if table_lines:
        full_text += "\n\n### BẢNG BIỂU / DỮ LIỆU BẢNG\n\n" + "\n".join(table_lines)
    full_text = full_text.strip()

    stem = os.path.splitext(os.path.basename(docx_path))[0]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {stem}\n\n{full_text}")
    print(f"[docx] {out_path} ({len(full_text)} chars)")


def copy_md(src_path: str, out_path: str) -> None:
    with open(src_path, encoding="utf-8") as f:
        content = f.read()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[copy] {out_path} ({len(content)} chars)")


def process_file(path: str, force: bool) -> None:
    stem = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    out_path = os.path.join(OUT_DIR, f"{stem}.md")

    if os.path.exists(out_path) and not force:
        print(f"[skip] {stem} — đã có output")
        return

    if ext == ".pdf":
        if has_real_text_layer(path):
            extract_pdf_text_layer(path, out_path)
        else:
            print(f"[vlm] {stem} — PDF dạng scan, trích xuất qua VLM từng trang (có thể mất vài phút)...")
            extract_pdf(path, out_path, force=True)
    elif ext in (".docx", ".doc"):
        extract_docx(path, out_path)
    elif ext == ".md":
        copy_md(path, out_path)
    else:
        print(f"[skip] {stem} — định dạng không hỗ trợ ({ext})")


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
