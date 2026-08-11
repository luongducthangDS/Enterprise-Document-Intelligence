# Architecture Diagram

> Bản đầy đủ (component, quyết định thiết kế, số liệu đo): [`../ARCHITECTURE.md`](../ARCHITECTURE.md) và [`rag-pipeline/PIPELINE.md`](rag-pipeline/PIPELINE.md).

## System Overview

```mermaid
graph TB
    User([User]) --> UI["Client app<br/>(chưa dựng trên nhánh này)"]
    UI -->|REST API| API["FastAPI Backend<br/>POST /api/v1/chat"]
    API --> Agent[LangGraph Agent]
    Agent --> LLM["LLM<br/>GLM-5.2 (FPT.AI Marketplace gateway)"]
    Agent --> Emb["Embedding<br/>multilingual-e5-large"]
    Agent --> Rerank["Reranker<br/>bge-reranker-v2-m3"]
    Agent --> VS["Vector Store<br/>Chroma Cloud"]
    API --> DB[(Supabase Postgres<br/>users/RBAC · conversations · tickets)]
```

## Agent Flow (LangGraph, 11 node)

```mermaid
graph LR
    START((Start)) --> Router{router}
    Router -->|greeting| Direct[direct] --> END((End))
    Router -->|ambiguous| Clarify[clarify] --> END
    Router -->|hr_question| Retrieve[retrieve]
    Retrieve --> Grade{grade}
    Grade -->|đủ context| Generate[generate]
    Grade -->|thiếu context| Rewrite[rewrite] --> Retrieve
    Generate --> Hallu[hallucination_check]
    Hallu --> Confidence{confidence}
    Confidence -->|đủ tin cậy| Finalize[finalize] --> END
    Confidence -->|thấp / out_of_scope / cần dữ liệu cá nhân| Escalate[escalate_ticket] --> END
```

## Data Ingestion Flow (offline)

```mermaid
graph LR
    Raw["data/raw/<br/>6 category HR"] --> Extract[extract + clean] --> Chunk[chunk] --> Embed["embed<br/>multilingual-e5-large"] --> Index[(Chroma Cloud)]
```

## Component Details

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Client app | Chưa dựng trên nhánh này (bản demo thử nghiệm ở nhánh khác) | Giao diện chat cho nhân viên |
| Backend | FastAPI | API server, endpoint `/api/v1/chat` |
| Agent | LangGraph (11 node) | Orchestration: router → retrieve → grade → generate → hallucination-check → confidence → finalize/escalate |
| LLM | GLM-5.2 qua FPT.AI Marketplace (OpenAI-compatible gateway) | Sinh câu trả lời, phân loại intent |
| Embedding | multilingual-e5-large qua FPT.AI Marketplace | Vector hoá chunk và câu hỏi (prefix `passage:`/`query:`) |
| Reranker | bge-reranker-v2-m3 qua FPT.AI Marketplace | Xếp hạng lại top-k kết quả retrieval, làm cơ sở tính confidence |
| Vector Store | Chroma Cloud (cosine distance) | Lưu trữ embedding chunk cho RAG |
| Database | Supabase (Postgres + Auth/RLS) | Users/RBAC, lịch sử hội thoại, ticket |
