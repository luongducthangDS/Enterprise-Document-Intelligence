# Phase F.1 — Acceptance Report (DATASET-CORRECTED DIAGNOSTIC BASELINE)

**Đây là dataset-corrected diagnostic baseline, CHƯA phải release baseline.** Không sửa product code trong toàn bộ F.1.

## 1. Xác nhận mutual-exclusivity (bắt buộc trước F.1)

total_failed = 39, G1=24, G2=0, G3=5, G4=3, G5=1, G6=5, G7=1 → **sum = 39 ✓**

## 2. Migration đã áp dụng — `eval/scripts/migrate_phase_f_stale_qrels.py`

- Idempotent xác nhận: chạy 2 lần liên tiếp → 0 thay đổi (verify nhiều lần trong quá trình làm, kể cả sau khi sửa lỗi authoring — xem mục 5).
- 12 case **remap** sang tài liệu nội bộ sống thật (đọc trực tiếp `data/processed/*.md` + `data/chunks/*.json`, KHÔNG dùng response agent làm nguồn).
- 4 case **retire** vì không có bằng chứng nội bộ sống hỗ trợ cùng assertion: qa_121, qa_125, qa_128, và **qa_139** (qa_139 bị retire ở vòng 2 sau khi tự phát hiện lỗi authoring — xem mục 5).
- 10 case pure_statutory (qa_113-116, qa_132-137) chuyển sang `eval/datasets/type_c_pure_statutory_holdout.json` — xác nhận **10/10 PURE STATUTORY thật**, router hành xử đúng theo Type-C contract đã đóng băng, KHÔNG phải bug router. Production router không đọc file holdout này.
- Đồng bộ `retrieval_qrels.json` + `retrieval_anchors.json` (2 file tách biệt khỏi `qa_eval_set.json`, ban đầu bị bỏ sót, `check_dataset_integrity.py` phát hiện).
- 141 audit record đầy đủ tại `eval/results/phase_f1_migration_audit.json`, đúng schema (old_value/new_value/field_changed/reason/source_of_truth/product_code_changed:false).
- `check_dataset_integrity.py`: ✅ PASS (0 vấn đề).

## 3. Denominator: 125 → 111

140 câu gốc − 15 câu đã retired từ trước (vòng loại luật) − 14 câu vừa retired/holdout ở F.1 (3 template-only + 10 pure_statutory + qa_139 tự sửa) = **111 câu active**. Đây là kết quả hợp lệ của việc loại đúng case không có evidence, không phải cắt để tăng score.

## 4. Điểm quan trọng phát hiện thêm: pipeline có nhiễu run-to-run thật

Chạy sống 2 lần liên tiếp trên CÙNG bộ dataset đã sửa (không đổi gì giữa 2 lần, chỉ cách nhau ít phút):

| | Run 1 | Run 2 |
|---|---|---|
| Overall | 99/112 (88.4%) | 92/111 (82.9%) |
| in_scope | 59/68 (86.8%) | 52/67 (77.6%) |
| ambiguous | 12/16 (75.0%) | 12/16 (75.0%) |
| out_of_scope | 15/15 (100%) | 15/15 (100%) |
| competitor_comparison | 13/13 (100%) | 13/13 (100%) |

Cả hai đều cao hơn nhiều so với before (86/125 = 68.8%), nhưng bản thân 2 lần chạy đã lệch nhau ~5.5 điểm phần trăm — CI hai lần overlap ([0.821,0.938] vs [0.757,0.892]) nên về mặt thống kê không phải regression thật, mà là nhiễu vốn có của pipeline (LLM sampling ở generation + confidence-scoring + judge). Đây đúng là loại vấn đề Ted đã cảnh báo trước ("hallucination-check flakiness") nhưng giờ thấy nó KHÔNG chỉ giới hạn ở hallucination-check — còn ảnh hưởng confidence-scoring (P1) và có thể cả judge. Em không chốt một con số duy nhất "X/125" vì làm vậy sẽ che giấu chính vấn đề này.

## 5. Tự phát hiện + tự sửa lỗi authoring trong chính F.1 (không phải product bug)

Sau Run 1, đối chiếu response thật của agent cho `qa_139` (được remap sang doc 04 §4): agent trả lời trung thực "các đoạn trích chỉ nêu thời hạn khi NLĐ tự xin nghỉ (Điều 35), KHÔNG nêu thời hạn khi công ty đơn phương chấm dứt (Điều 36)". Kiểm tra lại doc 04 xác nhận agent ĐÚNG — `legal_basis` frontmatter và tiêu đề §4 chỉ dẫn chiếu Điều 35, không có nội dung Điều 36. Giả định "áp dụng đối xứng" của em ở lần remap đầu là sai — đã sửa: chuyển `qa_139` từ remap sang retire, ghi rõ trong audit đây là lỗi migration, không phải product bug.

`qa_122` sau remap (đúng qrel, trỏ doc 13) vẫn KHÔNG được retrieve trên cả 2 lần chạy live — root cause thật của case này KHÔNG còn là G1 (dataset đã đúng) mà là retrieval-miss thật cho doc 13 trên câu hỏi cụ thể này. Reclassify sang phạm vi F.2 (gần G5 nhất), không tính là "đã giải quyết" ở F.1.

## 6. Newly passing vs still failing

So với Run 1 (12 case trong 39 case gốc còn nằm trong pool 112, loại `qa_139` đã retire riêng):
- **Newly passing vì qrel đã sửa: 15/26** case (trong số case G1 còn ở lại pool sau khi loại 13 case retired/holdout).
- **Still failing (ổn định ở CẢ 2 lần chạy — root cause đáng tin cậy nhất): 11 case** — giữ nguyên bucket từ triage gốc: `qa_003`(G6), `qa_005`(chưa gán bucket — xem mục 7), `qa_013`(G5), `qa_082/083/085/086`(G3), `qa_107`(G6), `qa_111`(G3), `qa_122`(reclassify G1→retrieval-gap, gần G5), `qa_124`(G4).
- **Chỉ fail ở 1 trong 2 lần (bằng chứng trực tiếp cho nhiễu run-to-run ở mục 4)**: Run-1-only: `qa_027`. Run-2-only: `qa_007, qa_015, qa_026, qa_035, qa_036, qa_047, qa_103, qa_138`. Trong số này, `qa_026`/`qa_036`/`qa_047` chính là 3 case đã có trong 39 case gốc (bucket G4/G7/G6) — xác nhận các bug đó THẬT nhưng KHÔNG deterministic 100%, chỉ biểu hiện một phần các lần chạy. `qa_007/015/035/103` là case mới chưa từng xuất hiện — chưa gán bucket, cần thêm dữ liệu (nhiều lần chạy hơn) trước khi kết luận.

## 7. `qa_005` — chưa gán bucket

Response thiếu vế "cần sự đồng ý của NLĐ" so với expected_answer (chỉ có "phê duyệt trước của quản lý trực tiếp"). Đây là fixture đã được ghi nhận trước đây là flaky trong `tests/test_agents/test_generation.py` (comment "Đây là fixture flaky đã đo được (qa_005)" — liên quan lớp deterministic numeric-grounding). Ổn định ở cả 2 lần chạy live vừa rồi (fail cả 2) nên KHÔNG phải nhiễu thuần — cần điều tra riêng, tạm chưa gán G1-G7 vì chưa đọc code để xác nhận cơ chế.

## 8. Không kết luận

Không tuyên bố CONTRACT COMPLIANT. Không tối ưu số cuối cùng. F.2 (product bug remediation) chỉ bắt đầu sau khi Ted xác nhận đã đọc report này.
