import re

from src.ingestion.chunkers import _word_boundary_tail, chunk_text, classify_line


class TestClassifyLine:
    def test_chapter_no_hash(self):
        assert classify_line("Chương I. QUY ĐỊNH CHUNG") == ("chapter", "Chương I. QUY ĐỊNH CHUNG")

    def test_article_no_hash(self):
        assert classify_line("Điều 1. Phạm vi điều chỉnh") == ("article", "Điều 1. Phạm vi điều chỉnh")

    def test_section_no_hash(self):
        assert classify_line("Mục 2. Hợp đồng lao động") == ("section", "Mục 2. Hợp đồng lao động")

    def test_roman_numeral_section_standalone(self):
        # Kiểu VinFast/mẫu quy chế lương: mục lớn đánh số La Mã đứng riêng,
        # không có markdown '#'.
        assert classify_line("I. TUYÊN NGÔN GIÁ TRỊ") == ("chapter", "I. TUYÊN NGÔN GIÁ TRỊ")
        assert classify_line("XII. ĐIỀU KHOẢN THI HÀNH") == ("chapter", "XII. ĐIỀU KHOẢN THI HÀNH")

    def test_roman_numeral_rejects_invalid_numeral(self):
        # "IIII." không phải số La Mã hợp lệ (dù regex ký tự vẫn khớp hình thức)
        assert classify_line("IIII. Không hợp lệ") is None

    def test_hash_heading_generic(self):
        assert classify_line("# CHÍNH PHỦ") == ("heading", "CHÍNH PHỦ")

    def test_policy_section_requires_hash(self):
        # '1. Người lao động...' không có '#' -> đây là khoản liệt kê THƯỜNG
        # nằm trong thân 1 Điều, KHÔNG phải ranh giới — POLICY_SECTION_RE chỉ
        # được áp dụng khi có '#' (xem comment trong chunkers.py).
        assert classify_line("1. Người lao động có quyền làm việc.") is None

    def test_policy_section_with_hash(self):
        assert classify_line("## 1. Mục tiêu chính sách") == ("policy_section", "1. Mục tiêu chính sách")

    def test_quoted_line_is_not_boundary(self):
        # Trích dẫn nội dung sửa đổi trong thân 1 Điều khác (luat51.md), không
        # phải ranh giới thật dù bắt đầu bằng "Điều".
        assert classify_line('"Điều 7a. Nội dung được trích dẫn sửa đổi."') is None
        assert classify_line("“Điều 7a. Trích dẫn dấu ngoặc kép kiểu Unicode.”") is None

    def test_empty_line(self):
        assert classify_line("") is None
        assert classify_line("   ") is None


class TestChunkTextStructured:
    def test_boundaries_and_offsets_are_contiguous(self):
        text = (
            "Chương I. QUY ĐỊNH CHUNG\n\n"
            "Điều 1. Phạm vi điều chỉnh\n"
            "Bộ luật này quy định tiêu chuẩn lao động.\n\n"
            "Điều 2. Đối tượng áp dụng\n"
            "Bộ luật này áp dụng đối với người lao động.\n"
        )
        chunks = chunk_text(text, target_chars=1000, max_chars=2000, min_chars=0)

        assert len(chunks) == 3
        assert chunks[0].heading_path == "Chương I. QUY ĐỊNH CHUNG"
        assert chunks[0].chapter is None
        assert chunks[1].heading_path == "Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh"
        assert chunks[1].chapter == "Chương I. QUY ĐỊNH CHUNG"
        assert chunks[1].article == "Điều 1. Phạm vi điều chỉnh"
        assert chunks[2].article == "Điều 2. Đối tượng áp dụng"
        assert chunks[2].heading_path == "Chương I. QUY ĐỊNH CHUNG > Điều 2. Đối tượng áp dụng"

        # start/end phải khớp offset thật trong text gốc (sau strip)
        for c in chunks:
            assert text[c.start:c.end].strip() == c.text

        # contiguous: không có khoảng trống/chồng lấn giữa các đoạn liên tiếp
        assert chunks[0].start == 0
        assert chunks[-1].end == len(text)
        for a, b in zip(chunks, chunks[1:]):
            assert a.end == b.start

    def test_first_undersized_title_merges_into_next(self):
        # Với min_chars mặc định (200), dòng "Chương I..." đứng một mình quá
        # ngắn -> phải gộp vào đoạn kế (Điều 1), không đứng thành 1 chunk rỗng.
        text = (
            "Chương I. QUY ĐỊNH CHUNG\n\n"
            "Điều 1. Phạm vi điều chỉnh\n"
            + ("Bộ luật này quy định tiêu chuẩn lao động, quyền và nghĩa vụ. " * 5)
            + "\n\n"
            "Điều 2. Đối tượng áp dụng\n"
            + ("Bộ luật này áp dụng đối với người lao động Việt Nam. " * 5)
        )
        chunks = chunk_text(text, target_chars=1000, max_chars=2000, min_chars=200)

        assert len(chunks) == 2
        assert chunks[0].text.startswith("Chương I. QUY ĐỊNH CHUNG")
        assert "Điều 1." in chunks[0].text
        assert chunks[0].heading_path == "Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh"
        assert chunks[1].article == "Điều 2. Đối tượng áp dụng"

    def test_merge_undersized_does_not_cross_chapter_boundary(self):
        text = (
            "Chương I. A\n\n"
            "Điều 1. X\n"
            "abc\n\n"
            "Chương II. B\n\n"
            "Điều 2. Y\n"
            "def\n"
        )
        chunks = chunk_text(text, target_chars=1000, max_chars=2000, min_chars=50)

        assert len(chunks) == 2
        assert "abc" in chunks[0].text and "def" not in chunks[0].text
        assert "def" in chunks[1].text and "abc" not in chunks[1].text

    def test_force_split_oversized_article_keeps_metadata_and_order(self):
        # Cần >= 2 boundary để chunk_text đi vào nhánh có cấu trúc (nếu chỉ có
        # 1 Điều, len(segments) < 2 nên toàn bộ rơi vào fallback — xem
        # chunk_text()). Điều 1 ngắn để giữ nguyên 1 segment, Điều 2 dài để
        # kích hoạt _force_split_oversized().
        sentence = "Đây là một câu ví dụ để kiểm tra việc tách đoạn quá dài thành nhiều phần. "
        text = (
            "Điều 1. Mở đầu\n"
            "Điều khoản mở đầu ngắn gọn.\n\n"
            "Điều 2. Quy định chi tiết\n" + sentence * 60
        )
        chunks = chunk_text(text, target_chars=300, max_chars=500, min_chars=0)

        article2_chunks = [c for c in chunks if c.article == "Điều 2. Quy định chi tiết"]
        assert len(article2_chunks) > 1
        for idx, c in enumerate(article2_chunks):
            assert c.heading_path == "Điều 2. Quy định chi tiết"
            assert c.part_index == idx
            assert len(c.text) <= 500 + len(sentence)  # cho phép lệch nhẹ do tách theo câu

        original_words = re.findall(r"\S+", text)
        produced_words = re.findall(r"\S+", " ".join(c.text for c in chunks))
        assert sorted(original_words) == sorted(produced_words)


class TestWordBoundaryTail:
    def test_cuts_on_whitespace_not_mid_word(self):
        text = "người lao động Việt Nam làm việc tại nhiều quốc gia khác nhau trên thế giới"
        tail = _word_boundary_tail(text, 15)
        assert tail != ""
        cut_index = len(text) - len(tail)
        assert text[cut_index - 1].isspace()
        assert not tail[0].isspace()

    def test_empty_when_no_whitespace_boundary_found(self):
        text = "a" * 100
        assert _word_boundary_tail(text, 10) == ""

    def test_empty_when_approx_chars_non_positive_or_too_large(self):
        assert _word_boundary_tail("một đoạn văn ngắn", 0) == ""
        assert _word_boundary_tail("một đoạn văn ngắn", -5) == ""
        assert _word_boundary_tail("ngắn", 100) == ""


class TestFallbackChunkingNoWordSplit:
    def test_no_partial_word_regression(self):
        """Regression test cho bug đã fix: overlap giữa 2 chunk từng cắt vỡ
        giữa 1 từ tiếng Việt có dấu (vd tạo ra 'ời Việt' thay vì 'người Việt').
        Nếu bug tái xuất hiện, produced_words sẽ chứa token không có trong
        original_words (fragment từ bị cắt)."""
        paragraph = (
            "Người lao động Việt Nam làm việc trong môi trường quốc tế cần trang bị "
            "kỹ năng ngoại ngữ và chuyên môn vững chắc để cạnh tranh hiệu quả trên thị trường."
        )
        text = "\n\n".join(f"{paragraph} Đoạn số {i}." for i in range(10))

        chunks = chunk_text(text, target_chars=200, max_chars=400, min_chars=0)
        assert len(chunks) > 1
        assert all(c.heading_path == "" for c in chunks)  # fallback path, không có cấu trúc

        original_words = set(re.findall(r"\S+", text))
        produced_words: set[str] = set()
        for c in chunks:
            produced_words.update(re.findall(r"\S+", c.text))

        assert produced_words == original_words
