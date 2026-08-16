# AI Safety & Production Guardrails — Thuật ngữ & Đối chiếu P-153

> Tài liệu này gồm 2 phần: (1) glossary thuật ngữ guardrail cho AI Agent production (không riêng dự án này), (2) đối chiếu **P-153 hiện đang có gì / thiếu gì** theo từng thuật ngữ. Cập nhật khi kiến trúc agent đổi (đặc biệt nếu thêm tool-calling thật) — xem [`PIPELINE.md`](PIPELINE.md) mục 3/6 để biết kiến trúc hiện tại.

---

## 0. Điểm mấu chốt cần biết trước khi đọc phần đối chiếu

**P-153 chưa có tool-calling tự do.** `LangGraph` (`src/agents/graph.py`) là 1 chuỗi node **cố định** do dev viết sẵn — LLM chỉ quyết định *nội dung câu trả lời* và *phân loại intent*, không tự chọn "gọi hàm nào tiếp theo", không có MCP/function-calling framework, không có tool registry. Vì vậy phần lớn thuật ngữ về Tool Misuse/Allowlist/Tool Poisoning/MCP bên dưới ở trạng thái **N/A** — không phải vì đã được phòng thủ, mà vì kiến trúc chưa tới mức có bề mặt tấn công đó. Nếu sau này roadmap thêm khả năng agent tự gọi hàm (tự ghi ticket vào Supabase, tự tra dữ liệu cá nhân qua `access_level`...), toàn bộ nhóm guardrail này cần xây **từ đầu**, không có gì tái dùng được từ hiện trạng.

---

## 1. Glossary

| Thuật ngữ | Hiểu đơn giản |
|---|---|
| **AI Guardrails** | Hàng rào kiểm soát AI được phép làm gì/không — có thể là code, rule, policy, validator, authorization, model classifier, human approval, logging. **Không phải** 1 model AI cụ thể. |
| **Prompt Injection** | Dữ liệu đầu vào (user message, document, tool output...) chứa chỉ dẫn nhằm thao túng LLM làm trái mục đích ban đầu. |
| **Untrusted Data** | Dữ liệu không nên mặc định tin tưởng — user input, website, email, PDF, RAG document, API/tool response. RAG document **cũng không mặc nhiên trusted**, kể cả khi đã qua ingestion nội bộ. |
| **Tool** | Hàm/API mà Agent có thể gọi (search DB, gửi email, xoá file...). |
| **Tool Misuse** | Agent dùng tool sai mục đích hoặc vượt quyền hạn được cấp. |
| **Authorization** | Kiểm tra 1 chủ thể (user/agent) được phép làm gì — quyết định nằm ở **code**, không phải ở lời hứa trong prompt. |
| **Allowlist** | Danh sách tool/hành động được phép — tư duy "chỉ cho phép N thứ này" tốt hơn "cấm các thứ nguy hiểm" (không liệt kê hết được). |
| **Schema Validation** | Kiểm tra request/payload đúng cấu trúc kiểu dữ liệu — **không đồng nghĩa** hành động đó được phép (đó là việc của Authorization). |
| **Least Privilege** | Chỉ cấp cho AI quyền tối thiểu cần để hoàn thành nhiệm vụ, không cấp quyền "cho chắc". |
| **Output Validation** | Kiểm tra cả **output** của LLM, không chỉ input — vd phát hiện PII bị lộ trong câu trả lời. |
| **PII** (Personally Identifiable Information) | Thông tin định danh cá nhân: họ tên, SĐT, email, địa chỉ, CCCD, thông tin tài chính... |
| **Hallucination** | AI tạo thông tin sai nhưng trình bày như đúng — giảm rủi ro bằng Retrieval + Citation + Evaluator + Output validation. |
| **Human-in-the-Loop (HITL)** | Hành động rủi ro cao không để AI tự quyết định cuối — cần người phê duyệt. |
| **Defense in Depth** | Không tin 1 lớp bảo vệ là đủ — nhiều lớp độc lập, lớp này bị bypass thì lớp khác vẫn chặn được. |
| **MCP** (Model Context Protocol) | Chuẩn kết nối Agent với tool/nguồn dữ liệu bên ngoài (DB, GitHub, file system...). |
| **Tool Supply Chain** | Toàn bộ chuỗi cung ứng tool mà Agent tin tưởng: Tool Registry → MCP Server → Tool → External API — mỗi mắt xích đều có thể bị compromise, không chỉ Agent. |
| **Tool Poisoning** | Tool description/metadata (không phải chỉ payload) bị cài chỉ dẫn độc hại — Agent đọc description và tin theo. |
| **MCP Server Compromise** | MCP server bị kẻ xấu kiểm soát → Agent dùng tool tưởng an toàn nhưng đã bị thay đổi hành vi. |
| **AI-based Detection** | Dùng 1 LLM khác để kiểm tra output/input của LLM chính (vd injection detector, hallucination evaluator) — **không nên là lớp bảo vệ duy nhất** vì evaluator cũng có thể sai/bị đánh lừa. |
| **Deterministic Enforcement** | Cùng input → cùng quyết định theo rule cố định trong code (vd `if tool not in ALLOWED: reject()`) — không hỏi ý kiến LLM. Đây mới là security enforcement thật. |
| **Audit & Monitoring** | Ghi log + giám sát mọi quyết định/hành động của agent để truy vết sau này (compliance, điều tra sự cố). |

---

## 2. Kiến trúc guardrail tham chiếu (mô hình tổng quát, không riêng P-153)

```
                     USER
                       │
                       ▼
              ┌─────────────────┐
              │ Input Guardrail │  validation / injection detection / PII
              └────────┬────────┘
                       ▼
               ┌──────────────┐
               │  AGENT / LLM │
               └──────┬───────┘
                       │ tool request
                       ▼
            ┌───────────────────┐
            │  Tool Guardrail   │  allowlist / schema validation /
            │                   │  authorization / least privilege
            └─────────┬─────────┘
                       ▼
                     TOOL → API / DB
                       ▼
            ┌───────────────────┐
            │  Output Guardrail │  PII / hallucination / policy
            └─────────┬─────────┘
                       ▼
                     USER

   (song song toàn bộ chuỗi: Audit · Logging · Monitoring · Human approval)
```

---

## 3. Đối chiếu P-153 — đã có gì, thiếu gì

| Thuật ngữ | Trạng thái | Bằng chứng cụ thể |
|---|---|---|
| AI Guardrails (nhiều lớp) | ✅ Có | `router → grade → generate → hallucination_check → confidence → escalate` (`src/agents/graph.py`) — 6 lớp riêng biệt |
| System prompt không đủ, cần code | ✅ Đúng tinh thần | `confidence_node` (`src/agents/nodes/escalation.py`) **thuần code, không gọi LLM**; `escalate_node` tra versioned config `src/agents/resources/ticket_routing_rules.json`, không hỏi LLM "có nên escalate không" |
| Prompt Injection (qua hội thoại) | ✅ Có cả 2 lớp: behavioral + kỹ thuật | User query được detect để audit; RAG chunks và history turn cũ được `strip_injection()` trước khi vào prompt. Audit chỉ ghi số lượng phát hiện, không ghi nội dung match thô. |
| Untrusted data (RAG document) | ✅ Có lớp kỹ thuật, đã test | `_build_context_block()` chạy `strip_injection()` trên TEXT của từng chunk trước khi đưa vào prompt — câu chứa chỉ dẫn injection bị CẮT BỎ hẳn (thay bằng `REDACTED_INJECTION_MARKER`), không chỉ dặn LLM "đừng nghe theo". Test: `tests/test_agents/test_guardrails.py`, `tests/test_agents/test_generation.py::test_strips_injection_embedded_in_chunk_text`. Toggle qua `settings.guardrail_injection_enabled` |
| Tool Misuse / Tool Authorization / Allowlist | N/A | Không có tool-calling nào để lạm dụng (xem mục 0) |
| Schema Validation | ✅ Có (ở lớp API, không phải tool) | `ChatRequest`/`AgentAnswer`/`Citation`/`TicketDraft` (`src/models/schemas.py`) đều Pydantic `BaseModel`, tự reject payload sai kiểu |
| Least Privilege | ✅ Có, nhưng "by design" hơn là chủ đích | Agent **không có quyền ghi Supabase** (`src/agents/service.py`, `docs/rag-pipeline/AGENT_API.md`: "Agent không tự ghi Supabase... ngoài phạm vi agent") — chưa từng được cấp quyền đó, không phải bị chặn bởi 1 cơ chế permission |
| Output Validation (PII) | ✅ Có | Agent service che email/SĐT VN/CCCD trong mọi response và citation metadata, kể cả direct/clarify/escalate. Backend che lại citation metadata/excerpt trước khi trả FE để bảo vệ dữ liệu cũ và dữ liệu không đi qua Agent adapter. |
| PII detector | ✅ Có, mức MVP | `src/agents/guardrails.py::redact_pii` — 3 pattern (email/phone/cccd), regex thuần, chưa phải NER đầy đủ (ghi rõ ceiling bằng `# ponytail:` trong code, nâng cấp khi đo được false positive/negative đáng kể). Test: `tests/test_agents/test_guardrails.py::TestRedactPii` |
| Hallucination | ✅ Điểm mạnh nhất | Sentinel `[KHÔNG_ĐỦ_THÔNG_TIN]` + `hallucination_check_node` (LLM khác kiểm tra) + bắt buộc trích `[Nguồn N]` + `is_official_policy`/`source_type` caveat trong mọi câu trả lời (`src/agents/nodes/generation.py`) |
| Human-in-the-Loop | ⚠️ Có cho nhánh escalate, không phải cho "hành động rủi ro cao" | `escalate_node` tạo `ticket_draft`, **backend/HR admin xử lý thật** — không phải HITL chặn hành động nguy hiểm (agent không có hành động nguy hiểm nào để chặn) |
| Defense in Depth | ✅ Có, khá rõ | 6 lớp ở dòng đầu bảng, mỗi lớp dùng tín hiệu khác nhau (rerank score/distance, LLM judge PASS/FAIL, threshold code) |
| Tool Supply Chain / MCP / Tool Poisoning / MCP Server Compromise | N/A | Không dùng MCP, không có tool registry |
| AI-based Detection (LLM kiểm tra LLM) | ✅ Có, đúng cách khuyến nghị | `hallucination_check_node` là LLM #2 — nhưng **không phải lớp cuối cùng**: `confidence_node` (code thuần) mới là gate cuối quyết định escalate, đúng khuyến nghị "không để AI-based detection làm security boundary duy nhất" |
| Deterministic Enforcement | ✅ Điểm mạnh thứ 2 | `confidence_node`, `grade_node`, mọi hàm `route_after_*` (`src/agents/graph.py`) đều là hàm Python thuần đọc `AgentState`, LLM không tự quyết "có nên tiếp tục không" |
| Ranh giới quyền hạn (RBAC) | ⚠️ Đúng tinh thần nhưng chưa enforce | `Profile.access_level` (`self_only`/`team_scope`/`org_wide`, `src/models/schemas.py`) đã **định nghĩa trong schema**, nhưng **không có code nào trong `src/agents/`/`src/api/` đọc/enforce field này** — RBAC mới ở mức thiết kế, chưa nối (khớp `PIPELINE.md` mục 6.5: backend/persistence chưa nối) |
| Audit & Monitoring | ✅ Có, mức MVP | `src/agents/service.py::_log_audit()` in 1 dòng JSON/request (`intent`, `confidence_score`, `escalate`, `escalate_reason`, `hallucination_passed`, `guardrail_injection_detected`, `guardrail_pii_redacted`, `citation_count`) ra stdout — đọc được qua log aggregator của hạ tầng deploy (Render/Docker) mà không cần thêm hệ thống mới. Cố tình KHÔNG log `query` thô để tránh audit trail tự thành nơi rò rỉ PII. Chưa phải audit trail có structured storage/query được (vd bảng riêng trong Supabase) — nâng cấp khi cần truy vết dài hạn/compliance thật |

---

## 4. Kết luận

Nếu chỉ nhớ 5 ý:

1. **"Prompt không phải security boundary"** — đúng ở tầng retrieval/escalate (code quyết định, không hỏi LLM). Tầng input/context giờ có **2 lớp độc lập**: behavioral (system prompt dặn model bỏ qua chỉ dẫn lạ trong `[Nguồn N]`) VÀ kỹ thuật (`strip_injection()` cắt hẳn câu nghi injection khỏi text RAG chunk trước khi model kịp đọc — không phụ thuộc model có "nghe lời" hay không). Đây chính là defense-in-depth đúng nghĩa: lớp kỹ thuật vẫn chặn được kể cả nếu lớp behavioral bị bypass.
2. **"LLM không tự quyết định quyền hạn của chính nó"** — đã đúng, nhờ kiến trúc graph cố định (không tool-calling tự do).
3. **"Tool call phải kiểm soát bằng code"** — N/A vì chưa có tool call nào — vừa là điểm an toàn (bề mặt tấn công nhỏ) vừa là điểm cần lưu ý (chưa có nền tảng guardrail nào sẵn sàng nếu sau này thêm tool thật).
4. **"Tool và MCP cũng là attack surface"** — không áp dụng ở giai đoạn hiện tại.
5. **"Nhiều lớp guardrail thay vì 1 lớp"** — dự án có 6 lớp luồng chính + 3 lớp guardrail kỹ thuật bổ sung (input injection detect, context injection strip, output PII redact — `src/agents/guardrails.py`) + audit log MVP (`service.py::_log_audit`). Khoảng trống còn lại: guardrail mới là regex/pattern-based (chưa phải NER/classifier), và audit log mới ở dạng stdout (chưa có structured storage để truy vết dài hạn).

**Tóm lại**: P-153 đang ở giai đoạn "RAG agent an toàn" (kiến trúc graph cố định + nhiều lớp threshold code-based + hallucination-check + guardrail kỹ thuật độc lập với model), chưa ở giai đoạn "Agentic system với tool-calling" mà phần lớn thuật ngữ ở mục 1 nhắm tới. Khi roadmap thêm tool thật (tự động ghi ticket vào Supabase, tự tra dữ liệu cá nhân qua `access_level`...), cần quay lại bảng mục 3 và xây các dòng N/A từ đầu.

---

## Tài liệu liên quan

- [`PIPELINE.md`](PIPELINE.md) mục 3/3.6 — kiến trúc agent hiện tại (graph cố định, `condense_node`/`history`).
- [`PIPELINE.md`](PIPELINE.md) mục 4.8 — luồng Guardrail eval (multi-turn pilot), nơi đo thực nghiệm hành vi `prompt_injection`/`source_authority_conflict`.
- [`../../eval/GUARDRAIL_EVAL_SPEC.md`](../../eval/GUARDRAIL_EVAL_SPEC.md) — đặc tả cách đo guardrail hành vi qua hội thoại.
- [`AGENT_API.md`](AGENT_API.md) — contract API, ghi rõ agent không tự ghi Supabase.
