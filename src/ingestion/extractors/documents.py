"""Trích xuất 1 file nguồn (PDF/DOCX/MD) thành markdown ở data/processed/.

Trước đây logic này chỉ nằm trong scripts/rag_pipeline/extract_documents.py nên
chỉ chạy được ngoại tuyến bằng CLI. Ingestion worker (src/workers/ingestion.py)
cần đúng logic đó cho file do Backend upload lên, vì vậy phần thuần xử lý được
chuyển vào đây; script giữ nguyên vai trò CLI đi quét data/raw/.
"""

import os
import re
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree

import docx
import fitz
import pdfplumber

from .pdf_extractor import extract_pdf
from .pdf_vlm import extract_page_markdown

# Trang được coi là "có text layer thật" nếu pdfplumber đọc được > 200 ký tự.
# PDF được coi là scan (cần VLM) nếu số trang có text layer < 50% tổng số trang.
TEXT_LAYER_MIN_CHARS_PER_PAGE = 200
TEXT_LAYER_MIN_RATIO = 0.5

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".md", ".png", ".jpg", ".jpeg", ".webp")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

_XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DATE_FORMAT_IDS = set(range(14, 23)) | set(range(45, 48))
_DATE_FORMAT_RE = re.compile(r"(?i)(?<!\\)[ymdhis]")


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


def _xlsx_shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.findall(".//x:t", _XLSX_NS)) for item in root]


def _xlsx_date_styles(book: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in book.namelist():
        return set()
    root = ElementTree.fromstring(book.read("xl/styles.xml"))
    custom_formats = {
        int(item.attrib["numFmtId"]): item.attrib.get("formatCode", "")
        for item in root.findall("x:numFmts/x:numFmt", _XLSX_NS)
    }
    date_styles: set[int] = set()
    for index, xf in enumerate(root.findall("x:cellXfs/x:xf", _XLSX_NS)):
        fmt_id = int(xf.attrib.get("numFmtId", "0"))
        fmt = re.sub(r'"[^"]*"|\\.', "", custom_formats.get(fmt_id, ""))
        if fmt_id in _DATE_FORMAT_IDS or _DATE_FORMAT_RE.search(fmt):
            date_styles.add(index)
    return date_styles


def _xlsx_column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    value = 0
    for char in letters.group(0) if letters else "A":
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def _xlsx_cell_value(cell, shared_strings: list[str], date_styles: set[int]) -> str:
    cell_type = cell.attrib.get("t", "n")
    value_node = cell.find("x:v", _XLSX_NS)
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", _XLSX_NS))
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    style = int(cell.attrib.get("s", "0"))
    if value and style in date_styles:
        try:
            parsed = datetime(1899, 12, 30) + timedelta(days=float(value))
            return parsed.strftime("%Y-%m-%d" if parsed.time() == datetime.min.time() else "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if cell_type == "n" and value.endswith(".0"):
        return value[:-2]
    return value


def _markdown_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    width = max(len(row) for row in rows)
    normalized = [(row + [""] * width)[:width] for row in rows]
    first_table_row = next((i for i, row in enumerate(normalized) if sum(bool(v) for v in row) > 1), 0)
    out: list[str] = []
    for row in normalized[:first_table_row]:
        values = [v for v in row if v]
        if values:
            out.append(f"### {' — '.join(values)}")
    table = normalized[first_table_row:]
    if not table:
        return out
    def escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", "<br>")

    out.append("| " + " | ".join(escape(v) for v in table[0]) + " |")
    out.append("|" + "|".join(["---"] * width) + "|")
    out.extend("| " + " | ".join(escape(v) for v in row) + " |" for row in table[1:])
    return out


def extract_xlsx(xlsx_path: str, out_path: str) -> str:
    """Trích toàn bộ worksheet sang Markdown và giữ marker sheet cho citation."""
    with zipfile.ZipFile(xlsx_path) as book:
        shared_strings = _xlsx_shared_strings(book)
        date_styles = _xlsx_date_styles(book)
        workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships.findall("r:Relationship", _REL_NS)}

        sections: list[str] = []
        for sheet in workbook.findall("x:sheets/x:sheet", _XLSX_NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib[f"{{{_OFFICE_REL_NS}}}id"]
            target = targets[rel_id].replace("\\", "/").lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            root = ElementTree.fromstring(book.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.findall(".//x:sheetData/x:row", _XLSX_NS):
                values: list[str] = []
                for cell in row.findall("x:c", _XLSX_NS):
                    index = _xlsx_column_index(cell.attrib.get("r", "A1"))
                    if len(values) <= index:
                        values.extend([""] * (index + 1 - len(values)))
                    values[index] = _xlsx_cell_value(cell, shared_strings, date_styles).strip()
                while values and not values[-1]:
                    values.pop()
                if any(values):
                    rows.append(values)
            sections.append(f"<!-- sheet: {name} -->\n\n## Sheet: {name}\n\n" + "\n".join(_markdown_table(rows)))

    stem = os.path.splitext(os.path.basename(xlsx_path))[0]
    return _write_markdown(out_path, stem, "\n\n---\n\n".join(sections))


def copy_md(src_path: str, out_path: str) -> str:
    with open(src_path, encoding="utf-8") as f:
        content = f.read()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def extract_image(image_path: str, out_path: str) -> str:
    """Normalize a standalone image to PNG, then extract it with the existing VLM."""
    try:
        with fitz.open(image_path) as document:
            if document.page_count != 1:
                raise UnsupportedDocumentError("File ảnh không hợp lệ hoặc có nhiều hơn một frame.")
            image_bytes = document[0].get_pixmap().tobytes("png")
    except UnsupportedDocumentError:
        raise
    except Exception as exc:
        raise UnsupportedDocumentError("Không đọc được nội dung ảnh.") from exc
    markdown = extract_page_markdown(image_bytes)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    return _write_markdown(out_path, stem, markdown)


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
    if ext == ".xlsx":
        return extract_xlsx(src_path, out_path), "xlsx"
    if ext == ".md":
        return copy_md(src_path, out_path), "copy"
    if ext in IMAGE_EXTENSIONS:
        return extract_image(src_path, out_path), "vlm-image"

    raise UnsupportedDocumentError(
        f"Định dạng không hỗ trợ: {ext or '(không có đuôi file)'}. "
        f"Chỉ nhận {', '.join(SUPPORTED_EXTENSIONS)}."
    )
