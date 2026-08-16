#!/usr/bin/env python3
"""Gộp nhãn relevance từ NHIỀU judge độc lập thành qrel đồng thuận, và đo độ tin
cậy của chính nhãn đó.

## Vì sao

Nhãn do một LLM gán là *giả định*, không phải dữ liệu — nhất là khi model đó
cùng họ với model sinh câu hỏi và model trả lời (circular evaluation). Cách xử
lý chuẩn khi không đủ nhân lực chấm tay:

1. Cho **2 judge khác họ** chấm độc lập cùng một pool ứng viên.
2. Đo **Cohen's kappa** — nếu dưới 0.6 thì nhãn tự động không đáng tin, phải có
   người vào cuộc trước khi dùng số liệu để ra quyết định.
3. Chỗ hai judge **đồng ý** → nhãn tin cậy cao, dùng luôn.
4. Chỗ **bất đồng** → lấy nhãn thấp hơn (thận trọng: không tự phong cho một
   chunk là "chứa câu trả lời" khi chỉ 1 trong 2 judge nghĩ vậy) VÀ đẩy vào
   hàng đợi để người phân xử.

Cách này không loại bỏ được hoàn toàn bias của LLM, nhưng biến "tin vào 1 model"
thành "có con số đo được về mức độ đáng tin của nhãn" — và đó là thứ phải ghi
vào báo cáo.

Chạy:
    python scripts/rag_pipeline/merge_judgments.py --judges GLM-5.2 Llama-3.3-70B-Instruct
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _stats import cohens_kappa  # noqa: E402

CACHE_DIR = "eval/.cache"
DATASET_PATH = "eval/datasets/retrieval_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_eval_qrels.json"
ADJUDICATION_PATH = "eval/datasets/retrieval_eval_needs_adjudication.json"
AGREEMENT_PATH = "eval/results/judge_agreement.json"


def judgments_path(model: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return f"{CACHE_DIR}/retrieval_judgments__{slug}.json"


def write_json_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judges", nargs=2, required=True, help="Tên 2 model judge đã chấm")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    judge_a, judge_b = args.judges
    data = {}
    for model in (judge_a, judge_b):
        path = judgments_path(model)
        if not os.path.exists(path):
            print(f"[LỖI] chưa có nhãn của {model}: {path}")
            print(f"  chạy: python scripts/rag_pipeline/build_retrieval_eval_set.py --stage judge --judge-model {model}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            data[model] = json.load(f)
        print(f"{model}: {len(data[model])} query")

    # Chỉ so trên các cặp (query, chunk) mà CẢ HAI judge đều đã chấm — so trên
    # tập lệch nhau sẽ làm kappa vô nghĩa.
    labels_a, labels_b = [], []
    consensus: dict[str, dict[str, int]] = {}
    disagreements = []

    # Chỉ giữ query CÒN trong dataset: khâu finalize có loại một số query hỏng
    # (chunk seed bị chấm 0), nhưng cache judgment vẫn giữ chúng. Không lọc thì
    # qrel có nhãn mồ côi — integrity check bắt được, nhưng nên chặn từ gốc.
    with open(DATASET_PATH, encoding="utf-8") as f:
        valid_ids = {q["id"] for q in json.load(f)}
    dropped = (set(data[judge_a]) & set(data[judge_b])) - valid_ids
    if dropped:
        print(f"Bỏ {len(dropped)} query không còn trong dataset: {sorted(dropped)}")
    shared_queries = set(data[judge_a]) & set(data[judge_b]) & valid_ids
    for qid in sorted(shared_queries):
        scores_a = data[judge_a][qid]["scores"]
        scores_b = data[judge_b][qid]["scores"]
        rel: dict[str, int] = {}
        for chunk_id in set(scores_a) & set(scores_b):
            a, b = int(scores_a[chunk_id]), int(scores_b[chunk_id])
            labels_a.append(a)
            labels_b.append(b)
            score = min(a, b)  # thận trọng khi bất đồng
            if a != b:
                disagreements.append(
                    {"query_id": qid, "chunk_id": chunk_id, judge_a: a, judge_b: b, "consensus_used": score}
                )
            if score > 0:
                rel[chunk_id] = score
        if rel:
            consensus[qid] = dict(sorted(rel.items()))

    kappa = cohens_kappa(labels_a, labels_b)
    exact = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / len(labels_a) if labels_a else 0.0
    # Với quyết định nhị phân "relevant hay không" (score >= 1) — sát với cách
    # metric thực sự dùng nhãn hơn là phân biệt 2 vs 1.
    kappa_binary = cohens_kappa([1 if v >= 1 else 0 for v in labels_a], [1 if v >= 1 else 0 for v in labels_b])
    kappa_strict = cohens_kappa([1 if v == 2 else 0 for v in labels_a], [1 if v == 2 else 0 for v in labels_b])

    def verdict(k: float) -> str:
        if k >= 0.8:
            return "tốt"
        if k >= 0.6:
            return "khá — chấp nhận dùng nhãn tự động"
        if k >= 0.4:
            return "trung bình — cần người kiểm tra mẫu"
        return "YẾU — không nên tin nhãn tự động"

    print(f"\n=== Đồng thuận giữa 2 judge (n = {len(labels_a)} cặp query-chunk) ===")
    print(f"Trùng khớp tuyệt đối : {exact:.1%}")
    print(f"Kappa (3 mức 0/1/2)  : {kappa:.3f} — {verdict(kappa)}")
    print(f"Kappa (relevant hay không) : {kappa_binary:.3f} — {verdict(kappa_binary)}")
    print(f"Kappa (chứa câu trả lời hay không) : {kappa_strict:.3f} — {verdict(kappa_strict)}")
    print(f"\nBất đồng: {len(disagreements)}/{len(labels_a)} cặp")
    print(f"Qrel đồng thuận: {len(consensus)} query, {sum(len(v) for v in consensus.values())} nhãn")

    report = {
        "judges": [judge_a, judge_b],
        "n_pairs": len(labels_a),
        "exact_agreement": round(exact, 4),
        "cohens_kappa_graded": round(kappa, 4),
        "cohens_kappa_binary": round(kappa_binary, 4),
        "cohens_kappa_strict": round(kappa_strict, 4),
        "n_disagreements": len(disagreements),
        "consensus_rule": "min(score) khi bất đồng — thận trọng, và đẩy vào hàng đợi phân xử",
    }

    if args.dry_run:
        print("\n(dry-run — không ghi file)")
        return

    write_json_atomic(QRELS_PATH, consensus)
    write_json_atomic(ADJUDICATION_PATH, disagreements)
    write_json_atomic(AGREEMENT_PATH, report)
    print(f"\nĐã ghi {QRELS_PATH}, {ADJUDICATION_PATH}, {AGREEMENT_PATH}")
    print("→ chạy `python scripts/rag_pipeline/remap_qrels.py --build-anchors` để cập nhật anchor theo qrel mới")


if __name__ == "__main__":
    main()
