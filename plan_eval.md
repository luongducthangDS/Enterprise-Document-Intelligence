# Kế hoạch Eval Nhiều Tầng — P-153 HR RAG Chatbot

> Tài liệu thiết kế hệ thống đánh giá (evaluation) theo pipeline RAG nhiều tầng.
> Ngày tạo: 2026-08-05

---

## 1. Bối cảnh

### 1.1. Pipeline hiện tại

```
router → retrieve → grade → [rewrite→retrieve] → generate → hallucination_check → confidence → [escalate|finalize]
```

| Node | File | Vai trò |
|---|---|---|
| `router` | `src/agents/nodes/router.py` | Phân loại intent → route đúng nhánh |
| `retrieve` | `src/agents/nodes/retrieval.py` | Embed query + search Chroma Cloud |
| `grade` | `src/agents/nodes/retrieval.py` | Lọc chunk theo `retrieval_max_distance` |
| `rewrite` | `src/agents/nodes/retrieval.py` | LLM viết lại query → retry retrieve |
| `generate` | `src/agents/nodes/generation.py` | Sinh câu trả lời từ context |
| `hallucination_check` | `src/agents/nodes/generation.py` | Kiểm tra answer có grounded không |
| `confidence` | `src/agents/nodes/generation.py` | Chấm confidence → escalate hoặc finalize |
| `escalate_ticket` | `src/agents/nodes/escalation.py` | Escalate cho human agent |

### 1.2. Hạ tầng eval hiện có

| Thành phần | Đường dẫn | Trạng thái |
|---|---|---|
| Dataset | `eval/datasets/qa_eval_set.json` | 100 câu (60 in_scope + 40 other) — thiết kế cho gen/agent eval |
| Script retrieval | `eval/scripts/eval_retrieval.py` | Có, đo Hit Rate@K + MRR (substring match) |
| Script agent | `eval/scripts/eval_agent.py` | Có, đo pass rate by type |
| Helper | `eval/scripts/_text_utils.py` | `normalize_for_match` |
| Unit test | `tests/test_agents/test_retrieval.py` | Test logic retrieval_node/grade/rewrite với mock |

### 1.3. Vấn đề hiện tại

- **Không có dataset retrieval chuyên dụng**: `qa_eval_set.json` thiết kế cho gen eval, `ground_truth_context` là snippet text, không phải chunk ID/document ID.
- **Không có relevance judgments (qrel) ở chunk-level**: Hiện chỉ có `source_file` (document-level) — không đủ để biết retrieval có trúng **chunk cụ thể** hay không. Cần mapping đến `chunk_id` (format `{stem}::{idx:04d}`, ví dụ `bo_luat_lao_dong::0007`).
- **Không hỗ trợ multi-chunk questions**: Nhiều câu hỏi cần truy xuất **nhiều chunk** để trả lời đầy đủ (ví dụ: "thời hạn báo trước tăng ca + ai có thẩm quyền phê duyệt" cần 2 chunk khác nhau). Hiện eval chỉ check first-hit, không đo xem có tìm đủ **tất cả** chunk relevant không.
- **Không có eval riêng cho từng tầng**: Router, grade, rewrite, hallucination check chưa có script eval riêng.
- **Metric chưa đầy đủ**: Thiếu Faithfulness, Answer Relevance, nDCG, latency.

---

## 2. Kế hoạch Eval Nhiều Tầng

### Tầng 1 — Router (Intent Classification)

**Mục tiêu:** Đo độ chính xác phân loại intent để route đúng nhánh.

| Metric | Ý nghĩa |
|---|---|
| Accuracy | % câu dự đoán intent đúng |
| Precision / Recall / F1 per-class | Cho 4 lớp: `hr_question`, `ambiguous`, `out_of_scope`, `greeting` |
| Confusion Matrix | Xem nhầm lẫn giữa các lớp |
| Latency p50 / p95 | Độ trễ router |

**Cách chấm:** So sánh `result["intent"]` vs `item["type"]` (mapping: `in_scope`→`hr_question`, `ambiguous`→`ambiguous`, `out_of_scope`/`competitor_comparison`→`out_of_scope`).

**File:** `eval/scripts/eval_router.py` (mới)

---

### Tầng 2 — Retrieval (Embedding + Vector Search)

**Mục tiêu:** Đo chất lượng search thuần, độc lập với agent logic. **Quan trọng**: phải đánh giá ở mức **chunk** (không chỉ document), và hỗ trợ câu hỏi cần **nhiều chunk**.

#### 2.1. Vì sao phải đánh giá chunk-level + multi-chunk

- **Chunk-level**: `source_file` (document-level) chỉ cho biết retrieval tìm đúng **tài liệu** — không đủ. Cần biết retrieval có trúng **chunk cụ thể** (đoạn chứa câu trả lời) hay không. Ví dụ: `bo_luat_lao_dong::0007` chứa Điều 107 về tăng ca, `bo_luat_lao_dong::0012` chứa Điều 111 về chuyển việc — query "thời hạn báo trước tăng ca" phải trúng `::0007`, không phải `::0012`.
- **Multi-chunk**: Nhiều câu hỏi cần **nhiều chunk** để trả lời đầy đủ. Ví dụ: "Thời hạn báo trước tăng ca và ai có thẩm quyền phê duyệt?" cần 2 chunk — 1 chunk về thời hạn (Điều 107), 1 chunk về thẩm quyền (Điều 107 hoặc quy định nội bộ khác). Nếu eval chỉ check first-hit, sẽ miss chunk thứ 2.

#### 2.2. Format chunk_id

```
{source_stem}::{chunk_index:04d}
```

Ví dụ: `bo_luat_lao_dong::0007`, `quy_che_tuyen_dung::0003`, `chinh_sach_luong::0012`

Chunk ID được lưu trong Chroma metadata field `chunk_id`, và cũng là document `id` trong collection.

#### 2.3. Metric

| Metric | Ý nghĩa | Multi-chunk? |
|---|---|---|
| **Recall@K** (K=1,3,5,10) | `\|relevant_chunks ∩ top-K\| / \|relevant_chunks\|` — tỷ lệ chunk relevant tìm thấy trong top-K | **Có** — đo xem tìm đủ **tất cả** chunk relevant chưa |
| **Precision@K** | `\|relevant_chunks ∩ top-K\| / K` — tỷ lệ chunk trong top-K thực sự relevant | **Có** |
| **Hit Rate@K** | Tỷ lệ câu tìm thấy **ít nhất 1** chunk relevant trong top-K | Bất kể 1 hay nhiều |
| **MRR** | `1/rank` của chunk relevant **đầu tiên`** — thứ hạng trung bình | Bất kể |
| **nDCG@K** | Xếp hạng có trọng số — thưởng khi chunk relevant xếp cao | **Có** — có ý nghĩa khi nhiều chunk relevant |
| **Coverage@K** | % query có ít nhất 1 kết quả trong top-K | Bất kể |
| **Multi-chunk Recall@K** | `% query có Recall@K = 1.0` (tìm đủ **tất cả** chunk relevant) | **Có** — metric quan trọng nhất cho multi-chunk |

**Công thức Recall@K (multi-chunk):**

```
Cho query q có relevant_chunks = {c1, c2, c3} (3 chunk relevant)
Retrieved top-K = [r1, r2, r3, r4, r5] (K=5)

Recall@5 = |{c1,c2,c3} ∩ {r1,r2,r3,r4,r5}| / |{c1,c2,c3}|
         = (số chunk relevant nằm trong top-5) / 3
```

#### 2.4. Yêu cầu dataset

Mỗi câu in_scope cần field:

```json
{
  "id": "q_001",
  "question": "Thời hạn báo trước tăng ca và ai có thẩm quyền phê duyệt?",
  "type": "in_scope",
  "relevant_chunk_ids": ["bo_luat_lao_dong::0007", "quy_che_tang_ca::0003"],
  "relevant_source_files": ["bo_luat_lao_dong.pdf", "quy_che_tang_ca.pdf"],
  "ground_truth_context": "...",  // giữ làm fallback
  "expected_answer": "..."
}
```

- `relevant_chunk_ids`: **list** chunk ID (1 hoặc nhiều) — đây là ground truth chính
- `relevant_source_files`: **list** source_file — dùng cho document-level eval
- `ground_truth_context`: giữ làm fallback khi chưa có qrel chunk-level

**File:** `eval/scripts/eval_retrieval.py` (nâng cấp) + `eval/datasets/retrieval_qrels.json` (mới — qrel chuẩn chunk-level)

---

### Tầng 3 — Grading (Distance Filter)

**Mục tiêu:** Đo chất lượng lọc chunk bằng ngưỡng `retrieval_max_distance`. **Quan trọng**: grade phải giữ lại **tất cả** chunk relevant, không chỉ 1 — nếu lọc mất chunk relevant thứ 2 của multi-chunk question, generation sẽ thiếu thông tin.

| Metric | Ý nghĩa |
|---|---|
| Precision sau grade | % chunk giữ lại thực sự relevant |
| Recall sau grade | % chunk relevant bị giữ lại (không bị lọc nhầm) — **đặc biệt quan trọng cho multi-chunk** |
| Multi-chunk Recall sau grade | % query giữ đủ **tất cả** chunk relevant sau grade |
| Chunk retention rate | Tỷ lệ chunk trung bình còn sau grade |
| Empty-after-grade rate | % query không còn chunk nào sau grade (gây trigger rewrite) |

**Cách chấm:** Cần qrel (chunk relevant/non-relevant) để tính precision/recall của bộ lọc. Dùng cùng `relevant_chunk_ids` từ Tầng 2.

**File:** Tích hợp vào `eval_retrieval.py` (thêm section "post-grade metrics")

---

### Tầng 4 — Rewrite (Query Transformation)

**Mục tiêu:** Đo xem rewrite có cải thiện retrieval không — đặc biệt cho multi-chunk question khi query gốc miss 1 trong nhiều chunk relevant.

| Metric | Ý nghĩa |
|---|---|
| Recall@K trước vs sau rewrite | So sánh Recall@K (multi-chunk) của query gốc vs rewritten |
| Hit Rate trước vs sau rewrite | So sánh top-K hit của query gốc vs rewritten |
| MRR delta | Thay đổi MRR sau rewrite |
| Rewrite trigger rate | % query cần rewrite (grade rỗng) |
| Rewrite improvement rate | % query rewrite xong tìm thấy kết quả |
| Multi-chunk recovery rate | % query rewrite xong tìm đủ **tất cả** chunk relevant (Recall@K = 1.0) |

**File:** `eval/scripts/eval_rewrite.py` (mới)

---

### Tầng 5 — Generation (Answer Quality)

**Mục tiêu:** Đo chất lượng câu trả lời cuối. **Quan trọng**: với multi-chunk question, answer phải **tổng hợp thông tin từ nhiều chunk** — cần đo xem answer có bao phủ đủ tất cả điểm cần trả lời không.

| Metric | Ý nghĩa |
|---|---|
| Faithfulness | Answer có grounded trong retrieved context không (anti-hallucination) |
| Answer Relevance | Answer có trả lời đúng câu hỏi không |
| Context Precision / Recall | Context đưa cho LLM có relevant không |
| **Multi-chunk Coverage** | % answer bao phủ đủ **tất cả** điểm cần trả lời (mỗi chunk relevant → 1 điểm) — đo bằng LLM-as-judge hoặc so khớp `expected_answer` |
| Grounding score | % câu có `ground_truth_context` xuất hiện trong answer |
| ROUGE-L / semantic similarity vs `expected_answer` | Đo giống câu trả lời kỳ vọng |
| Latency p50 / p95 | Độ trễ generate |

**Công cụ:** Dùng **RAGAS** (thêm vào requirements) hoặc tự implement heuristic + LLM-as-judge.

**File:** `eval/scripts/eval_generation.py` (mới)

---

### Tầng 6 — Hallucination Check

**Mục tiêu:** Đo chất lượng bước kiểm tra hallucination.

| Metric | Ý nghĩa |
|---|---|
| Hallucination detection accuracy | % câu flag hallucination đúng (so với ground truth) |
| False positive rate | % câu grounded nhưng bị flag sai |
| False negative rate | % câu hallucinated nhưng bị bỏ qua |
| Retry rate | % query cần retry generate |

**Cách chấm:** Tạo subset câu có answer cố tình sai (negative samples) + câu đúng.

**File:** `eval/scripts/eval_hallucination.py` (mới)

---

### Tầng 7 — End-to-End (Agent Behavior)

**Mục tiêu:** Đo hành vi cuối cùng của toàn bộ pipeline.

| Metric | Ý nghĩa |
|---|---|
| Pass rate by type | in_scope / ambiguous / out_of_scope pass đúng behavior |
| Escalation accuracy | % câu out_of_scope escalate đúng |
| Clarification accuracy | % câu ambiguous ask_clarification đúng |
| Context found rate | % câu in_scope có context đúng trong retrieved_chunks |
| End-to-end latency p50 / p95 | Tổng thời gian |

**File:** `eval/scripts/eval_agent.py` (nâng cấp thêm latency)

---

## 3. Dataset cần bổ sung

| File | Mục đích | Trạng thái |
|---|---|---|
| `eval/datasets/qa_eval_set.json` | Gen/agent eval (100 câu) — **cần thêm field `relevant_chunk_ids` (list) cho 60 câu in_scope** | Đã có, cần nâng cấp |
| `eval/datasets/retrieval_qrels.json` | Qrel chuẩn chunk-level + multi-chunk: `{query_id: {chunk_id: relevance_score}}` — 1 query có thể có **nhiều chunk relevant** | **Mới** |
| `eval/datasets/hallucination_samples.json` | Subset câu có answer đúng + sai để test hallucination check | **Mới** |

### 3.1. Format qrel multi-chunk

```json
{
  "q_001": {
    "bo_luat_lao_dong::0007": 2,
    "quy_che_tang_ca::0003": 1
  },
  "q_002": {
    "chinh_sach_luong::0012": 2
  },
  "q_003": {
    "quy_che_tuyen_dung::0003": 2,
    "quy_che_tuyen_dung::0004": 2,
    "bo_luat_lao_dong::0107": 1
  }
}
```

- Relevance score: `2` = directly relevant (chứa câu trả lời chính), `1` = supporting context (bổ trợ), `0` = not relevant
- 1 query có thể có **1 hoặc nhiều** chunk relevant — đây là điểm khác biệt vs eval hiện tại (chỉ check first-hit)

---

## 4. Cấu trúc thư mục đề xuất

```
eval/
├── datasets/
│   ├── qa_eval_set.json            (existing)
│   ├── retrieval_qrels.json        (new)
│   └── hallucination_samples.json  (new)
├── scripts/
│   ├── _text_utils.py              (existing)
│   ├── eval_router.py              (new — Tầng 1)
│   ├── eval_retrieval.py           (upgrade — Tầng 2+3)
│   ├── eval_rewrite.py             (new — Tầng 4)
│   ├── eval_generation.py          (new — Tầng 5)
│   ├── eval_hallucination.py       (new — Tầng 6)
│   ├── eval_agent.py               (upgrade — Tầng 7)
│   └── run_all.py                  (new — chạy tất cả tầng, tổng hợp báo cáo)
├── results/
│   ├── router_eval_report.json
│   ├── retrieval_eval_report.json
│   ├── rewrite_eval_report.json
│   ├── generation_eval_report.json
│   ├── hallucination_eval_report.json
│   └── agent_eval_report.json
└── plan_eval.md                    (file này)
```

---

## 5. Makefile targets đề xuất

```makefile
eval-router:        # Tầng 1 — Router
eval-retrieval:     # Tầng 2+3 — Retrieval + Grading
eval-rewrite:       # Tầng 4 — Rewrite
eval-generation:    # Tầng 5 — Generation
eval-hallucination: # Tầng 6 — Hallucination Check
eval-agent:         # Tầng 7 — End-to-End
eval-all:           # Tất cả tầng + tổng hợp báo cáo
```

---

## 6. Thứ tự ưu tiên triển khai

| Ưu tiên | Tầng | Lý do |
|---|---|---|
| 1 | Tầng 2 (Retrieval) | Impact cao nhất — retrieval đang yếu (Hit@10=75%), cần qrel chuẩn |
| 2 | Tầng 1 (Router) | Script đơn giản, dùng dataset hiện có |
| 3 | Tầng 5 (Generation) | Cần RAGAS hoặc LLM-as-judge |
| 4 | Tầng 7 (Agent E2E) | Nâng cấp `eval_agent.py` thêm latency |
| 5 | Tầng 3, 4, 6 | Cần qrel/negative samples, phức tạp hơn |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Tạo qrel chunk-level thủ công tốn thời gian (60 câu × review nhiều chunk) | Dùng LLM-assisted labeling (cho LLM đọc chunk + question → gán relevance) → human review |
| **Multi-chunk labeling khó**: xác định 1 câu cần bao nhiêu chunk | Bắt đầu với single-chunk qrel, sau đó review các câu có `expected_answer` dài / nhiều ý → nâng cấp lên multi-chunk |
| RAGAS cần thêm dependency + API key | Thêm optional vào requirements, fallback LLM-as-judge nội bộ |
| Hallucination samples cần tạo negative cases cẩn thận | Sinh bằng LLM + human verify |
| Chi phí API khi chạy nhiều tầng | Cho phép `--limit N` và `--concurrency` để kiểm soát |
| Substring match không chuẩn cho retrieval | Ưu tiên tạo qrel bằng chunk ID; substring match chỉ là fallback |
| **Chunk boundary thay đổi** khi re-chunk → chunk_id cũ không còn đúng | Pin chunk_id trong qrel; khi re-chunk phải re-label. Hoặc dùng metadata (source_file + article/chapter) làm secondary key |

---

## 8. Kết quả baseline hiện tại (2026-08-05, sau đợt fix router prompt + eval set + normalize)

> Cập nhật: bản trước của mục này viết trước đợt fix router/eval-set, số liệu đã lỗi thời. Số dưới đây là kết quả chạy thật cuối cùng, đã verify.

### Retrieval — Chunk-level (eval_retrieval.py, so khớp chuỗi con ground_truth_context)

```
in_scope_n: 60
hit_rate@1:  0.417  (25/60)
hit_rate@3:  0.633  (38/60)
hit_rate@5:  0.717  (43/60)
hit_rate@10: 0.75   (45/60)
mrr:         0.543
other_n: 40
other_avg_top1_distance: 0.335
```

### Retrieval — Chunk-level qrel-based (mới, 2026-08-06 — thay thế substring match, xem mục 9)

Qrel xây bằng `scripts/build_retrieval_qrels.py`: 60/60 câu map được, 0 multi-chunk tự phát hiện (mỗi câu chỉ có đúng 1 chunk relevant trong Chroma Cloud). Lưu ở `eval/datasets/retrieval_qrels.json`.

```
recall@1:  0.417   precision@1:  0.417  ndcg@1:  0.417
recall@3:  0.633   precision@3:  0.211  ndcg@3:  0.549
recall@5:  0.717   precision@5:  0.143  ndcg@5:  0.583
recall@10: 0.750   precision@10: 0.075  ndcg@10: 0.594
multi_chunk_recall@K == recall@K (mọi câu chỉ có 1 relevant chunk)
mrr: 0.543
```

Khớp gần như tuyệt đối với số liệu Hit Rate@K/MRR substring-match cũ (dự đoán đúng về mặt toán học khi mỗi câu chỉ có 1 relevant item) — xác nhận cách đo cũ không sai lệch hệ thống, nhưng qrel-based đúng phương pháp luận hơn (so ID chính xác) và sẵn sàng cho multi-chunk nếu sau này cần.

### Retrieval — Document-level (so field `source_file` đã backfill)

```
doc_hit_rate@1:  0.700  (42/60)
doc_hit_rate@3:  0.833  (50/60)
doc_hit_rate@5:  0.883  (53/60)
doc_hit_rate@10: 0.933  (56/60)
```

Chênh lệch 75% (chunk) vs 93.3% (document) → retrieval hầu như luôn tìm đúng TÀI LIỆU, nhưng không phải lúc nào cũng trúng đúng ĐOẠN cụ thể — vấn đề còn lại nằm nhiều ở chunking/ranking trong 1 document hơn là embedding chọn sai tài liệu.

### Router (eval_router.py — mới)

```
Accuracy: 0.91 (91/100)

hr_question               P=0.98 R=0.92 F1=0.95 (support=60)
ambiguous                 P=1.00 R=0.73 F1=0.85 (support=15)
out_of_scope_or_personal  P=0.76 R=1.00 F1=0.86 (support=25)

Confusion:
  ambiguous -> hr_question: 1
  ambiguous -> out_of_scope_or_personal: 3
  hr_question -> out_of_scope_or_personal: 5
```

### Agent — End-to-End (eval_agent.py)

```
Tổng: 75/100

- in_scope:              39/60  (65.0%)
- ambiguous:              11/15  (73.3%)
- competitor_comparison:  10/10  (100.0%)
- out_of_scope:           15/15  (100.0%)
```

**Liên kết giữa 2 eval**: đối chiếu router eval với agent eval, xác nhận 5/5 câu router misfire (`hr_question`→`out_of_scope_or_personal`) đều nằm trong 21 câu in_scope fail → 5/21 (24%) fail do router, 16/21 còn lại mới thật sự là vấn đề retrieval/generation.

---

## 9. Bước tiếp theo

> Cập nhật (2026-08-06): đã hoàn tất chunk-level qrel (mục 9.1 cũ). Không dùng LLM-assisted labeling như đề xuất ban đầu — xây qrel deterministic (string match `ground_truth_context` đã verify verbatim, lấy dữ liệu trực tiếp từ Chroma Cloud) để tránh lặp lại lỗi "LLM bịa nội dung tưởng verbatim" đã gặp (xem CLAUDE.md 2026-08-05). Kết quả: 60/60 câu single-chunk, 0 multi-chunk phát hiện được — nên phần "multi-chunk" của kế hoạch coi như đã xử lý ở mức "không có case nào cần" cho bộ dữ liệu hiện tại, không phải bị bỏ qua.

### 9.1. Đã làm

- Backfill field `source_file` (document-level) vào `qa_eval_set.json` qua `scripts/backfill_eval_source_file.py`.
- **Xây `eval/datasets/retrieval_qrels.json`** (chunk-level qrel, `{query_id: {chunk_id: relevance_score}}`) qua `scripts/build_retrieval_qrels.py` — deterministic, không dùng LLM. Backfill thêm field `relevant_chunk_ids` vào `qa_eval_set.json`.
- Nâng cấp `eval/scripts/eval_retrieval.py` — thay substring-match cũ bằng Recall@K/Precision@K/nDCG@K/Multi-chunk Recall@K tính từ qrel, giữ Document Hit Rate@K làm tham chiếu.
- Tạo `eval/scripts/eval_router.py` — accuracy, P/R/F1, confusion matrix.
- Dọn `eval/`: xoá backup/`.gitkeep`/`__pycache__` thừa; xác nhận `eval/results/report.md` là deliverable bắt buộc #10 của cohort (KHÔNG xoá) và `mock_user_personas.json` là artifact chủ đích cho việc sau (giữ).

### 9.2. Còn lại (hoãn, chỉ làm nếu còn thời gian)

1. Điền số liệu thật vào `eval/results/report.md` (deliverable bắt buộc, hiện vẫn là template rỗng).
2. `eval/scripts/eval_generation.py` (RAGAS hoặc LLM-as-judge) — cần adapter riêng nếu dùng RAGAS; nên tự làm LLM-as-judge bằng `fpt_client.chat_completion` sẵn có. Thêm metric **Multi-chunk Coverage** nếu sau này có câu hỏi multi-chunk thật.
3. `eval/scripts/eval_agent.py` + latency — chưa cấp thiết cho quy mô demo.
4. `eval/scripts/eval_rewrite.py`, `eval_hallucination.py` — nhánh phụ ít khi kích hoạt; rủi ro cao khi tự sinh negative samples bằng LLM (đúng bài học đã rút ra).
5. `eval/scripts/run_all.py` + Makefile targets — chưa cần khi số script còn ít (4 script, chạy tay vẫn nhanh).
6. Nếu tương lai có câu hỏi in_scope mới cần **thật sự** nhiều chunk để trả lời đủ (multi-chunk) — phải gán `relevant_chunk_ids` thủ công/review tay cho câu đó, không dùng LLM đoán thêm.
- Tầng 3 (Grading riêng) — không cần script riêng, tái sử dụng số liệu Tầng 2 ở threshold khác.
