import os
import re
import time

import pymupdf
import requests

from .pdf_vlm import (
    DPI,
    atomic_write_text,
    extract_page_markdown,
    render_table,
    repair_tables,
    valid_table_blocks,
)

MIN_TABLE_COLS = 2
MIN_TABLE_ROWS = 2


def looks_like_real_table(rows) -> bool:
    return any(all(c is not None and str(c).strip() for c in row) for row in rows)


def find_page_tables(doc: pymupdf.Document) -> dict[int, list]:
    tables_by_page = {}
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        if not text.strip():
            continue
        tables = []
        tab_finder = page.find_tables()
        for tbl in tab_finder.tables:
            rows = tbl.extract()
            if not rows or len(rows) < MIN_TABLE_ROWS or len(rows[0]) < MIN_TABLE_COLS:
                continue
            if not looks_like_real_table(rows):
                continue
            tables.append(rows)
        if tables:
            tables_by_page[i + 1] = tables
    return tables_by_page


def _table_to_lines(rows):
    clean = [
        ["" if c is None else str(c).replace("\n", "<br>").strip() for c in row]
        for row in rows
    ]
    return render_table(clean[0], clean[1:])


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _table_matches_block(table_rows, block_text: str, min_len: int = 4) -> bool:
    haystack = _normalize_text(block_text)
    for row in table_rows:
        for cell in row:
            if not cell:
                continue
            needle = _normalize_text(str(cell))
            if len(needle) >= min_len and needle in haystack:
                return True
    return False


def _substitute_tables(lines, vlm_blocks, page_tables):
    n = min(len(vlm_blocks), len(page_tables))
    out_lines = []
    cursor = 0
    skipped = 0
    for i in range(n):
        start, end = vlm_blocks[i]
        out_lines.extend(lines[cursor:start])
        block_text = "\n".join(lines[start:end])
        if _table_matches_block(page_tables[i], block_text):
            out_lines.extend(_table_to_lines(page_tables[i]))
        else:
            out_lines.extend(lines[start:end])
            skipped += 1
        cursor = end
    out_lines.extend(lines[cursor:])
    return "\n".join(out_lines), skipped


def extract_pdf(pdf_path: str, out_path: str, force: bool = False, log=print) -> None:
    """Trích xuất PDF -> Markdown, page-by-page qua VLM (PyMuPDF cho bảng
    chính xác hơn khi có ô merge phức tạp). KHÔNG bao giờ yêu cầu model "viết
    lại nội dung theo trí nhớ" cho cả file — mỗi trang phải được model nhìn
    thấy ảnh thật và trích xuất riêng."""
    if os.path.exists(out_path) and not force:
        log(f"=== {os.path.basename(out_path)} === đã có output, bỏ qua — dùng force=True để chạy lại")
        return

    log(f"=== {os.path.basename(pdf_path)} ===")

    pages_md = []
    zoom = DPI / 72
    matrix = pymupdf.Matrix(zoom, zoom)

    with pymupdf.open(pdf_path) as doc:
        tables_by_page = find_page_tables(doc)

        for i, page in enumerate(doc):
            page_no = i + 1
            log(f"[page {page_no}] extracting...")
            t0 = time.time()

            pix = page.get_pixmap(matrix=matrix)
            img_bytes = pix.tobytes("png")
            del pix

            try:
                md = extract_page_markdown(img_bytes)
            except requests.exceptions.RequestException as e:
                detail = f" - {e.response.text[:300]}" if e.response is not None else ""
                log(f"[page {page_no}] LỖI: {e}{detail}")
                md = f"<!-- extraction failed: {e} -->"
            finally:
                del img_bytes

            page_tables = tables_by_page.get(page_no, [])
            if page_tables:
                lines = md.splitlines()
                vlm_blocks = valid_table_blocks(lines)
                if len(vlm_blocks) != len(page_tables):
                    log(
                        f"[page {page_no}] CẢNH BÁO: VLM thấy {len(vlm_blocks)} bảng, "
                        f"PyMuPDF thấy {len(page_tables)} bảng — chỉ xét "
                        f"{min(len(vlm_blocks), len(page_tables))} cặp đầu."
                    )
                md, skipped = _substitute_tables(lines, vlm_blocks, page_tables)
                if skipped:
                    log(f"[page {page_no}] CẢNH BÁO: {skipped} cặp bảng không khớp nội dung — giữ nguyên bảng VLM.")

            log(f"[page {page_no}] done in {time.time() - t0:.1f}s, {len(md)} chars")
            pages_md.append(f"<!-- page {page_no} -->\n\n{md}")

    full_md = "\n\n---\n\n".join(pages_md)
    full_md = repair_tables(full_md)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    atomic_write_text(out_path, full_md)
    log(f"Đã lưu: {out_path} ({len(full_md)} chars, {len(pages_md)} trang)")
