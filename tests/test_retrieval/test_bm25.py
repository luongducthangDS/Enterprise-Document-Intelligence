from src.retrieval.bm25 import BM25, tokenize


class TestTokenize:
    def test_lowercases_and_keeps_vietnamese_diacritics(self):
        assert tokenize("Người Lao Động") == ["người", "lao", "động"]

    def test_drops_punctuation_and_keeps_digits(self):
        assert tokenize("Điều 107, khoản 2.") == ["điều", "107", "khoản", "2"]


class TestBM25:
    def _index(self) -> BM25:
        return BM25(
            ["c1", "c2", "c3"],
            [
                "Người lao động làm việc đủ 12 tháng được nghỉ hằng năm 12 ngày làm việc.",
                "Công ty tổ chức team building thường niên vào tháng 8.",
                "Số ngày nghỉ hằng năm tăng thêm 1 ngày sau mỗi 5 năm làm việc.",
            ],
        )

    def test_ranks_documents_sharing_query_terms_first(self):
        results = self._index().top_k("nghỉ hằng năm bao nhiêu ngày", k=3)
        # c1 và c3 cùng nói về nghỉ hằng năm; thứ tự giữa chúng do chuẩn hoá độ
        # dài quyết định nên không cố định. Điều cần đảm bảo là cả hai đều nổi
        # lên và tài liệu lạc đề (c2) bị loại.
        assert set(cid for cid, _ in results) == {"c1", "c3"}

    def test_excludes_requested_ids(self):
        results = self._index().top_k("nghỉ hằng năm", k=3, exclude={"c1"})
        assert "c1" not in [cid for cid, _ in results]

    def test_drops_zero_score_documents(self):
        """Tài liệu không chứa từ nào của truy vấn thì không được trả về, kể cả
        khi k còn chỗ — pooling ứng viên không nên nhận rác."""
        results = self._index().top_k("team building", k=3)
        assert [cid for cid, _ in results] == ["c2"]

    def test_empty_query_returns_nothing(self):
        assert self._index().top_k("!!!", k=5) == []

    def test_rejects_mismatched_ids_and_texts(self):
        try:
            BM25(["a", "b"], ["chỉ một văn bản"])
        except ValueError as e:
            assert "không khớp số lượng" in str(e)
        else:
            raise AssertionError("phải báo lỗi khi ids và texts lệch nhau")
