from src.ingestion.cleaners import (
    clean_document,
    extract_page_map,
    page_for_offset,
    strip_frontmatter,
)


class TestStripFrontmatter:
    def test_with_frontmatter(self):
        raw = "---\ntitle: Chính sách OT\ndocument_code: HR-POL-OT-2025\n---\n# Nội dung\nAbc\n"
        fm, body = strip_frontmatter(raw)
        assert fm == {"title": "Chính sách OT", "document_code": "HR-POL-OT-2025"}
        assert body == "# Nội dung\nAbc\n"

    def test_without_frontmatter(self):
        raw = "# Nội dung\nAbc\n"
        fm, body = strip_frontmatter(raw)
        assert fm == {}
        assert body == raw

    def test_malformed_yaml_falls_back_to_empty_dict(self):
        raw = "---\nfoo: [unterminated\n---\nBody text\n"
        fm, body = strip_frontmatter(raw)
        assert fm == {}
        assert body == "Body text\n"


class TestExtractPageMap:
    def test_page_markers_recorded_and_removed(self):
        body = "<!-- page 1 -->\n\nNội dung trang 1.\n\n<!-- page 2 -->\n\nNội dung trang 2.\n"
        text, page_offsets = extract_page_map(body)

        assert "<!-- page" not in text
        assert len(page_offsets) == 2
        assert page_offsets[0][1] == 1
        assert page_offsets[1][1] == 2
        # offset của marker trang 2 phải trỏ vào đúng vùng nội dung trang 2 (có
        # thể có dòng trống phân cách đứng trước do dòng trống gốc sau marker
        # được giữ lại làm ranh giới đoạn văn)
        offset2 = page_offsets[1][0]
        assert text[offset2:].strip().startswith("Nội dung trang 2.")

    def test_stray_page_number_after_marker_removed(self):
        body = "<!-- page 1 -->\n12\nNội dung thật.\n"
        text, _ = extract_page_map(body)
        assert "12" not in text.splitlines()
        assert "Nội dung thật." in text

    def test_separator_line_removed(self):
        body = "Đoạn 1.\n\n---\n\nĐoạn 2.\n"
        text, _ = extract_page_map(body)
        assert "---" not in text
        assert "Đoạn 1." in text and "Đoạn 2." in text

    def test_cong_bao_header_removed(self):
        body = "Nội dung.\n2 CÔNG BÁO/Số 123 Ngày 1-1-2026 3\nTiếp theo.\n"
        text, _ = extract_page_map(body)
        assert "CÔNG BÁO" not in text
        assert "Nội dung." in text and "Tiếp theo." in text

    def test_dangling_code_fence_removed(self):
        body = "```markdown\nNội dung trong fence.\n```\nSau fence.\n"
        text, _ = extract_page_map(body)
        assert "```" not in text
        assert "Sau fence." in text

    def test_degenerate_empty_table_run_removed(self):
        rows = "\n".join(["|  |  |"] * 6)
        body = f"Trước bảng.\n{rows}\nSau bảng.\n"
        text, _ = extract_page_map(body)
        assert "|  |  |" not in text
        assert "Trước bảng." in text and "Sau bảng." in text

    def test_short_table_run_kept(self):
        # Dưới ngưỡng _DEGENERATE_TABLE_MIN_RUN (4) -> giữ nguyên, có thể là
        # bảng thật chỉ vài dòng, không phải hallucination.
        rows = "\n".join(["|  |  |"] * 2)
        body = f"Trước bảng.\n{rows}\nSau bảng.\n"
        text, _ = extract_page_map(body)
        assert text.count("|  |  |") == 2

    def test_multiple_blank_lines_collapsed(self):
        body = "Đoạn 1.\n\n\n\n\nĐoạn 2.\n"
        text, _ = extract_page_map(body)
        assert "\n\n\n" not in text


class TestPageForOffset:
    def test_no_page_offsets_returns_none(self):
        assert page_for_offset([], 10) is None

    def test_offset_before_first_marker_clamped_to_first_page(self):
        assert page_for_offset([(50, 3)], 0) == 3

    def test_offset_between_markers_returns_earlier_page(self):
        offsets = [(0, 1), (100, 2), (250, 3)]
        assert page_for_offset(offsets, 150) == 2
        assert page_for_offset(offsets, 100) == 2
        assert page_for_offset(offsets, 99) == 1

    def test_offset_after_last_marker_returns_last_page(self):
        offsets = [(0, 1), (100, 2)]
        assert page_for_offset(offsets, 9999) == 2


class TestCleanDocument:
    def test_combines_frontmatter_strip_and_page_map(self):
        raw = "---\ntitle: X\n---\n<!-- page 1 -->\n\nNội dung.\n"
        cleaned = clean_document(raw)
        assert cleaned.frontmatter == {"title": "X"}
        assert "Nội dung." in cleaned.text
        assert cleaned.page_offsets[0][1] == 1
