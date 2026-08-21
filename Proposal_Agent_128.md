# Đề xuất nâng tầng kỹ thuật Agent — HR Document Intelligence

> Mục tiêu: bổ sung các kỹ thuật ở **tầng agent** để hồ sơ dự án thể hiện được năng lực AI Engineer thật, không phải "làm theo tutorial RAG".
> Đối tượng đọc: hiring manager / AI Engineer phỏng vấn — người sẽ mở code 10 phút và hỏi *"vì sao anh chọn cái này?"*

---

## 0. Nguyên tắc chọn đề xuất

Nhà tuyển dụng AI Engineer **không ấn tượng vì số lượng node**. Họ ấn tượng vì 3 thứ:

1. **Kỹ thuật được chọn để giải một vấn đề ĐO ĐƯỢC** — không phải vì nó đang hot.
2. **Có trade-off rõ ràng, và biết TỪ CHỐI kỹ thuật không phù hợp** — đây là thứ phân biệt engineer với người ghép thư viện.
3. **Chứng minh được bằng số before/after** — không phải "cảm giác tốt hơn".

Vì vậy mọi đề xuất dưới đây đều theo đúng khuôn: **Vấn đề (có số đo thật trong repo) → Thiết kế (khớp code hiện có) → Cách chứng minh → Chi phí → Câu hỏi phỏng vấn nó mở ra.**

Dự án hiện đã có sẵn nền rất tốt để làm việc này: `eval/` có qrels + CI bootstrap, `config.py` chú thích bằng số đo thật, `service.py` đã có `stage_timings_ms` và audit log. Các đề xuất bám vào nền đó thay vì dựng mới.

---

## TIER 1 — Làm trước, đòn bẩy cao nhất

### 1. Tool-calling layer: HR Computation Tools ⭐ *(đề xuất trọng tâm)*

**Vấn đề.** LLM tính số học không đáng tin, nhưng một tỷ lệ lớn câu hỏi HR Việt Nam **là bài toán deterministic có công thức trong luật**:

| Bài toán | Căn cứ | Tính chất |
|---|---|---|
| Trợ cấp thôi việc | Điều 46 BLLĐ 2019 | Deterministic |
| Trợ cấp mất việc làm | Điều 47 BLLĐ 2019 | Deterministic |
| Ngày phép năm theo thâm niên | Điều 113–114 BLLĐ | Deterministic |
| Lương làm thêm giờ (150/200/300%) | Điều 98 BLLĐ | Deterministic |
| Thuế TNCN lũy tiến từng phần | Luật thuế TNCN (đã có trong corpus) | Deterministic |
| Mức lương tối thiểu vùng | NĐ 293/2025 (đã có trong corpus) | Tra bảng |

Hiện agent để LLM **đọc điều luật rồi tự tính** — đây đúng là chỗ hallucination số liệu sinh ra. Trong 8 câu `in_scope` "context đúng nhưng trả lời sai" (`eval/results/agent_eval_report.json`), cần bóc tách xem bao nhiêu câu thuộc dạng tính toán — em dự đoán tỷ lệ đáng kể, và đây là số cần đo trước khi làm.

**Thiết kế.** Thêm nhánh tool vào graph hiện có, đặt **sau `grade`, trước `generate`**:

```
grade → tool_planner ─(có tool phù hợp)→ tool_exec → generate
              └────────(không)──────────────────────→ generate
```

- `tool_planner`: LLM đọc câu hỏi + context, trả về JSON `{tool_name, params}` hoặc `null`. Dùng `router_model` (DeepSeek-V4-Flash) — đây là tác vụ phân loại + trích xuất, không cần model to.
- `tool_exec`: thực thi **hàm Python thuần**, deterministic, có unit test riêng. Không gọi LLM.
- Kết quả tool đưa vào `generate` như một nguồn đặc biệt: `[Tính toán] <kết quả> (công thức: ..., căn cứ: Điều 46 BLLĐ)`.
- Citation trả về kèm **cả công thức lẫn điều luật** — user kiểm chứng được.

Điểm tinh tế nên làm (và nên nói trong phỏng vấn): **tool chỉ chạy khi tham số đủ và hợp lệ**. Thiếu tham số (vd không biết thâm niên) → không đoán bừa, mà chuyển sang `clarify` hỏi lại. Đây là chỗ tái dùng đúng node `clarify_node` đã có.

**Cách chứng minh.** Dựng `eval/datasets/computation_set.json` (~30 câu có đáp án số chính xác), đo:
- Accuracy số học: baseline (LLM tự tính) vs có tool.
- Đây là loại metric **không thể tranh cãi** — đúng hoặc sai, không cần LLM judge.

**Chi phí ước tính.** 2–3 ngày: 5–6 tool + planner node + eval set.

**Câu hỏi phỏng vấn nó mở ra (đây là giá trị thật):**
- *"Nếu tool và tài liệu mâu thuẫn thì tin ai?"* → trả lời được vì `generate` đã có sẵn quy tắc ưu tiên nguồn 3 bậc.
- *"Làm sao biết LLM trích tham số đúng?"* → validate schema + echo tham số vào câu trả lời để user tự kiểm.
- *"Vì sao không để LLM tự tính, model bây giờ tính tốt mà?"* → vì sai 5% trên tiền lương là không chấp nhận được, và tool cho phép **audit** được cách ra số.

---

### 2. Query Decomposition — Multi-hop Retrieval

**Vấn đề — có số đo cực chắc.** `eval/results/retrieval_eval_hybrid_report.json`:

| Metric | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| `recall` | 0,575 | 0,784 | 0,882 | 0,937 |
| **`multi_chunk_recall`** | **0,384** | **0,603** | 0,753 | 0,849 |

Khoảng cách giữa 2 dòng chính là **câu hỏi cần nhiều đoạn từ nhiều tài liệu thì retrieval một lượt trượt nặng**. Mà câu hỏi HR thật lại hay đúng dạng đó:

> *"Tôi nghỉ việc sau 3 năm thì được trợ cấp bao nhiêu, và có phải hoàn tiền đào tạo không?"*
> → cần Điều 46 BLLĐ **+** quy chế đào tạo/bồi hoàn — hai tài liệu khác nhau.

**Thiết kế.** Node `decompose` đặt giữa `router` và `retrieve`:

- Kích hoạt **có điều kiện**, không phải mọi câu: heuristic rẻ trước (phát hiện liên từ "và/hoặc", nhiều dấu hỏi, nhiều mệnh đề) → chỉ khi khớp mới gọi LLM tách.
- Budget cứng: **tối đa 3 sub-query** — chặn latency nổ.
- Retrieve các sub-query **song song** (`asyncio.gather`) → không cộng dồn latency.
- Hợp nhất bằng **RRF** — tái dùng đúng `fuse_candidate_ids` đã có trong `src/retrieval/hybrid.py`, không viết cơ chế mới.
- Dedupe theo `chunk_id`, rồi mới rerank một lượt.

**Cách chứng minh.** Chạy lại `eval/scripts/eval_retrieval.py` trên đúng bộ qrels hiện có, so `multi_chunk_recall@5` trước/sau. Đây là A/B sạch vì baseline đã tồn tại.

**Chi phí.** 1–2 ngày.

**Vì sao ấn tượng.** Ứng viên chỉ ra được *"metric X của tôi thấp → tôi thêm kỹ thuật Y → metric X tăng bao nhiêu"* là mẫu tư duy mà interviewer tìm kiếm. Ở đây baseline đã có sẵn nên câu chuyện rất chặt.

---

### 3. Parent-Document Retrieval cho văn bản pháp luật

**Vấn đề — có số đo.** `eval/results/retrieval_eval_reranked.json` (n=100):

- `doc_hit_rate@1` = **0,87** — tìm đúng **TÀI LIỆU** rất tốt.
- `recall@1` = **0,58** — nhưng sai **ĐOẠN**.

Comment trong `retrieval.py` đã ghi nhận đúng hiện tượng này. Reranker đã kéo lên được một phần, nhưng còn một nguyên nhân **chưa được khai thác**: chunker đã trích sẵn `chapter` / `article` / `heading_path` vào metadata (`src/ingestion/metadata.py`) nhưng **retrieval không hề dùng tới**.

**Thiết kế (small-to-big).**
- Vẫn embed và tìm ở mức chunk nhỏ (chính xác về ngữ nghĩa).
- Khi trúng một chunk thuộc văn bản luật (`source_type == "government_law"`), **mở rộng lên toàn bộ Điều** chứa nó — lấy các chunk cùng `source_stem` + cùng `article` qua `collection.get(where=...)`, ghép lại theo `chunk_index`.
- Lý do đúng domain: một Điều luật là **đơn vị ngữ nghĩa nguyên tử**. Trả nửa Điều cho câu hỏi pháp lý thường tạo ra câu trả lời thiếu khoản loại trừ — đúng loại lỗi nguy hiểm nhất trong HR.
- Có trần độ dài để không nổ context (Điều quá dài thì giữ chunk gốc + các chunk liền kề).

**Cách chứng minh.** Metric hiện tại (`recall@k` theo chunk) sẽ **không** phản ánh đúng cải thiện này — cần nói rõ điều đó, và đo bằng: (a) tỷ lệ câu trả lời có đủ khoản loại trừ trên bộ câu hỏi pháp lý, (b) `answer_correct` trên nhóm `in_scope` category legal.

**Chi phí.** 1 ngày.

**Vì sao ấn tượng.** Thể hiện hiểu domain (cấu trúc văn bản pháp luật VN) chứ không chỉ hiểu thư viện. Và việc **tự nhận metric hiện tại không đo được cải thiện này** là dấu hiệu trưởng thành về evaluation.

---

### 4. Confidence Calibration — thay ngưỡng chỉnh tay bằng xác suất có căn cứ

**Vấn đề.** `confidence_node` hiện lấy `max(rerank_score)` làm confidence, so với ngưỡng `0.2` chỉnh tay. Comment trong `config.py` cho thấy ngưỡng này đã phải chỉnh đi chỉnh lại (0,5 → 0,2) và mỗi lần chỉnh lại kéo theo phải chỉnh `fail_cap`. Đó là triệu chứng kinh điển của **score chưa được hiệu chuẩn**: rerank score **không phải** xác suất trả lời đúng.

**Thiết kế.**
- Đã có sẵn nguyên liệu: 140 câu trong `agent_eval_report.json` đều có `retrieved_scores` + nhãn `answer_correct`.
- Fit **Platt scaling** (logistic 1 chiều) hoặc **isotonic regression** ánh xạ `rerank_score → P(đúng)`. Feature có thể mở rộng: `max_score`, `score_gap` giữa top-1 và top-2, `num_chunks_passed_grade`, `answerable`.
- Đo bằng **ECE (Expected Calibration Error)** + reliability diagram trước/sau.
- Khi đó ngưỡng escalate trở thành câu hỏi **business** rõ ràng: *"escalate khi P(đúng) < 70%"* — chứ không còn là con số ma thuật 0,2.

**Chi phí.** 1 ngày (scikit-learn, dữ liệu đã có, không cần gọi API).

**Vì sao ấn tượng — em xếp đây là đề xuất "rẻ nhất trên mỗi đơn vị ấn tượng".** Rất ít ứng viên RAG biết phân biệt *score* với *xác suất đã hiệu chuẩn*. Nói được câu *"tôi đo ECE và hiệu chuẩn confidence bằng Platt scaling trên tập eval có nhãn"* là tín hiệu rõ ràng của người làm ML thật, không phải chỉ ghép prompt.

---

## TIER 2 — Nâng chất lượng vận hành

### 5. Adaptive Retrieval Policy (router 2 chiều)

**Vấn đề.** Hiện mọi câu `hr_question` đi chung một đường retrieval (top_k=25 → rerank 10). Nhưng 3 loại câu hỏi có đặc tính rất khác nhau:

| Loại | Đặc tính | Chiến lược nên dùng |
|---|---|---|
| Tra cứu pháp lý | Cần đúng Điều, đủ khoản | Parent-document + metadata filter `source_type=government_law` |
| Chính sách công ty | Cần đúng bản mới nhất | Hybrid + ưu tiên `effective_date` mới |
| Quy trình (procedural) | Cần **nhiều bước liên tiếp** | Multi-chunk, giữ thứ tự `chunk_index` |

**Thiết kế.** Mở rộng `router_node` trả thêm `topic` (đã có `intent`), rồi `retrieval_node` chọn strategy theo `(intent, topic)`. Không thêm LLM call — gộp vào chính prompt router hiện tại, chỉ đổi output format thành 2 nhãn.

**Chi phí.** 1 ngày. **Chứng minh:** recall theo từng nhóm category (eval set đã có trường `category`).

---

### 6. Semantic Cache có version-aware invalidation

**Vấn đề.** `src/retrieval/cache.py` hiện chỉ cache embedding theo **exact match**. Trong HR thật, phân bố câu hỏi lệch cực mạnh — top ~20 câu chiếm phần lớn traffic, nhưng diễn đạt khác nhau ("nghỉ phép được mấy ngày" / "một năm được bao nhiêu ngày phép").

**Thiết kế.**
- Cache **câu trả lời đã qua guardrail** theo similarity ≥ ngưỡng (vd 0,95 cosine) thay vì exact string.
- Cache key gắn **hash của document version** — re-index là cache tự invalidate. Đây là phần quan trọng nhất và cũng là chỗ hay bị làm sai: cache câu trả lời chính sách mà không invalidate khi chính sách đổi là **lỗi nghiêm trọng**, không phải lỗi hiệu năng.
- **Không** cache nhánh escalate và nhánh có `answerable=False`.

**Chi phí.** 1 ngày. **Chứng minh:** hit rate + p50 latency trên bộ eval chạy 2 lượt; đồng thời phải chứng minh **0 lần trả lời stale** sau khi re-index.

---

### 7. Cost & Latency Budget per Request

**Đã có:** `stage_timings_ms` + audit log JSON 1 dòng/request (`service.py:58`). Nền tốt.

**Còn thiếu:** token in/out per node, cost ước tính per request, và **budget guard**.

**Thiết kế.**
- `fpt_client` trả thêm `usage` → cộng dồn vào state → vào audit log.
- **Budget guard**: nếu request đã vượt ngưỡng thời gian/chi phí, tự bỏ `hallucination retry` lượt 2 và đi thẳng `confidence` (vẫn an toàn vì `confidence_node` cap điểm và escalate).
- Xuất một bảng nhỏ: chi phí trung bình / câu, phân rã theo node.

**Chi phí.** 0,5–1 ngày.

**Vì sao ấn tượng.** Câu hỏi *"một câu trả lời tốn bao nhiêu tiền?"* xuất hiện trong hầu hết buổi phỏng vấn AI Engineer có yếu tố production. Trả lời được kèm bảng phân rã theo node là điểm cộng lớn.

---

## TIER 3 — Đóng vòng lặp

### 8. Online Feedback → Regression Set

Thumbs up/down ở FE → ghi kèm `chunk_ids` + `confidence_score` + `intent` → câu bị down tự động vào `eval/datasets/regression_pending.json` chờ human adjudicate → nhập vào bộ eval chính.

Dự án đã có `make_human_review_sample.py` và `merge_judgments.py` — đây là **hoàn thiện vòng lặp đã xây dở**, không phải làm mới. Chi phí thấp, và nó biến hệ thống từ "chạy một lần" thành "tự cải thiện" — câu chuyện rất tốt khi kể.

### 9. Ablation Study đóng gói thành `EVAL.md`

Không phải thêm kỹ thuật, mà là **làm nổi bật cái đã có**. Một bảng duy nhất:

| Cấu hình | recall@5 | multi_chunk_recall@5 | in_scope acc | p50 latency | cost/query |
|---|---|---|---|---|---|
| Dense only | 0,727\* | — | — | — | — |
| + Reranker | 0,801\* | — | — | — | — |
| + Hybrid BM25 | 0,882 | 0,753 | — | — | — |
| + Decomposition | ? | ? | ? | ? | ? |
| + Tools | — | — | ? | ? | ? |

\* *số từ `retrieval_benchmark_*.json` (n=97), các dòng dưới từ bộ qrels mới (n=73) — khi đóng gói phải chạy lại toàn bộ trên CÙNG một dataset, nếu không bảng sẽ sai lệch.*

Với nhà tuyển dụng, **một bảng ablation đọc 30 giây có sức thuyết phục hơn 500 dòng code**. Đây là việc rẻ nhất và cần làm cuối cùng, sau khi các tier trên xong.

---

## 10. Những gì em đề xuất KHÔNG làm (và lý do)

Phần này quan trọng ngang phần đề xuất — biết từ chối là tín hiệu năng lực rõ nhất.

| Kỹ thuật | Vì sao KHÔNG |
|---|---|
| **Multi-agent debate / critic nhiều vòng** | Nhân 2–3 lần chi phí và latency, trong khi latency đã là vấn đề P0 (p50 16,5s). Không neo vào bất kỳ lỗi đo được nào — 8 câu "context đúng trả lời sai" là lỗi **tính toán và đọc hiểu điều khoản**, tool + parent-document giải trực tiếp và rẻ hơn nhiều. |
| **GraphRAG / knowledge graph** | Corpus 1.498 chunks chưa đủ lớn để hoàn vốn chi phí xây và bảo trì graph. Quan trọng hơn: văn bản luật **vốn đã có cấu trúc cây** (Chương→Mục→Điều) và chunker đã trích ra rồi — parent-document retrieval khai thác đúng cấu trúc đó với chi phí bằng một phần nhỏ. Làm GraphRAG ở đây là dùng dao mổ trâu, và interviewer giỏi sẽ hỏi đúng câu này. |
| **Fine-tune embedding model** | Chỉ có ~100 câu có nhãn → gần như chắc chắn overfit. Reranker cross-encoder đã lấy phần lớn lợi ích (recall@1: 0,375 → 0,477 trên cùng dataset). Chỉ cân nhắc lại khi có >5.000 cặp query-doc từ feedback thật (đề xuất #8). |
| **ReAct loop tự do, không giới hạn bước** | Ngược hẳn triết lý đang làm nên sức mạnh của dự án: graph có kiểm soát, guardrail deterministic, mọi nhánh đều eval được. Agent tự do khó eval, khó reproduce, khó giải thích khi sai — đánh đổi tệ cho một sản phẩm HR nơi câu trả lời sai có hậu quả pháp lý. |
| **Đổi sang framework agent khác (CrewAI/AutoGen)** | Thuần chi phí viết lại, không giải quyết vấn đề đo được nào. LangGraph đang dùng đúng chỗ mạnh của nó (state machine tường minh). |

---

## 11. Lộ trình đề xuất

| Tuần | Việc | Kết quả đo được |
|---|---|---|
| 1 | #1 Tool-calling + #4 Calibration | Accuracy số học; ECE trước/sau |
| 2 | #2 Decomposition + #3 Parent-document | `multi_chunk_recall@5`; recall nhóm legal |
| 3 | #5 Adaptive policy + #6 Semantic cache + #7 Cost budget | recall theo category; p50 latency; cost/query |
| 4 | #8 Feedback loop + #9 `EVAL.md` ablation | Bảng ablation hoàn chỉnh trên cùng 1 dataset |

**Nếu chỉ có thời gian cho 2 việc:** chọn **#1 (Tool-calling)** và **#4 (Calibration)**.
Lý do: #1 là thứ gây ấn tượng mạnh nhất về mặt sản phẩm (agent biết dùng công cụ, không bịa số tiền), #4 là thứ gây ấn tượng mạnh nhất về mặt ML (biết score ≠ xác suất). Hai cái cộng lại phủ đúng hai nửa mà nhà tuyển dụng AI Engineer đánh giá.

---

## 12. Cách trình bày để nhà tuyển dụng thấy được tầng kỹ thuật

Kỹ thuật tốt mà không ai đọc ra thì bằng không. Ba việc cần làm song song:

1. **README có 1 sơ đồ graph + 1 bảng số** ngay phần đầu — không bắt người đọc lội vào code mới thấy pipeline có 12 node.
2. **`EVAL.md` với bảng ablation** (#9) — bằng chứng "tôi đo, không phải tôi đoán".
3. **Một mục "Decisions & Trade-offs"** — trích thẳng các quyết định đã có trong code, vì đây đang là tài sản bị chôn trong comment:
   - Từ chối DeepSeek cho hallucination check (chỉ đồng thuận 76,7%, dưới ngưỡng 95%) dù nhanh gấp đôi.
   - Từ chối skip hallucination check theo rerank score, vì đo được 7 câu reranker tự tin 0,78–1,00 nhưng đoạn sai.
   - Từ chối sort chunk theo `source_type`, vì đo được nó làm regress 3 câu.
   - Từ chối stream token thô, vì guardrail chạy sau `generate` có thể huỷ/sửa câu trả lời.

**Bốn quyết định "đã thử và từ chối có số liệu" này là thứ giá trị nhất trong toàn bộ dự án** — chúng chứng minh có vòng lặp đo-quyết định thật. Hiện chúng chỉ nằm trong comment code, gần như chắc chắn không ai đọc tới trong 10 phút review. Đưa lên README là việc **0 chi phí kỹ thuật, lợi ích cao nhất** trong cả bản đề xuất này.
