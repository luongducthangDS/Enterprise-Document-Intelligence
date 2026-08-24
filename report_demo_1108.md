# Báo Cáo Lỗi Demo Ngày 11/08

> Phạm vi kiểm tra: chạy local trên code đang trùng `origin/develop` tại commit `3ff9008`. Mục tiêu là ghi nhận vấn đề để feedback cho team, không sửa code sản phẩm.

## 1. Tóm Tắt Tình Trạng

Local hiện có thể chạy đủ 3 service:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- Agent: `http://127.0.0.1:8001`

Luồng API cơ bản đã chạy được:

- Login: thành công.
- Tạo conversation: Backend trả `201 Created`.
- Gửi câu hỏi HR: Backend nhận request, Agent xử lý và trả kết quả.
- Health check Backend/Agent: pass.

Tuy nhiên, demo chưa ổn định vì còn nhiều lỗi ảnh hưởng trực tiếp đến trải nghiệm người dùng, bảo mật API, chất lượng câu trả lời và khả năng build/test.

## 2. Lỗi P0 - Cần Xử Lý Trước Demo

### P0.1 - Màn chat kẹt ở `CREATING`

**Role chính:** Frontend  
**Role liên quan:** QA

**Hiện tượng**

- Sau khi đăng nhập và vào màn “Trợ lý AI HR”, phiên hội thoại hiển thị `CREATING`.
- Người dùng chờ lâu nhưng UI không chuyển sang `ACTIVE`.
- Ô nhập câu hỏi không dùng được vì điều kiện gửi đang phụ thuộc `conversationState === "ACTIVE"`.

**Bằng chứng kiểm tra**

Backend tạo conversation thành công:

```text
POST /api/v1/conversations - Status: 201 Created - Duration: khoảng 1.3s
```

Log cũng cho thấy API tạo conversation bị gọi 2 lần gần như cùng lúc.

**Nguyên nhân nghi ngờ**

Trong `frontend/components/ChatView.tsx`, code dùng `mounted.current`:

```ts
const mounted = useRef(true);

useEffect(() => () => {
  mounted.current = false;
}, []);
```

Trong React/Next dev mode, effect có thể cleanup rồi chạy lại. Sau cleanup, `mounted.current` bị set `false` nhưng không được set lại `true`. Khi API trả kết quả, code gặp:

```ts
if (!mounted.current) return;
```

nên bỏ qua `setConversationId()` và `setConversationState()`.

**Impact**

- Người dùng không thể bắt đầu chat.
- Demo nhìn như hệ thống bị treo dù Backend đã trả thành công.
- Có thể tạo dư conversation trong DB.

**Đề xuất**

- Reset `mounted.current = true` khi component mount.
- Thêm guard để không gọi tạo conversation 2 lần trong dev mode.
- Khi tạo conversation lỗi, hiển thị lỗi rõ và có nút retry.

**Acceptance Criteria**

- Vào màn chat, trạng thái chuyển từ `CREATING` sang `ACTIVE` sau khi API trả `201`.
- Một lần vào màn chat không tạo 2 conversation.
- Nếu API lỗi, UI hiển thị message có thể retry, không treo.

### P0.2 - Ticket API vẫn là placeholder và không kiểm tra auth

**Role chính:** Backend  
**Role liên quan:** Security, Frontend, QA

**Hiện tượng**

- `GET /api/v1/tickets` trả `200` ngay cả khi không gửi token.
- `GET /api/v1/tickets` cũng trả `200` với token sai.
- `POST /api/v1/tickets` trả placeholder, không tạo ticket thật qua public API.

**Bằng chứng kiểm tra**

```text
GET /api/v1/tickets
=> 200 {"message":"List tickets endpoint"}

GET /api/v1/tickets với Bearer invalid-token
=> 200 {"message":"List tickets endpoint"}

POST /api/v1/tickets
=> 200 {"message":"Create ticket endpoint"}
```

Code hiện tại trong `backend/app/api/v1/endpoints/tickets.py` chỉ trả message placeholder.

**Impact**

- Route ticket chưa có bảo vệ auth/role.
- Không thể demo workflow escalation/ticket thật.
- Frontend không thể nối màn “Ticket của tôi” một cách đúng contract.
- Rủi ro bảo mật vì endpoint nhạy cảm trả `200` không cần xác thực.

**Đề xuất**

- Thêm `get_current_user` cho ticket endpoints.
- Tách quyền employee và HR Admin.
- Implement tối thiểu:
  - employee xem ticket của mình;
  - HR Admin xem queue;
  - get ticket detail;
  - update status/resolve.
- Response theo chuẩn wrapper `{ success, data, error, meta }`.

**Acceptance Criteria**

- Không token hoặc token sai phải trả `401`.
- Employee chỉ thấy ticket của mình.
- HR Admin thấy queue ticket.
- FE có contract thật để nối màn Ticket.

### P0.3 - Backend test suite còn fail

**Role chính:** Backend  
**Role liên quan:** Agent/RAG, QA

**Kết quả test**

Chạy trong thư mục `backend`:

```text
py -3.11 -m pytest tests -q
=> 62 passed, 1 failed
```

Test fail:

```text
tests/test_agent_integration.py::test_agent_history_preserves_follow_up_context
```

**Nội dung lỗi**

Expected history:

```json
[
  {"role": "user", "content": "How many annual leave days do I receive?"},
  {"role": "assistant", "content": "Are you a full-time or probationary employee?"}
]
```

Actual history bị đảo thứ tự:

```json
[
  {"role": "assistant", "content": "Are you a full-time or probationary employee?"},
  {"role": "user", "content": "How many annual leave days do I receive?"}
]
```

**Impact**

- Follow-up/multi-turn chat có thể mất ngữ cảnh hoặc hiểu sai câu hỏi tiếp theo.
- Đây là rủi ro trực tiếp cho demo nếu stakeholder hỏi nối tiếp.

**Đề xuất**

- Sửa ordering history ổn định, không chỉ dựa vào timestamp nếu timestamp có thể trùng.
- Thêm secondary order key hoặc logic dựa trên `chat_request_id` và role sequence.

**Acceptance Criteria**

- Backend tests pass 100%.
- Follow-up question giữ đúng thứ tự user → assistant → user.

## 3. Lỗi P1 - Ảnh Hưởng Trải Nghiệm Demo

### P1.1 - Câu trả lời AI hiển thị Markdown thô và khó đọc

**Role chính:** Frontend  
**Role liên quan:** Backend/Agent contract

**Hiện tượng**

Câu trả lời hiển thị trực tiếp các ký tự Markdown:

```text
**12 ngày/năm**
**Tăng thêm theo thâm niên:**
```

Answer body dài, dính nhiều ý vào một khối lớn, khó scan.

**Impact**

- Người dùng có cảm giác UI lỗi hoặc AI trả lời kém chuyên nghiệp.
- Khó đọc nhanh trong demo.

**Đề xuất FE**

- Render tối thiểu bold, bullet/list, paragraph.
- Giữ câu trả lời chính ngắn gọn, dễ scan.
- Tách warning/citation ra khỏi body answer.

**Lưu ý trách nhiệm**

FE chỉ chịu trách nhiệm render. Việc nguồn nào đáng tin, nguồn nào là template/synthetic phải được xử lý ở RAG/Backend/Data.

### P1.2 - Latency hiển thị sai ngữ cảnh

**Role chính:** Frontend  
**Role liên quan:** Backend

**Hiện tượng**

UI có thể hiển thị latency kiểu:

```text
25.094 ms
```

Với người dùng Việt Nam, dấu chấm dễ bị hiểu là số thập phân, nhìn giống `25 ms` thay vì `25.094 ms` hoặc `25,1 giây`.

**Kết quả smoke test**

Một câu hỏi phổ biến:

```text
Nhân viên có bao nhiêu ngày phép năm?
```

Kết quả:

```text
final_state: COMPLETED
answer_status: ANSWERED
latency_ms: 31639
elapsed_s: khoảng 32.2 giây
```

**Đề xuất**

- Dưới 1000 ms: hiển thị `xxx ms`.
- Từ 1000 ms trở lên: hiển thị theo giây, ví dụ `31,6 giây`.

### P1.3 - Chất lượng nguồn RAG chưa sạch

**Role chính:** Agent/RAG, Data/Knowledge Owner  
**Role liên quan:** Backend, PM

**Hiện tượng**

Câu trả lời đang trộn nhiều loại nguồn:

- luật nhà nước;
- chính sách nội bộ;
- tài liệu mẫu/template;
- tài liệu synthetic/tham khảo.

Trong câu trả lời có đoạn thể hiện nguồn không phải chính sách công ty thật:

```text
nguồn tham khảo/template, không phải chính sách công ty thật
```

**Impact**

- Rủi ro người dùng hiểu nhầm thông tin là chính sách công ty chính thức.
- Rủi ro compliance, đặc biệt với chủ đề nhân sự/pháp lý.
- Demo dễ bị hỏi: “Đâu là policy chính thức của công ty?”

**Đề xuất**

- Data owner phân loại lại tài liệu:
  - policy nội bộ chính thức;
  - luật tham khảo;
  - template/synthetic;
  - rejected/expired.
- RAG chỉ dùng policy chính thức cho câu trả lời chính nếu câu hỏi hỏi về chính sách công ty.
- Luật nhà nước chỉ nên là nguồn tham chiếu phụ.
- Template/synthetic không nên xuất hiện trong answer chính.
- Backend/Agent contract nên trả metadata như `source_type`, `is_official`, `confidence`, `warnings`.

### P1.4 - Answer contract còn trộn answer và nguồn tham khảo

**Role chính:** Backend/Agent  
**Role liên quan:** Frontend

**Hiện tượng**

API đã có trường `citations`, nhưng body `answer` vẫn chứa danh sách nguồn dài. FE vì thế có thể hiển thị trùng:

- nguồn trong answer text;
- citation cards riêng.

**Impact**

- UI rối.
- Người dùng khó phân biệt câu trả lời chính và nguồn đối soát.
- FE phải tự xử lý/cắt chuỗi, không bền vững.

**Đề xuất**

- `answer`: chỉ chứa câu trả lời chính.
- `citations`: chứa danh sách nguồn.
- `warnings`: chứa cảnh báo như nguồn không chính thức, thiếu bằng chứng, dữ liệu tham khảo.
- Không nhét “Nguồn tham khảo” dài vào `answer`.

### P1.5 - Frontend production build fail ở local

**Role chính:** Frontend/DevOps  
**Role liên quan:** QA

**Kết quả kiểm tra**

```text
corepack pnpm build
```

Compile pass nhưng fail ở bước generate static pages:

```text
Generating static pages (0/4) ...
ELIFECYCLE Command failed with exit code 1.
Build error occurred
[Error: spawn UNKNOWN]
```

**Impact**

- Chưa đủ tự tin deploy production build.
- CI nếu thêm frontend build có thể đỏ.

**Đề xuất**

- FE/DevOps reproduce trên máy khác hoặc CI.
- Kiểm tra tương thích Next.js/Node/Windows process spawn.
- Thêm frontend build vào CI để bắt lỗi sớm.

## 4. Lỗi P2 - Local Dev / Vận Hành

### P2.1 - Next local dev cache dễ bị hỏng

**Role chính:** Frontend/DevOps

**Hiện tượng**

Frontend từng trả `500`, log báo thiếu file:

```text
frontend/.next/prerender-manifest.json
```

Sau khi đổi tên cache hỏng `.next` và để Next rebuild lại, Frontend chạy lại bình thường.

**Impact**

- Người test demo thấy app load lâu hoặc 500.
- Tốn thời gian debug local.

**Đề xuất**

- Thêm script:

```json
"clean": "rimraf .next",
"dev:clean": "pnpm clean && pnpm dev"
```

- Hoặc ghi hướng dẫn local: nếu Next 500 do cache, xóa `.next` rồi chạy lại.

### P2.2 - CORS local dễ lỗi khi dùng `127.0.0.1`

**Role chính:** DevOps/Backend  
**Role liên quan:** Frontend

**Hiện tượng**

Nếu Frontend mở bằng `http://127.0.0.1:3000` nhưng Backend chỉ allow `http://localhost:3000`, browser bị CORS và UI báo:

```text
Không thể kết nối tới Backend.
```

**Đề xuất**

Trong local env nên allow cả:

```env
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### P2.3 - Backend log lỗi Unicode trên Windows

**Role chính:** Backend/DevOps

**Hiện tượng**

Backend log có lỗi:

```text
UnicodeEncodeError: 'charmap' codec can't encode character
```

Xảy ra khi SQLAlchemy/logging ghi tiếng Việt ra stream Windows `cp1252`.

**Impact**

- Log bị nhiễu, khó debug.
- Có thể làm team tưởng app lỗi nghiệp vụ dù request vẫn xử lý được.

**Đề xuất**

- Set `PYTHONIOENCODING=utf-8` khi chạy local.
- Cấu hình logging file/stream dùng UTF-8.
- Giảm SQL echo verbose ở môi trường demo nếu không cần.

## 5. Kết Quả Check Đã Chạy

### Pass

```text
Frontend /               => 200 OK
Backend /health          => 200 OK
Agent /health            => 200 OK
corepack pnpm lint       => PASS
corepack pnpm typecheck  => PASS
py -3.11 -m ruff check src/ tests/ => PASS
```

### Fail / Có vấn đề

```text
py -3.11 -m pytest tests -q trong backend
=> 62 passed, 1 failed
```

```text
corepack pnpm build trong frontend
=> compile pass, fail ở static generation với spawn UNKNOWN
```

```text
GET /api/v1/tickets không token
=> 200 placeholder
```

```text
GET /api/v1/tickets với invalid token
=> 200 placeholder
```

## 6. Gợi Ý Ưu Tiên Cho Team

### FE

- Sửa kẹt `CREATING`.
- Chặn tạo trùng conversation trong dev mode.
- Render Markdown/list/paragraph cho answer.
- Format latency theo giây khi quá 1000 ms.
- Tách answer, warning và citations rõ trong UI.
- Reproduce và fix `pnpm build` fail.

### Backend

- Implement Ticket API thật và bắt buộc auth/role.
- Sửa test history ordering.
- Chuẩn hóa response Ticket theo wrapper chung.
- Cấu hình logging UTF-8 cho local/demo.

### Agent/RAG/Data

- Lọc template/synthetic khỏi câu trả lời chính.
- Tách rõ official policy, luật tham khảo, template, rejected/expired.
- Không nhét danh sách nguồn dài vào answer text nếu API đã có `citations`.
- Giảm latency cho câu hỏi phổ biến hoặc chuẩn bị demo-safe fallback.

### QA/DevOps

- Thêm smoke E2E: login → tạo conversation → hỏi → poll → mở citation → ticket.
- Thêm frontend `lint/typecheck/build` vào CI.
- Document local setup: CORS, UTF-8 logging, clean `.next`.
- Gate PR vào `develop`, không chỉ `main`.

## 7. Kết Luận

Demo hiện có thể chạy được luồng chat cơ bản, nhưng chưa nên xem là ổn định. Các blocker lớn nhất là:

1. Chat UI có thể kẹt `CREATING`.
2. Ticket API chưa thật và chưa có auth.
3. Backend test còn fail ở multi-turn history.
4. Câu trả lời RAG còn lẫn nguồn template/synthetic và hiển thị chưa sạch.
5. Frontend production build còn fail ở local.

Nếu chỉ còn ít thời gian trước demo, nên ưu tiên: sửa `CREATING`, khóa/implement Ticket API, làm backend test xanh, và chuẩn hóa hiển thị answer/citation.
