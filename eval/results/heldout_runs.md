# Sổ chạy held-out

> Mỗi lần chạy tập held-out phải ghi vào đây: ngày, lý do, kết quả.
> Lý do tồn tại: held-out chỉ có giá trị khi được chạy hiếm. Chạy nhiều lần rồi
> chọn lần đẹp nhất thì nó thành dev set, và mọi con số báo cáo mất ý nghĩa.
>
> Quy ước: chỉ chạy khi **chốt một cột mốc**, không chạy để debug.

| # | Ngày | Tập | Lý do | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| 0 | 2026-08-06 | `retrieval_eval_set` (20 query heldout) | **Vô ý** — chạy trước khi có cờ `--split`, script khi đó đo cả 97 query | Đã gộp chung trong số 97-query, không tách riêng | Không có thay đổi nào được tune dựa trên 20 query này. Ghi lại làm vết. |
| invalid-1 | 2026-08-19 | `qa_heldout_set` (30 câu) | Release run sau integration | **Không hợp lệ — 30/30 lỗi kết nối** | Sandbox chặn socket `WinError 10013` trước khi model xử lý. Không dùng 0% làm quality score; cần chạy lại với quyền data egress. |
| 1 | 2026-08-19 | `qa_heldout_set` (30 câu) | Release run sau integration, đã được chủ dữ liệu cho phép egress | **0/30 (0,0%)** | 0 lỗi hạ tầng; context gold 0/30; answer judge 2/30; intent: 17 pure_statutory, 11 hr_question, 2 out_of_scope_or_personal; p50 10,0s, p95 59,7s. Không tune/rerun. |
| 2 | 2026-08-19 | `retrieval_eval_set` split heldout (20 query) | Đo Recall release độc lập, đã được chủ dữ liệu cho phép egress | **Hit@5 45%; Recall@5 29,6%; Doc Hit@5 15%** | MRR 0,425; 0 lỗi hạ tầng; không đạt gate Recall@5 85%. Không tune/rerun. |

## Chưa chạy

- `qa_heldout_set.json` (30 câu, agent + router): đã chạy release run hợp lệ #1; không chạy lại để tune.
- `retrieval_eval_set` split `heldout` (20 query): đã chạy release run #2; không chạy lại để tune.
