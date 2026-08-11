# HR Document Intelligence Agent — P-153

AI Agent trả lời câu hỏi của nhân viên về chính sách nhân sự — pháp luật lao động, BHXH/BHYT, thuế TNCN, và quy định nội bộ (nghỉ phép, lương thưởng, tuyển dụng, onboarding/offboarding) — dựa trên RAG (Retrieval-Augmented Generation), tự động tạo ticket chuyển phòng ban phù hợp khi không đủ tự tin trả lời hoặc câu hỏi cần dữ liệu cá nhân.

> Dự án học phần **VinUni AI20K Build Phase**, team **AI20K-Build-Phase-Cohort-3**.

## Vấn đề & phạm vi

Nhân viên thường không tra cứu được nhanh các quy định rải rác giữa văn bản pháp luật (Bộ luật Lao động, Nghị định 145/2020, Luật BHXH/BHYT, Luật thuế TNCN...) và quy định nội bộ công ty. Agent giải quyết bài toán này cho HR nói chung — **không gắn cứng vào một công ty cụ thể**: dữ liệu gồm văn bản pháp luật công khai + quy định nội bộ mẫu (VinFast/Vingroup) + template công khai (nội quy lao động, quy chế lương thưởng, quy trình chấm dứt HĐLĐ).

Khi agent không đủ tự tin, câu hỏi ngoài phạm vi, hoặc cần dữ liệu cá nhân (lương, số ngày phép còn lại...), agent tạo **ticket draft** để backend chuyển cho đúng phòng ban (Comp & Benefits, Employee Relations, Talent Acquisition, Learning & Development, hoặc HRBP fallback).

## Kiến trúc tóm tắt

```
Data ingestion (extract → clean → chunk → embed)  →  Chroma Cloud (vector store)
                                                              │
User query → FastAPI (/api/v1/chat) → LangGraph Agent ───────┘
             router → retrieve → grade → generate → hallucination-check → confidence → finalize / escalate
                                                              │
                                              Supabase (users/RBAC, chat history, ticket)
```

Chi tiết đầy đủ (từng node, quyết định thiết kế, kết quả đo eval): [`docs/rag-pipeline/PIPELINE.md`](docs/rag-pipeline/PIPELINE.md). Contract API của agent cho backend: [`docs/rag-pipeline/AGENT_API.md`](docs/rag-pipeline/AGENT_API.md).

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph (11 node: router/retrieve/grade/rewrite/generate/hallucination-check/confidence/escalate/finalize/...) |
| Backend | FastAPI + Uvicorn |
| LLM / Embedding / Rerank | FPT.AI Marketplace gateway (OpenAI-compatible) — `GLM-5.2` (chat), `multilingual-e5-large` (embedding), `bge-reranker-v2-m3` (rerank) — xem [`models_config.json`](models_config.json) |
| Vector Store | Chroma Cloud (cosine distance, prefix `passage:`/`query:`) |
| Database | Supabase (Postgres + Auth/RLS) — users/RBAC, chat history, ticket |
| Frontend | Chưa hoàn thiện trên nhánh này — xem mục "Trạng thái hiện tại" |
| Testing | pytest + pytest-asyncio |
| DevOps | Docker + GitHub Actions |

## ⚡ Quick Start

```bash
# 1. Setup môi trường
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Cấu hình
cp .env.example .env
# Điền: FPT_API_KEY, CHROMA_CLOUD_*, SUPABASE_* (xem .env.example để biết ý nghĩa từng biến)

# 3. Cài AI Logging Hooks (bắt buộc — nộp bài cần log prompt tự động)
bash scripts/setup_hooks.sh
# Windows PowerShell: powershell -ExecutionPolicy Bypass -File scripts/setup_hooks.ps1

# 4. Chạy server
make run            # = uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Lệnh thường dùng

```bash
make test            # pytest tests/ -v
make lint            # ruff check
make check           # lint + format + test + eval-check

make eval-retrieval  # đo retrieval (dense + rerank) trên split dev
make eval-router     # đo router (intent classification)
make eval-agent      # đo agent end-to-end (tốn ~300 LLM call, ~25 phút)
make eval-heldout    # CHỈ chạy 1 lần khi đã chốt config — không tune dựa trên kết quả này
```

## 📁 Cấu trúc dự án

```
├── src/
│   ├── agents/          # LangGraph agent (graph, state, nodes/, tools/)
│   ├── api/              # FastAPI routes (POST /api/v1/chat)
│   ├── ingestion/        # Pipeline extract → clean → chunk → embed → index
│   ├── retrieval/        # Retrieval + BM25 + rerank client
│   ├── models/           # Pydantic schemas (AgentAnswer, Citation, TicketDraft...)
│   ├── services/         # LLM/embedding client (FPT.AI gateway)
│   └── config.py, main.py
├── data/                 # gitignored — raw/processed/chunks/metadata/rejected theo 6 category HR
├── eval/                 # Bộ eval 3 tầng (router/retrieval/agent) + datasets + results
├── scripts/rag_pipeline/ # CLI cho ingestion + eval (collect_data, build_chunks, build_vector_db, ...)
├── supabase/migrations/  # Schema: users/RBAC, conversations, tickets
├── docs/
│   ├── rag-pipeline/     # PIPELINE.md, AGENT_API.md, folder_structure.md
│   ├── project/          # Brief, PRD (.docx), diagrams chung
│   └── guide/            # Technical Guidebook 10 chương (từ template gốc)
├── tests/                # pytest suite
├── presentation/         # Demo Day slides
├── JOURNAL.md, WORKLOG.md
└── docker-compose.yml, Dockerfile
```

## 📋 Trạng thái hiện tại (2026-08-07)

- ✅ Data ingestion + RAG agent (LangGraph) hoạt động end-to-end, pass rate 75.7%/140 câu eval, router accuracy 95.7%
- ✅ Bộ eval 3 tầng có thống kê (bootstrap CI, kappa liên-giám khảo), coverage đang mở rộng từ 40% → phủ đủ 29/29 tài liệu
- ⚠️ Latency p50 in-scope ~35s — chưa tối ưu cho demo, xem `docs/rag-pipeline/PIPELINE.md`
- ⚠️ 2 kiến trúc backend song song (`src/api/` dùng Supabase Auth/RLS, `backend/` trên nhánh `develop` dùng JWT tự chế) — chưa chốt 1 hướng
- ⚠️ Frontend chưa dựng trên nhánh này
- 📄 Chi tiết vấn đề đang mở: theo dõi nội bộ trong `docs/reports/` (không đưa lên GitHub, xem `.gitignore`)

Xem tiến độ chi tiết theo ngày ở [`WORKLOG.md`](WORKLOG.md) và theo tuần ở [`JOURNAL.md`](JOURNAL.md).

## 📊 AI Usage Logging

Prompt và tool-call của Claude Code/Cursor/Codex/Gemini CLI/Copilot được tự động log vào `.ai-log/session.jsonl` và submit lên grading server mỗi khi `git push` (yêu cầu đã chạy `scripts/setup_hooks.sh`). ChatGPT/web tools khác cần log thủ công:

```bash
bash scripts/_pyrun.sh scripts/log_manual.py --tool chatgpt --prompt "What you asked"
```

## 🔗 Liên kết

- 📖 Technical Guidebook (nguồn template): [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)
- 🏫 VinUni AI20K Build Phase — Cohort 3
