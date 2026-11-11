# Tasks

## Đã xong (11/2026)
- [x] Demo public cho nhà tuyển dụng trên Render (05/11)
- [x] Chế độ tool-calling `AGENT_MODE=react` + MCP server (`569b216`, đã push, chạy trên demo)
- [x] Vá rò rỉ ACL, SSE tiến trình tool (`b54771e`)
- [x] Trajectory eval, CREATE_CASE có người duyệt, tool tính phép năm (`5257273`)
- [x] Code chuyển sang Gemini + reindex collection riêng (`5d8b952`)
- [x] React: search trong cùng lượt chạy song song, cache query trùng, báo model khi search không có chunk mới (11/11, chưa đo live)

## Tiếp theo (lần lượt từ trên xuống)
- [ ] Có key LLM mới (FPT trả 401 từ 09/11) hoặc Gemini: `GEMINI_API_KEY` trong `.env` đang **rỗng** (11/11); kiểm tên model qua `/models`
- [ ] Chạy `scripts/reindex_collections.py`, rồi chạy lại eval_agent / eval_acl_e2e / eval_agent_trajectory (so redundant_searches/latency với số 09/11: 20 search thừa, p50 4,1 s), hiệu chỉnh ngưỡng retrieval/rerank cho Gemini
- [ ] Push 3 commit local (`b54771e`, `5257273`, `5d8b952`) khi user cho phép; trước đó chạy migration 0014 trên Supabase
- [ ] Thu hồi/đổi FPT key từng nằm trong `.env.example` (cả `.env` local và env Render)
- [ ] Sửa metadata Chroma của 33 chunk `13-QD-ABC` cho khớp registry
- [ ] Cập nhật baseline số chunk trong `tests/test_migration_parity.py`, `test_production_cutover_smoke.py` cho collection `_gemini` (4 test live fail 11/11)
- [ ] Held-out set mới (không còn câu active)
- [ ] Merge PR #1, chuyển các service Render sang `--branch main`
- [ ] Bỏ URL hardcode `DEMO_FRONTEND_ORIGIN` / `DEMO_AGENT_SERVICE_URL`, đặt bằng env qua Render API
