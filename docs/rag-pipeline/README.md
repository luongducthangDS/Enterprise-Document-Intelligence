# docs/rag-pipeline/

> Tài liệu kỹ thuật cho luồng Data Ingestion + RAG Agent (data → chunk → embed → retrieve →
> generate). Script tương ứng nằm ở [`scripts/rag_pipeline/`](../../scripts/rag_pipeline/).

| File | Nội dung |
|---|---|
| [`PIPELINE.md`](PIPELINE.md) | Kiến trúc chi tiết toàn bộ hành trình: thu thập & quản trị dữ liệu thô, Data Ingestion Pipeline, Agentic RAG Pipeline, Evaluation Pipeline — cơ chế hoạt động, cấu trúc dữ liệu, quyết định thiết kế, kết quả đo được, sơ đồ luồng đầy đủ. |
| [`AGENT_API.md`](AGENT_API.md) | Contract API của agent cho backend: điểm vào duy nhất `src/agents/service.py::answer()`, schema `AgentAnswer`. |
| [`folder_structure.md`](folder_structure.md) | Cấu trúc thư mục cho pipeline ingestion (`data/`, `src/ingestion/`, `scripts/`) và vị trí trong project. |

`docs/architecture_diagram.md` (kiến trúc tổng hệ thống, path cố định theo yêu cầu BTC) và
`docs/project/` (brief, PRD, diagram chung của cả nhóm) không thuộc phần này, vẫn ở `docs/` gốc.
