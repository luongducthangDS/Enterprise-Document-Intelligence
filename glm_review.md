# Audit Eval — Góc nhìn PM (Bản cập nhật 2026-08-06)

> Đánh giá lại toàn bộ quy trình, dữ liệu eval, metrics, và chunking sau các đợt fix.
> Ngày audit gốc: 2026-08-05 | Cập nhật: 2026-08-06
> Auditor: PM perspective

---

## TL;DR — Trạng thái sau fix

| # | Vấn đề (bản gốc 2026-08-05) | Mức độ | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 1 | `expected_answer` không được dùng để chấm | 🔴 Critical | ✅ **Đã fix** | `eval_agent.py` giờ dùng LLM-as-judge so `response` vs `expected_answer` |
| 2 | Circular evaluation (LLM sinh + LLM chấm) | 🔴 Critical | ⚠️ **Một phần** | Đã thêm LLM-judge (temperature=0) nhưng vẫn cùng GLM-5.2 sinh+chấm |
| 3 | Không có qrel chunk-level | 🔴 Critical | ✅ **Đã fix** | `retrieval_qrels.json` + Recall@K/Precision@K/nDCG@K |
| 4 | Overfitting — tune trên chính eval set | 🔴 Critical | ❌ **Chưa fix** | Vẫn chưa có held-out set |
| 5 | Không đo chất lượng câu trả lời | 🟠 High | ✅ **Đã fix** | `answer_correct` (LLM-judge) + tách `context_found`/`answer_correct` |
| 6 | Không đo latency | 🟠 High | ✅ **Đã fix** | p50/p95 + theo type |
| 7 | Không có multi-turn/multi-chunk test | 🟠 High | ❌ **Chưa fix** | Qrel vẫn single-chunk (0 multi-chunk tự phát hiện) |
| 8 | Không có negative retrieval test | 🟠 High | ⚠️ **Một phần** | Competitor đã fix, out_of_scope vẫn chỉ check escalate |
| 9 | Không có CI/golden baseline | 🟡 Medium | ❌ **Chưa fix** | Eval vẫn chạy tay |
| 10 | Không có human-verified ground truth | 🟡 Medium | ❌ **Chưa fix** | 0/100 human-verified |

**Điểm tổng (cập nhật): 5.8/10** — Tăng từ 3.6/10. Đã fix 4 critical + 2 high, nhưng vẫn còn 2 critical + 2 high chưa giải quyết.

---

## 1. Metrics Hiện Tại (sau toàn bộ fix)

### 1.1. End-to-end Agent (`eval_agent.py` — 100 câu)

| Type | Pass | Tỷ lệ | Ghi chú |
|---|---|---|---|
| in_scope | 37/60 | **61.7%** | Giảm từ 65% vì chấm chặt hơn (cần `answer_correct`) |
| ambiguous | 11/15 | 73.3% | Không đổi |
| competitor_comparison | 10/10 | **100%** | Chấm đúng tiêu chí (decline, không escalate) |
| out_of_scope | 15/15 | 100% | |
| **Tổng** | **73/100** | **73%** | |

### 1.2. Latency (đo lần đầu)

| Metric | Giá trị | Đánh giá |
|---|---|---|
| p50 tổng thể | **14.9s** | 🔴 Quá cao cho UX demo |
| p95 tổng thể | **38.4s** | 🔴 Rất cao |
| p50 in_scope | 18.9s | Đi qua đủ 7 node |
| p50 out_of_scope | 3.7s | Chỉ router + escalate |
| p50 competitor | 4.9s | Router + decline |
| Max | 57s | |

### 1.3. Retrieval (`eval_retrieval.py` — qrel-based)

| Metric | Giá trị | Ghi chú |
|---|---|---|
| Recall@10 (chunk-level) | **75.0%** | == Hit Rate@10 cũ |
| Document Hit Rate@10 | **93.3%** | Tìm đúng file nhưng sai đoạn |
| Precision@10 | 7.5% | 1 relevant chunk / 10 retrieved |
| nDCG@10 | 0.594 | |
| MRR | 0.543 | |
| Multi-chunk Recall@10 | 75.0% | == Recall@10 (mọi câu single-chunk) |

### 1.4. Router (`eval_router.py`)

| Metric | Giá trị |
|---|---|
| Accuracy | **91.0%** |
| hr_question F1 | 0.95 |
| ambiguous F1 | 0.85 |
| out_of_scope F1 | 0.86 |

---

## 2. Vấn Đề Tồn Đọng (chưa fix)

### 2.1. 🔴 Overfitting — vẫn chưa có held-out set

**Bằng chứng** (xem CLAUDE.md): Mỗi lần phát hiện lỗi → fix → số liệu tăng, nhưng fix dựa trên đúng 100 câu này:
1. Fix `ground_truth_context` (25→10→0 câu không verbatim)
2. Fix router prompt (thêm few-shot cho đúng case fail)
3. Regenerate `recruitment_policies` (sai giọng ứng viên)
4. Fix normalize function (Unicode quote, whitespace)

**Rủi ro**: Số liệu 73% có thể bị inflate — hệ thống trên dữ liệu mới (câu hỏi thật của nhân viên) có thể chỉ đạt 50-60%.

**Phương án**: Tạo 20-30 câu held-out KHÔNG dùng để debug/tune, chỉ report final number.

---

### 2.2. 🔴 Chunk Hit Rate (75%) << Document Hit Rate (93.3%) — Vấn đề chunking

**Phát hiện quan trọng nhất**: Retrieval hầu như luôn tìm ĐÚNG TÀI LIỆU (93.3%) nhưng không phải lúc nào cũng trúng ĐÚNG ĐOẠN (75%). Khoảng cách **18.3%** này là vấn đề **chunking/thứ hạng trong 1 document**, không phải embedding chọn sai tài liệu.

**Phân tích 23 câu in_scope fail**:
- **20/23 (87%) do retrieval sai** (`context_found=False`) — chunk đúng tồn tại trong index nhưng không lọt top-5/top-10
- **3/23 (13%) do generation sai** (qa_012, qa_013, qa_047) — retrieval đúng nhưng câu trả lời không khớp `expected_answer`

**Nguyên nhân cụ thể đã xác định**:
1. **Chunk bị chia sai chỗ** — boundary detection không tối ưu cho mọi loại tài liệu
2. **Chunk quá lớn hoặc quá nhỏ** — kích thước 41–2447 ký tự, phân bố không đều
3. **Bảng PDF bị vỡ layout** — `qa_055` (VinFast doc): bảng 2 cột bị interleave sai khi extract, chunk chứa text vỡ không match được
4. **`data/chunks/*.json` có thể stale** — `nghi_dinh_145_2020` ra 270 chunk với code mới nhưng JSON lưu 265 chunk (xây từ code cũ)
5. **Không dùng reranker** — `bge-reranker-v2-m3` có sẵn trên FPT.AI Marketplace nhưng chưa dùng

---

### 2.3. 🔴 Router misfire — 5 câu hr_question bị chặn nhầm

**5 câu** (qa_042, qa_049, qa_051, qa_052, qa_053) bị router phân loại `out_of_scope_or_personal` thay vì `hr_question`:
- **qa_042**: "Cá nhân tự kinh doanh có quyền thuê người làm việc không?" — router nghĩ "cá nhân" = dữ liệu cá nhân
- **qa_049**: "Chủ hộ kinh doanh..." — tương tự
- **qa_051/052/053**: Hỏi về "Vingroup"/"VinFast" — router nhận diện nhầm là **tên công ty khác** (competitor) → decline. Nhưng thực tế đây là **tài liệu nội bộ công ty mình** (VinFast/Vingroup docs nằm trong corpus)!

**Đây là vấn đề CHUNKING/METADATA**: Tài liệu VinFast/Vingroup được gắn `source_type=official_policy` nhưng agent không biết đây là "công ty mình" — nó chỉ thấy keyword "Vingroup" trong danh sách competitor → decline.

**Phương án**:
1. Thêm config `COMPANY_NAMES = ["Vingroup", "VinFast", ...]` — router/escalate check: nếu tên công ty nằm trong config → KHÔNG phải competitor
2. Hoặc gắn metadata `is_internal_document: true` cho chunk, agent check trước khi decline

---

### 2.4. 🟠 Latency 14.9s p50 — rủi ro UX

**Nguyên nhân**: Pipeline 7 node, mỗi node gọi LLM:
```
router (1 call) → retrieve (embed) → grade (0 call) → [rewrite (1 call) → retrieve] → generate (1 call) → hallucination_check (1 call) → confidence → finalize
```

**Phương án** (theo `antigravity_review.md`):
1. Tạm tắt `rewrite` + `hallucination_check` → đo baseline `router→retrieve→generate` thuần
2. Nếu latency giảm đáng kể mà chất lượng không giảm nhiều → giữ bản rút gọn cho demo
3. Parallel hóa: `hallucination_check` có thể chạy song song `confidence`

---

### 2.5. 🟠 Không có multi-chunk test

- `retrieval_qrels.json`: 60/60 câu chỉ có **1 relevant chunk** (0 multi-chunk tự phát hiện)
- Không có câu hỏi cần tổng hợp nhiều đoạn (vd "Thời hạn báo trước tăng ca AND ai phê duyệt?")
- **Phương án**: Tạo 10-15 câu multi-chunk thủ công (human-annotate), không dùng LLM đoán thêm chunk

---

### 2.6. 🟡 Circular evaluation vẫn còn

- GLM-5.2 sinh câu hỏi + `expected_answer` + `ground_truth_context`
- GLM-5.2 (trong agent) trả lời
- GLM-5.2 (LLM-judge, temperature=0) chấm `answer_correct`

**Giảm rủi ro**: LLM-judge dùng temperature=0 + prompt yêu cầu so nội dung cốt lõi. Nhưng vẫn cùng model → bias đồng hướng. Cần human-verify ít nhất 20 câu (golden set).

---

## 3. Review Dataset (`qa_eval_set.json` — 100 câu)

### 3.1. Cấu trúc

| Type | Số câu | Fields | Có ground truth? |
|---|---|---|---|
| in_scope | 60 | `question`, `expected_answer`, `ground_truth_context`, `source_file`, `relevant_chunk_ids` | ✅ Đầy đủ |
| ambiguous | 15 | `question`, `expected_clarifying_question` (không dùng) | ⚠️ Không chấm chất lượng câu làm rõ |
| out_of_scope | 15 | `question`, `expected_behavior: "escalate_to_ticket"` | ✅ |
| competitor_comparison | 10 | `question`, `expected_behavior: "decline_politely"` | ✅ (đã fix) |

### 3.2. Vấn đề chất lượng dataset

| # | Vấn đề | Mức độ | Chi tiết |
|---|---|---|---|
| A | **0/100 human-verified** | 🔴 | 100% LLM-generated, không có annotation guideline |
| B | **Không có held-out set** | 🔴 | Tune trên chính 100 câu → overfit |
| C | **0 multi-chunk question** | 🟠 | Tất cả single-hop, không test tổng hợp |
| D | **qa_055 ground_truth_context bị break** | 🟠 | Bảng VinFast vỡ layout → context không tồn tại dạng liền mạch trong source |
| E | **company_regulations nhắc "Vingroup"/"VinFast"** | 🟠 | Router misfire (xem 2.3) — 3 câu bị decline nhầm |
| F | **`expected_clarifying_question` không dùng** | 🟡 | 15 câu ambiguous chỉ check `needs_clarification=True`, không check câu làm rõ có đúng không |
| G | **Không có greeting test** | 🟡 | Router có class `greeting` nhưng 0 câu test |
| H | **Không có adversarial test** | 🟡 | Typo, mixed language, prompt injection — 0 test |

### 3.3. Đề xuất sửa dataset

| Ưu tiên | Hành động | Giải quyết |
|---|---|---|
| **Gấp** | Fix qa_055 — tìm context thật (không vỡ) hoặc đánh dấu "broken table" | D |
| **Gấp** | Fix router/config cho "Vingroup"/"VinFast" = internal | E |
| Cao | Human-verify 20 câu (stratified: 12 in_scope + 3 ambiguous + 3 out_of_scope + 2 competitor) | A |
| Cao | Tạo 20 câu held-out (không tune) | B |
| Trung bình | Thêm 10 câu multi-chunk (human-annotate) | C |
| Trung bình | Thêm 5 câu greeting + 5 câu adversarial | G, H |

---

## 4. Review Metrics

### 4.1. Metrics đang đo (đúng phương pháp)

| Metric | Script | Đánh giá |
|---|---|---|
| Recall@K (qrel-based) | `eval_retrieval.py` | ✅ Đúng — so chunk_id chính xác |
| Precision@K | `eval_retrieval.py` | ✅ |
| nDCG@K | `eval_retrieval.py` | ✅ |
| MRR | `eval_retrieval.py` | ✅ |
| Document Hit Rate@K | `eval_retrieval.py` | ✅ Tham chiếu cận trên |
| Router Accuracy/P/R/F1 | `eval_router.py` | ✅ |
| Pass rate by type | `eval_agent.py` | ✅ (sau fix) |
| `answer_correct` (LLM-judge) | `eval_agent.py` | ✅ Đã thêm |
| `context_found` (tách riêng) | `eval_agent.py` | ✅ Cho phép chẩn đoán retrieval vs generation |
| Latency p50/p95 | `eval_agent.py` | ✅ Đã thêm |

### 4.2. Metrics còn thiếu

| Metric | Tại sao cần | Ưu tiên |
|---|---|---|
| **Faithfulness** (answer grounded trong context) | Chống hallucination | Cao |
| **Answer Relevance** (answer trả lời đúng câu hỏi) | Đo chất lượng generation | Cao |
| **Citation accuracy** (trích dẫn đúng nguồn) | Đo độ tin cậy | Trung bình |
| **Confidence calibration** (confidence vs accuracy) | Đo threshold escalate có hợp lý | Trung bình |
| **Negative retrieval** (out_of_scope không retrieve HR content) | Đo precision retrieval cho câu ngoài phạm vi | Cao |
| **Multi-chunk Recall** | Đo khả năng tổng hợp nhiều đoạn | Trung bình |
| **Statistical significance** (CI, bootstrapping) | 60 câu → CI ±10% | Thấp |

### 4.3. Độ tin cậy số liệu hiện tại

| Khía cạnh | Đánh giá |
|---|---|
| **Recall@10 = 75%** | ⚠️ Có thể bị deflate do chunking boundary (chunk đúng nhưng bị chia khác → context không match) |
| **Document Hit Rate = 93.3%** | ✅ Đáng tin — so source_file, không phụ thuộc chunking |
| **in_scope pass = 61.7%** | ⚠️ Có thể bị inflate do overfitting, nhưng `answer_correct` (LLM-judge) giúp giảm false positive |
| **Router accuracy = 91%** | ⚠️ 5 câu misfire (qa_042/049/051/052/053) kéo xuống — fix được |
| **Latency p50 = 14.9s** | ✅ Đo đúng (không tính judge call) |

---

## 5. 🔴 PHƯƠNG ÁN CHUNKING SỚM (Priority 1)

### 5.1. Vấn đề chunking hiện tại

| # | Vấn đề | Tác động | Bằng chứng |
|---|---|---|---|
| C1 | **Chunk Hit Rate (75%) << Document Hit Rate (93.3%)** | 18.3% câu tìm đúng file nhưng sai đoạn | `eval_retrieval.py` |
| C2 | **Bảng PDF bị vỡ layout** | Chunk chứa text vỡ, không match câu hỏi | qa_055 (VinFast), `CLAUDE.md` |
| C3 | **`data/chunks/*.json` stale** | Chunk trong JSON ≠ chunk code mới tạo | `nghi_dinh_145_2020`: 270 vs 265 chunk |
| C4 | **Chunk size phân bố không đều** (41–2447 ký tự) | Chunk quá nhỏ → thiếu context; quá lớn → loãng | `CLAUDE.md` |
| C5 | **Không dùng reranker** | Top-5 embedding có thể không phải top-5 relevant | `bge-reranker-v2-m3` có sẵn nhưng chưa dùng |
| C6 | **Fallback chunking cắt fixed-size** | Tài liệu không có cấu trúc Chương/Điều bị cắt cơ học | VinFast, Vingroup tuyển dụng, Base.vn |

### 5.2. Phương án chunking (theo thứ tự ưu tiên)

#### Bước 1: Rebuild toàn bộ chunks (ngay — 0.5 ngày)
```bash
python scripts/build_chunks.py --force  # toàn bộ 29 file, không --only
python scripts/build_vector_db.py --force  # re-index toàn bộ
```
**Giải quyết**: C3 (stale JSON)
**Chi phí**: ~1379 embedding API call
**Lợi ích**: Đảm bảo `data/chunks/*.json` + Chroma Cloud khớp code mới nhất

#### Bước 2: Thêm reranker (1 ngày)
- Dùng `bge-reranker-v2-m3` (có sẵn FPT.AI Marketplace)
- Flow: `retrieve top-20 (embedding) → rerank → top-5 (reranker)`
- **Giải quyết**: C5 (không dùng reranker)
- **Lợi ích ước tính**: Recall@5 có thể tăng 5-10% (reranker tốt hơn embedding cho fine-grained ranking)

#### Bước 3: Sửa chunk size target + min/max bounds (1 ngày)
- **Hiện tại**: Không có target size rõ ràng, fallback cắt fixed-size
- **Đề xuất**:
  - Target: **512-1024 ký tự/chunk** (optimal cho embedding model)
  - Min: **200 ký tự** (merge chunk quá nhỏ)
  - Max: **2048 ký tự** (force-split chunk quá lớn)
  - Overlap: **100-150 ký tự** (giữ context xuyên chunk)
- **Giải quyết**: C4 (size không đều), C6 (fallback cơ học)
- **Lợi ích**: Chunk đều hơn → embedding chất lượng hơn → Recall tăng

#### Bước 4: Sửa bảng PDF vỡ layout (1-2 ngày)
- **Vấn đề**: `qa_055` — bảng 2 cột VinFast bị interleave sai khi extract
- **Phương án**:
  1. Rà lại `data/processed/` cho các file có bảng (VinFast, Vingroup tuyển dụng)
  2. Nếu bảng vỡ → re-extract bằng VLM với prompt yêu cầu giữ cấu trúc bảng
  3. Hoặc: post-process chunker nhận diện bảng markdown (`|...|`) → giữ nguyên không split
- **Giải quyết**: C2 (bảng vỡ)

#### Bước 5: Semantic chunking (optional — 2-3 ngày)
- Thay fixed-size fallback bằng **semantic chunking**: group câu có embedding similarity > threshold
- Dùng `multilingual-e5-large` (đã có) tính similarity giữa câu liên tiếp
- **Lợi ích**: Chunk theo ý nghĩa thay vì ký tự → Recall@K tăng
- **Rủi ro**: Phức tạp, cần test kỹ — chỉ làm nếu Bước 1-4 chưa đủ

### 5.3. Đo lường sau chunking

Sau mỗi bước, chạy lại:
```bash
python eval/scripts/eval_retrieval.py  # Recall@K, Document Hit Rate
python eval/scripts/eval_agent.py      # in_scope pass rate
```
**Mục tiêu**:
- Recall@10: 75% → **≥85%**
- Document Hit Rate@10: 93.3% → **≥95%**
- in_scope pass: 61.7% → **≥75%**

---

## 6. Đề Xuất Hành Động (Priority Order)

### Phase 1: Chunking + Router fix (2-3 ngày) — ROI cao nhất

| # | Hành động | Giải quyết | Chi phí |
|---|---|---|---|
| 1.1 | **Rebuild toàn bộ chunks + re-index** | C3 (stale) | 0.5 ngày + API |
| 1.2 | **Thêm reranker `bge-reranker-v2-m3`** | C5 | 1 ngày |
| 1.3 | **Sửa chunk size target + bounds** | C4, C6 | 1 ngày |
| 1.4 | **Fix router "Vingroup/VinFast" = internal** | 2.3 (router misfire) | 0.5 ngày |
| 1.5 | **Sửa bảng PDF vỡ (qa_055)** | C2 | 1 ngày |

### Phase 2: Dataset quality (2-3 ngày)

| # | Hành động | Giải quyết |
|---|---|---|
| 2.1 | Human-verify 20 câu (golden set) | #2.6 (circular) |
| 2.2 | Tạo 20 câu held-out (không tune) | #2.1 (overfitting) |
| 2.3 | Thêm 10 câu multi-chunk | #2.5 |
| 2.4 | Thêm 5 câu greeting + 5 câu adversarial | #3.2 (greeting gap) |

### Phase 3: Metrics nâng cao (2-3 ngày)

| # | Hành động | Giải quyết |
|---|---|---|
| 3.1 | Thêm Faithfulness + Answer Relevance eval | Metrics thiếu |
| 3.2 | Thêm negative retrieval test | #2.8 (một phần) |
| 3.3 | Confidence calibration eval | #4.3 |

### Phase 4: Latency + Infra (1-2 ngày)

| # | Hành động | Giải quyết |
|---|---|---|
| 4.1 | Tắt rewrite + hallucination_check → đo baseline | #2.4 (latency) |
| 4.2 | CI integration + golden baseline | #2.9 |

---

## 7. Đánh Giá Tổng Quan (cập nhật)

| Khía cạnh | Điểm (trước) | Điểm (sau) | Nhận xét |
|---|---|---|---|
| **Coverage** | 4/10 | **6/10** | Đã thêm qrel, LLM-judge, latency. Vẫn thiếu faithfulness, multi-chunk, negative retrieval |
| **Methodology** | 3/10 | **6/10** | Qrel-based đúng hơn substring. LLM-judge tốt hơn không chấm. Vẫn circular, vẫn overfit |
| **Dataset** | 4/10 | **5/10** | 100 câu + source_file + relevant_chunk_ids. Vẫn 0 human-verify, 0 held-out, 0 multi-chunk |
| **Reliability** | 2/10 | **4/10** | Số liệu chi tiết hơn (context_found vs answer_correct). Vẫn chưa có CI/baseline, vẫn overfit |
| **Actionability** | 5/10 | **7/10** | Tách được retrieval-sai vs generation-sai. Có latency. Có confusion matrix. Đủ để chẩn đoán |
| **Chunking** | — | **5/10** | Có structured + fallback, có word-boundary overlap. Nhưng stale JSON, không reranker, bảng vỡ |
| **Tổng** | **3.6/10** | **5.8/10** | Tiến bộ rõ nhưng cần fix chunking + held-out set trước khi ra quyết định product |

---

> **Kết luận (cập nhật)**: Đã fix 4 critical + 2 high (expected_answer, qrel, latency, competitor scoring). Số liệu giờ đáng tin hơn — tách được "retrieval sai" (87%) vs "generation sai" (13%). **Đòn bẩy lớn nhất tiếp theo là CHUNKING**: Recall@10 = 75% do chunk bị chia sai/stale, không phải embedding kém (Document Hit Rate = 93.3%). Ưu tiên: (1) rebuild chunks + thêm reranker, (2) fix router "Vingroup/VinFast" = internal, (3) tạo held-out set.