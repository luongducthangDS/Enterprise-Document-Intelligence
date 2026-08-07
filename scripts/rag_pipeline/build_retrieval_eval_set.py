#!/usr/bin/env python3
"""Xây bộ eval RETRIEVAL riêng (`eval/datasets/retrieval_eval_set.json` +
`retrieval_eval_qrels.json`), tách hẳn khỏi `qa_eval_set.json` vốn được thiết kế
cho generation/agent.

## Vì sao phải có bộ riêng

`qa_eval_set.json` sinh theo hướng document-first: đọc 1-2 cửa sổ 4.000 ký tự
của mỗi tài liệu → sinh câu hỏi → sau đó mới dò ngược `ground_truth_context`
để tìm chunk gold. Cách đó có 2 lỗi hệ thống (đo được, xem project_review.md):

- **Coverage lệch**: 60 câu in_scope chỉ chạm 11/29 tài liệu = 40% index;
  Nghị định 145/2020 (270 chunk, tài liệu HR chi tiết nhất) không có câu nào.
- **Gold lệch**: với 2 bộ luật, 10/10 chunk gold rơi vào 1-2% đầu tài liệu
  (Điều 1-5: phạm vi, giải thích từ ngữ) — phần ít đáng hỏi nhất — nên câu hỏi
  sinh ra thường có câu trả lời thật nằm ở điều khoản KHÁC, và retrieval bị
  chấm MISS oan.

## Cách làm ở đây: chunk-first

    bốc mẫu chunk (phủ đều 29 tài liệu) → sinh câu hỏi TỪ CHÍNH chunk đó
    → gold chunk_id biết trước, không cần dò chuỗi.

Coverage trở thành *tính chất của cách bốc mẫu* thay vì thứ phải chữa về sau,
và gold không thể lệch khỏi nguồn sinh ra nó.

## 4 stage (chạy được riêng lẻ, có cache để không mất công gọi LLM khi crash)

1. `sample`   — bốc seed (KHÔNG gọi API): seed đơn cho câu hỏi hẹp, và nhóm
                2-3 chunk liên quan (tìm bằng BM25 local) cho câu hỏi RỘNG cần
                nhiều chunk mới trả lời đủ.
2. `generate` — LLM viết câu hỏi từ seed. Câu hẹp có 2 kiểu: giọng nhân viên
                tự nhiên, và truy vấn tra cứu ngắn kiểu keyword.
3. `judge`    — pooling ứng viên từ **dense (Chroma) + BM25** rồi LLM chấm từng
                ứng viên 2/1/0. Pooling từ 2 hệ thống độc lập để nhãn không
                thiên vị theo đúng retriever đang được đo (pooling bias).
4. `finalize` — ghi dataset + qrels, chia split dev/heldout.

Query nào mà chunk seed bị chấm 0 (LLM cho rằng đoạn gốc không trả lời được câu
hỏi vừa sinh ra từ nó) → coi là câu hỏi hỏng, tách sang file `*_flagged.json`
để người review, KHÔNG đưa vào dataset chính.

Chạy:
    python scripts/rag_pipeline/build_retrieval_eval_set.py --stage sample --dry-run
    python scripts/rag_pipeline/build_retrieval_eval_set.py --stage all
"""

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings  # noqa: E402
from src.ingestion.indexer import get_chroma_client, get_collection  # noqa: E402
from _text_utils import normalize_for_match  # noqa: E402
from src.retrieval.bm25 import BM25  # noqa: E402
from src.services.fpt_client import chat_completion, embed_batch  # noqa: E402

CHUNKS_DIR = "data/chunks"
CACHE_DIR = "eval/.cache"
SEEDS_PATH = f"{CACHE_DIR}/retrieval_seeds.json"
QUERIES_PATH = f"{CACHE_DIR}/retrieval_queries.json"
# Cache judgment TÁCH THEO MODEL: cần giữ song song nhãn của nhiều judge để đo
# độ đồng thuận giữa chúng (xem scripts/rag_pipeline/merge_judgments.py). Ghi đè chung 1 file
# thì mất luôn khả năng kiểm chứng nhãn.
def judgments_path(model: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return f"{CACHE_DIR}/retrieval_judgments__{slug}.json"
DATASET_PATH = "eval/datasets/retrieval_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_eval_qrels.json"
FLAGGED_PATH = "eval/datasets/retrieval_eval_set_flagged.json"

MIN_BODY_CHARS = 150
POOL_DENSE_K = 10
POOL_BM25_K = 10
CANDIDATE_SNIPPET_CHARS = 700
HELDOUT_RATIO = 0.2


# ---------------------------------------------------------------- helpers


def load_chunks() -> dict[str, dict]:
    """Đọc toàn bộ chunk từ data/chunks/*.json → {chunk_id: chunk}."""
    chunks: dict[str, dict] = {}
    for name in sorted(os.listdir(CHUNKS_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CHUNKS_DIR, name), encoding="utf-8") as f:
            for c in json.load(f):
                chunks[c["metadata"]["chunk_id"]] = c
    return chunks


def is_question_worthy(chunk: dict) -> bool:
    """Loại chunk gần như chỉ có heading / dòng bảng cụt — không sinh được câu
    hỏi có nội dung thật từ chúng."""
    text = chunk["text"].strip()
    body = re.sub(r"^#+ .*$", "", text, flags=re.M)
    body = re.sub(r"^\|.*\|$", "", body, flags=re.M).strip()
    if len(body) < MIN_BODY_CHARS:
        return False
    return len(re.findall(r"[.,;:]", body)) >= 3


def parse_json_block(raw: str):
    """LLM hay bọc JSON trong ```json ... ``` hoặc kèm lời dẫn — lấy phần JSON."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError(f"Không tìm thấy JSON trong output LLM: {raw[:200]}")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start : end + 1])


def write_json_atomic(path: str, data) -> None:
    """Ghi ra file tạm rồi replace — giữ nguyên pattern an toàn đã dùng cho
    document_registry.csv (đã từng hỏng file vì script crash giữa chừng)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)


def llm(system: str, user: str, temperature: float = 0.4, model: str | None = None) -> str:
    settings = get_settings()
    return chat_completion(
        system,
        user,
        model=model or settings.llm_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        temperature=temperature,
    )


# ---------------------------------------------------------------- stage 1: sample


def allocate(counts: dict[str, int], budget: int, floor: int, cap: int) -> dict[str, int]:
    """Chia `budget` mẫu cho các tài liệu theo tỉ lệ số chunk, nhưng có SÀN
    (tài liệu nhỏ vẫn được đo) và TRẦN (Nghị định 145 với 270 chunk không nuốt
    hết ngân sách)."""
    total = sum(counts.values())
    alloc = {}
    for stem, n in counts.items():
        share = round(budget * n / total) if total else 0
        alloc[stem] = max(min(floor, n), min(cap, share, n))
    return alloc


def _weighted_sample(items: list, weights: list[int], k: int, rng: random.Random) -> list:
    """Bốc `k` phần tử KHÔNG lặp theo trọng số (random.choices có lặp nên không dùng)."""
    pool = list(zip(items, weights))
    picked = []
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool) or 1
        threshold = rng.uniform(0, total)
        acc = 0.0
        for i, (item, w) in enumerate(pool):
            acc += w
            if acc >= threshold:
                picked.append(item)
                pool.pop(i)
                break
    return picked


def build_seeds(chunks: dict[str, dict], n_single: int, n_multi: int, seed: int) -> dict:
    rng = random.Random(seed)
    eligible: dict[str, list[str]] = defaultdict(list)
    for cid, c in chunks.items():
        if is_question_worthy(c):
            eligible[c["metadata"]["source_stem"]].append(cid)
    for cids in eligible.values():
        cids.sort()

    counts = {stem: len(cids) for stem, cids in eligible.items()}
    single_alloc = allocate(counts, n_single, floor=1, cap=6)
    multi_alloc = allocate(counts, n_multi, floor=1, cap=4)

    # BM25 trên toàn bộ chunk (kể cả chunk không đủ điều kiện làm seed — chúng
    # vẫn có thể là chunk liên quan hợp lệ trong 1 nhóm multi-chunk).
    ids = sorted(chunks)
    bm25 = BM25(ids, [chunks[i]["text"] for i in ids])

    single_seeds = []
    used: set[str] = set()
    for stem, k in sorted(single_alloc.items()):
        picked = rng.sample(eligible[stem], min(k, len(eligible[stem])))
        for cid in picked:
            used.add(cid)
            single_seeds.append({"chunk_ids": [cid], "source_stem": stem})
    rng.shuffle(single_seeds)
    single_seeds = single_seeds[:n_single]
    # Sàn/trần ở allocate() thường cho ra ít hơn ngân sách — bù thêm từ các tài
    # liệu lớn (bốc theo tỉ lệ số chunk) để đạt đúng chỉ tiêu.
    if len(single_seeds) < n_single:
        spare = [(stem, cid) for stem, cids in eligible.items() for cid in cids if cid not in used]
        weights = [len(eligible[stem]) for stem, _ in spare]
        for stem, cid in _weighted_sample(spare, weights, n_single - len(single_seeds), rng):
            used.add(cid)
            single_seeds.append({"chunk_ids": [cid], "source_stem": stem})
    # Xen kẽ 2 kiểu truy vấn: câu hỏi tự nhiên (2/3) và truy vấn keyword (1/3).
    for i, s in enumerate(single_seeds):
        s["query_style"] = "keyword" if i % 3 == 2 else "natural"
        s["type"] = "single_chunk"

    multi_seeds = []
    for stem, k in sorted(multi_alloc.items()):
        pool = [c for c in eligible[stem] if c not in used] or eligible[stem]
        for cid in rng.sample(pool, min(k, len(pool))):
            related = bm25.top_k(chunks[cid]["text"], k=12, exclude={cid})
            same_doc = [r for r, _ in related if chunks[r]["metadata"]["source_stem"] == stem]
            cross_doc = [r for r, _ in related if chunks[r]["metadata"]["source_stem"] != stem]
            # ~60% nhóm trong cùng tài liệu (câu hỏi kiểu "quy trình gồm những
            # bước nào"), ~40% liên tài liệu (kiểu "luật quy định thế nào và
            # công ty áp dụng ra sao") — đúng dạng câu hỏi HR thật hay gặp.
            prefer_cross = rng.random() < 0.4
            ordered = (cross_doc + same_doc) if prefer_cross else (same_doc + cross_doc)
            if not ordered:
                continue
            group = [cid] + ordered[: rng.choice([1, 1, 2])]
            multi_seeds.append(
                {
                    "chunk_ids": group,
                    "source_stem": stem,
                    "type": "multi_chunk",
                    "query_style": "broad",
                    "group_kind": "cross_doc" if prefer_cross and cross_doc else "same_doc",
                }
            )
    rng.shuffle(multi_seeds)
    multi_seeds = multi_seeds[:n_multi]

    seeds = single_seeds + multi_seeds
    for i, s in enumerate(seeds, start=1):
        s["id"] = f"rq_{i:03d}"
    return {"built_at": datetime.now(timezone.utc).isoformat(), "seed": seed, "seeds": seeds}


def print_sample_plan(chunks: dict[str, dict], payload: dict) -> None:
    seeds = payload["seeds"]
    per_doc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    covered: set[str] = set()
    for s in seeds:
        per_doc[s["source_stem"]][0 if s["type"] == "single_chunk" else 1] += 1
        covered.update(s["chunk_ids"])
    docs_all = {c["metadata"]["source_stem"] for c in chunks.values()}
    print(f"\n{'tài liệu':<52} {'hẹp':>4} {'rộng':>5}")
    for stem in sorted(docs_all):
        a, b = per_doc.get(stem, [0, 0])
        print(f"{stem[:52]:<52} {a:>4} {b:>5}")
    n_single = sum(1 for s in seeds if s["type"] == "single_chunk")
    print(f"\nTổng: {len(seeds)} query ({n_single} hẹp + {len(seeds) - n_single} rộng)")
    print(f"Tài liệu được phủ: {len(per_doc)}/{len(docs_all)}")
    print(f"Chunk được chạm (seed): {len(covered)}/{len(chunks)}")
    sizes = [len(s["chunk_ids"]) for s in seeds if s["type"] == "multi_chunk"]
    if sizes:
        print(f"Nhóm multi-chunk: {len(sizes)} nhóm, {sum(sizes) / len(sizes):.1f} chunk/nhóm")


# ---------------------------------------------------------------- stage 2: generate

_GEN_SYSTEM = """Bạn giúp xây bộ dữ liệu đánh giá cho chatbot HR nội bộ của một công ty Việt Nam.

Chatbot này CHỈ phục vụ nhân viên đang làm việc tại công ty và cán bộ HR. Vì vậy câu hỏi phải đúng giọng người trong công ty (hoặc HR đang tra cứu để tư vấn), TUYỆT ĐỐI không viết giọng ứng viên bên ngoài đang đi xin việc.

Nguyên tắc bắt buộc:
- Câu hỏi phải trả lời được bằng CHÍNH đoạn trích được cung cấp, không cần thông tin ngoài.
- KHÔNG nhắc tới "đoạn trích", "tài liệu này", "theo văn bản trên" — người hỏi thật không biết đoạn trích tồn tại.
- Dùng cách diễn đạt tự nhiên của người đi làm, KHÔNG sao chép nguyên văn câu trong đoạn trích (nếu chép nguyên văn thì phép đo retrieval trở nên vô nghĩa).
- Chỉ trả về JSON, không giải thích gì thêm."""

_GEN_NATURAL = """Đoạn trích (tài liệu: {title}, mục: {heading}):
---
{text}
---

Viết 1 câu hỏi mà một nhân viên sẽ gõ vào chatbot HR, trả lời được hoàn toàn bằng đoạn trích trên.

Trả về JSON:
{{"query": "...", "answer_points": ["ý chính 1", "ý chính 2"], "evidence_span": "<copy NGUYÊN VĂN câu/đoạn ngắn (<=300 ký tự) trong đoạn trích chứa câu trả lời>"}}"""

_GEN_KEYWORD = """Đoạn trích (tài liệu: {title}, mục: {heading}):
---
{text}
---

Viết 1 TRUY VẤN TRA CỨU NGẮN (3-8 từ, dạng cụm từ khoá, KHÔNG phải câu hỏi đầy đủ, không có dấu hỏi) mà người dùng sẽ gõ khi muốn tìm đúng nội dung trên. Ví dụ phong cách: "mức phụ cấp công tác phí vùng 1", "thời gian báo trước khi nghỉ việc".

Trả về JSON:
{{"query": "...", "answer_points": ["ý chính 1"], "evidence_span": "<copy NGUYÊN VĂN câu/đoạn ngắn (<=300 ký tự) trong đoạn trích chứa câu trả lời>"}}"""

_GEN_BROAD = """Dưới đây là {n} đoạn trích khác nhau:

{blocks}

Viết 1 câu hỏi RỘNG mà một nhân viên hoặc cán bộ HR sẽ hỏi, và để trả lời ĐẦY ĐỦ thì phải dùng CẢ {n} đoạn trên — mỗi đoạn đóng góp một phần của câu trả lời. Câu hỏi phải nghe tự nhiên như một câu hỏi thật, không phải ghép cơ học 2 câu hỏi rời bằng chữ "và".

Trả về JSON:
{{"query": "...", "answer_points": ["phần đến từ đoạn 1", "phần đến từ đoạn 2"], "evidence_spans": ["<copy NGUYÊN VĂN câu ngắn trong Đoạn 1>", "<copy NGUYÊN VĂN câu ngắn trong Đoạn 2>"]}}"""


def generate_one(seed: dict, chunks: dict[str, dict]) -> dict | None:
    metas = [chunks[cid]["metadata"] for cid in seed["chunk_ids"]]
    try:
        if seed["type"] == "single_chunk":
            meta = metas[0]
            template = _GEN_KEYWORD if seed["query_style"] == "keyword" else _GEN_NATURAL
            user = template.format(
                title=meta.get("title") or meta["source_stem"],
                heading=meta.get("heading_path") or "-",
                text=chunks[seed["chunk_ids"][0]]["text"][:2500],
            )
        else:
            blocks = "\n\n".join(
                f"[Đoạn {i}] (tài liệu: {m.get('title') or m['source_stem']}, mục: {m.get('heading_path') or '-'})\n"
                f"{chunks[cid]['text'][:1500]}"
                for i, (cid, m) in enumerate(zip(seed["chunk_ids"], metas), start=1)
            )
            user = _GEN_BROAD.format(n=len(seed["chunk_ids"]), blocks=blocks)

        data = parse_json_block(llm(_GEN_SYSTEM, user))
        query = (data.get("query") or "").strip()
        if not query:
            return None

        # Lưu thêm đoạn bằng chứng nguyên văn, chỉ giữ đoạn thực sự có trong
        # chunk gốc. Có nó thì mỗi lần đổi chunker chỉ cần map lại bằng string
        # match xác định, không phải sinh lại dataset — chính là thứ đã làm
        # hỏng qa_eval_set khi chunk_max_chars đổi 2000 -> 1500.
        raw_spans = data.get("evidence_spans") or ([data["evidence_span"]] if data.get("evidence_span") else [])
        spans = []
        for span in raw_spans:
            span = (span or "").strip()
            needle = normalize_for_match(span)
            if len(needle) >= 30 and any(needle in normalize_for_match(chunks[cid]["text"]) for cid in seed["chunk_ids"]):
                spans.append(span)

        return {
            **seed,
            "query": query,
            "evidence_spans": spans,
            "answer_points": data.get("answer_points") or [],
            "category": metas[0].get("category", ""),
            "source_files": sorted({m.get("source_file", "") for m in metas}),
        }
    except Exception as e:  # noqa: BLE001 — 1 seed hỏng không được làm chết cả mẻ
        print(f"  [lỗi sinh query] {seed['id']}: {type(e).__name__}: {e}")
        return None


def stage_generate(seeds: list[dict], chunks: dict[str, dict], workers: int) -> list[dict]:
    done: dict[str, dict] = {}
    if os.path.exists(QUERIES_PATH):  # resume: không gọi lại LLM cho seed đã sinh
        with open(QUERIES_PATH, encoding="utf-8") as f:
            done = {q["id"]: q for q in json.load(f)}
        print(f"[resume] đã có {len(done)} query trong cache")

    todo = [s for s in seeds if s["id"] not in done]
    print(f"Sinh query cho {len(todo)} seed (bỏ qua {len(done)} đã có)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, result in enumerate(pool.map(lambda s: generate_one(s, chunks), todo), start=1):
            if result:
                done[result["id"]] = result
                print(f"  [{i}/{len(todo)}] {result['id']} ({result['type']}): {result['query'][:70]}")
            if i % 10 == 0:
                write_json_atomic(QUERIES_PATH, list(done.values()))

    queries = sorted(done.values(), key=lambda q: q["id"])
    write_json_atomic(QUERIES_PATH, queries)
    print(f"Đã sinh {len(queries)} query → {QUERIES_PATH}")
    return queries


# ---------------------------------------------------------------- stage 3: judge

_JUDGE_SYSTEM = """Bạn là chuyên gia đánh giá hệ thống tìm kiếm tài liệu HR/pháp luật lao động Việt Nam.

Với mỗi đoạn ứng viên, chấm mức liên quan so với truy vấn:
- 2 = đoạn CHỨA câu trả lời (hoặc một phần thiết yếu của câu trả lời cho câu hỏi rộng)
- 1 = liên quan, bổ trợ ngữ cảnh, nhưng không tự nó trả lời được
- 0 = không liên quan

Chấm độc lập từng đoạn theo nội dung thực tế, không suy đoán theo thứ tự xuất hiện. Chỉ trả về JSON."""

_JUDGE_USER = """Truy vấn: {query}

Các đoạn ứng viên:
{blocks}

Trả về JSON: [{{"i": 1, "score": 0}}, {{"i": 2, "score": 2}}, ...] — đủ {n} đoạn."""


def dense_top_k(query: str, k: int) -> list[str]:
    settings = get_settings()
    vector = embed_batch(
        [f"query: {query}"],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
    )[0]
    collection = get_collection(get_chroma_client(settings), settings.chroma_collection_name)
    result = collection.query(query_embeddings=[vector], n_results=k)
    return (result.get("ids") or [[]])[0]


def judge_one(item: dict, chunks: dict[str, dict], bm25: BM25, judge_model: str) -> dict | None:
    try:
        pooled = list(dict.fromkeys(item["chunk_ids"] + dense_top_k(item["query"], POOL_DENSE_K)))
        for cid, _ in bm25.top_k(item["query"], k=POOL_BM25_K):
            if cid not in pooled:
                pooled.append(cid)
        pooled = [cid for cid in pooled if cid in chunks]

        blocks = "\n\n".join(
            f"[Đoạn {i}] {chunks[cid]['text'][:CANDIDATE_SNIPPET_CHARS]}"
            for i, cid in enumerate(pooled, start=1)
        )
        raw = llm(
            _JUDGE_SYSTEM,
            _JUDGE_USER.format(query=item["query"], blocks=blocks, n=len(pooled)),
            temperature=0.0,
            model=judge_model,
        )
        scores = {}
        for entry in parse_json_block(raw):
            idx = int(entry["i"]) - 1
            if 0 <= idx < len(pooled):
                scores[pooled[idx]] = max(0, min(2, int(entry["score"])))
        return {"id": item["id"], "pooled": pooled, "scores": scores}
    except Exception as e:  # noqa: BLE001
        print(f"  [lỗi chấm] {item['id']}: {type(e).__name__}: {e}")
        return None


def stage_judge(queries: list[dict], chunks: dict[str, dict], workers: int, judge_model: str) -> dict[str, dict]:
    path = judgments_path(judge_model)
    done: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            done = json.load(f)
        print(f"[resume] đã có {len(done)} judgment trong cache")

    ids = sorted(chunks)
    bm25 = BM25(ids, [chunks[i]["text"] for i in ids])
    todo = [q for q in queries if q["id"] not in done]
    print(f"Chấm relevance cho {len(todo)} query bằng {judge_model} (pooling dense+BM25)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, result in enumerate(pool.map(lambda q: judge_one(q, chunks, bm25, judge_model), todo), start=1):
            if result:
                done[result["id"]] = result
                n2 = sum(1 for s in result["scores"].values() if s == 2)
                n1 = sum(1 for s in result["scores"].values() if s == 1)
                print(f"  [{i}/{len(todo)}] {result['id']}: {len(result['pooled'])} ứng viên → {n2}×score2, {n1}×score1")
            if i % 10 == 0:
                write_json_atomic(path, done)

    write_json_atomic(path, done)
    print(f"Đã chấm {len(done)} query → {path}")
    return done


# ---------------------------------------------------------------- stage 4: finalize


def stage_finalize(queries: list[dict], judgments: dict[str, dict], seed: int) -> None:
    rng = random.Random(seed)
    dataset, flagged, qrels = [], [], {}

    for q in queries:
        j = judgments.get(q["id"])
        if not j:
            continue
        scores = {cid: s for cid, s in j["scores"].items() if s > 0}
        seed_scores = [j["scores"].get(cid, 0) for cid in q["chunk_ids"]]
        # Chunk seed chính là nguồn sinh ra câu hỏi — nếu judge cho nó 0 điểm
        # thì câu hỏi đó hỏng (quá mơ hồ, hoặc trả lời được bằng chỗ khác), tách
        # ra cho người review thay vì để nó âm thầm làm nhiễu metric.
        if min(seed_scores, default=0) == 0:
            flagged.append({**q, "seed_scores": seed_scores, "reason": "seed_chunk_scored_0"})
            continue
        entry = {
            "id": q["id"],
            "query": q["query"],
            "type": q["type"],
            "query_style": q["query_style"],
            "category": q["category"],
            "seed_chunk_ids": q["chunk_ids"],
            "evidence_spans": q.get("evidence_spans") or [],
            "source_files": q["source_files"],
            "answer_points": q["answer_points"],
            "num_relevant": len(scores),
            "num_highly_relevant": sum(1 for s in scores.values() if s == 2),
        }
        if q["type"] == "multi_chunk":
            entry["group_kind"] = q.get("group_kind")
        dataset.append(entry)
        qrels[q["id"]] = dict(sorted(scores.items()))

    # Split held-out phân tầng theo type — giữ nguyên tỉ lệ hẹp/rộng ở cả 2 bên.
    by_type: dict[str, list[dict]] = defaultdict(list)
    for entry in dataset:
        by_type[entry["type"]].append(entry)
    heldout_ids: set[str] = set()
    for items in by_type.values():
        picked = rng.sample(items, max(1, round(len(items) * HELDOUT_RATIO)))
        heldout_ids.update(e["id"] for e in picked)
    for entry in dataset:
        entry["split"] = "heldout" if entry["id"] in heldout_ids else "dev"

    dataset.sort(key=lambda e: e["id"])
    write_json_atomic(DATASET_PATH, dataset)
    write_json_atomic(QRELS_PATH, qrels)
    if flagged:
        write_json_atomic(FLAGGED_PATH, flagged)

    multi = [e for e in dataset if e["type"] == "multi_chunk"]
    avg_rel = sum(e["num_relevant"] for e in dataset) / len(dataset) if dataset else 0
    print(f"\n=== Kết quả ===")
    print(f"Dataset: {len(dataset)} query → {DATASET_PATH}")
    print(f"  hẹp (single_chunk): {len(dataset) - len(multi)}   rộng (multi_chunk): {len(multi)}")
    print(f"  dev: {sum(1 for e in dataset if e['split'] == 'dev')}   heldout: {len(heldout_ids)}")
    print(f"  trung bình {avg_rel:.1f} chunk relevant/query")
    print(f"  query có >1 chunk relevant: {sum(1 for e in dataset if e['num_relevant'] > 1)}")
    with_span = sum(1 for e in dataset if e["evidence_spans"])
    print(f"  query có evidence_span verbatim: {with_span}/{len(dataset)}")
    print(f"Qrels: {QRELS_PATH}")
    if flagged:
        print(f"⚠ {len(flagged)} query bị loại (seed chấm 0 điểm) → {FLAGGED_PATH} — nên review tay")


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["sample", "generate", "judge", "finalize", "all"], default="all")
    parser.add_argument("--n-single", type=int, default=60, help="Số query hẹp (1 chunk)")
    parser.add_argument("--n-multi", type=int, default=40, help="Số query rộng (nhiều chunk)")
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--judge-model", default=None,
        help="Model chấm relevance. Mặc định `judge_model` trong config (khác họ với model sinh dữ liệu)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in kế hoạch bốc mẫu, không ghi file, không gọi API")
    args = parser.parse_args()

    chunks = load_chunks()
    print(f"Đã nạp {len(chunks)} chunk từ {CHUNKS_DIR}")

    if args.stage in ("sample", "all") or args.dry_run:
        payload = build_seeds(chunks, args.n_single, args.n_multi, args.seed)
        print_sample_plan(chunks, payload)
        if args.dry_run:
            return
        write_json_atomic(SEEDS_PATH, payload)
        print(f"\nĐã lưu seed → {SEEDS_PATH}")
        if args.stage == "sample":
            return

    with open(SEEDS_PATH, encoding="utf-8") as f:
        seeds = json.load(f)["seeds"]

    if args.stage in ("generate", "all"):
        queries = stage_generate(seeds, chunks, args.workers)
        if args.stage == "generate":
            return
    else:
        with open(QUERIES_PATH, encoding="utf-8") as f:
            queries = json.load(f)

    if args.stage in ("judge", "all"):
        judgments = stage_judge(queries, chunks, args.workers, args.judge_model or get_settings().judge_model)
        if args.stage == "judge":
            return
    else:
        with open(judgments_path(args.judge_model or get_settings().judge_model), encoding="utf-8") as f:
            judgments = json.load(f)

    stage_finalize(queries, judgments, args.seed)


if __name__ == "__main__":
    main()
