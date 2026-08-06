# Project Review & Roadmap — P-153 (Data · RAG Pipeline · Eval)

> Rà soát toàn bộ dự án và đề xuất kế hoạch tiếp theo, **giới hạn phạm vi ở 3 mảng: xử lý dữ liệu, RAG pipeline, và evaluation**.
> Backend / frontend / deploy / deliverables BTC → xem mục 7 (tạm gác, chỉ liệt kê để không quên).
> Ngày review: **2026-08-06** · Dữ liệu đối chiếu: code thật + `eval/results/*.json` + `data/chunks/*.json` + qrels (không lấy số từ log cũ).

---

## 0. TL;DR

Ba kết luận quan trọng nhất, xếp theo mức độ ảnh hưởng:

**① Cái thước đang đo sai → đừng tune trước khi sửa nó.**
Bộ eval 60 câu in_scope chỉ phủ **11/29 tài liệu = 554/1384 chunk (40% index)**. **830 chunk (60%) chưa từng được test một lần nào** — trong đó có **Nghị định 145/2020 (270 chunk, tài liệu HR quan trọng nhất trong kho)**, Luật ATVSLĐ (142), NĐ 158/2025 (131), Luật BHYT 51/2024 (45), Luật thuế TNCN (40). Nặng hơn: với 2 bộ luật đang có câu hỏi, **10/10 chunk gold nằm trong 1–2% đầu tài liệu** (Điều 1–5: phạm vi, giải thích từ ngữ) — hệ quả trực tiếp của cách `read_excerpt_window()` lấy trích đoạn.

**② Ngưỡng `retrieval_max_distance = 0.16` đang gây hại ròng.**
Tính lại phân phối distance từ 100 câu: ngưỡng này **xoá sạch context của 9/60 câu in_scope (15%)**, đổi lại chỉ chặn thêm out_of_scope — thứ mà router đã chặn với **recall 100%** ở tầng trên nên gần như không bao giờ chạy tới `grade_node`.

**③ Retrieval tìm đúng tài liệu nhưng sai thứ hạng đoạn → reranker là đòn bẩy lớn nhất.**
Document Hit@10 = **95%** nhưng Recall@1 chỉ **41.7%**. Phân bố thứ hạng chunk đúng: rank 1 = 25 câu, rank 2 = 10, rank 3–10 = 14, miss = 11. Tức có **24 câu đã nằm trong top-10 nhưng không ở top-1** — đúng bài toán của cross-encoder reranker.

Kèm theo là 2 blocker hành chính phải xử lý ngay: **toàn bộ code agent + eval chưa commit** (41 file), và **số liệu agent 73/100 đã lỗi thời** (chạy lúc 07:00, trước khi đổi cosine/E5/threshold lúc 07:22–07:33).

---

## 1. Trạng thái thật (đã verify hôm nay)

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Processed docs | 29 tài liệu | `data/processed/`, verify gate `verify_processed.py` pass |
| Chunks | **1.384 chunk**, rebuild 07:23 hôm nay | `data/chunks/` — khớp code chunker mới nhất |
| Vector DB | Chroma Cloud, cosine + E5 prefix | `passage:` tại `build_chunks.py:83`, `query:` tại `retrieval.py:28` |
| Test | **107 passed** | `pytest -q` chạy thật |
| Qrel chunk-level | 60/60 câu, deterministic | `eval/datasets/retrieval_qrels.json` |
| Eval scripts | 3 tầng (router / retrieval / agent) | `eval/scripts/` |

### 1.1. Số liệu — cái nào còn tin được

| Report | Chạy lúc | Hợp lệ? |
|---|---|---|
| `retrieval_eval_report.json` | 08-06 **07:33** | ✅ Sau khi đổi cosine/E5 → đáng tin |
| `agent_eval_report.json` | 08-06 **07:00** | ❌ **Lỗi thời** — trước `config.py` (07:33), `retrieval.py` (07:22), `build_chunks.py` (07:22) |
| `router_eval_report.json` | 08-05 22:46 | ⚠️ Prompt router chưa đổi từ đó → có thể vẫn đúng, nên chạy lại |

**Retrieval (số mới nhất):**

| Metric | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| Recall (chunk) | 41.7% | 63.3% | **71.7%** | **81.7%** |
| nDCG | 0.417 | 0.547 | 0.580 | 0.612 |
| Document Hit Rate | 63.3% | 83.3% | 86.7% | **95.0%** |

MRR = 0.547. So với lần đo trước cosine/E5 (Recall@10 = 75.0%, DocHit@10 = 93.3%) → thay đổi đó **có tác dụng thật, +6.7 điểm**.

---

## 2. Phân tích sâu — Dữ liệu & Chunking

### 2.1. Phân bố kích thước chunk

```
1384 chunk | min 24 · p10 277 · p25 484 · median 876 · p75 1117 · p90 1326 · max 2447
<200 ký tự: 54 chunk    <400: 267 chunk    >2000: 3 chunk
```

Phân bố nhìn chung **lành mạnh** (median 876 nằm đúng vùng tối ưu cho embedding). Hai đuôi cần xử lý:

- **54 chunk < 200 ký tự** — kiểm tra mẫu cho thấy đây là các mục heading ngắn bị tách riêng: `"## 1. Mục đích ..."` (170), `"## 2. Phạm vi ..."` (147), `"## 8. 60 ngày ..."` (138). Chúng **không vô dụng** (qa_025 hỏi đúng chunk `03_quy-trinh-onboarding::0008` dài 138 ký tự — và câu đó MISS). Chunk quá ngắn → embedding thiếu tín hiệu → khó nổi lên top-10.
- **3 chunk > 2000 ký tự** — 1 trong số đó là `842059170-...Vingroup::0002` (2.025 ký tự, **không có `heading_path`** vì rơi vào nhánh fallback chunking). Chunk này là gold của **2 câu và cả 2 đều MISS** (qa_019, qa_020).

### 2.2. Chunk gold dài → miss nhiều hơn

| Nhóm | n | median độ dài chunk gold |
|---|---|---|
| Hit@10 | 49 | **572** ký tự |
| Miss@10 | 11 | **855** ký tự |

→ Chunk càng dài, vector càng "loãng" (trung bình hoá nhiều ý) → càng khó khớp câu hỏi ngắn cụ thể. Ủng hộ hướng: chia nhỏ vùng > 1.500 ký tự ở nhánh fallback, và gộp chunk < 200 vào đoạn kề.

### 2.3. Tài liệu chunk thô nhất

| Tài liệu | n chunk | median | Ghi chú |
|---|---|---|---|
| `842059170-...Vingroup` (quy trình tuyển dụng) | **10** | 1228 | Fallback chunking, không heading_path, gold của 2 câu MISS |
| `talentnet_quy-trinh-cham-dut-hdld` | 8 | 1254 | Fallback |
| `[Base.vn] Mẫu sơ đồ tuyển dụng` | 6 | 1672 | Đã biết là template rỗng, giá trị thấp |
| `nghi_dinh_145_2020_nd_cp` | 270 | 943 | min = **24 ký tự** → có chunk rác |

---

## 3. Phân tích sâu — Retrieval

### 3.1. Recall@10 theo category — điểm yếu tập trung ở luật

| Category | Recall@10 |
|---|---|
| company_regulations | 10/10 |
| compensation_policies | 10/10 |
| leave_policies | 10/10 |
| onboarding_offboarding | 7/10 |
| recruitment_policies | 7/10 |
| **government_legal** | **5/10** |

### 3.2. Nhưng một phần "miss" của government_legal là **lỗi ground truth, không phải lỗi retrieval**

11 câu MISS@10, xem chi tiết thì chia làm 3 loại rõ rệt:

| Loại | Câu | Bản chất |
|---|---|---|
| **A. Gold sai/thiếu** (~4–5 câu) | qa_041, qa_042, qa_043 | Gold chunk = `bộ luật lao động::0003/0004` = **"Điều 3. Giải thích từ ngữ"**. Câu hỏi "Công ty tuyển dụng em từ năm 14 tuổi có được không?" — câu trả lời **thật** nằm ở Điều 143 (lao động chưa thành niên), không phải ở phần định nghĩa. Retrieval trả về chunk khác **trong đúng tài liệu** (doc_hit@10 = True) và bị chấm MISS oan |
| **B. Nhiều tài liệu cùng trả lời được** (2 câu) | qa_027, qa_029 | Gold = tài liệu synthetic offboarding, nhưng top-1 = **NĐ 145/2020** — cũng là căn cứ pháp lý đúng cho "trợ cấp thôi việc"/"bàn giao tài sản". Qrel single-chunk single-doc phạt oan |
| **C. Miss thật** (~4–5 câu) | qa_015, qa_019, qa_020, qa_025 | Gold chunk quá dài (2.025 ký tự) hoặc quá ngắn (138 ký tự) → không nổi lên được |

→ **Recall@10 = 81.7% đang bị deflate**. Con số "thật" có thể cao hơn 5–8 điểm. Nhưng đừng vội mừng: đổi lại nó **chỉ đo trên 40% index**, nên cũng có thể đang inflate ở chiều khác. Cả hai sai lệch đều bắt nguồn từ cùng một nguyên nhân ở mục 4.

### 3.3. Phân bố thứ hạng — dư địa của reranker

```
rank 1: 25 câu   rank 2: 10   rank 3: 3   rank 4: 1   rank 5: 4
rank 6-10: 6     miss@10: 11
```

- Agent đang chạy `retrieval_top_k = 5` → **trần cứng của `context_found` chỉ là Recall@5 = 71.7%**, trong khi Recall@10 = 81.7% đang không được dùng.
- Nếu có reranker hoàn hảo trên top-10: Recall@1 41.7% → **81.7%** (24 câu đang ở rank 2–10 được đẩy lên đầu). Thực tế reranker tốt thường lấy được 60–75% dư địa đó.

### 3.4. Ngưỡng `retrieval_max_distance = 0.16` — bằng chứng số học

`walkthrough.md` chọn 0.16 dựa trên **giá trị trung bình** (in-scope 0.138 vs out-of-scope 0.165). Xét **phân phối** thì hai nhóm chồng lấn nặng:

| Nhóm | median | p75 | p90 | max | top-1 distance > 0.16 |
|---|---|---|---|---|---|
| in_scope (60) | 0.137 | 0.155 | 0.165 | 0.178 | **9/60 (15%)** |
| out_of_scope (15) | 0.181 | 0.216 | 0.223 | 0.234 | 10/15 |
| ambiguous (15) | 0.157 | 0.163 | 0.171 | 0.171 | 4/15 |
| competitor (10) | 0.160 | 0.171 | 0.185 | 0.185 | 5/10 |

in_scope p90 = 0.165 **cao hơn** out_of_scope p25 = 0.140 → không tồn tại ngưỡng nào tách sạch được hai nhóm bằng distance.

Hệ quả: 9/60 câu in_scope bị `grade_node` **xoá sạch chunk** → `generate` chỉ còn nước nói "chưa đủ thông tin" → fail chắc chắn, không node nào phía sau cứu được. Đổi lại nó chặn out_of_scope — nhưng những câu đó đã bị router chặn từ trước (`recall = 1.00`).

---

## 4. Phân tích sâu — Eval (vấn đề gốc rễ)

### 4.1. Eval set chỉ phủ 40% index

| | |
|---|---|
| Tài liệu có ít nhất 1 câu hỏi | **11 / 29** |
| Chunk thuộc tài liệu có câu hỏi | **554 / 1384 (40%)** |
| Chunk **chưa từng được test** | **830 (60%)** |

**18 tài liệu không có câu hỏi nào** — đáng lo nhất là 5 văn bản luật lớn:

| Tài liệu chưa test | n chunk |
|---|---|
| `nghi_dinh_145_2020_nd_cp` | **270** |
| `luat_an_toan_ve_sinh_lao_dong_84_2015` | 142 |
| `nghi_dinh_158_2025_nd_cp_bhxh_bat_buoc` | 131 |
| `luat51` (BHYT sửa đổi) | 45 |
| `112-vbhn-vpqh_luat_thue_tncn` | 40 |
| `leanh_mau-noi-quy-lao-dong` | 41 |
| `nghi_dinh_293_2025` (lương tối thiểu) | 33 |
| `05_chinh-sach-lam-viec-tu-xa` | 32 |
| + 10 tài liệu nhỏ khác | ~50 |

Nghị định 145/2020 là văn bản hướng dẫn thi hành Bộ luật Lao động — chi tiết nhất về OT, nghỉ phép, kỷ luật, trợ cấp. **Nó chiếm 20% index và chưa có một câu hỏi nào.** Nếu chunk của nó bị lỗi, toàn bộ hệ thống eval hiện tại không phát hiện được.

### 4.2. Nguyên nhân gốc: cách sinh eval set

`scripts/collect_data.py::EVAL_EXCERPT_SOURCES` hardcode **đúng 2 nguồn cho mỗi category** (6 category × 2 = tối đa 12 tài liệu, thực tế 11 vì `leave_policies` lặp cùng 1 file). `read_excerpt_window()` sau đó chỉ đọc **1–2 cửa sổ 4.000 ký tự** trên mỗi file.

Với `bộ luật lao động` (196.000 ký tự) và `luat_bao_hiem_xa_hoi` — cửa sổ đầu rơi vào Chương I (Điều 1–5: *phạm vi điều chỉnh, giải thích từ ngữ*). Đây là phần **ít đáng hỏi nhất** của một bộ luật. Kết quả:

- 10/10 chunk gold của 2 luật này nằm ở **1–2% đầu tài liệu**;
- Câu hỏi sinh ra nghe tự nhiên nhưng **câu trả lời thật lại nằm ở điều khoản khác** → tạo ra loại "miss oan" ở mục 3.2A;
- 40.000+ ký tự nội dung thực chất của mỗi luật không bao giờ được đo.

Tính chung 60 câu: median vị trí gold = 32% chiều dài tài liệu, **21/60 câu nằm trong 20% đầu**.

### 4.3. Các khoảng trống eval khác (đã ghi trong `glm_review.md`, vẫn đúng)

| Vấn đề | Trạng thái |
|---|---|
| Không có held-out set → tune trên chính 100 câu | ❌ Chưa fix (🔴 duy nhất chưa ai động tới) |
| 60/60 câu chỉ 1 chunk relevant → không test được khả năng tổng hợp | ❌ Chưa fix |
| 0/100 câu human-verified; GLM sinh câu + GLM trả lời + GLM chấm | ❌ Chưa fix |
| Router có class `greeting` nhưng 0 câu test | ❌ Chưa fix |
| Không có faithfulness / answer-relevance metric | ❌ Chưa fix |
| `expected_clarifying_question` có trong data nhưng không script nào dùng | ❌ Chưa fix |

---

## 5. Kế hoạch — 4 phase

Nguyên tắc: **sửa thước đo trước, tune sau**; mỗi thay đổi chỉ đổi 1 biến và kèm 1 lần đo trước/sau.

> **Mẹo tiết kiệm API:** `eval_retrieval.py` chỉ tốn 100 embedding call (~1 phút) — dùng nó cho **mọi** thí nghiệm sweep threshold/top_k/reranker. `eval_agent.py` tốn ~300 LLM call và ~25 phút — chỉ chạy ở các mốc kiểm chứng (cuối mỗi phase), không chạy cho từng thí nghiệm.

### Phase 0 — Ổn định nền (~2 giờ) 🔴

| # | Việc | Done khi |
|---|---|---|
| 0.1 | **Commit + push toàn bộ 41 file đang chưa track** (agent nodes, eval scripts, qrels, reports, reviews) | `git status` sạch |
| 0.2 | Merge/rebase `origin/main` (đang đi sau 15 commit) | Không còn "behind" |
| 0.3 | `pip install ruff && ruff check src/ tests/` — CI chạy lệnh này nhưng nhánh hiện tại không trigger CI, chưa ai biết có pass không | 0 lỗi |
| 0.4 | Chạy lại `eval_agent.py` + `eval_router.py` với config hiện tại | 3 report cùng một mốc thời gian |
| 0.5 | Ghi thay đổi cosine/E5/threshold (`walkthrough.md`) vào `CLAUDE.md` — hiện đang thiếu trong log chính | Log liền mạch |

> Dự đoán ở 0.4: `in_scope` có thể **giảm** so với 61.7% dù retrieval tốt lên, vì threshold 0.16 mới siết vào (mục 3.4). Nếu đúng vậy thì đó chính là bằng chứng cho Phase 1.1.

### Phase 1 — Thí nghiệm rẻ, hiệu quả cao (0.5–1 ngày) 🔴

Không đụng dữ liệu, chỉ đổi config + đo bằng `eval_retrieval.py`.

| # | Việc | Chi tiết | Kỳ vọng |
|---|---|---|---|
| 1.1 | **Sweep `retrieval_max_distance`** | Đo `{0.16, 0.18, 0.20, tắt}` — chấm theo *bao nhiêu câu in_scope còn ít nhất 1 chunk sau grade* và *bao nhiêu câu out_of_scope bị lọt* | Lấy lại ~15% câu in_scope bị xoá oan |
| 1.2 | **Sweep `retrieval_top_k`** | 5 → 10. Kèm kiểm tra generation có bị loãng vì nhiều context không | `context_found` +10 điểm (71.7 → 81.7) |
| 1.3 | **Sửa "Vingroup/VinFast = đối thủ"** | Thêm `internal_company_names` vào `Settings`; `_mentions_competitor_company()` loại các tên này; sửa ví dụ trong `_ROUTER_SYSTEM`; thêm test. Hiện corpus chứa chính tài liệu VinFast/Vingroup (`source_type=official_policy`) mà agent lại từ chối trả lời | Router accuracy 91% → ~94% |
| 1.4 | Mốc kiểm chứng | Chạy `eval_agent.py` 1 lần với cấu hình thắng | Có số so với Phase 0 |

### Phase 2 — Sửa thước đo (1.5–2 ngày) 🔴 — *quan trọng nhất về dài hạn*

| # | Việc | Chi tiết |
|---|---|---|
| 2.1 | **Mở rộng coverage eval sang 18 tài liệu chưa test** | Sửa `EVAL_EXCERPT_SOURCES` để liệt kê **tất cả** tài liệu RAG-eligible, ưu tiên NĐ 145 (270 chunk), Luật ATVSLĐ, NĐ 158, Luật BHYT, thuế TNCN. Sinh thêm **~40 câu** (mục tiêu: ≥ 80% chunk nằm trong tài liệu có câu hỏi) |
| 2.2 | **Sửa `read_excerpt_window()`** | Trải cửa sổ đều theo **số lượng "Điều"** thay vì offset ký tự, và **bỏ qua Chương I** (phạm vi / giải thích từ ngữ) với văn bản luật — đây chính là nguồn gốc của "miss oan" (mục 3.2A) |
| 2.3 | **Review tay 11 câu MISS** | Phân loại A/B/C như mục 3.2; câu loại A sửa gold, loại B thêm chunk thứ 2 vào qrel (graded relevance: 2 = chính, 1 = liên quan). Việc này **làm tay, không dùng LLM** — đúng bài học từ vụ `ground_truth_context` bị paraphrase |
| 2.4 | **Held-out set 20–30 câu** | Sinh từ tài liệu chưa test, **niêm phong** — không dùng để debug/tune, chỉ report con số cuối. Đây là 🔴 duy nhất chưa ai động tới |
| 2.5 | Chạy lại `build_retrieval_qrels.py` | Cập nhật qrel cho câu mới |

**Done khi:** coverage ≥ 80% chunk, ≥ 25/29 tài liệu có câu hỏi, qrel cho phép multi-chunk, có held-out set niêm phong.

### Phase 3 — Reranker + chunking (2–3 ngày) 🟠

Chỉ làm **sau** Phase 2, để đo trên thước đã sửa.

| # | Việc | Chi tiết | Kỳ vọng |
|---|---|---|---|
| 3.1 | **Reranker `bge-reranker-v2-m3`** | Có sẵn trên FPT.AI Marketplace. Flow `retrieve top-20 → rerank → top-5`; thêm cờ `use_reranker` để A/B. Thêm hàm vào `fpt_client.py` (đúng pattern đã gom) | Recall@1 41.7% → 60–70% |
| 3.2 | **Gộp chunk < 200 ký tự** | 54 chunk (chủ yếu heading `"## 1. Mục đích"`). Gộp vào đoạn kề trong cùng section | qa_025 (gold 138 ký tự) hết miss |
| 3.3 | **Chia nhỏ vùng > 1.500 ở nhánh fallback** | `842059170-...Vingroup` chỉ 10 chunk / median 1228, gold 2.025 ký tự là nguyên nhân của qa_019 + qa_020 | 2 câu MISS được cứu |
| 3.4 | **Rà bảng vỡ layout** | `qa_055` (bảng 2 cột VinFast bị interleave). Kiểm tra các file có bảng, cân nhắc giữ nguyên khối bảng markdown khi chunk | |
| 3.5 | Rebuild + re-index + đo lại đủ 3 tầng | `build_chunks.py --force` (toàn bộ) → `build_vector_db.py --force` | |

**Mục tiêu cuối Phase 3:** Recall@5 ≥ 85%, Recall@1 ≥ 60%, Document Hit@10 ≥ 95%, in_scope pass ≥ 75% (đo trên eval set **đã mở rộng**, không phải bộ cũ).

### Phase 4 — Latency & metric nâng cao (1–1.5 ngày) 🟡

| # | Việc | Chi tiết |
|---|---|---|
| 4.1 | **Cờ `pipeline_profile`** | `"full"` (7 node) vs `"lean"` (router→retrieve→grade→generate→finalize). `build_graph()` đọc cờ |
| 4.2 | Đo cả 2 profile | p50 hiện tại **14.9s** (p95 38.4s) là không dùng được cho demo. Nếu `lean` mất < 3 điểm chất lượng mà latency giảm > 40% → dùng `lean` mặc định, giữ `full` sau cờ |
| 4.3 | Chạy song song `hallucination_check` + `confidence` | Hai node không phụ thuộc nhau → `asyncio.gather` |
| 4.4 | Faithfulness + answer-relevance | Bổ sung vào `eval_agent.py` (đã có sẵn hạ tầng LLM-judge) |
| 4.5 | Negative retrieval test | Đo out_of_scope **không** kéo về nội dung HR, thay vì chỉ check `escalate` |

---

## 6. Việc **không** nên làm

| Việc | Lý do |
|---|---|
| **GraphRAG** | Đồng ý với `antigravity_review.md`: chưa có baseline vững, chi phí LLM để trích entity cho hàng nghìn trang luật quá lớn. Chỉ xét lại khi Recall > 90% mà vẫn fail câu multi-hop |
| **Semantic chunking** | Reranker (3.1) rẻ hơn và chữa cùng triệu chứng. Chỉ làm nếu sau Phase 3 vẫn chưa đạt |
| **Tầng 3/4/6 của `plan_eval.md`** (eval riêng cho grade/rewrite/hallucination) | Over-scope. Phase 4.1–4.2 trả lời cùng câu hỏi với chi phí thấp hơn nhiều |
| **Đổi embedding model lần nữa** | Đã thực nghiệm chọn `multilingual-e5-large` (90% vs 83.33%), và E5 prefix vừa cho thêm +6.7 điểm. Nút thắt hiện nằm ở **ranking và thước đo**, không ở embedding |
| **Sinh thêm review .md** | Đã có 4 file review. Từ giờ ghi kết quả vào `WORKLOG.md` + `eval/results/report.md` |

---

## 7. Tạm gác (ngoài phạm vi lần này — liệt kê để không quên)

- **API/backend**: `src/api/routes.py` vẫn là boilerplate template (trả `response` + `analysis`, không có citations/confidence/escalation, không ghi Supabase). Có 2 backend song song: `src/api/` và `backend/` trên nhánh `develop` (JWT tự chế, xung đột với Supabase Auth/RLS đã dựng) — **cần chốt 1 cái với team trước khi cả hai phình thêm**.
- **Supabase migration `0003`** (chặn tự leo quyền `role` → `hr_admin`): chưa rõ đã apply lên project thật chưa. **Cần xác nhận** — đây là lỗ hổng bảo mật đang sống, không phải việc code.
- **Deliverables BTC**: README vẫn là README template AI20K; `JOURNAL.md` còn nguyên placeholder; `WORKLOG.md` thiếu 2 ngày làm nhiều nhất (08-05, 08-06); `eval/results/report.md` rỗng dù số liệu đã có sẵn trong 3 file JSON; `docs/architecture_diagram.md` vẫn ghi "GPT-4o/Gemini". Bốn mục cuối tốn vài giờ mà đang là 0 điểm — nên làm xen kẽ, đừng dồn cuối kỳ.

---

## 8. Thứ tự đề xuất

```
Hôm nay      Phase 0 (2h)   commit + push, chạy lại eval  →  có mốc số liệu sạch
Ngày 1       Phase 1        sweep threshold/top_k + fix "công ty mình"   (rẻ, hiệu quả ngay)
Ngày 2-3     Phase 2        SỬA THƯỚC ĐO: coverage 40% → 80%, held-out set
Ngày 4-6     Phase 3        reranker + chunking, đo trên thước đã sửa
Ngày 7       Phase 4        latency profile + faithfulness
```

Lý do đặt Phase 1 **trước** Phase 2 dù Phase 2 quan trọng hơn: 1.1–1.3 chỉ đổi config, đo bằng script rẻ, xong trong 1 ngày, và kết quả của chúng không bị ảnh hưởng bởi việc eval set sau này được mở rộng.

**Nếu chỉ làm được 1 việc hôm nay: commit và push.**
