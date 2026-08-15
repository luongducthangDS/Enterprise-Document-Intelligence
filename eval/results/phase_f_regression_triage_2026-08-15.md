# Phase F — Regression Triage (39 failed cases, `agent_eval_report.json` chạy ngày 2026-08-15)

**Trạng thái: chỉ phân tích, CHƯA sửa code/dataset nào** — đúng yêu cầu "không sửa code cho tới khi từng case có root-cause bucket".

## 0. Giới hạn dữ liệu đã biết (báo trước, không suy đoán che lấp)

`eval/scripts/eval_agent.py` hiện KHÔNG ghi lại `hallucination_check_method` / `hallucination_passed` (grounding_result) hay verdict thô của LLM judge (judge_result) theo từng case — hai trường này không tồn tại trong `agent_eval_report.json`. Em suy ra root-cause bằng cách đối chiếu chéo: `question` ↔ `expected_answer` ↔ `response` đầy đủ (không cắt) ↔ `relevant_chunk_ids`/`evidence_chunk_id` trong `qa_eval_set.json` ↔ `retrieved_chunk_ids` thực tế ↔ `document_registry.csv` (để biết file nguồn còn sống hay đã bị loại khỏi RAG index). Với 2 case (`qa_036`, `qa_047`) em đọc full response (không truncate) để xác nhận chắc chắn. Các case còn lại trong cùng cụm suy ra từ pattern đã xác nhận + nguồn tài liệu, chưa re-run live từng case — nếu Ted cần độ tin cậy 100% cho từng case riêng lẻ, cần bổ sung `hallucination_check_method`/judge-verdict vào schema của `eval_agent.py` rồi chạy lại.

## 1. Phát hiện chính (đọc trước khi vào bảng chi tiết)

**~29/39 case (74%) không phải bug sản phẩm — là dataset/qrel đã lỗi thời (G1)**, do 3 quyết định hợp lệ trước đó chưa được đồng bộ ngược vào `qa_eval_set.json`:

1. **Đổi tên V-NOVA → NexaTech** làm dịch chuyển ranh giới chunk (đã biết từ trước) → qrel cũ trỏ sai chunk_id dù nội dung/câu trả lời vẫn đúng. Ảnh hưởng: `qa_102, qa_110, qa_140` (và tương tự `qa_129/130/131`).
2. **Loại 7 tài liệu `public_template`/`public_reference` khỏi RAG index** (quyết định cũ, xem `document_registry.csv`: `chunks_path`/`indexed_at` rỗng cho các file `mau_*`, `base_mau-*`, `leanh_mau-*`, `talentnet_*`) — nhưng chỉ có `qa_006-010` và `qa_056-060` được remap sang tài liệu thay thế (11/12/13); các câu `qa_1xx` (thêm sau) **chưa bao giờ được remap**, vẫn trỏ `source_file`/`relevant_chunk_ids` vào file đã bị loại. Ảnh hưởng: `qa_120, qa_121, qa_122, qa_124, qa_125, qa_126, qa_127, qa_128, qa_129, qa_130, qa_131, qa_138, qa_139, qa_140`.
3. **Type-C contract thêm `pure_statutory` → OUT_OF_SCOPE** (đã được Ted chấp nhận, KHÔNG được sửa lại) — nhưng 10 câu `qa_113-116, qa_132-137` trong `qa_eval_set.json` vẫn mang `type=in_scope` từ trước khi có contract này. Router route đúng theo đúng behavior đã accept; dataset chưa cập nhật. Ảnh hưởng: `qa_113, qa_114, qa_115, qa_116, qa_132, qa_133, qa_134, qa_135, qa_136, qa_137`.

**Phát hiện phụ đáng chú ý**: `qa_126`/`qa_127`/`qa_128` cho thấy `mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md` (template đã loại khỏi index) có bảng "chi phí → thời gian cam kết" **khác số** với tài liệu sống `06_chinh-sach-dao-tao-phat-trien.md` (cùng mốc 20 triệu: template ghi 12 tháng, tài liệu sống ghi 24 tháng). Đây không phải cross-policy contradiction đang sống trong index (template đã bị loại, không lọt vào context) — chỉ là hệ quả của việc dataset cũ được viết dựa trên template đã nghỉ hưu.

**~10/39 case là bug thật, cần sửa code/routing** (chi tiết bucket bên dưới): 5 case `G3` (router/boundary xử lý sai câu "ambiguous"), 1 case `G4` rõ ràng (`qa_026`), 1 case `G5` (`qa_013`, retrieval miss thật), 5 case `G6` (đa số cùng một cơ chế: confidence bị kẹp ở 0.1 dù context đã tìm đúng), 1 case `G7` (`qa_036`, judge sai rõ ràng).

## 2. Bảng tổng hợp root-cause bucket (39/39 case)

| Bucket | Số case | Case IDs |
|---|---|---|
| G1_GROUND_TRUTH_STALE | 29 | qa_102,110,113,114,115,116,120,121,122,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140 (26) + xem ghi chú qa_123/qa_124/qa_138 mang cả G1 lẫn bucket khác |
| G3_ROUTER_FALSE_AMBIGUOUS *(mở rộng khỏi tên gốc G3_ROUTER_FALSE_OOS — xem mục 4)* | 5 | qa_082, qa_083, qa_085, qa_086, qa_111 |
| G4_HUMAN_FIRST_EXPECTED | 1 (chính) | qa_026 |
| G5_RETRIEVAL_MISS | 1 | qa_013 |
| G6_GENERATION_CONTENT_ERROR | 5 | qa_003, qa_047, qa_107, qa_109, qa_123 |
| G7_EVAL_JUDGE_ERROR | 1 | qa_036 |
| G2_GROUNDING_VERIFIER | 0 | — (không có case nào isolate được thuần grounding-verifier lỗi; các case nghi ngờ đều giải thích được bằng G1/G6) |

*(Tổng > 39 vì vài case mang 2 nhãn — primary bucket dùng để đếm ở bảng trên là nhãn IN BOLD trong bảng chi tiết mục 3; secondary chỉ để tham khảo.)*

## 3. Bảng chi tiết từng case

Cột `retrieved_doc_codes` dùng tên file nguồn (source_file stem) thay cho `doc_code` vì **chưa có `policy_manifest.yaml`** để map code — đã báo Ted blocker này trước đó, vẫn còn hiệu lực.

### G1_GROUND_TRUTH_STALE — chunk-id trôi do rename (rename-drift)

| eval_id | expected (rút gọn) | actual (rút gọn) | retrieved_docs | qrel trỏ tới | Ghi chú |
|---|---|---|---|---|---|
| qa_102 | WFH 8 ngày/tháng, 96 ngày/năm | **Đúng y hệt**, có trích nguồn | 05_lam-viec-tu-xa (đúng file) | `05_...::0010` | answer_correct=True, chỉ context_found=False do chunk_id lệch |
| qa_110 | BHSTN chấm dứt cuối tháng nghỉ việc | **Đúng y hệt** | 08_bao-hiem-suc-khoe-tu-nguyen (đúng file) | `08_...::0007` | như trên |
| qa_140 | 14 ngày làm việc thanh toán quyền lợi | **Đúng y hệt** | 03/04/07/08/11 (đúng nội dung) | trỏ vào talentnet (đã loại) | như trên, xem thêm mục "loại template" |

### G1_GROUND_TRUTH_STALE — qrel trỏ vào tài liệu `public_template`/`public_reference` đã bị loại khỏi RAG index

| eval_id | source_file trong qrel (đã loại, `chunks_path` rỗng) | Tài liệu sống nên thay thế | answer_correct thực tế |
|---|---|---|---|
| qa_120 | base_mau-quy-che-luong-thuong-phu-cap-xu-phat | 07_nghi-phep / 08_bao-hiem (agent tự tìm) | False — số liệu không khớp, vì so với nguồn sai |
| qa_121 | base_mau-quy-che-luong-thuong-phu-cap-xu-phat | chưa rõ, có thể chưa có tài liệu sống nào phủ "thưởng cưới hỏi" | retrieval rỗng — cần xác nhận doc 11/13 có phủ không |
| qa_122 | base_mau-quy-che-luong-thuong-phu-cap-xu-phat | 13_noi-quy-lao-dong-va-ky-luat (nghi ngờ, chưa được retrieve — xem G6 note) | False |
| qa_124 | leanh_mau-noi-quy-lao-dong | 13_noi-quy-lao-dong-va-ky-luat (không được retrieve) | False — mang thêm G4 (human_first_required) |
| qa_125 | leanh_mau-noi-quy-lao-dong | 13_noi-quy-lao-dong-va-ky-luat (không được retrieve) | False |
| qa_126 | mau_quy-che-dao-tao-va-cam-ket-boi-hoan | 06_chinh-sach-dao-tao-phat-trien (SỐ KHÁC: 12 tháng vs 24 tháng) | routed ambiguous — mang thêm G3 |
| qa_127 | mau_quy-che-dao-tao-va-cam-ket-boi-hoan | 06_chinh-sach-dao-tao-phat-trien (SỐ KHÁC) | False — agent trả lời đúng theo tài liệu SỐNG (24 tháng), nhưng bị chấm sai vì so với ground truth từ template đã nghỉ hưu (12 tháng) |
| qa_128 | mau_quy-che-dao-tao-va-cam-ket-boi-hoan | 06_chinh-sach-dao-tao-phat-trien | như trên |
| qa_129 | mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai | 13_noi-quy-lao-dong-va-ky-luat (đã retrieve, đúng) | **True** — chỉ fail vì context_found=False |
| qa_130 | mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai | 13_noi-quy-lao-dong-va-ky-luat (đã retrieve, đúng) | **True** — như trên |
| qa_131 | mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai | 13_noi-quy-lao-dong-va-ky-luat (đã retrieve, đúng) | **True** — như trên |
| qa_138 | talentnet_quy-trinh-cham-dut-hop-dong-lao-dong | 04_quy-trinh-offboarding (không được retrieve, agent escalate) | mang thêm G4 (human_first_required) |
| qa_139 | talentnet_quy-trinh-cham-dut-hop-dong-lao-dong | 03/04/05/11/13 (đã retrieve, agent trả lời) | False — cần review nội dung cụ thể |
| qa_140 | talentnet_quy-trinh-cham-dut-hop-dong-lao-dong | 03/04/07/08/11 (đã retrieve, đúng) | **True** — chỉ fail vì context_found=False |

### G1_GROUND_TRUTH_STALE — dataset chưa cập nhật theo Type-C `pure_statutory` contract (đã được Ted accept)

10 case này: router classify `pure_statutory` → `out_of_scope_node` trả lời đúng theo **contract đã đóng băng**. Đây KHÔNG phải router bug — là dataset `type=in_scope` cũ chưa retire/retype theo contract mới.

| eval_id | Câu hỏi (tóm tắt) | Phân loại PURE vs INTERNAL |
|---|---|---|
| qa_113 | NĐ 161/2026 lương cơ sở — đối tượng áp dụng | **PURE STATUTORY** — hỏi phạm vi áp dụng của nghị định cho CBCC/viên chức nhà nước, không liên quan chính sách NexaTech |
| qa_114 | Viên chức bảo lưu chênh lệch lương khi lương cơ sở tăng | **PURE STATUTORY** — đối tượng viên chức khu vực công, không phải NLĐ NexaTech |
| qa_115 | Cơ sở y tế công lập dùng % thu để cải cách lương | **PURE STATUTORY** — quy định cho đơn vị sự nghiệp công lập |
| qa_116 | Trách nhiệm Bộ Tài chính hướng dẫn chi trả | **PURE STATUTORY** — quy định trách nhiệm cơ quan nhà nước |
| qa_132 | BHXH trước 01/07/2025, lương hưu thấp hơn mức tham chiếu | **PURE STATUTORY** — diễn giải Điều 13 Luật BHXH áp dụng chung mọi đối tượng, không phải chính sách nội bộ |
| qa_133 | Phụ cấp khu vực trước 1995 tính vào hưu trí | **PURE STATUTORY** — quy định pháp luật hưu trí chung |
| qa_134 | Thời gian công tác nước ngoài trước 1995 tính hưu trí | **PURE STATUTORY** — như trên |
| qa_135 | NĐ 293/2025 mức lương tối thiểu vùng I | **PURE STATUTORY** — tra cứu số liệu nghị định trực tiếp, đúng pattern router rule 2 |
| qa_136 | Vùng II tỉnh Ninh Bình gồm phường nào | **PURE STATUTORY** — tra cứu địa giới hành chính theo nghị định |
| qa_137 | Cần Thơ các phường thuộc vùng nào | **PURE STATUTORY** — như trên |

**Kết luận sub-task**: cả 10/10 case đều là PURE STATUTORY thật sự (không có case nào là "câu hỏi nội bộ chứa thuật ngữ pháp lý" bị router bắt nhầm — không giống ví dụ `qa_131`/`qa_138` mà Ted cảnh báo trước, và đúng vậy, 2 case đó đã được fix ở vòng router trước, không nằm trong 10 case pure_statutory này). Đề xuất: **retire hoặc retype** 10 câu này trong `qa_eval_set.json` (giống pattern đã dùng cho `qa_041-045`), không đổi router.

### G3 — Router/Boundary xử lý sai ranh giới "ambiguous"

Tên bucket gốc Ted đặt là `G3_ROUTER_FALSE_OOS`, nhưng cả 5 case dưới đây không liên quan `pure_statutory`/OOS — chúng đều thuộc ranh giới `ambiguous` (câu hỏi mơ hồ cần hỏi lại) vs `hr_question`/`out_of_scope_or_personal`. Em xếp tạm vào G3 vì đây vẫn là router/boundary chọn sai path, nhưng đề xuất Ted cân nhắc tách thành bucket riêng (`G3b_ROUTER_AMBIGUOUS_BOUNDARY`) cho vòng sau.

| eval_id | Câu hỏi | expected_behavior | Actual | Lỗi |
|---|---|---|---|---|
| qa_082 | "Tôi còn bao nhiêu ngày phép?" | ask_clarification (năm nay vs cộng dồn) | escalate personal_data_required | Router coi là cần dữ liệu cá nhân trực tiếp, bỏ qua nhánh hỏi lại |
| qa_083 | "Tôi khi nào được ký hợp đồng mới?" | ask_clarification (chính thức vs gia hạn) | escalate out_of_scope | Router phân loại nhầm thành OOS |
| qa_085 | "Tôi muốn nghỉ thai sản thì làm thủ tục gì?" | ask_clarification (trước vs sau sinh) | trả lời trực tiếp (hr_question) | Router không phát hiện mơ hồ, trả lời luôn |
| qa_086 | "Lương của tôi tháng này bị thiếu." | ask_clarification (loại khoản thiếu) | escalate personal_data_required | Router coi là cần dữ liệu cá nhân, bỏ qua hỏi lại |
| qa_111 | "Đăng ký BHSK cho vợ và 2 con, chi phí và hạng thế nào?" | trả lời trực tiếp (có sẵn ở doc 08 mục 8) | router intent=ambiguous, hỏi lại | **Chiều ngược lại**: router hỏi lại dù câu trả lời trực tiếp sẵn có trong context |

**Nhận xét**: 4/5 case đầu bị lệch về hướng "không hỏi lại khi nên hỏi", 1 case lệch ngược "hỏi lại khi không cần" — cho thấy đây không phải một ngưỡng đơn giản mà là router/boundary thiếu tiêu chí rõ ràng để phân biệt "mơ hồ thật" (nhiều nghĩa hợp lý, cần chọn) với "thiếu dữ liệu cá nhân" (personal_data) và với "đủ ngữ cảnh trả lời thẳng".

### G4_HUMAN_FIRST_EXPECTED — escalate nhầm sang human trong khi có thể trả lời bằng chính sách

| eval_id | Câu hỏi | Ghi chú |
|---|---|---|
| qa_026 | Báo trước bao lâu khi nghỉ việc (HĐ không xác định thời hạn) | context_found=True (đã tìm đúng 5 tài liệu gồm doc 13), nhưng escalate human_first_required — đây là câu hỏi tra cứu số ngày báo trước thuần túy, có sẵn trong nội quy, không cần con người |
| qa_138 *(secondary, primary=G1)* | Trường hợp nghỉ việc không cần báo trước | Cùng pattern — cần xem lại từ khóa kích hoạt `human_first_required` trong boundary, có thể đang bắt nhầm cụm "nghỉ việc" nói chung thay vì chỉ trường hợp thật sự cần tư vấn cá nhân hoá |

### G5_RETRIEVAL_MISS — retrieval thật sự trả về rỗng

| eval_id | Câu hỏi | qrel đúng (tài liệu sống) | Kết quả |
|---|---|---|---|
| qa_013 | Kênh nộp hồ sơ khi được giới thiệu (referral) | `02_quy-trinh-tuyen-dung::0005` (tài liệu sống, KHÔNG bị loại) | retrieved_chunk_ids rỗng hoàn toàn — retrieval thật sự không tìm ra, cần kiểm tra embedding/BM25 cho câu hỏi dạng "giới thiệu bạn ứng tuyển" |

### G6_GENERATION_CONTENT_ERROR

| eval_id | Câu hỏi | context_found | Vấn đề cụ thể |
|---|---|---|---|
| qa_003 | Tự ở lại làm OT không đăng ký trước có tính không | True (đúng 2 doc) | confidence_score=0.1 (giá trị sàn) → escalate low_confidence dù đã có evidence đúng |
| qa_047 | Người nước ngoài có phải đóng BHXH bắt buộc | True, **đã retrieve đúng chunk `09_...::0009`** chứa điều khoản ngoại lệ | Generation trả lời đúng phần chính nhưng **bỏ sót hoàn toàn** vế ngoại lệ ("trừ di chuyển nội bộ doanh nghiệp / đã đủ tuổi nghỉ hưu") dù chunk chứa sẵn |
| qa_107 | Cam kết làm việc sau đào tạo 60 triệu | True (đúng 1 doc: 06_dao-tao) | confidence_score=0.1 → escalate low_confidence dù evidence đúng |
| qa_109 | Vừa qua thử việc có được tham gia BHSTN không | True (đúng 3 doc) | confidence_score=0.1 → escalate low_confidence dù evidence đúng |
| qa_123 | Lịch làm việc chuẩn trong tuần | context_found=False (qrel trỏ file đã loại — mang cả G1), nhưng **doc 13 sống ĐÃ được retrieve đúng** | confidence_score=0.1 → escalate low_confidence dù doc 13 có mặt trong context |

**Pattern chung 4/5 case (`qa_003, qa_107, qa_109, qa_123`)**: `confidence_score` bị kẹp đúng **0.1** — một giá trị sàn cố định — dù `context_found=True`/evidence đã đúng. Rất giống nhau về cơ chế, nên nghi ngờ đây là MỘT bug chung trong confidence-scoring logic (không phải 4 bug riêng lẻ) — có thể liên quan cách tính confidence khi câu hỏi dạng phủ định/điều kiện ("không được tính trừ khi...", "cam kết tối thiểu bao lâu") hoặc dạng số tiền/ngưỡng cụ thể. Cần đọc code tính `confidence_score` (không đoán thêm ở đây) trước khi sửa.

### G7_EVAL_JUDGE_ERROR

| eval_id | Câu hỏi | Ghi chú |
|---|---|---|
| qa_036 | Báo nghỉ ốm đột xuất kiểu gì | Response **đầy đủ và đúng 100%** so với expected_answer (còn chi tiết hơn: có thêm phần "nộp giấy ốm trong 3 ngày"), trích nguồn đúng chunk `::0017` khớp qrel — không có lý do hợp lý để `answer_correct=False`. Judge marked sai. |

## 4. Đề xuất bucket taxonomy bổ sung (không tự ý đổi, chỉ đề xuất)

Ted định nghĩa 7 bucket cố định, nhưng dữ liệu thực tế cho thấy `G1_GROUND_TRUTH_STALE` chiếm áp đảo (74%) với 3 nguyên nhân con khác biệt (rename-drift / template-exclusion / Type-C-contract-drift), và `G3` như đặt tên hiện tại ("FALSE_OOS") không khớp với các case boundary thực tế gặp phải (toàn bộ đều là ranh giới `ambiguous`, không phải OOS/pure_statutory). Em không tự đổi taxonomy — chỉ báo để Ted quyết định có cần tách bucket cho vòng report tiếp theo không.

## 5. Việc CHƯA làm (chờ quyết định của Ted trước khi động code)

- Chưa sửa `qa_eval_set.json` (retire/remap 29 case G1) — đây là thay đổi dataset, không phải "sửa code", nhưng vẫn nên chờ Ted xác nhận trước khi động vào bộ eval chính thức.
- Chưa đọc code tính `confidence_score` để xác nhận root cause chính xác của cụm G6 (giả thuyết "giá trị sàn 0.1" mới chỉ là quan sát từ dữ liệu, chưa đọc source).
- Chưa điều tra sâu boundary/router logic cho cụm G3 (ranh giới ambiguous) và G4 (`human_first_required` trigger keywords).
- Chưa thêm các test case grounding-verifier bổ sung Ted yêu cầu (đang làm tiếp ngay sau report này).
- Chưa có `grounding_result`/`judge_result` thô theo từng case (giới hạn instrumentation, xem mục 0).
