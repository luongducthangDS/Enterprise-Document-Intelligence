# Architecture

Bản đầy đủ: [../ARCHITECTURE.md](../ARCHITECTURE.md), [architecture_diagram.md](architecture_diagram.md), đặc tả mục 5–9. File này chỉ tóm tắt và ghi phần thêm từ 11/2026.

## Stack
Agent: Python, LangGraph, Chroma (local + Chroma Cloud), BM25 + dense + RRF + rerank, LLM qua FPT AI Marketplace (GLM-5.2, DeepSeek-V4-Flash) hoặc Gemini OpenAI-compatible (`LLM_PROVIDER=gemini`), MCP server (`mcp` 2.x). Backend: FastAPI + PostgreSQL (Supabase, migration `supabase/` 0001–0014). Frontend: Next.js (pnpm). Deploy: Render (frontend static, backend, agent) + Supabase + Chroma Cloud.

## Thư mục chính
```
src/agents/            LangGraph graph, nodes/ (condense, routing, boundary, retrieve, grade, rewrite, generate, confidence, hallucination, finalize, react)
src/agents/llm.py      chọn model theo vai trò; _gemini_chat_model
src/mcp_server.py      MCP tool ask_documents (danh tính từ env MCP_*)
backend/               FastAPI: auth, chat (SSE), ticket proposal, demo mode
frontend/              Next.js, styles.css
supabase/              migration SQL
eval/                  datasets, scripts (eval_agent, eval_acl_e2e, eval_agent_trajectory, …), results
scripts/reindex_collections.py   chép collection cũ sang <tên>_gemini với embedding Gemini
tests/
```

## Luồng (chế độ react, 11/2026)
`câu hỏi + danh tính → condense/route → react: LLM gọi search_policies / lookup_structured_policy / calculate_annual_leave / escalate_to_human (≤ REACT_MAX_STEPS=4) → generate → confidence + hallucination guard → finalize (trích dẫn, ticket_proposal nếu ENABLE_CREATE_CASE)`. ACL áp ở retrieval: file có trong registry thì registry quyết định quyền, không tin metadata `RUNTIME_UPLOAD` trong Chroma.
