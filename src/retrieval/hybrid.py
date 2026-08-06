"""Trộn kết quả dense (Chroma) với BM25 bằng Reciprocal Rank Fusion (RRF).

Lý do: Multi-chunk Recall@10 (câu hỏi cần nhiều đoạn để trả lời đầy đủ) chỉ đạt
69.1%, và reranker làm nó GIẢM so với dense thuần — cross-encoder tối ưu "đoạn
nào giống câu hỏi nhất", không tối ưu "phủ đủ các mảnh của câu trả lời". BM25
bắt khớp từ khoá chính xác (số hiệu điều luật, thuật ngữ hiếm) — đúng chỗ dense
embedding yếu nhất — nên trộn thêm ứng viên từ BM25 trước khi đưa vào reranker,
không thay reranker.

RRF (không cộng điểm thô của 2 hệ khác thang đo) là lựa chọn chuẩn cho bài toán
này: dense trả về cosine distance, BM25 trả về điểm Okapi không bị chặn trên —
cộng trực tiếp sẽ để một hệ áp đảo hệ kia tuỳ ngẫu nhiên theo phân phối điểm.
"""

from src.retrieval.bm25 import BM25


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Trộn nhiều danh sách id đã xếp hạng (mỗi list: id giảm dần theo độ liên
    quan của HỆ ĐÓ) thành một thứ hạng duy nhất bằng RRF.

    `k` là hằng số làm mượt chuẩn trong TREC/RRF gốc (Cormack et al. 2009) —
    giảm ảnh hưởng của rank quá cao ở một hệ đơn lẻ, không cần tinh chỉnh theo
    corpus cụ thể.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def fuse_candidate_ids(
    dense_ids: list[str],
    bm25: BM25 | None,
    query: str,
    bm25_top_k: int,
    rrf_k: int,
    fused_top_k: int,
) -> list[str]:
    """Trả về danh sách chunk_id đã trộn dense + BM25, cắt còn `fused_top_k`.

    `bm25=None` (corpus rỗng hoặc lỗi tải) coi như tắt hybrid cho lần gọi này —
    trả nguyên `dense_ids`, KHÔNG raise, để một lỗi tải corpus phụ không làm
    chết cả pipeline retrieval chính.
    """
    if bm25 is None:
        return dense_ids[:fused_top_k]

    bm25_ids = [chunk_id for chunk_id, _ in bm25.top_k(query, k=bm25_top_k)]
    fused = reciprocal_rank_fusion([dense_ids, bm25_ids], k=rrf_k)
    return [chunk_id for chunk_id, _ in fused[:fused_top_k]]
