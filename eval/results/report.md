# Evaluation Report

> Báo cáo đánh giá chất lượng sản phẩm theo tiêu chí BTC — HR Document Intelligence Agent (RAG).
> Cập nhật lần cuối: 2026-08-06, sau Phase 3 (latency + robustness — xem `CLAUDE.md`). Số liệu chất lượng (accuracy, retrieval) không đổi so với Phase 2; phần đổi ở đợt này là latency.

---

## 1. Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Response accuracy (in_scope, dev, 100 câu) | >80% | 75.0% (75/100) | ⚠️ Chưa đạt |
| Response accuracy (tổng, dev, 140 câu — gồm ambiguous/out_of_scope/competitor) | — | 79.3% (111/140) | ℹ️ Tham khảo |
| Response accuracy (in_scope, **held-out**, 30 câu, chạy 1 lần duy nhất) | >80% | 80.0% (24/30) | ✅ Đạt (CI rộng vì n nhỏ: [66.7%, 93.3%]) |
| Response latency (p50, câu cần RAG đầy đủ) | <3s | 19.1s (từ 24.9s trước Phase 3) | ❌ Chưa đạt — xem mục 5 |
| Response latency (p50, tổng thể mọi loại câu hỏi) | <3s | 16.6s (từ 21.3s trước Phase 3) | ❌ Chưa đạt |
| User satisfaction | >4/5 | — | ⏳ Chưa thực hiện demo với user thật |
| Test coverage (`pytest --cov=src`) | >60% | 87% (167 test, tăng từ 154/86%) | ✅ Đạt |

**Ghi chú về "Response accuracy"**: đo bằng LLM-as-judge (model `Llama-3.3-70B-Instruct`, khác họ với agent dùng `GLM-5.2` để tránh circular evaluation) so `response` thực tế với `expected_answer` mẫu — không chỉ kiểm tra retrieval có đúng đoạn hay không (xem mục 3). Con số dev accuracy 75% *thấp hơn* held-out 80% là **bất thường tích cực**: không có dấu hiệu overfit vào bộ câu hỏi dùng để tune (chênh lệch nằm trong khoảng nhiễu tự nhiên của mẫu 30 câu — CI của cả hai đều chồng lấn nhau). Accuracy không đổi đáng kể giữa Phase 2 và Phase 3 (110→111/140, trong biên nhiễu bootstrap) — Phase 3 chủ đích chỉ nhắm latency, không đụng logic chấm điểm đúng/sai.

---

## 2. Test Results

### Unit Tests

```
pytest tests/ -v
167 passed in ~10s   (154 cuối Phase 2 -> +13 test mới cho Session/backoff, embedding cache, skip-hallucination)

pytest --cov=src --cov-report=term-missing
TOTAL: 1293 statements, 166 miss, 87% coverage
```

Coverage thấp nhất tập trung ở phần **không nên** có coverage cao ở giai đoạn này: `src/services/supabase_client.py` (0% — chưa có test tích hợp DB thật, out of scope đợt này vì backend/auth do team khác phụ trách), `src/ingestion/embeddings.py`/`extractors/pdf_extractor.py` (I/O nặng, gọi API ngoài, được test qua kịch bản chạy tay + `scripts/rag_pipeline/verify_processed.py` thay vì unit test). Toàn bộ logic nghiệp vụ cốt lõi (`src/agents/*`, `src/retrieval/*`, `src/models/schemas.py`, `src/ingestion/chunkers.py`/`cleaners.py`) đạt 95-100%.

### Integration / Eval Tests (đặc thù hệ thống RAG — thay cho "integration test" cổ điển)

Hệ thống không có test tích hợp DB/API cổ điển (chưa có backend thật kết nối Supabase — xem mục 6). Thay vào đó, 3 tầng eval chạy trên dữ liệu/API thật:

| Tầng | Script | Kết quả (dev) | Kết quả (held-out, chạy 1 lần) |
|---|---|---|---|
| Router (phân loại intent) | `eval/scripts/eval_router.py` | Accuracy 95.7-96.4% tuỳ model (xem mục Latency Phase 3) | *(không tách riêng — dùng chung 140 câu dev)* |
| Retrieval (chunk-level, qrel-based, sau rerank) | `eval/scripts/eval_retrieval.py --rerank` | Recall@10 92.8%, MRR 0.916, Multi-chunk Recall@10 83.6% | Recall@10 81.9%, MRR 0.881, Multi-chunk Recall@10 55.0% |
| Agent end-to-end | `eval/scripts/eval_agent.py` | 111/140 (79.3%) | 24/30 (80.0%) — chạy trước Phase 3, chưa có lý do đo lại (Phase 3 không đụng logic chấm điểm) |

Chi tiết breakdown theo type (dev, 140 câu, sau Phase 3): `in_scope` 75/100, `ambiguous` 12/15, `out_of_scope` 15/15, `competitor_comparison` 9/10 (1 câu fail do lỗi nhãn dataset, xem `CLAUDE.md` — Vingroup/VinFast vừa là "công ty mình" vừa bị gán nhãn test "hỏi đối thủ", mâu thuẫn logic không thể vừa đúng cả hai).

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
- **Latency đã tối ưu trong Phase 3** (Session + backoff dùng chung cho gateway, cache embedding câu hỏi lặp lại, bỏ hallucination check khi câu trả lời là "chưa đủ thông tin", router đổi từ GLM-5.2 sang DeepSeek-V4-Flash sau A/B):

  | | Trước Phase 3 | Sau Phase 3 | Đổi |
  |---|---|---|---|
  | p50 tổng thể | 21.3s | 16.6s | −22% |
  | p50 in_scope (cần RAG đầy đủ) | 24.9s | 19.1s | −23% |
  | p50 out_of_scope | 4.4s | 2.1s | −52% |
  | p50 competitor_comparison | 5.6s | 2.0s | −64% |
  | p95 tổng thể | 50.9s | 48.9s | ~không đổi |

  `out_of_scope`/`competitor_comparison` giảm mạnh nhất vì các câu này chỉ đi qua router rồi escalate/decline ngay (bỏ qua toàn bộ nhánh RAG) — router nhanh hơn 3.3x (GLM-5.2 p50 6.0s → DeepSeek-V4-Flash p50 1.8s, xem `eval/results/router_ab_*.json`) tác động trực tiếp gần như toàn bộ latency của nhóm này.
- **Vẫn CHƯA đạt target <3s** cho câu cần RAG đầy đủ — kiến trúc còn 3-5 lệnh gọi mạng tuần tự (router → embed → rerank → generate → [hallucination-check] → confidence). Target <3s đòi hỏi streaming hoặc redesign kiến trúc (song song hoá node, giảm số vòng LLM), ngoài phạm vi Phase 3.
- **Đã thử và KHÔNG đổi**: model nhỏ hơn cho `hallucination_check` — A/B replay offline 60 câu cho thấy DeepSeek-V4-Flash chỉ đồng thuận PASS/FAIL với GLM-5.2 ở mức 76.7% (ngưỡng chấp nhận đặt ra là ≥95%) dù nhanh hơn (p50 4.2s vs 8.1s) — sai lệch verdict trên lớp bảo vệ chống hallucination rủi ro hơn nhiều so với phần latency tiết kiệm được, nên giữ nguyên GLM-5.2 cho tác vụ này (xem `eval/results/hallucination_model_ab.json`).

---

## 6. Action Items / Nợ kỹ thuật đã biết

Xếp theo mức độ ưu tiên nếu tiếp tục dự án:

- [ ] **Latency 16.6s p50 tổng / 19.1s p50 in_scope** (đã giảm 22-23% trong Phase 3, xem mục 5) — vẫn chưa dùng được cho demo live liền mạch, chưa đạt target <3s. Hướng còn lại: streaming response (user thấy chữ chạy thay vì chờ cả pipeline), song song hoá `hallucination_check` với phần đầu `confidence`, hoặc bớt hẳn 1 node cho profile "nhanh" và so đánh đổi chất lượng — chưa làm, đòi hỏi redesign kiến trúc graph.
- [ ] **Multi-chunk Recall lệch dev/held-out (83.6% vs 55.0%, n=20)** — cần thêm câu hỏi held-out đa-chunk để xác nhận đây là suy giảm thật hay nhiễu mẫu nhỏ trước khi đầu tư thêm vào hybrid/rerank.
- [ ] **0 nhãn con người xác nhận độc lập** — toàn bộ ground truth do LLM sinh + LLM chấm. 50 mẫu bất đồng giữa 2 judge đã chuẩn bị sẵn (`human_review_sample.json`) nhưng chưa chấm.
- [ ] **CI chưa gate được eval** — `.github/workflows/ci.yml` chỉ chạy `pytest` + `check_dataset_integrity.py` (không gọi API), chưa chạy `eval_agent.py`/`eval_retrieval.py` trên CI (cần secret `FPT_API_KEY` + chấp nhận thời gian chạy dài hơn nhiều).
- [ ] **Backend/persistence chưa nối** — `src/agents/service.py` + `docs/AGENT_API.md` đã định nghĩa xong contract (response, citations, confidence, escalate, ticket_draft), nhưng chưa có backend thật gọi vào để lưu conversation/message/ticket vào Supabase. Theo quyết định của user, phần này để team backend (nhánh `develop`) tự triển khai dựa trên `docs/AGENT_API.md`.
- [ ] **Chưa chống prompt injection** — user query được chèn thẳng vào prompt không qua sanitization/delimiter. Đây là gap thật duy nhất được xác nhận từ 3 report audit ngoài đọc trong Phase 3 (2 report khác có nhiều đề xuất bị bác bỏ vì mâu thuẫn với số liệu đã đo — xem `CLAUDE.md`).
- [x] ~~29 câu in_scope fail chưa rõ nguyên nhân~~ — đã bóc tách và fix 3/4 nhóm nguyên nhân trong Phase 2 (xem `CLAUDE.md`): hạ ngưỡng confidence, chặn "retrieval sai nhưng vẫn trả lời" bằng sentinel, sửa xung đột nguồn trong prompt generate (sau khi tự phát hiện và sửa 2 bug do chính các fix này gây ra — sentinel false-positive và sort phá relevance).
- [x] ~~Latency chưa đo lại sau tối ưu, retry fixed-2s không backoff~~ — Phase 3: `requests.Session` dùng chung + exponential backoff (thay 3 vòng retry trùng lặp), cache embedding câu hỏi lặp lại, bỏ hallucination check khi không đủ thông tin, router đổi model sau A/B. Giảm p50 22-23%, chất lượng giữ nguyên trong biên nhiễu.
