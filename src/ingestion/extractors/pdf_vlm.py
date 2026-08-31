import os
import re

import pymupdf

from src.config import get_settings
from src.services.fpt_client import extract_page_markdown as _fpt_extract_page_markdown

VLM_MODEL = "Qwen2.5-VL-7B-Instruct"
DPI = 150

PROMPT = (
    "Trích xuất toàn bộ nội dung trang này sang Markdown. "
    "Giữ nguyên cấu trúc heading, danh sách và bảng (dùng cú pháp bảng Markdown). "
    "Nếu bảng có ô bị gộp (merge) theo chiều dọc hoặc ngang, hãy lặp lại giá trị đó ở "
    "TẤT CẢ các hàng/cột mà ô gộp bao phủ — không được để trống. Mỗi hàng markdown phải "
    "có đủ số cột và đúng vị trí cột gốc. Nếu trang này là phần tiếp theo của một bảng "
    "chưa có tiêu đề hiển thị trên trang, hãy xuất các hàng dữ liệu bình thường, không tự "
    "tạo tiêu đề giả từ hàng dữ liệu đầu tiên. "
    "Không thêm bình luận hay giải thích, chỉ trả về nội dung Markdown của trang."
)


def atomic_write_text(path: str, text: str) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp_path, path)


def pdf_to_page_images(pdf_path: str, dpi: int = DPI):
    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix)
            img_bytes = pix.tobytes("png")
            del pix
            yield i + 1, img_bytes


def strip_markdown_fence(text: str) -> str:
    m = re.fullmatch(r"```(?:markdown)?\s*\n(.*?)\n?```\s*", text.strip(), re.DOTALL)
    return m.group(1) if m else text


def extract_page_markdown(image_bytes: bytes, model: str | None = None, retries: int = 2) -> str:
    """Trích xuất trang PDF qua VLM. Khi USE_GLM=OFF tự động dùng OpenAI gpt-4o vision."""
    from src.agents.llm import resolve_vlm_endpoint

    vlm_model, vlm_base_url, vlm_api_key = resolve_vlm_endpoint(model=model)
    content = _fpt_extract_page_markdown(
        image_bytes,
        prompt=PROMPT,
        model=vlm_model,
        base_url=vlm_base_url,
        api_key=vlm_api_key,
        retries=retries,
    )
    return strip_markdown_fence(content)


# ---------- Table repair: forward-fill merged cells + stitch cross-page tables ----------
TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
SEP_CELL_RE = re.compile(r"^:?-+:?$")
PAGE_BOUNDARY_RE = re.compile(r"^\s*(<!--\s*page\s+\d+\s*-->|-{3,})\s*$")


def split_row(line: str):
    m = TABLE_ROW_RE.match(line)
    inner = m.group(1) if m else line.strip().strip("|")
    return [c.strip() for c in inner.split("|")]


def is_separator_row(cells) -> bool:
    return bool(cells) and all(SEP_CELL_RE.match(c) for c in cells)


def only_boundary_lines(gap_lines) -> bool:
    has_marker = False
    for line in gap_lines:
        if not line.strip():
            continue
        if not PAGE_BOUNDARY_RE.match(line):
            return False
        has_marker = True
    return has_marker


def find_table_blocks(lines):
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        if TABLE_ROW_RE.match(lines[i]):
            start = i
            while i < n and TABLE_ROW_RE.match(lines[i]):
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def valid_table_blocks(lines):
    out = []
    for start, end in find_table_blocks(lines):
        if (end - start) >= 2 and is_separator_row(split_row(lines[start + 1])):
            out.append((start, end))
    return out


def ffill_rows(ncols: int, data_rows):
    last = [None] * ncols
    out = []
    for row in data_rows:
        row = (list(row) + [""] * ncols)[:ncols]
        new_row = []
        for idx, cell in enumerate(row):
            cell = cell.strip()
            if cell:
                last[idx] = cell
                new_row.append(cell)
            else:
                new_row.append(last[idx] or "")
        out.append(new_row)
    return out


def render_table(header_cells, data_rows):
    out = ["| " + " | ".join(header_cells) + " |"]
    out.append("|" + "|".join(["---"] * len(header_cells)) + "|")
    for row in data_rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def repair_tables(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    groups = []
    cur = None
    for start, end in valid_table_blocks(lines):
        header_cells = split_row(lines[start])
        ncols = len(header_cells)
        data_rows = [split_row(line) for line in lines[start + 2 : end]]
        if (
            cur is not None
            and only_boundary_lines(lines[cur["span_end"] : start])
            and ncols == cur["ncols"]
        ):
            cur["data_rows"].append(header_cells)
            cur["data_rows"].extend(data_rows)
            cur["span_end"] = end
        else:
            cur = {
                "span_start": start,
                "span_end": end,
                "ncols": ncols,
                "header": header_cells,
                "data_rows": data_rows,
            }
            groups.append(cur)

    out_lines = []
    cursor = 0
    for g in groups:
        out_lines.extend(lines[cursor : g["span_start"]])
        filled = ffill_rows(g["ncols"], g["data_rows"])
        out_lines.extend(render_table(g["header"], filled))
        cursor = g["span_end"]
    out_lines.extend(lines[cursor:])
    return "\n".join(out_lines)
