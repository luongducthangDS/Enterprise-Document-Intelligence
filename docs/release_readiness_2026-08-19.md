# Release readiness — 19/08/2026

## Kết luận

Phần do minhphu sở hữu đã hoàn tất ở mức code, migration, database security và
offline regression. Agent held-out đã chạy hợp lệ sau integration và không đạt
release gate; retrieval held-out 20 query còn cần quyền data egress riêng.

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

Run đầu trong sandbox trả 0/30 do 30 lỗi `WinError 10013`; file
`heldout_agent_report_2026-08-19_invalid_network.json` được giữ làm dấu và bị
loại khỏi mọi phép đánh giá chất lượng.

Sau khi chủ dữ liệu xác nhận cho phép egress 30 câu synthetic, release run hợp
lệ hoàn tất với kết quả:

| Metric | Kết quả |
|---|---:|
| Agent pass | 0/30 (0,0%) |
| Infrastructure errors | 0 |
| Gold context found | 0/30 |
| Answer judge correct | 2/30 |
| Intent distribution | 17 pure_statutory / 11 hr_question / 2 out_of_scope_or_personal |
| Latency | p50 10.021ms / p95 59.662ms / max 127.350ms |

Không sửa code hay chạy lại held-out sau khi thấy kết quả. Hai nguyên nhân đo
được cần đưa vào known limitations: bộ 30 câu legacy gắn toàn bộ nhãn
`in_scope` trong khi contract v3.1 loại câu luật thuần túy (`pure_statutory`), và
toàn bộ `evidence_chunk_id` không còn khớp chunk được retrieval trả về. Script
agent held-out hiện cũng không lưu/chấm citation, nên không suy diễn Citation
Coverage từ report này.

## Known limitations

- Backend chỉ đồng bộ worker khi client poll endpoint trạng thái; chưa có poller
  chủ động khi không có client theo dõi.
- Upload được submit ngay sang Agent; nếu Backend chết giữa lúc commit DB và
  submit HTTP, job cần thao tác retry vận hành.
- Backend test còn cảnh báo khóa JWT test ngắn, FastAPI deprecation và thread
  cleanup của `aiosqlite`; không làm test fail nhưng nên dọn sau release.
- Release gate chưa đạt: Answer 6,7% và Recall theo gold chunk 0%; Citation chưa
  được script agent held-out đo. Retrieval held-out độc lập chưa chạy vì 20
  query đó cần xác nhận data egress riêng.
