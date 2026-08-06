from src.retrieval.bm25 import BM25
from src.retrieval.hybrid import fuse_candidate_ids, reciprocal_rank_fusion


class TestReciprocalRankFusion:
    def test_doc_ranked_first_in_both_lists_wins(self):
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]])
        assert fused[0][0] == "a"

    def test_doc_only_in_one_list_still_included(self):
        fused = reciprocal_rank_fusion([["a", "b"], ["c"]])
        assert {doc_id for doc_id, _ in fused} == {"a", "b", "c"}

    def test_empty_lists_return_empty(self):
        assert reciprocal_rank_fusion([[], []]) == []

    def test_smaller_k_amplifies_top_rank_influence(self):
        # Cùng 2 danh sách bất đồng thứ hạng, k nhỏ hơn phải kéo giãn khoảng
        # cách điểm số giữa hạng 1 và hạng cuối nhiều hơn.
        lists = [["a", "b", "c"], ["c", "b", "a"]]
        spread_small_k = dict(reciprocal_rank_fusion(lists, k=1))
        spread_large_k = dict(reciprocal_rank_fusion(lists, k=1000))
        gap_small = max(spread_small_k.values()) - min(spread_small_k.values())
        gap_large = max(spread_large_k.values()) - min(spread_large_k.values())
        assert gap_small > gap_large


class TestFuseCandidateIds:
    def _bm25(self) -> BM25:
        return BM25(
            ["c1", "c2", "c3"],
            [
                "Người lao động làm việc đủ 12 tháng được nghỉ hằng năm 12 ngày.",
                "Công ty tổ chức team building thường niên vào tháng 8.",
                "Số ngày nghỉ hằng năm tăng thêm 1 ngày sau mỗi 5 năm làm việc.",
            ],
        )

    def test_none_bm25_falls_back_to_dense_only(self):
        result = fuse_candidate_ids(
            dense_ids=["c2", "c1", "c3"], bm25=None, query="nghỉ hằng năm",
            bm25_top_k=10, rrf_k=60, fused_top_k=2,
        )
        assert result == ["c2", "c1"]

    def test_bm25_candidate_absent_from_dense_can_surface(self):
        # c3 không nằm trong dense top-3 dưới đây nhưng khớp từ khoá BM25 mạnh
        # -> phải xuất hiện trong kết quả trộn nếu fused_top_k đủ rộng.
        result = fuse_candidate_ids(
            dense_ids=["c2"], bm25=self._bm25(), query="nghỉ hằng năm bao nhiêu ngày",
            bm25_top_k=10, rrf_k=60, fused_top_k=5,
        )
        assert "c3" in result or "c1" in result

    def test_respects_fused_top_k(self):
        result = fuse_candidate_ids(
            dense_ids=["c1", "c2", "c3"], bm25=self._bm25(), query="nghỉ hằng năm",
            bm25_top_k=10, rrf_k=60, fused_top_k=1,
        )
        assert len(result) == 1
