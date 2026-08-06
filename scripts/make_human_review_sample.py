#!/usr/bin/env python3
"""Sinh phiếu chấm cho NGƯỜI và tính độ đồng thuận người ↔ LLM.

## Vì sao cần

Nhãn relevance hiện do LLM gán. Dù đã dùng 2 judge khác họ và đo kappa giữa
chúng, hai model vẫn có thể **cùng sai theo một hướng** (vd cùng ưu ái đoạn dài,
cùng bỏ qua bảng biểu). Chỉ có người mới cắt được vòng đó.

Không cần chấm hết — thực hành chuẩn là chấm một **mẫu phân tầng** đủ lớn để đo
kappa người ↔ LLM. Kappa >= 0.6 thì mới có cơ sở nói "nhãn tự động dùng được cho
phần còn lại", và con số đó phải xuất hiện trong báo cáo.

## Cách dùng

    # 1. Sinh phiếu (ưu tiên các cặp 2 judge bất đồng — chỗ nhãn yếu nhất)
    python scripts/make_human_review_sample.py --n 50

    # 2. Mở eval/datasets/human_review_sample.json, điền "human_score": 0/1/2

    # 3. Đo đồng thuận người ↔ nhãn tự động
    python scripts/make_human_review_sample.py --score
"""

import argparse
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _stats import cohens_kappa  # noqa: E402

DATASET_PATH = "eval/datasets/retrieval_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_eval_qrels.json"
ADJUDICATION_PATH = "eval/datasets/retrieval_eval_needs_adjudication.json"
SAMPLE_PATH = "eval/datasets/human_review_sample.json"
AGREEMENT_PATH = "eval/results/human_llm_agreement.json"
SNIPPET_CHARS = 600


def load_chunks() -> dict[str, str]:
    chunks: dict[str, str] = {}
    for path in sorted(glob.glob("data/chunks/*.json")):
        with open(path, encoding="utf-8") as f:
            for c in json.load(f):
                chunks[c["metadata"]["chunk_id"]] = c["text"]
    return chunks


def write_json_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)


def build_sample(n: int, seed: int) -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = {q["id"]: q for q in json.load(f)}
    with open(QRELS_PATH, encoding="utf-8") as f:
        qrels = json.load(f)
    chunks = load_chunks()

    disputed = set()
    if os.path.exists(ADJUDICATION_PATH):
        with open(ADJUDICATION_PATH, encoding="utf-8") as f:
            disputed = {(d["query_id"], d["chunk_id"]) for d in json.load(f)}

    pairs = [(qid, cid, score) for qid, rel in qrels.items() for cid, score in rel.items()]
    rng = random.Random(seed)
    rng.shuffle(pairs)

    # Ưu tiên cặp mà 2 judge bất đồng (nhãn yếu nhất), rồi mới tới cặp đồng thuận
    # — chấm ngẫu nhiên thuần sẽ tốn công người vào những chỗ vốn đã chắc chắn.
    disputed_pairs = [p for p in pairs if (p[0], p[1]) in disputed]
    agreed_pairs = [p for p in pairs if (p[0], p[1]) not in disputed]
    n_disputed = min(len(disputed_pairs), n // 2)
    selected = disputed_pairs[:n_disputed] + agreed_pairs[: n - n_disputed]

    sample = []
    for qid, cid, score in selected:
        sample.append({
            "query_id": qid,
            "chunk_id": cid,
            "query": dataset.get(qid, {}).get("query", ""),
            "chunk_text": chunks.get(cid, "")[:SNIPPET_CHARS],
            "is_disputed_by_judges": (qid, cid) in disputed,
            "auto_score": score,
            "human_score": None,  # ← ĐIỀN 0, 1 hoặc 2 vào đây
        })

    write_json_atomic(SAMPLE_PATH, sample)
    print(f"Đã tạo {SAMPLE_PATH}: {len(sample)} cặp query-chunk cần chấm")
    print(f"  trong đó {n_disputed} cặp mà 2 judge bất đồng (ưu tiên chấm trước)")
    print('\nHướng dẫn chấm: 2 = đoạn CHỨA câu trả lời, 1 = liên quan/bổ trợ, 0 = không liên quan')
    print("Điền vào field `human_score`, rồi chạy: python scripts/make_human_review_sample.py --score")


def score_sample() -> None:
    if not os.path.exists(SAMPLE_PATH):
        print(f"Chưa có {SAMPLE_PATH} — chạy không kèm --score để tạo phiếu trước")
        sys.exit(1)
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        sample = json.load(f)

    scored = [s for s in sample if s.get("human_score") is not None]
    if not scored:
        print(f"Chưa có dòng nào được điền `human_score` trong {SAMPLE_PATH}")
        sys.exit(1)

    human = [int(s["human_score"]) for s in scored]
    auto = [int(s["auto_score"]) for s in scored]

    kappa = cohens_kappa(human, auto)
    kappa_binary = cohens_kappa([1 if v >= 1 else 0 for v in human], [1 if v >= 1 else 0 for v in auto])
    exact = sum(1 for h, a in zip(human, auto) if h == a) / len(scored)

    def verdict(k: float) -> str:
        if k >= 0.8:
            return "tốt"
        if k >= 0.6:
            return "khá — nhãn tự động dùng được cho phần còn lại"
        if k >= 0.4:
            return "trung bình — cần mở rộng mẫu người chấm"
        return "YẾU — nhãn tự động không đáng tin, phải chấm tay"

    print(f"=== Đồng thuận người ↔ nhãn tự động (n = {len(scored)}/{len(sample)}) ===")
    print(f"Trùng khớp tuyệt đối: {exact:.1%}")
    print(f"Kappa (3 mức)       : {kappa:.3f} — {verdict(kappa)}")
    print(f"Kappa (nhị phân)    : {kappa_binary:.3f} — {verdict(kappa_binary)}")

    disputed = [s for s in scored if s["is_disputed_by_judges"]]
    if disputed:
        agree_on_disputed = sum(1 for s in disputed if int(s["human_score"]) == int(s["auto_score"])) / len(disputed)
        print(f"\nRiêng {len(disputed)} cặp 2 judge bất đồng: nhãn đồng thuận trùng người {agree_on_disputed:.1%}")

    write_json_atomic(AGREEMENT_PATH, {
        "n_scored": len(scored),
        "n_total_sample": len(sample),
        "exact_agreement": round(exact, 4),
        "cohens_kappa_graded": round(kappa, 4),
        "cohens_kappa_binary": round(kappa_binary, 4),
    })
    print(f"\nĐã ghi {AGREEMENT_PATH} — đưa con số này vào báo cáo eval")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Số cặp query-chunk cần người chấm")
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--score", action="store_true", help="Tính đồng thuận sau khi người đã điền human_score")
    args = parser.parse_args()

    if args.score:
        score_sample()
    else:
        build_sample(args.n, args.seed)


if __name__ == "__main__":
    main()
