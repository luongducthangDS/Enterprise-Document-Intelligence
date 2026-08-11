# Architecture Diagram

Code on `develop` is the source of truth. Product traffic uses REST polling; streaming transport remains future scope.

## System overview

```mermaid
flowchart LR
    USER["Employee / HR Admin"] --> FE["Next.js frontend"]
    FE -->|"REST + JWT + polling"| BE["FastAPI backend"]
    BE --> DB[("PostgreSQL")]
    BE -->|"Internal REST + service token\nquery + optional history"| AGENT["FastAPI Agent service\nLangGraph"]
    AGENT --> CHROMA[("Chroma Cloud")]
    AGENT --> FPT["FPT.AI\nLLM + embedding + rerank"]
```

## Responsibilities

| Component | Current responsibility |
|---|---|
| Next.js FE | Login, chat, polling, clarification, retry, citation viewer and admin screens |
| FastAPI BE | JWT/RBAC, conversations, recent history, background processing, persistence, citation access and ticket creation |
| Agent service | Stateless condense, intent routing, RAG, guardrails, generation, confidence, clarification and escalation draft |
| PostgreSQL | Users, conversations, messages, chat requests, tickets and document metadata |
| Chroma Cloud | RAG chunks and embeddings |

## Agent flow

```mermaid
flowchart LR
    START((Start)) --> CONDENSE["condense\nwhen history exists"] --> ROUTER{router}
    ROUTER -->|greeting| DIRECT[direct] --> SAFE["PII-safe AgentAnswer"]
    ROUTER -->|ambiguous| CLARIFY[clarify] --> SAFE
    ROUTER -->|out of scope / personal| ESC[escalate_ticket] --> SAFE
    ROUTER -->|HR question| RETRIEVE[retrieve] --> GRADE{grade}
    GRADE -->|no evidence| REWRITE[rewrite] --> RETRIEVE
    GRADE -->|evidence / retry exhausted| GENERATE[generate]
    GENERATE --> CHECK{answerable?}
    CHECK -->|yes| HALLUC[hallucination_check] --> CONF[confidence]
    CHECK -->|no| CONF
    CONF -->|accepted| FINAL[finalize] --> SAFE
    CONF -->|low| ESC
```

Detailed current diagrams are in [`project/diagrams`](project/diagrams), and the Agent-BE-FE contract is in [`project/integration/AGENT_BE_FE_INTEGRATION.md`](project/integration/AGENT_BE_FE_INTEGRATION.md).
