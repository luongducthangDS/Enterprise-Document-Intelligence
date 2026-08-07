import importlib

from src.ingestion.extractors import pdf_vlm
from src.ingestion.extractors.pdf_vlm import (
    ffill_rows,
    find_table_blocks,
    is_separator_row,
    only_boundary_lines,
    render_table,
    repair_tables,
    split_row,
    strip_markdown_fence,
    valid_table_blocks,
)


def test_import_does_not_require_fpt_api_key_env(monkeypatch):
    """Regression test cho fix #1: trước đây module đọc os.environ['FPT_API_KEY']
    ở module-level, khiến import crash nếu thiếu biến môi trường dù chỉ cần
    nhánh pdfplumber text-layer (không cần VLM). Giờ phải đọc lazy qua
    get_settings() bên trong hàm, nên import/reload không được phép raise dù
    thiếu FPT_API_KEY."""
    monkeypatch.delenv("FPT_API_KEY", raising=False)
    importlib.reload(pdf_vlm)  # không raise KeyError


class TestStripMarkdownFence:
    def test_strips_markdown_fence(self):
        assert strip_markdown_fence("```markdown\nfoo\n```") == "foo"

    def test_strips_bare_fence(self):
        assert strip_markdown_fence("```\nfoo\n```") == "foo"

    def test_no_fence_returns_unchanged(self):
        assert strip_markdown_fence("foo bar") == "foo bar"


class TestSplitRow:
    def test_pipe_delimited_with_edges(self):
        assert split_row("| a | b | c |") == ["a", "b", "c"]

    def test_pipe_delimited_without_edges(self):
        assert split_row("a | b") == ["a", "b"]


class TestIsSeparatorRow:
    def test_dashes_are_separator(self):
        assert is_separator_row(["---", "---"]) is True

    def test_data_is_not_separator(self):
        assert is_separator_row(["abc", "---"]) is False

    def test_empty_list_is_not_separator(self):
        assert is_separator_row([]) is False


class TestFfillRows:
    def test_forward_fills_empty_cells_per_column(self):
        rows = [["1", "x"], ["", "y"], ["2", ""]]
        out = ffill_rows(2, rows)
        assert out == [["1", "x"], ["1", "y"], ["2", "y"]]

    def test_pads_short_rows(self):
        out = ffill_rows(3, [["1", "2"]])
        assert out == [["1", "2", ""]]


class TestRenderTable:
    def test_renders_header_separator_and_rows(self):
        out = render_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert out == ["| A | B |", "|---|---|", "| 1 | 2 |", "| 3 | 4 |"]


class TestFindAndValidTableBlocks:
    def test_finds_contiguous_pipe_lines(self):
        lines = ["text", "| a | b |", "| --- | --- |", "| 1 | 2 |", "text2"]
        assert find_table_blocks(lines) == [(1, 4)]

    def test_valid_requires_separator_second_row(self):
        lines = ["| a | b |", "| --- | --- |", "| 1 | 2 |"]
        assert valid_table_blocks(lines) == [(0, 3)]

    def test_invalid_without_separator_row(self):
        lines = ["| a | b |", "| 1 | 2 |"]
        assert valid_table_blocks(lines) == []


class TestOnlyBoundaryLines:
    def test_true_for_page_marker_and_blank_lines(self):
        assert only_boundary_lines(["", "<!-- page 2 -->", ""]) is True

    def test_false_when_real_content_present(self):
        assert only_boundary_lines(["", "Ghi chú thật", ""]) is False

    def test_false_when_no_marker_at_all(self):
        assert only_boundary_lines(["", ""]) is False


class TestRepairTables:
    def test_ffill_within_single_table(self):
        md = "| A | B |\n| --- | --- |\n| 1 | x |\n|  | y |\n"
        out = repair_tables(md)
        rows = [split_row(line) for line in out.splitlines() if line.strip().startswith("|")]
        assert rows[0] == ["A", "B"]
        assert rows[2] == ["1", "x"]
        assert rows[3] == ["1", "y"]  # cột A được forward-fill từ hàng trước

    def test_non_table_content_untouched(self):
        # repair_tables đi qua splitlines()+join("\n") nên không giữ newline cuối file
        md = "Đoạn văn thường.\n\nKhông có bảng nào ở đây.\n"
        assert repair_tables(md) == md.rstrip("\n")

    def test_different_column_count_not_merged(self):
        md = (
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
            "\n<!-- page 2 -->\n\n"
            "| X | Y | Z |\n| --- | --- | --- |\n| 3 | 4 | 5 |\n"
        )
        out = repair_tables(md)
        # cả 2 bảng (2 cột và 3 cột) đều còn nguyên trong output, không gộp nhầm
        assert "| A | B |" in out
        assert "| X | Y | Z |" in out
