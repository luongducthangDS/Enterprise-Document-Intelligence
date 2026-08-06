# Evaluation Report

> Báo cáo đánh giá chất lượng sản phẩm theo tiêu chí BTC — HR Document Intelligence Agent (RAG).
> Cập nhật lần cuối: 2026-08-06, sau Phase 2 (tối ưu agent theo 29 câu in_scope fail đã bóc tách — xem `CLAUDE.md`).

---

## 1. Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Response accuracy (in_scope, dev, 100 câu) | >80% | 75.0% (75/100) | ⚠️ Chưa đạt |
| Response accuracy (tổng, dev, 140 câu — gồm ambiguous/out_of_scope/competitor) | — | 78.6% (110/140) | ℹ️ Tham khảo |
| Response accuracy (in_scope, **held-out**, 30 câu, chạy 1 lần duy nhất) | >80% | 80.0% (24/30) | ✅ Đạt (CI rộng vì n nhỏ: [66.7%, 93.3%]) |
| Response latency (p50, câu cần RAG đầy đủ) | <3s | 24.9s | ❌ Chưa đạt — xem mục 5 |
| Response latency (p50, tổng thể mọi loại câu hỏi) | <3s | 21.3s | ❌ Chưa đạt |
| User satisfaction | >4/5 | — | ⏳ Chưa thực hiện demo với user thật |
| Test coverage (`pytest --cov=src`) | >60% | 86% (1242 statements, 154 test) | ✅ Đạt |

**Ghi chú về "Response accuracy"**: đo bằng LLM-as-judge (model `Llama-3.3-70B-Instruct`, khác họ với agent dùng `GLM-5.2` để tránh circular evaluation) so `response` thực tế với `expected_answer` mẫu — không chỉ kiểm tra retrieval có đúng đoạn hay không (xem mục 3). Con số dev accuracy 75% *thấp hơn* held-out 80% là **bất thường tích cực**: không có dấu hiệu overfit vào bộ câu hỏi dùng để tune (chênh lệch nằm trong khoảng nhiễu tự nhiên của mẫu 30 câu — CI của cả hai đều chồng lấn nhau).

---

## 2. Test Results

### Unit Tests

```
pytest tests/ -v
154 passed in ~2s

pytest --cov=src --cov-report=term-missing
TOTAL: 1242 statements, 172 miss, 86% coverage
```

Coverage thấp nhất tập trung ở phần **không nên** có coverage cao ở giai đoạn này: `src/services/supabase_client.py` (0% — chưa có test tích hợp DB thật, out of scope đợt này vì backend/auth do team khác phụ trách), `src/ingestion/embeddings.py`/`extractors/pdf_extractor.py` (I/O nặng, gọi API ngoài, được test qua kịch bản chạy tay + `scripts/verify_processed.py` thay vì unit test). Toàn bộ logic nghiệp vụ cốt lõi (`src/agents/*`, `src/retrieval/*`, `src/models/schemas.py`, `src/ingestion/chunkers.py`/`cleaners.py`) đạt 95-100%.

### Integration / Eval Tests (đặc thù hệ thống RAG — thay cho "integration test" cổ điển)

Hệ thống không có test tích hợp DB/API cổ điển (chưa có backend thật kết nối Supabase — xem mục 6). Thay vào đó, 3 tầng eval chạy trên dữ liệu/API thật:

| Tầng | Script | Kết quả (dev) | Kết quả (held-out, chạy 1 lần) |
|---|---|---|---|
| Router (phân loại intent) | `eval/scripts/eval_router.py` | Accuracy 95.7% (134/140) | *(không tách riêng — dùng chung 140 câu dev)* |
| Retrieval (chunk-level, qrel-based, sau rerank) | `eval/scripts/eval_retrieval.py --rerank` | Recall@10 92.8%, MRR 0.916, Multi-chunk Recall@10 83.6% | Recall@10 81.9%, MRR 0.881, Multi-chunk Recall@10 55.0% |
| Agent end-to-end | `eval/scripts/eval_agent.py` | 110/140 (78.6%) | 24/30 (80.0%) |

Chi tiết breakdown theo type (dev, 140 câu): `in_scope` 75/100, `ambiguous` 11/15, `out_of_scope` 15/15, `competitor_comparison` 9/10 (1 câu fail do lỗi nhãn dataset, xem `CLAUDE.md` — Vingroup/VinFast vừa là "công ty mình" vừa bị gán nhãn test "hỏi đối thủ", mâu thuẫn logic không thể vừa đúng cả hai).

---

## 3. Retrieval — chi tiết

| Metric | Dev (n=73, sau lọc min-relevance=2) | Held-out (n=20) |
|---|---|---|
| Hit Rate@10 | 98.6% | 100.0% |
| Recall@10 | 92.8% | 81.9% |
| Precision@10 | 18.2% | 21.5% |
| nDCG@10 | 0.873 | 0.766 |
| Multi-chunk Recall@10 | 83.6% | 55.0% |
| Doc Hit Rate@10 | 79.5% | 85.0% |
| MRR | 0.916 | 0.881 |

**Phát hiện quan trọng nhất**: Hit Rate@10 gần như tuyệt đối (98.6-100%) — retrieval hầu như luôn tìm được ít nhất 1 đoạn đúng. Nhưng **Multi-chunk Recall@10 lệch mạnh giữa dev (83.6%) và held-out (55.0%)** — câu hỏi cần TỔNG HỢP nhiều đoạn để trả lời đầy đủ vẫn là điểm yếu chưa được xác nhận ổn định trên dữ liệu chưa từng thấy. Với n=20 câu held-out, mỗi câu lệch 1 đơn vị đổi 5 điểm phần trăm — cần thêm dữ liệu held-out trước khi kết luận chắc chắn đây là suy giảm thật hay nhiễu mẫu nhỏ.

**Hybrid retrieval (BM25 + dense qua RRF)** — thử nghiệm trong Phase 2, đo trên dev: Multi-chunk Recall@10 83.6% → 84.9% (+1.3pp), Recall@10 92.8% → 93.7% (+0.9pp), MRR 0.916 → 0.912 (~không đổi). Cải thiện nhỏ, khả năng nằm trong nhiễu thống kê của mẫu 73 câu. **Giữ `use_hybrid=False` làm mặc định** — code đã sẵn sàng (`src/retrieval/hybrid.py`, bật qua `USE_HYBRID=true` hoặc sửa `src/config.py`), nhưng chưa đủ bằng chứng để đổi mặc định production.

---

## 4. User Feedback

**Chưa thực hiện.** Sản phẩm chưa demo với user thật (nhân viên/HR admin) — toàn bộ eval hiện tại dùng bộ câu hỏi + LLM-judge tự động (`eval/datasets/qa_eval_set.json`, sinh bởi GLM-5.2, đã qua nhiều vòng kiểm tra chất lượng thủ công — xem `CLAUDE.md`). Đây là giới hạn phương pháp đã biết: **circular evaluation** (LLM sinh câu hỏi + LLM trả lời + LLM chấm) — chưa có nhãn con người xác nhận độc lập.

50 mẫu `eval/datasets/human_review_sample.json` (cặp query-chunk mà 2 LLM-judge bất đồng) đã chuẩn bị sẵn để chấm tay nhưng **chưa được chấm** (`human_score` toàn bộ null) — user dự định tự chấm sau, ngoài phạm vi đợt Phase 2 này.

| User | Feedback | Rating |
|------|----------|--------|
| — | Chưa có phiên demo/thu thập feedback | — |

---

## 5. Demo Results

- Ngày demo: chưa thực hiện.
- Latency là rủi ro chính cần biết trước khi demo live: p50 21.3s tổng thể, riêng câu cần RAG đầy đủ (in_scope) p50 24.9s, p95 50.9s — chuỗi 6 lệnh gọi mạng tuần tự (router → embed → rerank → generate → hallucination-check → confidence). Câu `out_of_scope`/`competitor_comparison` nhanh hơn nhiều (p50 4.4-5.6s) vì bỏ qua toàn bộ nhánh RAG.
- Chưa tối ưu latency trong Phase 2 này (ngoài phạm vi đã chốt với user) — xem mục 6.

---

## 6. Action Items / Nợ kỹ thuật đã biết

Xếp theo mức độ ưu tiên nếu tiếp tục dự án:

- [ ] **Latency 21-25s p50** — chưa dùng được cho demo live liền mạch. Hướng khắc phục đã xác định nhưng chưa làm: dùng model nhỏ hơn cho `router`/`hallucination_check` (2 tác vụ phân loại nhị phân, không cần model mạnh), chạy song song `hallucination_check` + phần đầu `confidence`, hoặc cân nhắc bớt 1 trong 2 node đó cho profile "nhanh" và so đánh đổi chất lượng.
- [ ] **Multi-chunk Recall lệch dev/held-out (83.6% vs 55.0%, n=20)** — cần thêm câu hỏi held-out đa-chunk để xác nhận đây là suy giảm thật hay nhiễu mẫu nhỏ trước khi đầu tư thêm vào hybrid/rerank.
- [ ] **0 nhãn con người xác nhận độc lập** — toàn bộ ground truth do LLM sinh + LLM chấm. 50 mẫu bất đồng giữa 2 judge đã chuẩn bị sẵn (`human_review_sample.json`) nhưng chưa chấm.
- [ ] **CI chưa gate được eval** — `.github/workflows/ci.yml` chỉ chạy `pytest` + `check_dataset_integrity.py` (không gọi API), chưa chạy `eval_agent.py`/`eval_retrieval.py` trên CI (cần secret `FPT_API_KEY` + chấp nhận thời gian chạy dài hơn nhiều).
- [ ] **Backend/persistence chưa nối** — `src/agents/service.py` + `docs/AGENT_API.md` đã định nghĩa xong contract (response, citations, confidence, escalate, ticket_draft), nhưng chưa có backend thật gọi vào để lưu conversation/message/ticket vào Supabase. Theo quyết định của user, phần này để team backend (nhánh `develop`) tự triển khai dựa trên `docs/AGENT_API.md`.
- [x] ~~29 câu in_scope fail chưa rõ nguyên nhân~~ — đã bóc tách và fix 3/4 nhóm nguyên nhân trong Phase 2 (xem `CLAUDE.md`): hạ ngưỡng confidence, chặn "retrieval sai nhưng vẫn trả lời" bằng sentinel, sửa xung đột nguồn trong prompt generate (sau khi tự phát hiện và sửa 2 bug do chính các fix này gây ra — sentinel false-positive và sort phá relevance).
