# Release readiness — 19/08/2026

## Kết luận

Phần do minhphu sở hữu đã hoàn tất ở mức code, migration, database security và
offline regression. Release eval qua dịch vụ ngoài chưa được phép chạy, nên
không có số held-out mới hợp lệ sau integration.

## Bằng chứng hoàn thành

| Hạng mục | Kết quả |
|---|---|
| G5 retrieval | `qa_013` và `qa_122` retrieve/grade đúng evidence |
| Schema | 10/10 bảng backend; migration liên tục `0001`–`0007` |
| Supabase RLS | Không còn bảng bắt buộc nào tắt RLS |
| Profile guard | `trg_prevent_self_privilege_escalation` hiện diện |
| Worker contract | Backend submit/poll ingestion, index rebuild, evaluation và persist kết quả thật |
| Evaluation persistence | Đã xóa fallback metric/quality gate giả trong backend |
| Core tests | 421 passed |
| Backend tests | 106 passed |
| Root lint | Ruff passed |

## Release eval

Run ngày 19/08 trong sandbox trả 0/30, nhưng cả 30 case đều có cùng lỗi
`WinError 10013` trước khi FPT.AI nhận request. Run này được lưu dưới tên
`heldout_agent_report_2026-08-19_invalid_network.json` và bị loại khỏi mọi phép
đánh giá chất lượng. Chỉ chạy lại sau khi người sở hữu dữ liệu xác nhận cho phép
gửi 30 câu hỏi synthetic tới FPT.AI và Chroma Cloud.

## Known limitations

- Backend chỉ đồng bộ worker khi client poll endpoint trạng thái; chưa có poller
  chủ động khi không có client theo dõi.
- Upload được submit ngay sang Agent; nếu Backend chết giữa lúc commit DB và
  submit HTTP, job cần thao tác retry vận hành.
- Backend test còn cảnh báo khóa JWT test ngắn, FastAPI deprecation và thread
  cleanup của `aiosqlite`; không làm test fail nhưng nên dọn sau release.
- Release gate Citation ≥85%, Answer ≥80%, Recall@5 ≥85% chưa thể kết luận bằng
  số mới cho tới khi có một held-out run hợp lệ.
