import zipfile

from src.config import get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.extractors.documents import extract_document


def _write_minimal_xlsx(path) -> None:
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Roadmap" sheetId="1" r:id="rId1"/></sheets>
    </workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
    </Relationships>"""
    worksheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
      <row r="1"><c r="A1" t="str"><v>Product Roadmap</v></c></row>
      <row r="3"><c r="A3" t="str"><v>Feature</v></c><c r="B3" t="str"><v>Status</v></c></row>
      <row r="4"><c r="A4" t="str"><v>Checkout Redesign</v></c><c r="B4" t="str"><v>In Progress</v></c></row>
    </sheetData></worksheet>"""
    styles = """<?xml version="1.0" encoding="UTF-8"?>
    <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <cellXfs count="1"><xf numFmtId="0"/></cellXfs>
    </styleSheet>"""
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", relationships)
        book.writestr("xl/worksheets/sheet1.xml", worksheet)
        book.writestr("xl/styles.xml", styles)


def test_extract_xlsx_and_preserve_sheet_metadata(tmp_path):
    source = tmp_path / "roadmap.xlsx"
    output = tmp_path / "roadmap.md"
    _write_minimal_xlsx(source)

    content, method = extract_document(str(source), str(output))

    assert method == "xlsx"
    assert "<!-- sheet: Roadmap -->" in content
    assert "Checkout Redesign" in content
    assert "| Feature | Status |" in content

    settings = get_settings().model_copy(
        update={"chunk_target_chars": 500, "chunk_max_chars": 1000, "chunk_min_chars": 0}
    )
    chunks = build_chunks_from_text(
        content,
        source_file="roadmap.xlsx",
        department="Product",
        category="ROADMAP",
        source_type="synthetic",
        is_official_policy=True,
        settings=settings,
    )
    assert chunks
    assert all(chunk.metadata.department == "PRODUCT" for chunk in chunks)
    assert all(chunk.metadata.sheet_start == "Roadmap" for chunk in chunks)
