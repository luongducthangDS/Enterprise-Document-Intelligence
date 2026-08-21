# Đề xuất: siết ranh giới contract Backend ↔ Agent

> Người viết: phụ trách Agent
> Ngày: 12/08
> Mục đích: đề xuất cơ chế phát hiện lệch contract giữa các tầng, sau khi rà lại code và docs hiện có.

---

## 1. Tóm tắt

Mình rà lại toàn bộ contract giữa FE, BE và Agent. **Kết luận: contract của mình đã có và khá đầy đủ** — vấn đề không nằm ở chỗ thiếu tài liệu.

Vấn đề là: **contract đã chốt nhưng không có cơ chế nào phát hiện khi code trôi khỏi nó.** Hiện đã có ít nhất 3 chỗ lệch mà cả CI lẫn test đều không báo, trong đó 1 chỗ khiến FE có nhánh code không bao giờ chạy.

Đề xuất chính: **thêm một bộ golden fixture cho `AgentAnswer` mà cả test Backend lẫn test Agent cùng dùng.** Hiện hai bên mock riêng nên cả hai đều xanh trong khi thực tế có thể đã lệch nhau.

Mình nhận phần ranh giới BE ↔ Agent.

---

## 2. Những gì mình đã có sẵn (để không ai phải làm lại)

Ghi lại phần này vì dễ bị đề xuất trùng:

| Tài sản | Vị trí | Quy mô |
|---|---|---|
| Contract BE ↔ FE | `docs/project/API/apiBackend.md` | 1.053 dòng |
| Contract BE ↔ FE (bản trước) | `docs/project/API/APIdoc.md` | ~21 KB |
| Contract Agent | `docs/rag-pipeline/AGENT_API.md` | 148 dòng |
| Tổng quan tích hợp | `docs/project/integration/AGENT_BE_FE_INTEGRATION.md` | 84 dòng |
| Standard response schema | `backend/app/schemas/common.py` → `StandardResponse` | Đã khớp `frontend/lib/types.ts` |
| Agent request schema | `src/models/schemas.py` → `AgentQueryRequest` | Có ràng buộc min/max, history ≤ 16 turn |
| Agent answer schema | `backend/app/schemas/agent.py` → `AgentAnswerDTO` | Có `model_validator` enforce runtime |
| Error code BE↔Agent | `backend/app/services/ai_agent_client.py` | `AGENT_TIMEOUT`, `AGENT_UNAVAILABLE`, `AGENT_INVALID_RESPONSE`, `AGENT_SERVICE_ERROR` |
| Test | `backend/tests/test_agent_integration.py` (7) + `tests/test_api/test_agent_query.py` (5) | Đều pass |

Đáng chú ý: rule *"escalate=true thì bắt buộc có ticket_draft"* **không chỉ nằm trên giấy** — nó đã được enforce lúc runtime trong `backend/app/schemas/agent.py`:

```python
@model_validator(mode="after")
def validate_control_fields(self):
    if self.needs_clarification and not (self.clarifying_question or self.response).strip():
        raise ValueError("Clarification result must contain a question")
    if self.escalate and self.ticket_draft is None:
        raise ValueError("Escalated result must contain ticket_draft")
    return self
```

Đây là cách làm đúng và nên nhân rộng, không phải viết lại.

---

## 3. Ba chỗ đang lệch (có bằng chứng)

### 3.1. `RETRIEVING` — state được khai báo khắp nơi nhưng không tồn tại

**Được khai báo ở 5 chỗ:**

| Vị trí | Nội dung |
|---|---|
| `docs/project/API/apiBackend.md:94` | `QUEUED → RETRIEVING → GENERATING → COMPLETED / ...` |
| `docs/project/API/apiBackend.md:246` | Bảng: "RETRIEVING — Đang tìm trong tài liệu — Tiếp tục poll" |
| `docs/project/API/APIdoc.md:276, 790` | Tương tự |
| `backend/app/schemas/chat.py:58` | Comment liệt kê state hợp lệ |
| `frontend/lib/types.ts:62` | Union type có `"RETRIEVING"` |
| `frontend/components/ChatView.tsx:20` | Label hiển thị `"Đang tìm trong tài liệu HR..."` |

**Thực tế trong code:** `backend/app/services/chat_service.py` chỉ set 2 state trước khi kết thúc:
- dòng 112: `state="QUEUED"`
- dòng 157: `.values(state="GENERATING")` — chuyển thẳng từ QUEUED

**Không có dòng nào set `RETRIEVING`.**

**Hệ quả:** FE có một nhánh render không bao giờ chạy, và bất kỳ ai đọc docs để implement mới đều hiểu sai state machine.

**Cần chốt:** hoặc BE set thật (đúng như docs mô tả), hoặc xoá khỏi docs + FE types + ChatView. Mình nghiêng về **BE set thật**, vì trạng thái "đang tìm tài liệu" là thông tin có ích cho người dùng và agent đã phát event tương ứng rồi.

---

### 3.2. Contract chặt một chiều — Agent chặt, Backend lỏng

Agent định nghĩa bằng `Literal` (`src/models/schemas.py`):

```python
EscalateReason   = Literal["low_confidence", "out_of_scope", "personal_data_required",
                           "user_requested_human", "competitor_question"]
TargetDepartment = Literal["CB", "ER", "TA", "LD", "HRBP"]
```

Backend nhận bằng `str` (`backend/app/schemas/agent.py`):

```python
escalate_reason: str | None = None          # lỏng
target_department: str                       # lỏng
```

**Hệ quả:** nếu phía Agent thêm/đổi một giá trị `escalate_reason` hoặc `target_department`, Backend **không báo lỗi** — giá trị lạ trôi thẳng xuống DB rồi ra FE, và chỉ phát hiện khi có người nhìn thấy ticket sai phòng ban.

**Đề xuất:** đổi 2 field này bên BE sang `Literal` khớp với Agent. Sửa 2 dòng, chặn được cả một lớp lỗi âm thầm. `priority` bên BE đã làm đúng theo cách này rồi (`Literal["Low", "Medium", "High"]`) — chỉ cần áp dụng nhất quán.

---

### 3.3. Hai nửa test không dùng chung fixture — đây là lỗ hổng lớn nhất

**Hiện trạng:**
- `backend/tests/test_agent_integration.py` mock agent bằng `AgentAnswerDTO` **tự dựng trong `backend/tests/conftest.py:43-61`**.
- `tests/test_api/test_agent_query.py` test phía Agent bằng client riêng.

Hai bộ dữ liệu test **không có liên hệ nào với nhau**.

**Hệ quả:** Agent đổi shape output → test Agent vẫn xanh (nó test theo shape mới), test BE vẫn xanh (nó mock theo shape cũ). **CI xanh toàn tập trong khi tích hợp thật đã gãy.** Đây nhiều khả năng là nguyên nhân gốc của các lỗi tích hợp mà mình đang gặp.

**Đề xuất — việc chính của bản này:**

```
tests/fixtures/agent_answer_golden.json
├── answer_normal.json          # trả lời bình thường + citations
├── answer_clarification.json   # needs_clarification=true
├── answer_escalate.json        # escalate=true + ticket_draft
├── answer_insufficient.json    # answerable=false
└── error_timeout.json          # AGENT_TIMEOUT
```

- **Phía Agent**: test khẳng định output thật serialize ra khớp fixture.
- **Phía Backend**: test mock bằng **chính fixture đó**, không tự dựng DTO nữa.
- **Kết quả**: một bên đổi shape mà không cập nhật fixture → CI đỏ ngay, đúng chỗ, đúng người.

Đây là thứ duy nhất trong bản đề xuất này **tự động phát hiện drift**. Các mục còn lại là sửa lệch đang có; mục này ngăn lệch mới sinh ra.

---

## 4. Một điểm cần chốt trước, vì sửa sau là breaking

`src/api/routes.py` hiện nhận `user_id` và `department` từ Backend nhưng **không dùng**:

```python
async def query_agent(request: AgentQueryRequest, ...):
    """Internal Backend-to-Agent contract. Identity fields are trace context only."""
    history = [turn.model_dump() for turn in request.history]
    return await agent_answer(request.query, history=history)   # user_id/department không được truyền
```

Hiện tại đúng — agent chưa filter theo phòng ban. Nhưng khi bật retrieval filter theo role/department (đã nằm trong mục "Chưa hoàn thành" của `AGENT_BE_FE_INTEGRATION.md`), hành vi của cùng một endpoint sẽ đổi: **cùng câu hỏi, cùng payload, khác kết quả tuỳ người hỏi**.

**Đề xuất ghi rõ vào `AGENT_API.md` ngay bây giờ:**
- Hiện tại: `user_id` / `department` là **trace context**, agent không dùng để lọc dữ liệu.
- Khi bật ACL: đây là **breaking change về hành vi** (dù shape không đổi) → cần version endpoint hoặc feature flag, và BE phải đảm bảo `department` gửi sang là giá trị đã xác thực từ JWT, không phải do client tự khai.

Điểm cuối quan trọng về bảo mật: nếu `department` có thể bị client chỉnh, ACL sau này sẽ vô hiệu ngay từ đầu.

---

## 5. Đề xuất hành động

| # | Việc | Phía làm | Ước tính |
|---|---|---|---|
| 1 | Golden fixture `AgentAnswer` dùng chung 2 bộ test | **Agent (mình nhận)** + BE review | 0,5 ngày |
| 2 | Siết `escalate_reason`, `target_department` sang `Literal` bên BE | BE | 15 phút |
| 3 | Chốt `RETRIEVING`: BE set thật, hoặc xoá khỏi docs + FE | BE + FE | 0,5 ngày |
| 4 | Ghi rõ hành vi `user_id`/`department` vào `AGENT_API.md` | **Agent (mình nhận)** | 15 phút |
| 5 | Thêm bước CI chạy cả 2 bộ test contract trên cùng fixture | Ai đang giữ CI | 0,5 ngày |

**Không đề xuất trong phase này:** viết lại contract FE↔BE (đã có `apiBackend.md`), chốt lại rule escalate/clarification (đã có validator enforce). Ưu tiên làm cho phần đã có **được bảo vệ**, thay vì viết thêm tài liệu mới.

---

## 6. Cách mình sẽ làm việc từ giờ

Để phần Agent không bị block bởi tiến độ FE/BE, và ngược lại:

1. **Agent chỉ bám vào contract `AgentQueryRequest` / `AgentAnswerDTO`**, không phụ thuộc trạng thái FE/BE tại thời điểm đó.
2. **Test agent chạy độc lập** với fixture, không cần BE chạy thật.
3. **Khi có lỗi tích hợp, phân loại trước khi debug:**
   - request sai shape → phía gọi
   - response sai contract → phía Agent
   - response đúng contract nhưng map sai → adapter phía BE
   - contract chưa định nghĩa case đó → cả hai cùng chốt bổ sung

   Mục đích là tránh mọi lỗi đều bị gom thành "agent lỗi" hoặc "BE lỗi" mà không ai xác định được ranh giới.
4. **Đổi contract thì cập nhật fixture trước, code sau** — fixture đỏ là tín hiệu sớm, rẻ hơn nhiều so với phát hiện lúc demo.

---

## Phụ lục — cách xác minh các phát hiện trên

```bash
# 3.1 — RETRIEVING được khai báo ở đâu, và có ai set không
grep -rn "RETRIEVING" docs/ backend/ frontend/lib frontend/components
grep -n "state=\"" backend/app/services/chat_service.py

# 3.2 — so sánh độ chặt hai phía
grep -n "EscalateReason\|TargetDepartment" src/models/schemas.py
grep -n "escalate_reason\|target_department" backend/app/schemas/agent.py

# 3.3 — fixture mock của BE
sed -n '40,65p' backend/tests/conftest.py

# trạng thái test hiện tại
cd backend && python -m pytest tests/test_agent_integration.py -q
```
