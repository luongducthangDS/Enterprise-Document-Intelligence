import bisect
import re
from dataclasses import dataclass, field

import yaml

# Cùng định nghĩa "page marker" với src/ingestion/extractors/pdf_vlm.py để 2 giai
# đoạn (extract, ingest) luôn thống nhất — nhưng ở đây cần bắt được số trang, không
# chỉ phát hiện ranh giới.
PAGE_MARKER_RE = re.compile(r"^[ \t]*<!--\s*page\s+(\d+)\s*-->[ \t]*$")
SEPARATOR_LINE_RE = re.compile(r"^[ \t]*-{3,}[ \t]*$")
STRAY_PAGE_NUMBER_RE = re.compile(r"^[ \t]*\d{1,3}[ \t]*$")
# Header/footer lặp lại trên mọi trang của PDF Công báo (vd luat51.md, luat_bao_hiem_xa_hoi...)
# — pdfplumber đọc thẳng text layer nên dòng này lẫn vào giữa nội dung, không có
# marker riêng như <!-- page N --> để loại theo cách khác.
CONG_BAO_HEADER_RE = re.compile(r"^[ \t]*\d{0,3}[ \t]*CÔNG BÁO/Số.*Ngày\s+\d{1,2}-\d{1,2}-\d{4}[ \t]*\d{0,3}[ \t]*$")

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?", re.DOTALL)

# VLM extract đôi khi hallucinate 1 bảng markdown toàn ô rỗng trên trang gần trắng
# (vd trang chữ ký cuối văn bản) — hàng trăm dòng "|  |  |" không mang nội dung
# gì, làm phình 1 chunk lên hàng chục nghìn ký tự. Phát hiện và bỏ các đoạn liên
# tiếp gồm toàn dòng bảng rỗng/dòng phân cách.
EMPTY_TABLE_ROW_RE = re.compile(r"^\s*\|(?:\s*\|)+\s*$")
TABLE_SEPARATOR_ROW_RE = re.compile(r"^\s*\|(?:[\s:-]*\|)+\s*$")
_DEGENERATE_TABLE_MIN_RUN = 4

# Fence '```' hoặc '```markdown' trơ trọi sót lại sau khi VLM không đóng đúng
# code block (pdf_vlm.py có strip_markdown_fence nhưng chỉ bắt trường hợp fence
# bọc TOÀN BỘ nội dung 1 trang — không bắt được fence rơi rớt giữa/cuối trang).
CODE_FENCE_RE = re.compile(r"^\s*```\w*\s*$")


@dataclass
class CleanedDocument:
    frontmatter: dict = field(default_factory=dict)
    text: str = ""
    # (char_offset trong text, so_trang) — sắp xếp theo char_offset tăng dần
    page_offsets: list[tuple[int, int]] = field(default_factory=list)


def strip_frontmatter(raw_text: str) -> tuple[dict, str]:
    """Tách YAML frontmatter (nếu có) ra khỏi phần thân. Không phải file processed
    nào cũng có frontmatter (chỉ các file synthetic V-NOVA và talentnet có)."""
    m = FRONTMATTER_RE.match(raw_text)
    if not m:
        return {}, raw_text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = raw_text[m.end():]
    return fm, body


def extract_page_map(body: str) -> tuple[str, list[tuple[int, int]]]:
    """Một lượt duyệt theo dòng, làm mọi việc chuẩn hoá trong CÙNG 1 pass để
    page_offsets tính ra luôn khớp với text cuối cùng (không có bước xử lý nào
    sau đó làm lệch offset):
    - bỏ marker <!-- page N --> (ghi lại vị trí bắt đầu trang tương ứng)
    - bỏ dòng phân cách '---' đứng riêng, và fence ``` trơ trọi
    - bỏ số trang trơ trọi còn sót lại ngay sau ranh giới trang (rác OCR/VLM)
    - bỏ các đoạn dài toàn dòng bảng markdown rỗng (VLM hallucinate bảng trên
      trang gần trắng — vd trang chữ ký cuối văn bản)
    - rstrip từng dòng, gộp nhiều dòng trống liên tiếp thành tối đa 1 dòng trống
    """
    lines = body.splitlines()
    out_lines: list[str] = []
    page_offsets: list[tuple[int, int]] = []
    out_len = 0
    just_saw_page_marker = False
    pending_blank = False
    table_run_buffer: list[str] = []

    def emit(line: str) -> None:
        nonlocal out_len
        if out_lines:
            out_len += 1  # ký tự '\n' sẽ nối trước dòng này khi join
        out_lines.append(line)
        out_len += len(line)

    def flush_table_run() -> None:
        nonlocal table_run_buffer
        if len(table_run_buffer) < _DEGENERATE_TABLE_MIN_RUN:
            for buffered in table_run_buffer:
                emit(buffered)
        table_run_buffer = []

    for raw_line in lines:
        stripped = raw_line.strip()

        m = PAGE_MARKER_RE.match(stripped)
        if m:
            flush_table_run()
            page_offsets.append((out_len, int(m.group(1))))
            just_saw_page_marker = True
            pending_blank = False
            continue

        if EMPTY_TABLE_ROW_RE.match(stripped) or TABLE_SEPARATOR_ROW_RE.match(stripped):
            table_run_buffer.append(raw_line.rstrip())
            continue
        if table_run_buffer:
            flush_table_run()

        if SEPARATOR_LINE_RE.match(stripped) or CONG_BAO_HEADER_RE.match(stripped) or CODE_FENCE_RE.match(stripped):
            continue

        if not stripped:
            pending_blank = True
            continue

        if just_saw_page_marker and STRAY_PAGE_NUMBER_RE.match(stripped):
            just_saw_page_marker = False
            pending_blank = False
            continue

        just_saw_page_marker = False
        if pending_blank and out_lines:
            emit("")
        pending_blank = False
        emit(raw_line.rstrip())

    flush_table_run()
    text = "\n".join(out_lines) + "\n" if out_lines else ""
    return text, page_offsets


def clean_document(raw_text: str) -> CleanedDocument:
    frontmatter, body = strip_frontmatter(raw_text)
    text, page_offsets = extract_page_map(body)
    return CleanedDocument(frontmatter=frontmatter, text=text, page_offsets=page_offsets)


def page_for_offset(page_offsets: list[tuple[int, int]], offset: int) -> int | None:
    """Trang chứa vị trí `offset` trong text đã dọn, dựa vào page_offsets đã tính
    ở clean_document(). None nếu tài liệu không có page marker (không phải extract
    qua VLM/scan, ví dụ file docx/synthetic)."""
    if not page_offsets:
        return None
    starts = [o for o, _ in page_offsets]
    idx = bisect.bisect_right(starts, offset) - 1
    idx = max(0, idx)
    return page_offsets[idx][1]
