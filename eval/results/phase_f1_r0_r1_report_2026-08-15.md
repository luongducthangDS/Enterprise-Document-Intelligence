# Phase F.1 — R0 → R1 Report (Reproducibility & Change Attribution)

Trả lời đúng 5 điểm Ted yêu cầu ngày 2026-08-15.

## 1. Snapshot R0 (trước mọi remediation)

Ghi đầy đủ tại `eval/results/phase_f_r0_snapshot_2026-08-15.json`:

- `git_commit_before`: `4fc9ea791e69b056d3d3b0bdfd2b0cd955dca89c` (chưa có commit nào được tạo trong phiên này — mọi thay đổi F.1 vẫn ở working tree, chưa add/commit).
- `qa_eval_set.json` SHA-256 (bản HEAD, trước F.1): `6e739cf0...af2`
- `retrieval_qrels.json` SHA-256: `07aa062c...5862aa8`
- `retrieval_anchors.json` SHA-256: `03d06760...bf97306`... *(xem đủ digest trong file JSON)*
- Chroma index: collection `hr_documents`, 189 chunk, `data_mode=demo`. F.1 KHÔNG re-index — script không gọi bất kỳ hàm indexer nào, xác nhận bằng cách đọc code, không suy đoán.
- `regression_r0 = 86/125` (0.688) — từ `eval/results/agent_eval_report.json`, `run_at=2026-08-15T07:50:31Z`, lần chạy CUỐI trước khi F.1 áp dụng.
- `failed_eval_ids` R0 (đúng 39, liệt kê đầy đủ trong file JSON).

## 2. Schema — đã sửa, không ép schema mới vào dataset cũ

Bỏ hoàn toàn `target_state/reason_code/fact_evidence/citation_required` (tự invent, không có tiền lệ). Kiểm tra lại `eval/datasets/type_c_contract_set.json` (20 case canonical đã đóng băng) và phát hiện nó **đã có sẵn đúng schema cần**: `id / category="Type C" / archetype (ARC_1..ARC_4) / query / expected_state`. 10 case pure-statutory giờ dùng **chính schema này** (không phải schema mới), chỉ thêm 2 field thuần traceability trong file MỚI (`origin_eval_id`, `note`) — không đụng schema của `type_c_contract_set.json` hay `qa_eval_set.json`. "no internal evidence expected"/"no citation expected" là hệ quả tất định của `expected_state=OUT_OF_SCOPE` trong chính `out_of_scope_node()` (đã có trong code), không cần field riêng để mã hoá lại. Đã verify `eval/scripts/eval_type_c_contract.py` có `DATASET_PATH` hardcode trỏ đúng `type_c_contract_set.json`, không glob thư mục — xác nhận file holdout mới không lọt vào bất kỳ runner production nào.

## 3. G1 migration — bổ sung assertion-level proof

`eval/results/phase_f1_assertion_audit.json` — 13 record, đúng schema Ted yêu cầu (`old_chunk_ids/new_chunk_ids/supported_assertion/evidence_excerpt_or_hash/evidence_sha256/validation`). Mỗi record được `assert` ngay trong script (không rỗng, `validation` phải là `EXACT`/`SEMANTIC`) — script FAIL cứng nếu thiếu bằng chứng cho bất kỳ case remap nào.

Phân loại 13 case: **6 EXACT** (nội dung khớp verbatim, chỉ chunk_id/nguồn thay đổi: qa_102, qa_110, qa_123, qa_129, qa_130, qa_131) — **7 SEMANTIC** (giữ đúng assertion nhưng phải diễn giải lại hoặc cắt bớt phần không có bằng chứng: qa_120, qa_122, qa_124, qa_126, qa_127, qa_138, qa_140).

Rà lại đúng yêu cầu "internal source chỉ liên quan chủ đề nhưng không support đúng claim → D1, không remap": xác nhận cả 13 case đều KHÔNG rơi vào tình huống đó — mọi case SEMANTIC đều là do em **chủ động cắt bớt phần claim gốc không có bằng chứng** (vd qa_122 bỏ "15 ngày/năm", qa_138 bỏ "đánh đập"+"mang thai", qa_140 bỏ "bảo hiểm thất nghiệp"), chứ không giữ nguyên claim gốc rồi gán khiên cưỡng vào nguồn chỉ liên quan chủ đề. 3 case KHÔNG tìm được nguồn hỗ trợ đúng claim đã bị retire đúng theo quy tắc này (qa_121, qa_125, qa_128), cộng thêm qa_139 (tự phát hiện sau, xem báo cáo trước).

## 4. R0 → R1 (dataset-only, product code KHÔNG đổi)

**Xác nhận migration script chỉ đụng đúng nhóm file được phép** (không có product code trong diff): `eval/datasets/*.json`, `eval/scripts/migrate_phase_f_stale_qrels.py`, `eval/results/phase_f1_*.json`. Chưa tạo commit nào (theo quy tắc chỉ commit khi được yêu cầu) — khi Ted xác nhận commit, sẽ tách đúng thành 1 commit F.1 (dataset/script/audit) trước, KHÔNG trộn với F.2.

**Idempotent xác nhận lại lần cuối**: chạy `migrate_phase_f_stale_qrels.py` 2 lần liên tiếp trên trạng thái cuối → `changes = 0` cả 2 lần, hash 4 file dataset ổn định (`sha256_after_f1_final` trong snapshot JSON).

**R1 — 3 lần chạy sống trên dataset F.1 cuối** (KHÔNG đổi gì giữa các lần, chỉ cách nhau vài phút — phơi bày lại đúng vấn đề nhiễu run-to-run đã báo trước):

| Run | Denominator | Passed | Rate |
|---|---|---|---|
| R1-a (trước khi tự sửa qa_139) | 112 | 99 | 88.4% |
| R1-b | 111 | 92 | 82.9% |
| R1-c | 111 | 98 | 88.3% |

R1-b và R1-c chạy trên **CÙNG một dataset y hệt** (đã final, hash ổn định) — chênh 6 case (92 vs 98) chỉ vì LLM sampling/confidence-scoring không deterministic, KHÔNG phải do dataset đổi.

```
R0 = 86/125 (0.688)
R1 (range 3 lần chạy, denominator 111-112 sau khi loại 14 case không còn evidence) = 92-99/111-112 (0.829-0.884)
delta_dataset ≈ +14 đến +21 điểm phần trăm (rất lớn, nhưng KHÔNG phải một số cố định do nhiễu run-to-run)
```

**Case fail ổn định ở ≥2/3 lần chạy R1** (bộ có độ tin cậy cao nhất, dùng làm target cho F.2, giữ nguyên root-cause bucket từ triage gốc trừ khi ghi chú reclassify):

| eval_id | Số lần fail /3 | Bucket (từ R0 triage) |
|---|---|---|
| qa_003 | 3/3 | G6 (confidence=0.1) |
| qa_005 | 3/3 | **chưa gán bucket** — case mới, không có trong 39 case R0 |
| qa_082/083/085/086 | 3/3 | G3 (router/boundary — ranh giới ambiguous) |
| qa_107 | 3/3 | G6 (confidence=0.1) |
| qa_111 | 3/3 | G3 (false-ambiguous) |
| qa_122 | 3/3 | reclassify G1→retrieval-gap thật cho doc 13 (không phải qrel nữa) |
| qa_124 | 3/3 | G4 (human_first over-trigger) |
| qa_047 | 2/3 | G6 (từ 39 case gốc — xác nhận bug có thật, không deterministic 100%) |
| qa_138 | 2/3 | G4 (từ 39 case gốc, cùng lý do) |

Case fail chỉ 1/3 lần (qa_013, qa_015, qa_026, qa_027, qa_035, qa_036, qa_103, qa_108) — không đủ ổn định để xác nhận root cause riêng lẻ; đa số trùng case đã có bucket ở R0 (qa_013=G5, qa_026=G4, qa_036=G7) nên vẫn tính là "bug thật nhưng không deterministic", không phải case mới cần điều tra thêm.

## 5. Taxonomy cho F.4 (ghi nhận, chưa áp dụng)

Đã ghi nhận taxonomy khóa của Ted (`PASS/FAIL_PRODUCT_BUG/FAIL_MISSING_CORPUS/FAIL_ACCEPTED_HUMAN_FIRST/FAIL_EXPECTED_PRODUCT_LIMITATION/FAIL_KNOWN_EVAL_LIMITATION`, cấm `UNKNOWN/UNCLASSIFIED/NEED_MORE_INVESTIGATION`) — sẽ áp dụng ở F.4 sau khi F.2 xong, chưa dùng ở bước này vì F.1 chỉ là dataset remediation.

## Chưa làm / chờ xác nhận

- Chưa commit gì (đúng quy tắc chỉ commit khi được yêu cầu).
- Chưa bắt đầu F.2 (P1 confidence-collapse cluster) — chờ Ted xác nhận đã đọc report này, đặc biệt phần R1 3-lần-chạy vì nó ảnh hưởng cách đo R2 sau F.2 (nên dùng cùng phương pháp nhiều-lần-chạy, không dùng 1 lần duy nhất).
