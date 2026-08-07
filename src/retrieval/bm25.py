"""BM25 (Okapi) chạy local trên toàn bộ chunk — không gọi API, không phụ thuộc
thư viện ngoài.

Dùng cho 2 mục đích:

1. **Pooling ứng viên khi xây qrel** (`scripts/rag_pipeline/build_retrieval_eval_set.py`):
   gom ứng viên từ MỘT hệ thống độc lập với dense retrieval, để nhãn relevance
   không bị thiên vị theo đúng model đang được đo (pooling bias — vấn đề kinh
   điển của IR eval: nếu chỉ lấy ứng viên từ chính retriever đang đo thì mọi
   chunk nó bỏ sót sẽ vĩnh viễn không bao giờ được gán nhãn relevant).
2. Baseline / thành phần hybrid search sau này (BM25 bắt được khớp từ khoá chính
   xác — số hiệu điều luật, thuật ngữ hiếm — chỗ embedding thường yếu).

Tokenizer chỉ tách theo ký tự chữ-số Unicode: với tiếng Việt điều này cho ra
âm tiết ("người", "lao", "động") chứ không phải từ ghép. Chấp nhận được cho BM25
vì khớp âm tiết vẫn tạo tín hiệu tốt và không cần từ điển tách từ.
"""

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(
        self,
        ids: list[str],
        texts: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if len(ids) != len(texts):
            raise ValueError(f"ids ({len(ids)}) và texts ({len(texts)}) không khớp số lượng")
        self.ids = ids
        self.k1 = k1
        self.b = b
        self.docs: list[Counter] = [Counter(tokenize(t)) for t in texts]
        self.doc_lens = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.doc_lens) / len(self.doc_lens)) if self.doc_lens else 0.0

        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        # IDF dạng Okapi có smoothing (+0.5) — luôn dương, tránh điểm âm cho từ
        # xuất hiện ở hơn nửa số tài liệu.
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def _score(self, doc_index: int, query_terms: list[str]) -> float:
        doc = self.docs[doc_index]
        doc_len = self.doc_lens[doc_index]
        norm = self.k1 * (1 - self.b + self.b * doc_len / self.avg_len) if self.avg_len else self.k1
        score = 0.0
        for term in query_terms:
            tf = doc.get(term, 0)
            if not tf:
                continue
            score += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + norm)
        return score

    def top_k(self, query: str, k: int = 10, exclude: set[str] | None = None) -> list[tuple[str, float]]:
        """Trả về [(chunk_id, score)] giảm dần, bỏ qua các id trong `exclude`."""
        query_terms = tokenize(query)
        if not query_terms:
            return []
        exclude = exclude or set()
        scored = [
            (self.ids[i], self._score(i, query_terms))
            for i in range(len(self.docs))
            if self.ids[i] not in exclude
        ]
        scored = [(cid, s) for cid, s in scored if s > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]
