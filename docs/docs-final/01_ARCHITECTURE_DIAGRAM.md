# Architecture Diagrams — P-153

Các sơ đồ dưới đây được đồng bộ với `develop@87a85aa`. Phần giải thích quyết định kiến trúc nằm tại [`ARCHITECTURE.md`](../../ARCHITECTURE.md).

## 1. System context

```mermaid
flowchart LR
    Employee[Employee] -->|Chat / own tickets| P153[P-153 Document Intelligence]
    Manager[Department Manager] -->|Review / publish department documents| P153
    Admin[Super Admin] -->|Access / audit / index / evaluation| P153
    P153 -->|Business data| PG[(Supabase PostgreSQL)]
    P153 -->|Retrieve / index| Chroma[(Chroma)]
    P153 -->|LLM / embedding / VLM / rerank| Model[OpenAI or FPT.AI-compatible gateway]
    P153 -->|Upload / read files| Storage[Cloudinary or public document URLs]
```

## 2. Container diagram

```mermaid
flowchart LR
    subgraph Browser
        FE[Next.js Frontend]
        DV[Document Viewer]
    end

    subgraph BackendContainer[FastAPI Backend]
        AUTH[Auth/RBAC]
        CHAT[Chat/Conversation/SSE]
        DOC[Documents/HITL]
        OPS[Ticket/Index/Eval/Admin]
    end

    subgraph AgentContainer[FastAPI Agent]
        API[Signed internal API]
        GRAPH[LangGraph]
        RET[Hybrid retrieval]
        WORKERS[Workers]
    end

    FE --> DV
    FE -->|JWT REST/SSE| AUTH
    FE --> CHAT
    FE --> DOC
    FE --> OPS
    AUTH --> PG[(PostgreSQL)]
    CHAT --> PG
    DOC --> PG
    OPS --> PG
    FE -->|upload trực tiếp| OBJ[Cloudinary]
    DOC -->|lưu URL / dọn asset| OBJ
    CHAT -->|service token + signature| API
    DOC -->|job submit/poll| API
    OPS -->|job submit/poll| API
    API --> GRAPH
    API --> WORKERS
    GRAPH --> RET
    RET --> CH[(Chroma)]
    GRAPH --> LLM[Model Gateway]
    WORKERS --> CH
```

## 3. Agent workflow

```mermaid
stateDiagram-v2
    [*] --> CondenseRoute
    CondenseRoute --> Boundary
    Boundary --> Direct: greeting
    Boundary --> Capability: capability_discovery
    Boundary --> Clarify: ambiguous
    Boundary --> OutOfScope: pure_statutory
    Boundary --> Escalate: personal / unsupported
    Boundary --> KnowledgeLookup: knowledge query
    KnowledgeLookup --> Finalize: structured fact hit
    KnowledgeLookup --> Retrieve: evidence required
    Retrieve --> Grade
    Grade --> AccessDenied: department denied
    Grade --> Rewrite: no evidence + retry
    Rewrite --> Retrieve
    Grade --> Generate: evidence / retry exhausted
    Generate --> Confidence
    Confidence --> Finalize: answerable + threshold met
    Confidence --> HallucinationCheck: low confidence
    Confidence --> Escalate: unanswerable
    HallucinationCheck --> Generate: fail + retry
    HallucinationCheck --> Escalate: fail/exhausted
    HallucinationCheck --> Finalize: pass
    Finalize --> [*]
    Direct --> [*]
    Capability --> [*]
    Clarify --> [*]
    OutOfScope --> [*]
    Escalate --> [*]
    AccessDenied --> [*]
```

## 4. Retrieval and authorization

```mermaid
flowchart TD
    Q[Standalone query] --> T[Temporal expansion]
    T --> D[Domain and collection resolution]
    D --> ACL[Build tenant/role/department/lifecycle filter]
    ACL --> Dense[Dense vector candidates]
    ACL --> BM25[BM25 candidates]
    Dense --> RRF[Reciprocal-rank fusion]
    BM25 --> RRF
    RRF --> Diversity[Source diversity for multi-source queries]
    Diversity --> Rerank[Rerank]
    Rerank --> Guard[Metadata authorization re-check]
    Guard --> Context[Grounded generation context]
```

## 5. Document lifecycle

```mermaid
flowchart LR
    Upload[Upload / public URL] --> Submission[PENDING submission]
    Submission --> Analysis[Document analysis job]
    Analysis --> Review[Human review]
    Review -->|reject| Rejected[REJECTED]
    Review -->|approve| Version[Create approved version]
    Version --> Disable[Disable previous version chunks]
    Disable --> Index[Index new chunks]
    Index --> Active[ACTIVE document]
    Active --> Archive[Soft archive]
    Archive --> Disabled[Excluded from retrieval]
```

## 6. Role boundary

```mermaid
flowchart TB
    E[EMPLOYEE] --> EC[Chat + own tickets + authorized knowledge]
    M[DEPARTMENT_MANAGER] --> MC[Employee capabilities + manage department tickets/documents]
    A[SUPER_ADMIN] --> AC[Cross-department admin + access + audit + evaluation]
    EC --> B[Backend authorization]
    MC --> B
    AC --> B
    B --> R[Retrieval authorization]
    R -->|allowed| K[Authorized chunks]
    R -->|denied/unknown| X[Fail closed]
```
