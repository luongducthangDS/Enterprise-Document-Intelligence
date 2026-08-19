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

## Chưa chạy

- `qa_heldout_set.json` (30 câu, agent + router): chưa có release run hợp lệ sau integration; run `invalid-1` không tạo output model.
- `retrieval_eval_set` split `heldout` (20 query): chưa chạy riêng kể từ khi có cờ `--split`.
