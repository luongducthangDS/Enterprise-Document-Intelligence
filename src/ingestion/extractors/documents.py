"""Trích xuất 1 file nguồn (PDF/DOCX/MD) thành markdown ở data/processed/.

Trước đây logic này chỉ nằm trong scripts/rag_pipeline/extract_documents.py nên
chỉ chạy được ngoại tuyến bằng CLI. Ingestion worker (src/workers/ingestion.py)
cần đúng logic đó cho file do Backend upload lên, vì vậy phần thuần xử lý được
chuyển vào đây; script giữ nguyên vai trò CLI đi quét data/raw/.
"""

import os

import docx
import pdfplumber

from .pdf_extractor import extract_pdf

# Trang được coi là "có text layer thật" nếu pdfplumber đọc được > 200 ký tự.
# PDF được coi là scan (cần VLM) nếu số trang có text layer < 50% tổng số trang.
TEXT_LAYER_MIN_CHARS_PER_PAGE = 200
TEXT_LAYER_MIN_RATIO = 0.5

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".md")


class UnsupportedDocumentError(ValueError):
    """Định dạng file không nằm trong SUPPORTED_EXTENSIONS."""


def has_real_text_layer(pdf_path: str) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        if n == 0:
            return False
        pages_with_text = sum(
            1 for p in pdf.pages if len(p.extract_text() or "") >= TEXT_LAYER_MIN_CHARS_PER_PAGE
        )
        return (pages_with_text / n) >= TEXT_LAYER_MIN_RATIO


def extract_pdf_text_layer(pdf_path: str, out_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = []
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages_text.append(f"<!-- page {i} -->\n\n{text}")
    full_text = "\n\n---\n\n".join(pages_text)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    return _write_markdown(out_path, stem, full_text)


def extract_docx(docx_path: str, out_path: str) -> str:
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
    return _write_markdown(out_path, stem, full_text)


def copy_md(src_path: str, out_path: str) -> str:
    with open(src_path, encoding="utf-8") as f:
        content = f.read()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def _write_markdown(out_path: str, stem: str, body: str) -> str:
    content = f"# {stem}\n\n{body}"
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def extract_document(src_path: str, out_path: str) -> tuple[str, str]:
    """Trích xuất src_path -> out_path (markdown). Trả về (nội dung, phương pháp).

    Phương pháp: "text-layer" | "vlm" | "docx" | "copy" — dùng cho log/telemetry
    để biết file nào đi đường VLM (tốn API, chậm hàng phút).
    """
    ext = os.path.splitext(src_path)[1].lower()

    if ext == ".pdf":
        if has_real_text_layer(src_path):
            return extract_pdf_text_layer(src_path, out_path), "text-layer"
        extract_pdf(src_path, out_path, force=True)
        with open(out_path, encoding="utf-8") as f:
            return f.read(), "vlm"
    if ext in (".docx", ".doc"):
        return extract_docx(src_path, out_path), "docx"
    if ext == ".md":
        return copy_md(src_path, out_path), "copy"

    raise UnsupportedDocumentError(
        f"Định dạng không hỗ trợ: {ext or '(không có đuôi file)'}. "
        f"Chỉ nhận {', '.join(SUPPORTED_EXTENSIONS)}."
    )
