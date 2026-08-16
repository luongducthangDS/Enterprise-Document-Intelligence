# Knowledge Base Scope for Pitch

## Product Positioning

Sản phẩm nên được pitch là **HR Policy Copilot / HR Helpdesk Assistant** cho một khóa học, tập trung vào việc trả lời câu hỏi nhân sự lặp lại, tra cứu chính sách chung và escalate đúng bộ phận khi câu hỏi vượt phạm vi.

Không nên pitch như một **HR system đầy đủ** hoặc một assistant có khả năng trả lời tất cả vấn đề nhân sự của một công ty cụ thể.

Thông điệp chính:

> Knowledge base của hệ thống được giới hạn có chủ đích ở các chính sách HR phổ biến và văn bản pháp luật tham khảo. Với câu hỏi cần dữ liệu cá nhân, cần xác minh HR, hoặc có rủi ro pháp lý, agent không tự suy đoán mà tạo ticket/escalate đến đúng bộ phận HR.

## Pitch-Safe Naming

Để tránh rủi ro thương hiệu, trong slide/demo không nên nói "đây là chính sách của VinGroup/VinFast" hoặc gắn dataset với một công ty cụ thể.

Nên dùng cách gọi an toàn hơn:

- "tài liệu tham khảo từ một tập đoàn lớn tại Việt Nam"
- "internal policy reference document"
- "enterprise HR reference material"
- "sample corporate policy corpus"

Nếu cần nói về nguồn, chỉ nên nói:

> Một phần knowledge base gồm tài liệu tham khảo dạng corporate policy của một tập đoàn lớn tại Việt Nam; hệ thống không khẳng định đây là chính sách đang áp dụng của bất kỳ công ty cụ thể nào.

## What The Current Knowledge Base Contains

Bộ dữ liệu trong `data/` bao gồm các nhóm tài liệu chính:

- Chính sách nghỉ phép.
- Chính sách làm thêm giờ/OT.
- Chính sách làm việc từ xa/hybrid.
- Quy trình tuyển dụng.
- Quy trình onboarding.
- Quy trình offboarding/chấm dứt hợp đồng lao động.
- Chính sách đào tạo và phát triển.
- Chính sách bảo hiểm sức khỏe tự nguyện.
- Quy chế lương, thưởng, phụ cấp, công tác phí.
- Quy chế KPI/đánh giá hiệu suất.
- Quy trình kỷ luật lao động và khiếu nại.
- Chính sách bảo hiểm xã hội/y tế/thất nghiệp bắt buộc, an toàn vệ sinh lao động (soạn nội bộ, có căn cứ pháp luật).
- Cấu hình routing ticket sang các bộ phận HR như C&B, ER, TA, L&D, HRBP.

Văn bản pháp luật về lao động, BHXH, BHYT, thuế TNCN, lương tối thiểu **không nằm trong knowledge base agent truy vấn trực tiếp** — chỉ dùng offline để soạn ra các tài liệu chính sách nội bộ ở trên khi doanh nghiệp chưa cung cấp chính sách thật. Agent không bao giờ trích dẫn nguyên văn luật khi trả lời; nếu một câu hỏi chỉ có thể trả lời bằng luật mà chưa có chính sách nội bộ tương ứng, agent escalate thay vì tự suy diễn.

## Important Data Caveats

Đây là điểm cần nói rõ trong pitch để tránh phạm vi bị mơ hồ:

- Nhiều tài liệu nội bộ trong dataset là **synthetic/template**, không phải chính sách thật của một doanh nghiệp cụ thể.
- Một số tài liệu là template công khai, chỉ nên dùng để minh họa cấu trúc quy trình/chính sách.
- Các văn bản pháp luật là nguồn tham khảo tốt hơn, nhưng khi dùng trong production vẫn cần quy trình cập nhật và xác minh hiệu lực.
- Một số tài liệu có nguồn/tham chiếu từ một tập đoàn lớn tại Việt Nam nên được trình bày là **tài liệu tham khảo dạng corporate policy**, không gắn thành chính sách đang áp dụng cho một công ty cụ thể.
- Các tài liệu tham khảo này có thể là bản cũ hoặc không rõ thời hiệu, cần xác minh bản cập nhật trước khi dùng cho câu hỏi hiện tại.
- Knowledge base không chứa dữ liệu HRIS/payroll cá nhân, vì vậy không thể trả lời các câu hỏi về số dư phép, trạng thái đơn, bảng lương, thưởng hoặc bảo hiểm của một cá nhân cụ thể.

## In Scope

Hệ thống có thể xử lý tốt các nhóm câu hỏi sau trong demo/MVP:

| Capability | Mô tả |
|---|---|
| Policy Q&A | Trả lời câu hỏi chung về nghỉ phép, OT, WFH, onboarding, offboarding, tuyển dụng, đào tạo, bảo hiểm sức khỏe. |
| Legal reference | Tra cứu và tóm tắt các quy định pháp luật lao động/BHXH/BHYT/thuế ở mức tham khảo. |
| Procedure guidance | Hướng dẫn các bước đăng ký nghỉ phép, đăng ký OT, WFH, claim bảo hiểm, nghỉ việc, onboarding. |
| Role-based answers | Điều chỉnh cách trả lời cho employee, manager, HR admin nếu có context vai trò. |
| Source-aware answers | Đưa caveat khi nguồn là synthetic, template, public article, hoặc chính sách cũ cần xác minh. |
| Ticket routing | Phân loại câu hỏi và escalate sang C&B, ER, TA, L&D hoặc HRBP. |
| Low-confidence handling | Nếu không tìm thấy câu trả lời chắc chắn trong KB, agent nên thừa nhận giới hạn và tạo ticket. |
| MVP evaluation | Đo accuracy, refusal quality và routing accuracy trên bộ test nhỏ trước demo. |

## Agentic Behavior In MVP

Để tránh bị judge nhìn như "chatbot RAG + router", cần pitch rõ các hành vi agentic đang có trong MVP:

| Agentic capability | Cách thể hiện trong demo |
|---|---|
| Intent analysis | Agent tự phân loại greeting, HR question, ambiguous, personal/out-of-scope. |
| Retrieval planning | Agent chỉ retrieve khi câu hỏi đủ rõ và có thể trả lời bằng policy chung. |
| Source-grounded generation | Agent chỉ trả lời dựa trên đoạn trích, kèm citation và caveat nguồn. |
| Self-check | Agent có hallucination check/confidence check trước khi finalize. |
| Escalation decision | Agent quyết định khi nào không nên trả lời và cần tạo ticket draft. |
| Ticket routing | Agent chọn bộ phận xử lý phù hợp: C&B, ER, TA, L&D, HRBP. |
| Clarification | Agent hỏi lại khi câu hỏi mơ hồ thay vì đoán ý user. |

Nên nói thẳng giới hạn:

> In this MVP, the agent does not yet execute live HR transactions. Its agentic behavior is decision-making around retrieval, grounding, clarification, refusal, and ticket routing. Live ticket creation and status tracking are the next integration step.

Bản tiếng Việt:

> Trong MVP này, agent chưa thực hiện giao dịch HR trực tiếp trên HRIS/payroll. Tính agentic nằm ở việc tự quyết định retrieve hay hỏi lại, tự kiểm tra grounding/confidence, từ chối khi vượt phạm vi, và tạo ticket draft đến đúng bộ phận. Kết nối ticket system/HRIS thật là bước tích hợp tiếp theo.

## Out Of Scope

Hệ thống không nên tự trả lời các trường hợp sau:

| Out of scope | Lý do |
|---|---|
| Số dư phép của một nhân viên cụ thể | Cần dữ liệu HRIS cá nhân. |
| Trạng thái đơn nghỉ phép/OT/WFH/claim bảo hiểm | Cần kết nối workflow/system thật. |
| Lương, thưởng, khấu trừ, thuế TNCN cá nhân | Cần payroll và dữ liệu thu nhập cá nhân. |
| Kết quả phỏng vấn/offer của ứng viên cụ thể | Cần ATS hoặc dữ liệu tuyển dụng nội bộ. |
| Quyết định kỷ luật/chấm dứt hợp đồng cụ thể | Rủi ro pháp lý, cần HR/Legal xác minh. |
| Tư vấn pháp lý cuối cùng cho tranh chấp lao động | Agent chỉ nên cung cấp tham khảo và escalate. |
| Khẳng định chính sách đang áp dụng cho một công ty cụ thể | Dataset có nhiều synthetic/template, tài liệu tham khảo và tài liệu cũ. |
| Cập nhật pháp lý mới nhất nếu KB chưa được refresh | Cần quy trình update/verify nguồn pháp lý. |

## Recommended User Stories For Demo

### Employee

- Là nhân viên, tôi muốn hỏi mình được bao nhiêu ngày phép năm, để biết quyền nghỉ phép theo thâm niên và loại công việc.
- Là nhân viên, tôi muốn biết quy trình xin nghỉ phép trên HRIS, để nộp đơn đúng hạn.
- Là nhân viên, tôi muốn hỏi nghỉ cưới, nghỉ tang, nghỉ không lương có được hưởng lương không.
- Là nhân viên, tôi muốn biết làm OT vào ngày thường, cuối tuần, ngày lễ được tính như thế nào.
- Là nhân viên, tôi muốn biết mình có đủ điều kiện WFH/hybrid không.
- Là nhân viên, tôi muốn biết WFH đột xuất cần thông báo trước khi nào.
- Là nhân viên, tôi muốn biết gói bảo hiểm sức khỏe tự nguyện có áp dụng cho mình không.
- Là nhân viên, tôi muốn biết thủ tục claim bảo hiểm khi đã ứng tiền viện phí.
- Là nhân viên, tôi muốn biết nếu nghỉ việc thì phải báo trước bao lâu.
- Là nhân viên, tôi muốn biết sau khi nghỉ việc bao lâu được thanh toán các chế độ còn lại.
- Là nhân viên, tôi muốn biết nếu nghỉ sau khóa học chi phí cao thì có phải bồi hoàn không.

### Manager

- Là quản lý, tôi muốn biết quy trình phê duyệt OT, để đảm bảo nhân viên không vượt giờ theo quy định.
- Là quản lý, tôi muốn biết checklist onboarding 30-60-90 ngày, để hỗ trợ nhân viên mới.
- Là quản lý, tôi muốn biết khi nào có thể thu hồi quyền WFH của nhân viên.
- Là hiring manager, tôi muốn tạo yêu cầu tuyển dụng và biết luồng phê duyệt headcount.
- Là quản lý, tôi muốn biết vai trò của mình trong offboarding và bàn giao tài sản/công việc.

### HR / Admin

- Là HR, tôi muốn agent trả lời các câu hỏi chính sách lặp lại, để giảm tải cho HR helpdesk.
- Là HR, tôi muốn agent tự động phân loại ticket sang C&B, ER, TA, L&D hoặc HRBP.
- Là HR, tôi muốn agent escalate khi câu hỏi cần dữ liệu cá nhân hoặc có rủi ro pháp lý.
- Là HR admin, tôi muốn câu trả lời có source/caveat, để tránh nhầm lẫn giữa chính sách nội bộ, tài liệu tham khảo, template và synthetic data.
- Là HR admin, tôi muốn theo dõi các câu hỏi low-confidence, để biết cần bổ sung knowledge base nào.

## Escalation Rules

Agent nên escalate thay vì tự trả lời khi:

- Câu hỏi cần dữ liệu cá nhân: số dư phép, bảng lương, thuế, trạng thái đơn, trạng thái claim, offer cá nhân.
- Câu hỏi liên quan tranh chấp, khiếu nại, quấy rối, kỷ luật, chấm dứt hợp đồng.
- Câu hỏi có ảnh hưởng trực tiếp đến thu nhập đã nhận hoặc quyền lợi pháp lý.
- Câu hỏi nằm ngoài tài liệu hiện có.
- Câu hỏi có nguồn tài liệu cũ, synthetic/template, hoặc chưa rõ hiệu lực.
- User yêu cầu gặp người thật.

Routing gợi ý:

| Category | Department |
|---|---|
| Lương, thuế, OT, phụ cấp, BHXH/BHYT, chấm công | C&B |
| Nghỉ phép, số dư phép, trạng thái đơn | C&B |
| Khiếu nại, mâu thuẫn, kỷ luật, quấy rối, tranh chấp | ER |
| Tuyển dụng, phỏng vấn, offer, giới thiệu ứng viên | TA |
| Onboarding/offboarding, nghỉ việc, bàn giao | ER hoặc HRBP tùy tình huống |
| Đào tạo, cam kết bồi hoàn, lộ trình phát triển | L&D |
| Câu hỏi không khớp rõ | HRBP |

## Demo Boundary Statement

Có thể đưa nguyên văn này vào slide pitch:

> In this MVP, the HR AI Assistant focuses on policy Q&A and routing, not personal HR transactions. It answers common questions using a curated HR knowledge base, cites or caveats its source, and escalates to the right HR team when the request requires personal data, legal judgment, or system access.

Bản tiếng Việt:

> Trong MVP này, HR AI Assistant tập trung vào hỏi đáp chính sách và điều phối yêu cầu, không thay thế hệ thống HRIS/payroll. Agent trả lời các câu hỏi HR phổ biến dựa trên knowledge base đã curate, nêu rõ giới hạn của nguồn, và escalate đến đúng bộ phận khi câu hỏi cần dữ liệu cá nhân, cần đánh giá pháp lý, hoặc cần truy cập hệ thống nội bộ.

## MVP Evaluation

Eval không nên để ở roadmap. Nên có một bộ test nhỏ ngay trong MVP để chứng minh hệ thống đang được kiểm soát.

Bộ test để pitch có thể gồm 30-50 câu:

| Metric | Mục tiêu demo | Ví dụ test |
|---|---|---|
| Policy answer accuracy | Câu trả lời đúng theo nguồn và có citation | "OT Chủ nhật tính bao nhiêu phần trăm?" |
| Refusal quality | Từ chối/escalate đúng khi cần dữ liệu cá nhân | "Lương tháng này của tôi bị trừ bao nhiêu?" |
| Routing accuracy | Ticket draft đi đúng bộ phận | Lương/OT -> C&B, khiếu nại -> ER, đào tạo -> L&D |
| Clarification quality | Hỏi lại khi câu hỏi mơ hồ | "Khi nào tôi được nhận thưởng?" |
| Source caveat quality | Cảnh báo đúng khi nguồn là template/synthetic/reference | "Chính sách KPI như thế nào?" |

Thông điệp với judge:

> Because this is an enterprise HR use case, we evaluate not only answer correctness, but also refusal quality, escalation routing, and source caveat behavior.

## Suggested Pitch Framing

Nên nói sản phẩm giải quyết 3 vấn đề:

1. Giảm tải cho HR bằng cách tự động trả lời câu hỏi lặp lại.
2. Tăng tính nhất quán của câu trả lời vì dựa trên knowledge base có cấu trúc.
3. Kiểm soát rủi ro bằng cơ chế caveat và escalation.

Không nên nói sản phẩm:

- Thay thế HR.
- Trả lời mọi câu hỏi pháp lý/nhân sự.
- Có dữ liệu cá nhân thật.
- Là chính sách chính thức/đang áp dụng của một công ty cụ thể.

## Roadmap After MVP

Nếu muốn mở rộng sau pitch:

- Kết nối HRIS để xem số dư phép, trạng thái đơn, lịch sử chấm công.
- Kết nối payroll để giải thích bảng lương cá nhân có kiểm soát quyền truy cập.
- Thêm admin dashboard để quản lý nguồn tài liệu, version, ngày hiệu lực.
- Thêm approval workflow cho ticket và human-in-the-loop.
- Thêm cơ chế cập nhật văn bản pháp luật định kỳ.
