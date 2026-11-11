# Rules

Xem thêm: [../GIT-FLOW.md](../GIT-FLOW.md), [TESTING.md](TESTING.md), đặc tả mục 8 (bảo mật).

## Bất biến
- ACL fail-closed: file có trong registry thì registry quyết định quyền, không dùng metadata trong Chroma. `eval_acl_e2e.py` (qua agent thật) phải 15/15 trước khi deploy thay đổi retrieval/agent.
- Hành động ghi (tạo case) chỉ qua `ChatService.confirm_ticket_proposal` sau khi người dùng xác nhận; cờ `ENABLE_CREATE_CASE` mặc định tắt.
- Thứ tự deploy khi có migration: chạy migration trên Supabase **trước** khi deploy backend có ORM mới, rồi mới bật cờ.
- Đổi embedding: chạy `scripts/reindex_collections.py` trước khi đặt `CHROMA_COLLECTION_SUFFIX`, nếu không retrieval trả rỗng trong im lặng.
- `qa_eval_set` là dev set; không báo số trên nó như held-out.
- Tool tính toán (ví dụ `calculate_annual_leave`) chỉ trả số khi search đã lấy được chính sách tương ứng.

## Quy ước
- Eval agent phải truyền danh tính (EXECUTIVE/ADMIN) vì identity là bắt buộc.
- Ngưỡng retrieval/rerank đo trên e5 + bge-reranker; đổi model thì phải đo lại.

## AI không bao giờ được
- Commit `.env`, `.env.example` có key thật, `*.zip`.
- Push (push kích hoạt deploy production) hoặc merge PR khi user chưa cho phép.
- Sửa env trên Render mà không ghi lại cách quay về.
