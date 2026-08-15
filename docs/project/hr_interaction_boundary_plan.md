# HR Interaction Boundary Plan

## Phạm vi

Tài liệu này sửa cách tiếp cận trước khi thiết kế database cho HR Assistant của V-Nova. Mục tiêu không phải là số hóa mọi HR service, mà là xác định ranh giới tương tác giữa nhân viên, quản lý trực tiếp và các bộ phận HR trong môi trường doanh nghiệp thực tế.

Chưa thực hiện các việc sau: chưa code, chưa sửa database, chưa sinh policy, chưa re-embed, chưa mutate Chroma hoặc Supabase.

## Nguyên tắc thiết kế

- Không hỏi trước "có tự động hóa được không". Hỏi trước: trong doanh nghiệp bình thường, nhân viên sẽ làm gì đầu tiên, nói chuyện với ai, ai có quyền quyết định, và assistant đứng ở đâu để giảm tải mà không phá quy trình con người.
- Assistant không thay thế quản lý trực tiếp, HRBP, Employee Relations, C&B, Finance hoặc Legal ở các tình huống cần phán đoán, thương lượng, điều tra, quyết định quyền lợi cá nhân hoặc xử lý xung đột.
- Self-service chỉ phù hợp với thông tin lặp lại, quy trình rõ, biểu mẫu rõ, dữ liệu ít nhạy cảm và không cần quyết định cá nhân.
- Tình huống nhạy cảm phải thu thập tối thiểu, tránh biến chat thành nơi lấy lời khai chi tiết, rồi handoff đúng người.

## Cơ sở tham khảo

- CIPD nhấn mạnh line manager chịu trách nhiệm vận hành hằng ngày và triển khai chính sách con người trong đội: https://www.cipd.org/en/knowledge/factsheets/line-managers-factsheet/
- SHRM mô tả HR service delivery theo hướng self-service cho câu hỏi cơ bản và escalated support cho tình huống phức tạp, nhạy cảm hoặc liên quan compliance: https://www.shrm.org/topics-tools/news/technology/how-to-choose-hr-service-management-systems
- SHRM nhấn mạnh case management cần audit trail, escalation và bảo mật khi xử lý employee relations/investigation: https://www.shrm.org/mena/topics-tools/tools/how-to-guides/how-to-conduct-investigation
- ServiceNow định nghĩa employee self-service là tìm thông tin, tạo request và hoàn thành tác vụ thường lệ; các case phức tạp vẫn cần chuyển chuyên viên: https://www.servicenow.com/products/hr-service-delivery.html

## Assistant Role Taxonomy

| Role | Định nghĩa | Ranh giới |
|---|---|---|
| `ANSWER` | Assistant trả lời hoàn toàn bằng knowledge đã được duyệt. | Không tạo case, không hỏi thêm dữ liệu cá nhân ngoài ngữ cảnh tối thiểu. |
| `GUIDE` | Assistant hướng dẫn nhân viên tự thực hiện trên portal/form/kênh có sẵn. | Không thay nhân viên nộp đơn hoặc thay người duyệt quyết định. |
| `PREPARE_AND_HANDOFF` | Assistant giải thích, thu thập context tối thiểu rồi chuyển đúng người. | Chỉ lấy dữ liệu cần triage, không điều tra sâu, không kết luận. |
| `HUMAN_FIRST` | Cần trao đổi với manager/HR trước; assistant không biến thành workflow tự động. | Assistant chỉ nêu kênh an toàn, quyền liên hệ và cách chuẩn bị. |

## Employee-HR Interaction Boundary Matrix — Derived View

> Bảng này là view đọc nhanh từ `Runtime-Revised Canonical Scenario Registry`, không phải source-of-truth độc lập. Khi có khác biệt, runtime registry là nguồn đúng.

| # | scenario | employee intent | normal real-world first action | manager involvement | HR department | assistant role | human interaction required | sensitivity | final decision owner | allowed data collection | expected handoff |
|---:|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Hỏi số ngày phép năm theo chính sách | Biết quyền lợi chung | Xem handbook/portal | Không | C&B | ANSWER | Không | Low | C&B policy owner | Loại hợp đồng, thâm niên nếu cần | Không |
| 2 | Hướng dẫn tạo đơn nghỉ phép thường | Biết thao tác xin nghỉ | Vào HR Portal | Phê duyệt lịch nghỉ | C&B/HR Ops | GUIDE | Có, ở bước duyệt | Low | Line Manager | Ngày nghỉ dự kiến, loại nghỉ | Portal leave request |
| 3 | Nghỉ khẩn cấp trong ngày | Báo nghỉ gấp | Gọi/nhắn manager trước | Bắt buộc | C&B/HR Ops | GUIDE | Có | Medium | Line Manager | Loại nghỉ, ngày, khả năng bàn giao | Manager trước, portal sau |
| 4 | Leave exception, thiếu số dư phép | Xin ngoại lệ | Trao đổi manager trước | Bắt buộc đề xuất | C&B/HRBP | HUMAN_FIRST | Có | Medium | HRBP/C&B theo policy | Lý do ngắn, ngày, phương án bàn giao | Manager, sau đó HRBP/C&B |
| 5 | Nghỉ ốm thông thường | Biết quy trình | Báo manager và xem quy trình chứng từ | Xác nhận vắng mặt | C&B | GUIDE | Có nếu cần chứng từ | Medium | C&B | Ngày nghỉ, có/không chứng từ, không lấy chẩn đoán | C&B ticket nếu cần |
| 6 | Nghỉ thai sản/cha mẹ | Biết quyền lợi và hồ sơ | Liên hệ C&B để tư vấn hồ sơ | Thông báo kế hoạch nhân sự | C&B | PREPARE_AND_HANDOFF | Có | High | C&B | Mốc thời gian dự kiến, loại yêu cầu, không lấy hồ sơ y tế chi tiết | C&B confidential case |
| 7 | Nghỉ không lương | Xin nghỉ dài ngày | Trao đổi manager trước | Bắt buộc | HRBP/C&B | HUMAN_FIRST | Có | Medium | HRBP + Line Manager | Thời gian dự kiến, lý do mức cao | Manager/HRBP |
| 8 | Hỏi lịch nghỉ lễ | Tra cứu ngày nghỉ | Xem thông báo/handbook | Không | HR Ops | ANSWER | Không | Low | HR Ops | Năm/khu vực làm việc | Không |
| 9 | Manager chưa duyệt đơn nghỉ | Biết xử lý tiếp | Nhắc manager | Bắt buộc | C&B/HR Ops | GUIDE | Có | Low | Line Manager | Mã đơn, ngày gửi | Nhắc manager, HR Ops nếu quá SLA |
| 10 | Hủy hoặc đổi đơn nghỉ đã duyệt | Sửa lịch nghỉ | Trao đổi manager rồi sửa trên portal | Phê duyệt lại | C&B/HR Ops | GUIDE | Có | Low | Line Manager | Mã đơn, ngày đổi | Portal/manager |
| 11 | Quên chấm công | Bổ sung công | Vào timekeeping form | Xác nhận có đi làm | HR Ops/C&B | GUIDE | Có | Low | Line Manager | Ngày, ca, lý do ngắn | Timekeeping form |
| 12 | Đi trễ | Biết cách ghi nhận | Báo manager | Có thể cần | HR Ops | GUIDE | Có nếu ảnh hưởng công | Low | Line Manager | Ngày, ca, lý do ngắn | Manager/attendance form |
| 13 | Lỗi check-in khi WFH | Sửa dữ liệu công | Chụp bằng chứng hệ thống, báo manager | Xác nhận | HR Ops/IT | GUIDE | Có | Medium | HR Ops | Ngày, lỗi hệ thống, ảnh log nếu có | HR Ops/IT ticket |
| 14 | Đăng ký OT trước khi làm | Xin phê duyệt OT | Trao đổi manager về nhu cầu OT | Bắt buộc | HR Ops/C&B | GUIDE | Có | Low | Line Manager | Ngày, giờ, lý do công việc | OT form |
| 15 | Hỏi cách tính OT | Hiểu quyền lợi chung | Xem policy | Không | C&B | ANSWER | Không | Low | C&B | Loại ngày/khung giờ nếu cần | Không |
| 16 | Đổi ca/lịch làm việc | Điều chỉnh lịch đội | Nói với manager | Bắt buộc | HR Ops | HUMAN_FIRST | Có | Medium | Line Manager | Ngày, ca, lý do ngắn | Manager, sau đó HR Ops |
| 17 | Đơn bổ sung công bị từ chối | Khiếu nại kết quả công | Hỏi manager lý do | Bắt buộc | HR Ops/HRBP | PREPARE_AND_HANDOFF | Có | Medium | HR Ops/HRBP | Mã đơn, ngày, lý do từ chối | HR Ops case |
| 18 | Vắng mặt không báo trước | Muốn biết hậu quả/xử lý | Gặp manager/HRBP | Bắt buộc | HRBP/ER | HUMAN_FIRST | Có | High | HRBP/ER | Chỉ lấy nhu cầu gặp ai, không lấy lời khai dài | HRBP/ER |
| 19 | Xem payslip | Tìm bảng lương | Vào payroll portal | Không | C&B | GUIDE | Không | Medium | C&B | Tháng lương, kênh truy cập | Payroll portal |
| 20 | Payroll discrepancy | Báo sai lương/khấu trừ | Kiểm tra payslip rồi gửi C&B | Manager chỉ xác nhận công/OT nếu cần | C&B | PREPARE_AND_HANDOFF | Có | High | C&B | Tháng lương, loại sai lệch, mã payslip; không lấy số tài khoản đầy đủ | C&B payroll case |
| 21 | Đổi tài khoản ngân hàng nhận lương | Cập nhật thông tin trả lương | Vào form bảo mật/HR portal | Không | C&B/HR Ops | GUIDE | Có xác minh | High | C&B | Ngân hàng, 4 số cuối, giấy tờ theo form; không nhập full account vào chat | Secure profile/payroll form |
| 22 | Hỏi chứng từ thuế TNCN | Lấy chứng từ | Vào payroll/tax portal hoặc hỏi C&B | Không | C&B | GUIDE | Có nếu thiếu chứng từ | Medium | C&B | Năm tính thuế, loại chứng từ | C&B ticket nếu thiếu |
| 23 | Hỏi thời điểm thưởng | Biết timeline chung | Xem thông báo/policy | Không | C&B | ANSWER | Không | Medium | C&B/Leadership | Năm/kỳ thưởng | Không |
| 24 | Hỏi điều kiện phụ cấp | Biết mình có thuộc diện không | Xem policy, hỏi C&B nếu cá nhân | Có thể xác nhận vai trò | C&B | ANSWER | Có nếu case cá nhân | Medium | C&B | Nhóm công việc/khu vực, không lấy lương cá nhân | C&B nếu cần xác nhận |
| 25 | Claim bảo hiểm sức khỏe | Biết hồ sơ claim | Xem hướng dẫn claim | Không | C&B | GUIDE | Có với nhà bảo hiểm/C&B | High | C&B/Insurer | Loại claim, ngày phát sinh; không lấy chẩn đoán chi tiết trong chat | Insurance claim channel |
| 26 | Đăng ký người phụ thuộc/bảo hiểm | Thêm người phụ thuộc | Xem checklist, gửi hồ sơ qua kênh bảo mật | Không | C&B | GUIDE | Có | High | C&B | Quan hệ, loại hồ sơ; không nhập CCCD/full PII vào chat | Secure C&B form |
| 27 | Hỏi khoản khấu trừ trong lương | Hiểu lý do trừ | Xem payslip trước | Có nếu liên quan công/OT | C&B | PREPARE_AND_HANDOFF | Có | High | C&B | Tháng lương, loại khấu trừ, không lấy số tiền nhạy cảm nếu không cần | C&B payroll case |
| 28 | Thiếu giấy tờ onboarding | Hoàn tất hồ sơ nhận việc | Kiểm tra checklist onboarding | Không | HR Ops | GUIDE | Có nếu thiếu hồ sơ | Medium | HR Ops | Loại giấy tờ thiếu, ngày onboard | HR Ops onboarding ticket |
| 29 | Probation sang chính thức | Biết kết quả/chuyển trạng thái | Trao đổi với manager về feedback | Bắt buộc đánh giá | HRBP/HR Ops | HUMAN_FIRST | Có | High | Line Manager + HRBP | Ngày hết thử việc, nhu cầu hỏi trạng thái | Manager/HRBP meeting |
| 30 | Probation extension concern | Hiểu vì sao kéo dài thử việc | Gặp manager/HRBP | Bắt buộc | HRBP/ER nếu tranh chấp | HUMAN_FIRST | Có | High | HRBP + Line Manager | Chỉ lấy mốc thời gian, câu hỏi chính | HRBP case |
| 31 | Gia hạn hợp đồng | Biết có được gia hạn không | Trao đổi manager/HRBP | Bắt buộc | HR Ops/HRBP | HUMAN_FIRST | Có | High | HRBP/Business owner | Ngày hết hạn, loại hợp đồng | HRBP/HR Ops |
| 32 | Contract changes: chức danh, địa điểm, loại hợp đồng | Thay đổi điều khoản làm việc | Trao đổi manager/HRBP | Bắt buộc đề xuất | HRBP/HR Ops/Legal | HUMAN_FIRST | Có | High | HRBP + Legal khi cần | Loại thay đổi mong muốn, effective date | HRBP, Legal nếu cần |
| 33 | Employee transfer | Xin/chuyển bộ phận | Nói với manager hiện tại hoặc HRBP | Bắt buộc hai phía | HRBP/TA | HUMAN_FIRST | Có | High | Business leaders + HRBP | Bộ phận mong muốn, lý do mức cao | HRBP/internal mobility |
| 34 | Đổi thông tin hồ sơ cá nhân | Cập nhật địa chỉ/số điện thoại | Vào profile portal | Không | HR Ops | GUIDE | Không nếu self-service | Medium | HR Ops | Trường cần đổi; không nhập PII đầy đủ vào chat | HRIS profile form |
| 35 | Đổi emergency contact | Cập nhật liên hệ khẩn cấp | Vào profile portal | Không | HR Ops | GUIDE | Không | Medium | HR Ops | Quan hệ, kênh cập nhật; không nhập số điện thoại đầy đủ vào chat | HRIS profile form |
| 36 | Resignation | Muốn nghỉ việc đúng quy trình | Trao đổi manager trước khi nộp đơn | Bắt buộc | HRBP/HR Ops/C&B | HUMAN_FIRST | Có | High | Employee quyết định nộp; company xử lý bởi HRBP/HR Ops | Ngày dự kiến, loại hợp đồng, câu hỏi chính | Manager trước, sau đó HRBP/HR Ops |
| 37 | Exit handover | Biết bàn giao gì | Hỏi manager và xem checklist | Bắt buộc | HR Ops/IT/Admin | GUIDE | Có | Medium | Line Manager + HR Ops | Ngày nghỉ việc, loại tài sản/quyền truy cập | Offboarding checklist |
| 38 | Final settlement | Hỏi lương/phép còn lại sau nghỉ | Gửi C&B sau khi offboarding kích hoạt | Manager xác nhận bàn giao nếu cần | C&B/Finance | PREPARE_AND_HANDOFF | Có | High | C&B/Finance | Ngày nghỉ việc, kỳ lương, không lấy số tiền chi tiết nếu không cần | C&B settlement case |
| 39 | KPI goal clarification | Hiểu mục tiêu/KPI | Trao đổi manager | Bắt buộc | HRBP | GUIDE | Có | Medium | Line Manager | Kỳ đánh giá, loại KPI | Manager; HRBP nếu cần |
| 40 | KPI dispute | Khiếu nại điểm KPI | Nói với manager hoặc HRBP | Bắt buộc nhưng có thể bypass nếu conflict | HRBP/ER | HUMAN_FIRST | Có | High | HRBP/Performance committee | Kỳ đánh giá, điểm tranh chấp, tóm tắt ngắn | HRBP case |
| 41 | Quy trình performance review | Biết timeline và bước | Xem performance policy | Không | HRBP | ANSWER | Không | Low | HRBP | Kỳ đánh giá, role employee/manager | Không |
| 42 | Promotion/salary review | Muốn tăng lương/thăng chức | Career conversation với manager | Bắt buộc đề xuất | HRBP/C&B | HUMAN_FIRST | Có | High | Business leader + HRBP/C&B | Role hiện tại, nguyện vọng mức cao; không thu kỳ vọng lương chi tiết trong chat | Manager/HRBP |
| 43 | Development plan | Muốn phát triển năng lực | Trao đổi manager | Bắt buộc coaching | L&D/HRBP | GUIDE | Có | Medium | Line Manager/HRBP | Năng lực muốn phát triển, vai trò | Manager/L&D |
| 44 | Đăng ký khóa đào tạo | Tham gia khóa học | Vào LMS | Có nếu cần phê duyệt | L&D | GUIDE | Có nếu có ngân sách/thời gian | Low | L&D/Line Manager | Tên khóa, thời gian | LMS/manager approval |
| 45 | Training budget/chứng chỉ | Xin tài trợ học phí | Nói manager trước | Bắt buộc đề xuất | L&D/C&B/Finance | PREPARE_AND_HANDOFF | Có | Medium | L&D + Finance/Manager | Khóa học, chi phí ước tính, lợi ích công việc | Manager/L&D case |
| 46 | Internal job application | Ứng tuyển nội bộ | Xem internal job board, nói manager theo policy | Có theo chính sách | TA/HRBP | GUIDE | Có | Medium | Hiring manager + TA | Job ID, trạng thái nội bộ | TA/internal mobility |
| 47 | WFH request thường lệ | Đăng ký WFH | Vào portal hoặc xin manager | Phê duyệt | HR Ops | GUIDE | Có | Low | Line Manager | Ngày WFH, lý do nếu policy yêu cầu | WFH form |
| 48 | WFH exception | Xin WFH ngoài điều kiện | Trao đổi manager/HRBP | Bắt buộc | HRBP/HR Ops | HUMAN_FIRST | Có | Medium/High | HRBP + Line Manager | Thời gian, lý do mức cao; không lấy thông tin y tế chi tiết | Manager/HRBP |
| 49 | Cấp thiết bị làm việc | Xin laptop/màn hình | Gửi IT/Admin request, báo manager | Có nếu cần phê duyệt ngân sách | HR Ops/IT/Admin | GUIDE | Có | Low | IT/Admin + Manager | Loại thiết bị, nhu cầu công việc | IT/Admin ticket |
| 50 | Access badge/văn phòng | Làm thẻ/quyền vào văn phòng | Gửi Admin/Facilities | Có nếu cấp quyền đặc biệt | HR Ops/Admin | GUIDE | Có | Medium | Admin/Security | Địa điểm, loại quyền truy cập | Admin/Security ticket |
| 51 | Manager conflict | Xung đột với quản lý | Tìm kênh HRBP/ER an toàn | Manager có thể là bên liên quan | HRBP/ER | HUMAN_FIRST | Có | High | HRBP/ER | Chỉ lấy tóm tắt, mức khẩn cấp, mong muốn được liên hệ | HRBP/ER confidential case |
| 52 | Harassment/discrimination concern | Báo vấn đề nghiêm trọng | Liên hệ ER/hotline theo policy | Không qua manager nếu manager liên quan | ER/Legal | HUMAN_FIRST | Có | Critical | ER/Legal | Mức khẩn cấp, người liên hệ, không lấy lời khai chi tiết qua chat | ER/Legal confidential case |
| 53 | Hỏi grievance policy | Biết quyền và kênh khiếu nại | Xem policy | Không | ER | ANSWER | Không | Medium | ER | Không cần dữ liệu cá nhân | Không |
| 54 | Formal grievance submission | Muốn nộp khiếu nại chính thức | Liên hệ ER/HRBP hoặc hotline | Tùy bên liên quan | ER/Legal | PREPARE_AND_HANDOFF | Có | Critical | ER/Legal | Tóm tắt ngắn, mức khẩn cấp, kênh liên hệ an toàn | ER case |
| 55 | Disciplinary action notice | Nhận thông báo kỷ luật | Gặp HRBP/ER để được giải thích quy trình | Manager/ER tham gia theo case | ER/Legal | HUMAN_FIRST | Có | Critical | ER/Legal/Disciplinary committee | Mã case nếu có, nhu cầu hỏi quy trình; không tranh luận chứng cứ qua chat | ER/Legal meeting |
| 56 | Conflict of interest/ethics | Hỏi hoặc báo xung đột lợi ích | Xem code of conduct hoặc báo ER/Legal | Có thể không | ER/Legal | PREPARE_AND_HANDOFF | Có | High | Legal/ER | Loại concern, mức khẩn cấp, không lấy chi tiết nhạy cảm quá mức | Ethics/Legal channel |
| 57 | Stress/burnout/mental health support | Muốn được hỗ trợ | Nói với manager tin cậy hoặc HRBP/EAP nếu có | Tùy lựa chọn employee | HRBP/ER | HUMAN_FIRST | Có | Critical | Employee + HRBP/EAP | Chỉ lấy nhu cầu hỗ trợ, mức an toàn tức thời, kênh liên hệ | HRBP/EAP/hotline theo policy |
| 58 | Workplace safety incident | Báo tai nạn/sự cố | Báo manager/Safety/Admin ngay | Bắt buộc | HR Ops/Admin/Legal | HUMAN_FIRST | Có | Critical | Safety/Admin + HR/Legal | Địa điểm, thời gian, mức khẩn cấp | Safety/Admin emergency channel |
| 59 | Business trip advance | Xin tạm ứng công tác | Trao đổi manager, gửi finance form | Phê duyệt | Finance/HR Ops | GUIDE | Có | Medium | Finance + Manager | Chuyến đi, ngày, chi phí ước tính | Finance form |
| 60 | Expense reimbursement | Hoàn chi phí | Gửi expense claim | Có nếu cần xác nhận | Finance | GUIDE | Có | Medium | Finance | Loại chi phí, ngày, hóa đơn theo form | Expense system |
| 61 | Reference letter/employment confirmation | Xin xác nhận công tác | Gửi HR Ops request | Không hoặc manager xác nhận nếu đặc biệt | HR Ops | GUIDE | Có | Medium | HR Ops | Loại thư, mục đích chung, deadline | HR Ops document request |
| 62 | Data privacy/access correction request | Muốn xem/sửa dữ liệu cá nhân | Gửi kênh HR/Data Privacy | Không | HR Ops/Legal | PREPARE_AND_HANDOFF | Có | High | HR Ops/Legal | Loại dữ liệu, yêu cầu truy cập/sửa; không nhập dữ liệu đầy đủ vào chat | Privacy/HR Ops case |
| 63 | Change reporting line/supervisor | Hỏi vì sao đổi quản lý | Trao đổi manager/HRBP | Bắt buộc | HRBP | HUMAN_FIRST | Có | High | Business leader + HRBP | Tóm tắt câu hỏi, effective date | HRBP |
| 64 | Immigration/work permit/visa support | Cần hỗ trợ giấy phép làm việc | Liên hệ HR Ops/Legal | Có nếu liên quan role/location | HR Ops/Legal | PREPARE_AND_HANDOFF | Có | High | Legal/HR Ops | Quốc tịch, loại yêu cầu mức cao; không nhập passport đầy đủ vào chat | Legal/HR Ops confidential case |

## Employee - Manager - HR Flow Map

| Flow | Khi nào dùng | Luồng mặc định | Assistant đứng ở đâu |
|---|---|---|---|
| Tier 0 knowledge | Câu hỏi chung, policy rõ, không cần dữ liệu cá nhân | Employee -> Assistant -> Answer | Trả lời bằng KB nội bộ, dẫn policy/SOP/FAQ |
| Routine self-service | Có form/portal rõ, quyết định đơn giản | Employee -> Assistant guide -> Portal/Form -> Manager/HR approval nếu cần | Hướng dẫn bước, link kênh, SLA, điều kiện |
| Manager-mediated | Ảnh hưởng lịch làm việc, hiệu suất, phân công, ngoại lệ | Employee -> Line Manager -> HR nếu cần | Nhắc trao đổi manager trước, chuẩn bị checklist câu hỏi |
| HR specialist case | Payroll, benefits, hồ sơ, hợp đồng, lifecycle | Employee -> Assistant triage -> C&B/HR Ops/HRBP | Thu context tối thiểu, route đúng bộ phận |
| Sensitive ER case | Khiếu nại, xung đột, kỷ luật, harassment, safety | Employee -> ER/HRBP/Legal/hotline | Human-first, không điều tra trong chat, ưu tiên kênh bảo mật |
| Cross-functional case | Công tác phí, legal docs, work permit, privacy | Employee -> HR/Finance/Legal | Xác định owner, tránh tư vấn vượt quyền |

## Appendix A — HR Responsibility/RACI Overview Deprecated

> Bảng RACI overview này chỉ giữ lại để đọc nhanh theo area. Source-of-truth duy nhất cho decision ownership là `Normalized RACI And Decision Ownership`; không dùng bảng này để thiết kế database hoặc workflow approval.

| Area | Employee | Line Manager | HR Ops | C&B | HRBP | TA | L&D | ER | Finance/Legal | Assistant |
|---|---|---|---|---|---|---|---|---|---|---|
| Leave thường lệ | R | A | C | C | I | I | I | I | I | C |
| Leave/WFH exception | R | A/R | C | C | A/R | I | I | C | C nếu rủi ro | C |
| Attendance correction | R | A | R | C | C | I | I | I | I | C |
| Payroll/benefits | R | C | C | A/R | I | I | I | I | C Finance | C |
| Profile/bank data | R | I | R | A/R | I | I | I | I | C Legal nếu privacy | C |
| Probation/contract/transfer | R | A/R | R | C | A/R | C | I | C | C Legal | C |
| Resignation/offboarding | R | A/R | R | C | A/R | I | I | C | C Finance/Legal | C |
| KPI/performance | R | A/R | I | C | A/R | I | C | C | I | C |
| Promotion/salary review | R | A/R | I | R C&B | A/R | I | C | I | C Finance | C |
| Grievance/disciplinary/conflict | R | C hoặc subject | I | I | C/R | I | I | A/R | C/A Legal | C |
| Learning | R | A/C | I | C nếu ngân sách | C | I | A/R | I | C Finance | C |
| Expense/business trip | R | A/C | C | I | I | I | I | I | A/R Finance | C |

Ký hiệu: `R` chịu trách nhiệm thực hiện, `A` chịu trách nhiệm cuối, `C` được tham vấn, `I` được thông báo.

## Scenario Assistant Không Nên Tự Động Hóa

- Chuyển thử việc sang chính thức, kéo dài thử việc hoặc không đạt thử việc.
- Resignation acceptance, thương lượng ngày nghỉ, counter-offer hoặc miễn trừ notice period.
- Thay đổi hợp đồng, chức danh, địa điểm làm việc, reporting line hoặc transfer.
- Payroll dispute cần kiểm tra dữ liệu lương/công/thuế cá nhân.
- KPI dispute, promotion, salary review hoặc compensation exception.
- Grievance, harassment, discrimination, manager conflict, disciplinary action.
- Leave/WFH/unpaid leave exception có ảnh hưởng vận hành hoặc rủi ro pháp lý.
- Vấn đề sức khỏe tinh thần, safety incident, work permit/visa, data privacy request.

## Scenario Đáng Self-Service Nhất

- Hỏi policy chung: lịch nghỉ lễ, quy trình nghỉ phép, cách tính OT ở mức nguyên tắc, timeline performance review.
- Hướng dẫn thao tác: tạo đơn nghỉ, sửa chấm công, đăng ký OT/WFH thường lệ, tải payslip, gửi expense claim.
- Tra cứu checklist: onboarding, offboarding, training registration, claim bảo hiểm, employment confirmation.
- Điều hướng đúng kênh: HR directory, owner từng domain, SLA xử lý, escalation nếu quá hạn.
- FAQ lặp lại: khi nào nhận lương, manager chưa duyệt thì làm gì, cần chứng từ nào, form ở đâu.

## Derived HR Service Catalog

| Service group | Services | Default assistant role | Primary owner |
|---|---|---|---|
| Knowledge & Directory | Policy Q&A, HR directory, SLA lookup | ANSWER | HR Ops |
| Leave & Attendance | Leave request, urgent leave, attendance correction, OT | GUIDE/PREPARE_AND_HANDOFF | C&B/HR Ops |
| Payroll & Benefits | Payslip, discrepancy, benefits, insurance claim, tax docs | GUIDE/PREPARE_AND_HANDOFF | C&B |
| Employee Data | Profile, bank account, emergency contact, privacy request | GUIDE/PREPARE_AND_HANDOFF | HR Ops/C&B/Legal |
| Employee Lifecycle | Onboarding, probation, contract, transfer, resignation, offboarding | HUMAN_FIRST/PREPARE_AND_HANDOFF | HRBP/HR Ops |
| Performance & Career | KPI, review, promotion, salary review, development plan | ANSWER/HUMAN_FIRST | HRBP/C&B |
| Learning | Course registration, training budget, certification | GUIDE/PREPARE_AND_HANDOFF | L&D |
| Employee Relations | Grievance, conflict, discipline, ethics, safety concern | HUMAN_FIRST/PREPARE_AND_HANDOFF | ER/Legal |
| Finance-adjacent HR | Business trip advance, expense reimbursement, final settlement | GUIDE/PREPARE_AND_HANDOFF | Finance/C&B |

## Derived Database Entity Candidates

Đây chỉ là danh sách entity ứng viên, chưa phải schema.

| Entity | Mục đích |
|---|---|
| `actor` / `role` | Employee, Line Manager, HR Ops, C&B, HRBP, TA, L&D, ER, Finance, Legal, Admin |
| `hr_service` | Service catalog: domain, owner, default assistant role, SLA, sensitivity |
| `interaction_scenario` | Boundary matrix: scenario, intent, first action, role classification |
| `boundary_rule` | Rule quyết định ANSWER/GUIDE/PREPARE_AND_HANDOFF/HUMAN_FIRST |
| `case_type` | Loại case/ticket và routing owner |
| `handoff` | Kết quả chuyển người: target department, reason, expected SLA |
| `allowed_data_field` | Trường dữ liệu được phép thu cho từng scenario |
| `sensitivity_level` | Low, Medium, High, Critical |
| `approval_policy` | Ai duyệt, điều kiện duyệt, escalation khi quá SLA |
| `raci_assignment` | RACI theo service/domain |
| `knowledge_document` | Policy, SOP, FAQ, handbook, directory, form registry |
| `legal_basis` | Mapping compliance, không phải nguồn trả lời mặc định |
| `audit_event` | Log tối thiểu, không lưu PII nhạy cảm |
| `decision_record` | Quyết định của người có thẩm quyền, không do assistant tự tạo |

## Derived Knowledge Base Documents

| Document type | Cần có |
|---|---|
| Boundary playbook | Quy định khi nào assistant trả lời, hướng dẫn, handoff hoặc human-first |
| HR service catalog | Danh mục service, owner, SLA, channel, escalation |
| Policy set | Leave, attendance, OT, WFH, compensation, benefits, performance, lifecycle |
| SOP set | Leave request, attendance correction, payroll inquiry, onboarding, offboarding, expense, training |
| FAQ set | FAQ theo domain, chỉ diễn giải theo policy/SOP owner |
| Manager guide | Vai trò manager trong leave, probation, KPI, conflict, transfer, resignation |
| HR owner directory | C&B, HR Ops, HRBP, TA, L&D, ER, Finance/Legal |
| Forms registry | Portal/form/channel, required fields, privacy note, SLA |
| Legal basis map | Mapping nguồn luật/public source sang policy nội bộ, không index mặc định cho employee |
| Assistant guardrails | Data minimization, sensitive-case routing, refusal/handoff templates |

## Implication Cho Database Và KB

- Database không nên bắt đầu từ bảng `documents` hoặc `tickets` đơn thuần. Nó nên bắt đầu từ `hr_service`, `interaction_scenario`, `boundary_rule`, `case_type`, `allowed_data_field` và `handoff`.
- `ticket` chỉ là một kết quả của boundary decision, không phải default cho mọi câu hỏi.
- `document` và `chunk` chỉ phục vụ evidence. Chúng không đủ để quyết định assistant có được tự phục vụ hay không.
- RAG cần filter theo `visibility=user_facing`, `doc_type`, `domain`, `role_scope` và `sensitivity`.
- Legal/public sources chỉ đi vào authoring/compliance pipeline, không phải employee retrieval mặc định.

## Business Modeling V2

Phần này bổ sung một vòng phân tích nghiệp vụ trước database. Nó dùng 64 scenario hiện tại làm nền, nhưng thêm ba lớp ranh giới mới:

- Phía nhận việc vận hành ra sao: manager, HR Ops, C&B, HRBP, TA, L&D, ER, Finance, Legal, IT, Admin.
- Scenario cần loại dữ liệu nào và source-of-truth ở đâu.
- Assistant được phép làm hành động hệ thống ở mức nào.

## V-Nova HR Operating Model

| Role | Trách nhiệm chính thức | Không nên chịu trách nhiệm |
|---|---|---|
| Line Manager | Quản lý công việc hằng ngày, lịch nghỉ, WFH/OT, hiệu suất, feedback thử việc, bàn giao, đề xuất tăng lương/thăng chức/chuyển bộ phận. | Diễn giải pháp lý, tự quyết payroll/benefits, tự xử lý grievance nhạy cảm, tự thay đổi hợp đồng. |
| HR Ops | Vận hành vòng đời nhân sự: hồ sơ, onboarding, offboarding, HRIS, chấm công hành chính, xác nhận công tác, phối hợp IT/Admin. | Quyết định lương thưởng, điều tra ER, phê duyệt tăng lương, quyết định kỷ luật cuối. |
| C&B | Lương, thưởng, phụ cấp, payroll, thuế TNCN, BHXH/BHYT, bảo hiểm sức khỏe, leave balance, final settlement. | Đánh giá hiệu suất, xử lý xung đột quản lý, quyết định thăng chức. |
| HRBP | Tư vấn nhân sự cho business, probation, contract/lifecycle case, transfer, performance governance, org change, exception có ảnh hưởng đội nhóm. | Vận hành payroll chi tiết, nhập liệu HRIS thường lệ, điều tra ER độc lập nếu có xung đột nghiêm trọng. |
| TA | Tuyển dụng, offer, internal mobility ở góc độ vị trí tuyển, phối hợp hiring manager. | Quyết định transfer nội bộ khi chưa có business/HRBP approval, xử lý payroll hoặc grievance. |
| L&D | Đào tạo, LMS, ngân sách/chứng chỉ học tập, development plan framework. | Quyết định promotion/salary, xử lý kỷ luật hoặc payroll. |
| ER | Grievance, conflict, harassment/discrimination, disciplinary process, investigation coordination, case confidentiality. | Thay manager quản trị hiệu suất hằng ngày, tự quyết benefit/payroll. |
| Finance | Công tác phí, reimbursement, payment control, budget confirmation, final settlement payment support. | Quyết định HR policy hoặc employee relations outcome. |
| Legal | Tư vấn rủi ro pháp lý, hợp đồng đặc biệt, kỷ luật/chấm dứt nhạy cảm, immigration/work permit, privacy. | Vận hành HR self-service, trả lời FAQ thường lệ cho employee. |
| IT/Admin | Thiết bị, account, quyền truy cập, thẻ văn phòng, tài sản, facilities. | Quyết định HR lifecycle, payroll, grievance. |
| Assistant | Trả lời knowledge, hướng dẫn self-service, prefill draft/context tối thiểu, route/handoff đúng người. | Tự quyết quyền lợi cá nhân, tự phê duyệt, tự điều tra, tự giả lập dữ liệu cá nhân hoặc trạng thái giao dịch. |

## Revised Employee Boundary Matrix V2

Matrix gốc ở trên vẫn là lớp mô tả hành vi người dùng. V2 bổ sung hai overlay bắt buộc trước khi thiết kế database:

- `data_dependency`: loại dữ liệu tối thiểu cần để xử lý scenario.
- `system_action_boundary`: hành động hệ thống tối đa assistant được phép thực hiện.

Quy tắc đọc:

- `KNOWLEDGE_ONLY` chỉ được trả lời từ KB nội bộ.
- `EMPLOYEE_PROFILE`, `TRANSACTIONAL` và `EXTERNAL_SYSTEM` không được giả lập nếu chưa có source-of-truth thật.
- `MANAGER_DECISION` không được bypass quản lý trực tiếp.
- `HR_CASE` phải có handoff, owner, SLA, audit và privacy boundary.
- `HUMAN_FIRST` mặc định chỉ `NONE`, `LINK_ONLY` hoặc `PREFILL_DRAFT`; chỉ `CREATE_CASE` khi policy định nghĩa confidential handoff rõ ràng.

## Manager-HR Operational Matrix

SLA bên dưới là `V-Nova baseline operating assumptions` dùng nhất quán cho thiết kế sản phẩm. Khi onboarding khách hàng thật, SLA phải được cấu hình theo tenant/service thay vì hard-code trong logic.

| workflow | trigger | actor | action | required data | decision | next state | SLA | escalation | audit requirement |
|---|---|---|---|---|---|---|---|---|---|
| Leave | Employee hỏi quy định phép | Assistant | Trả lời theo policy/FAQ | Loại nhân viên, năm áp dụng nếu cần | Không có quyết định cá nhân | Employee hiểu rule | Ngay lập tức | C&B nếu KB thiếu/mâu thuẫn | Log citation và version |
| Leave | Employee tạo đơn nghỉ thường | Employee | Nộp đơn trên HR Portal | Ngày nghỉ, loại nghỉ, bàn giao | Submit hợp lệ | Chờ manager duyệt | Theo portal | HR Ops nếu lỗi hệ thống | Log request id từ portal |
| Leave | Đơn nghỉ chờ duyệt | Line Manager | Kiểm tra lịch đội, phê duyệt/từ chối | Lịch team, workload, số ngày nghỉ | Approve/reject lịch nghỉ | Approved hoặc rejected | 2 ngày làm việc | HRBP nếu manager quá SLA | Audit quyết định, lý do từ chối |
| Leave | Leave exception/âm phép/nghỉ dài | Line Manager | Trao đổi feasibility với employee | Lý do mức cao, thời gian, kế hoạch bàn giao | Có đề xuất exception hay không | Nếu có, chuyển HRBP/C&B | 1-2 ngày làm việc | HRBP nếu ảnh hưởng vận hành | Note cuộc trao đổi, không lưu chi tiết nhạy cảm quá mức |
| Leave | HR nhận exception | HRBP/C&B | Kiểm tra policy, leave balance, rủi ro | Hồ sơ phép, hợp đồng, lịch sử exception | Chấp thuận/từ chối exception | Case closed hoặc cập nhật leave | 3-5 ngày làm việc | Legal nếu có rủi ro pháp lý | Case record, owner, legal_basis nếu dùng |
| Attendance correction | Employee quên chấm công | Employee | Gửi form bổ sung công | Ngày, ca, lý do, bằng chứng nếu có | Submit hợp lệ | Chờ manager xác nhận | Trong 2 ngày sau phát sinh | HR Ops nếu quá hạn | Log form và timestamp |
| Attendance correction | Form cần xác nhận | Line Manager | Xác nhận employee có làm việc | Lịch làm việc, task/meeting evidence | Confirm/reject attendance | Chờ HR Ops ghi nhận | 2 ngày làm việc | HRBP nếu tranh chấp | Audit approval/reject reason |
| Attendance correction | HR Ops xử lý | HR Ops | Cập nhật attendance system hoặc trả lại | Form, manager confirmation | Dữ liệu công hợp lệ | Attendance corrected | 3 ngày làm việc | C&B nếu ảnh hưởng payroll cutoff | Audit old/new value |
| Attendance correction | Tranh chấp sau từ chối | HR Ops/HRBP | Triage case, lấy thêm xác nhận tối thiểu | Mã đơn, ngày, lý do từ chối | Có mở case HRBP không | HR case hoặc closed | 2 ngày làm việc | ER nếu có cáo buộc không công bằng | Case note và access control |
| OT | Nhu cầu làm OT | Employee/Manager | Thống nhất nhu cầu trước khi làm | Công việc, ngày, giờ dự kiến | Có cần OT không | Chờ đăng ký/phê duyệt | Trước khi OT | HRBP nếu OT bất thường | Log pre-approval |
| OT | Đăng ký OT | Employee | Gửi OT request | Ngày, giờ, lý do công việc | Submit hợp lệ | Chờ manager approve | Trước khi làm hoặc theo cutoff | HR Ops nếu lỗi hệ thống | Request id |
| OT | Manager phê duyệt OT | Line Manager | Kiểm tra business need và workload | Lịch đội, ngân sách nếu có | Approve/reject OT | Approved OT | 1 ngày làm việc | Business head nếu vượt ngưỡng | Audit approval |
| OT | Tính OT/payroll | C&B | Đối soát OT approved với attendance/payroll | OT approved, attendance, payroll cutoff | Có trả OT hay cần điều chỉnh | Payroll processed hoặc exception | Theo kỳ payroll | Finance nếu ảnh hưởng chi trả | Payroll audit trail |
| WFH | Employee xin WFH thường lệ | Employee | Gửi WFH request hoặc xin manager | Ngày, lý do nếu cần, địa điểm làm việc | Submit hợp lệ | Chờ manager approve | Theo policy | HR Ops nếu portal lỗi | Request id |
| WFH | Manager duyệt WFH | Line Manager | Kiểm tra yêu cầu công việc, lịch team | Lịch team, tính chất công việc | Approve/reject WFH | WFH approved/rejected | 1-2 ngày làm việc | HRBP nếu tranh chấp/exception | Audit decision |
| WFH | WFH exception | Line Manager/HRBP | Trao đổi trường hợp ngoại lệ | Lý do mức cao, thời gian, impact | Có cho exception không | Case HRBP hoặc closed | 2-3 ngày làm việc | Legal nếu liên quan sức khỏe/phân biệt đối xử | Case note tối thiểu |
| WFH | Lỗi check-in khi WFH | HR Ops/IT | Kiểm tra hệ thống, log truy cập | Ngày, lỗi, screenshot/log | Có lỗi hệ thống hay lỗi người dùng | Attendance corrected hoặc IT ticket | 3 ngày làm việc | IT lead nếu lỗi lặp | Audit evidence và correction |
| Payroll discrepancy | Employee nghi sai lương | Assistant | Hướng dẫn kiểm tra payslip và tạo draft case | Tháng lương, loại sai lệch, mã payslip | Không kết luận đúng/sai | Draft gửi C&B | Ngay lập tức | C&B nếu employee gửi | Không log số tiền chi tiết trong chat |
| Payroll discrepancy | C&B nhận case | C&B | Đối soát payroll, attendance, OT, benefits | Payroll record, attendance, approvals | Sai payroll hay misunderstanding | Investigating/need manager confirmation | 3 ngày làm việc | Payroll lead nếu gần cutoff | Audit source systems |
| Payroll discrepancy | Cần xác nhận công/OT | Line Manager | Xác nhận attendance/OT liên quan | Ngày công, OT approved, lịch team | Confirm/reject facts | C&B tiếp tục xử lý | 2 ngày làm việc | HRBP nếu manager không phản hồi | Audit manager confirmation |
| Payroll discrepancy | Kết luận case | C&B | Giải thích hoặc tạo điều chỉnh payroll | Kết quả đối soát, kỳ payroll | Có adjustment không | Closed hoặc adjustment scheduled | 5-7 ngày làm việc | Finance nếu cần chi trả bổ sung | Case resolution và old/new amount trong hệ thống bảo mật |
| Insurance claim | Employee hỏi hồ sơ claim | Assistant | Hướng dẫn checklist và kênh claim | Loại claim, policy group | Không quyết định chi trả | Employee chuẩn bị hồ sơ | Ngay lập tức | C&B nếu không rõ quyền lợi | Log citation |
| Insurance claim | Employee nộp claim | Employee | Gửi qua insurer portal/kênh bảo mật | Hồ sơ theo checklist | Submit hợp lệ | Claim submitted | Theo insurer | C&B nếu portal lỗi | Không lưu hồ sơ y tế trong chat |
| Insurance claim | C&B hỗ trợ claim | C&B | Kiểm tra eligibility và hỗ trợ insurer | Employee group, policy, claim id | Có hỗ trợ/escalate insurer không | Pending insurer hoặc closed | 3-5 ngày làm việc | Insurer account manager | Case note giới hạn |
| Probation | Gần hết thử việc | HR Ops | Nhắc manager review probation | Ngày bắt đầu, ngày hết thử việc, role | Cần review đúng hạn | Manager review pending | Trước hạn 10-15 ngày | HRBP nếu quá hạn | Audit reminder |
| Probation | Manager đánh giá | Line Manager | Review performance, fit, feedback | KPI thử việc, feedback, attendance | Đề xuất pass/extend/fail | HRBP review | Trước hạn 5 ngày | HRBP nếu thiếu evidence | Review record |
| Probation | HRBP kiểm tra đề xuất | HRBP | Kiểm tra fairness, documentation, risk | Manager review, contract, feedback trail | Đồng ý đề xuất hay cần thêm evidence | Official/extend/fail process | 3 ngày làm việc | ER/Legal nếu fail/extend rủi ro | Decision memo |
| Probation | HR Ops cập nhật trạng thái | HR Ops | Cập nhật HRIS và phát hành thông báo | Approved decision, effective date | Không quyết định, chỉ thực thi | Employee status updated | 2 ngày làm việc sau approval | HRBP nếu thiếu approval | HRIS audit |
| KPI review | Đến kỳ review | HRBP | Mở cycle và hướng dẫn timeline | Kỳ đánh giá, population, template | Cycle active | Employee/manager review | Theo calendar | Business head nếu delay | Cycle log |
| KPI review | Employee tự đánh giá | Employee | Hoàn thành self-review | KPI, evidence công việc | Submit self-review | Manager review pending | Theo calendar | Manager nếu quá hạn | Performance system log |
| KPI review | Manager đánh giá | Line Manager | Review KPI, feedback, rating đề xuất | Goals, evidence, calibration input | Rating đề xuất | Calibration/HRBP review | Theo calendar | HRBP nếu thiếu evidence | Rating audit |
| KPI dispute | Employee không đồng ý rating | Employee | Trao đổi manager hoặc gửi HRBP | Kỳ đánh giá, rating, điểm tranh chấp | Có mở dispute không | Manager discussion hoặc HRBP case | 5 ngày sau nhận rating | ER nếu có allegation | Case note tối thiểu |
| KPI dispute | HRBP xử lý dispute | HRBP | Kiểm tra process fairness và evidence | KPI record, manager notes, employee concern | Giữ/sửa/đưa committee | Closed hoặc committee review | 5-10 ngày làm việc | ER nếu có conflict/retaliation | Decision trail |
| Promotion | Employee muốn thăng chức/tăng lương | Line Manager | Career conversation và đánh giá readiness | Role hiện tại, performance, scope | Có đề xuất không | Proposal hoặc coaching plan | Theo cycle | HRBP nếu không rõ path | Manager note |
| Promotion | Manager đề xuất | Line Manager | Tạo promotion/salary proposal | Business case, performance, budget input | Submit proposal | HRBP/C&B review | Theo cycle | Business head nếu budget | Proposal audit |
| Promotion | HRBP/C&B review | HRBP/C&B | Kiểm tra leveling, comp range, equity | Proposal, salary band, performance history | Recommend approve/reject/adjust | Business decision | 5-10 ngày làm việc | Legal nếu risk equity | Review trail |
| Promotion | Final approval | Business leader | Quyết định promotion/salary | Recommendation, budget, org need | Approve/reject | HR Ops/C&B execution | Theo cycle | Leadership nếu exception lớn | Final approval record |
| Resignation/offboarding | Employee muốn nghỉ việc | Employee | Nói với manager trước, sau đó nộp đơn | Ngày dự kiến, loại hợp đồng | Employee có nộp resignation không | Manager informed hoặc request submitted | Employee-driven | HRBP nếu muốn tư vấn | Không log lý do nhạy cảm nếu chưa cần |
| Resignation/offboarding | Manager nhận resignation | Line Manager | Trao đổi notice, handover, retention nếu phù hợp | Ngày nghỉ, workload, replacement need | Đề xuất last working day/handover | HRBP/HR Ops process | 1-2 ngày làm việc | HRBP nếu conflict/counter-offer | Meeting note tối thiểu |
| Resignation/offboarding | HRBP xác nhận xử lý | HRBP | Kiểm tra rủi ro, exit reason, notice exception | Contract, policy, manager input | Accept process/need intervention | Offboarding initiated | 2-3 ngày làm việc | ER/Legal nếu tranh chấp | Case decision |
| Resignation/offboarding | HR Ops điều phối offboarding | HR Ops | Kích hoạt checklist, asset, access, documents | Last working day, checklist, departments | Không quyết định, điều phối hoàn tất | Tasks assigned | Ngay sau approval | IT/Admin nếu quá SLA | Task audit |
| Resignation/offboarding | C&B/Finance quyết toán | C&B/Finance | Tính final settlement | Payroll, leave balance, deductions, handover status | Amount payable/receivable | Settlement scheduled | Theo kỳ payroll hoặc SLA policy | Legal nếu dispute | Payroll audit |
| Grievance | Employee hỏi quyền/kênh khiếu nại | Assistant | Trả lời policy và kênh an toàn | Không cần PII | Không có kết luận | Employee biết kênh | Ngay lập tức | ER nếu muốn nộp case | Citation log |
| Grievance | Employee muốn nộp grievance | Assistant | Thu context tối thiểu và tạo confidential handoff nếu policy cho phép | Mức khẩn cấp, kênh liên hệ, tóm tắt ngắn | Không kết luận sự việc | ER case created | Ngay lập tức | ER lead nếu critical | Confidential case audit |
| Grievance | ER triage | ER | Đánh giá mức độ, conflict of interest, cần Legal không | Case summary, parties, urgency | Investigation/mediation/no action | Investigation plan hoặc closure | 1 ngày làm việc; critical trong ngày | Legal/Leadership nếu high risk | Restricted audit |
| Grievance | Investigation/mediation | ER/Legal | Thu thập thông tin qua kênh chính thức | Interviews, evidence, policy | Finding/recommendation | Corrective action hoặc closed | Theo policy | Legal nếu disciplinary/termination risk | Full case file, access control |

## Data Dependency Matrix — Derived View

> Bảng này là view phân tích từ `Runtime-Revised Canonical Scenario Registry`, không phải source-of-truth độc lập.

| # | scenario | data_dependency | source_of_truth | assistant data rule |
|---:|---|---|---|---|
| 1 | Hỏi số ngày phép năm theo chính sách | KNOWLEDGE_ONLY | KB | Được trả lời theo policy, không suy ra balance cá nhân |
| 2 | Hướng dẫn tạo đơn nghỉ phép thường | TRANSACTIONAL | HRIS/Leave Portal | Chỉ hướng dẫn hoặc link; không tạo request nếu chưa tích hợp |
| 3 | Nghỉ khẩn cấp trong ngày | MANAGER_DECISION | Manager + Leave Portal | Nhắc báo manager trước, không tự duyệt |
| 4 | Leave exception, thiếu số dư phép | HR_CASE | Manager + HRBP/C&B | Không tự cấp ngoại lệ |
| 5 | Nghỉ ốm thông thường | TRANSACTIONAL | Leave Portal + C&B | Không thu chẩn đoán y tế trong chat |
| 6 | Nghỉ thai sản/cha mẹ | HR_CASE | C&B + HRIS | Chỉ thu mốc thời gian mức cao |
| 7 | Nghỉ không lương | HR_CASE | Manager + HRBP | Human-first, không tạo leave tự động |
| 8 | Hỏi lịch nghỉ lễ | KNOWLEDGE_ONLY | KB | Trả lời từ thông báo/handbook |
| 9 | Manager chưa duyệt đơn nghỉ | TRANSACTIONAL | Leave Portal + Manager | Không đọc trạng thái nếu chưa có portal |
| 10 | Hủy hoặc đổi đơn nghỉ đã duyệt | TRANSACTIONAL | Leave Portal | Chỉ hướng dẫn thao tác |
| 11 | Quên chấm công | TRANSACTIONAL | Attendance System | Không ghi công nếu chưa có workflow |
| 12 | Đi trễ | MANAGER_DECISION | Manager + Attendance | Nhắc báo manager nếu ảnh hưởng công |
| 13 | Lỗi check-in khi WFH | EXTERNAL_SYSTEM | Attendance + IT logs | Không kết luận lỗi hệ thống |
| 14 | Đăng ký OT trước khi làm | MANAGER_DECISION | Manager + OT Portal | Không tự approve OT |
| 15 | Hỏi cách tính OT | KNOWLEDGE_ONLY | KB | Trả lời rule chung, không tính lương cá nhân |
| 16 | Đổi ca/lịch làm việc | MANAGER_DECISION | Manager | Human-first với manager |
| 17 | Đơn bổ sung công bị từ chối | HR_CASE | Attendance + HR Ops/HRBP | Thu mã đơn và tóm tắt ngắn |
| 18 | Vắng mặt không báo trước | HR_CASE | Manager + HRBP/ER | Không tư vấn kết quả kỷ luật |
| 19 | Xem payslip | EXTERNAL_SYSTEM | Payroll Portal | Link-only nếu chưa có payroll integration |
| 20 | Payroll discrepancy | HR_CASE | Payroll + C&B | Không giả lập đúng/sai payroll |
| 21 | Đổi tài khoản ngân hàng nhận lương | EMPLOYEE_PROFILE | HRIS/Payroll | Không nhập full account vào chat |
| 22 | Hỏi chứng từ thuế TNCN | TRANSACTIONAL | Payroll/Tax Portal | Hướng dẫn lấy chứng từ, case nếu thiếu |
| 23 | Hỏi thời điểm thưởng | KNOWLEDGE_ONLY | KB/C&B announcement | Không hứa payout cá nhân |
| 24 | Hỏi điều kiện phụ cấp | KNOWLEDGE_ONLY | KB | Nếu hỏi cá nhân thì chuyển C&B |
| 25 | Claim bảo hiểm sức khỏe | EXTERNAL_SYSTEM | Insurer Portal + C&B | Không lưu hồ sơ y tế trong chat |
| 26 | Đăng ký người phụ thuộc/bảo hiểm | EMPLOYEE_PROFILE | HRIS/C&B Secure Form | Không thu CCCD/full PII trong chat |
| 27 | Hỏi khoản khấu trừ trong lương | HR_CASE | Payroll + C&B | Không suy đoán khoản trừ cá nhân |
| 28 | Thiếu giấy tờ onboarding | TRANSACTIONAL | HRIS/Onboarding Checklist | Hướng dẫn checklist hoặc tạo HR Ops case |
| 29 | Probation sang chính thức | MANAGER_DECISION | Manager + HRBP + HRIS | Không báo pass/fail nếu chưa có quyết định |
| 30 | Probation extension concern | HR_CASE | HRBP/ER | Không kết luận tính hợp lệ |
| 31 | Gia hạn hợp đồng | HR_CASE | HRBP + HR Ops | Không hứa gia hạn |
| 32 | Contract changes | HR_CASE | HRBP + Legal + HRIS | Không soạn quyết định hợp đồng tự động |
| 33 | Employee transfer | HR_CASE | HRBP + Business leaders + TA | Không bypass manager/HRBP |
| 34 | Đổi thông tin hồ sơ cá nhân | EMPLOYEE_PROFILE | HRIS Profile | Hướng dẫn form; không thu PII đầy đủ |
| 35 | Đổi emergency contact | EMPLOYEE_PROFILE | HRIS Profile | Hướng dẫn form |
| 36 | Resignation | HR_CASE | Employee submission + HRBP/HR Ops | Không tự chấp nhận nghỉ việc |
| 37 | Exit handover | TRANSACTIONAL | Offboarding Checklist + Manager | Hướng dẫn checklist |
| 38 | Final settlement | HR_CASE | Payroll + C&B + Finance | Không tính số tiền nếu không có payroll |
| 39 | KPI goal clarification | MANAGER_DECISION | Manager + Performance System | Nhắc trao đổi manager |
| 40 | KPI dispute | HR_CASE | Performance System + HRBP/ER | Không tự sửa rating |
| 41 | Quy trình performance review | KNOWLEDGE_ONLY | KB | Trả lời timeline/process chung |
| 42 | Promotion/salary review | MANAGER_DECISION | Manager + HRBP/C&B | Không cam kết tăng lương/thăng chức |
| 43 | Development plan | MANAGER_DECISION | Manager + L&D | Hướng dẫn chuẩn bị career talk |
| 44 | Đăng ký khóa đào tạo | TRANSACTIONAL | LMS | Hướng dẫn LMS, không approve ngân sách |
| 45 | Training budget/chứng chỉ | HR_CASE | L&D + Manager + Finance | Không tự duyệt chi phí |
| 46 | Internal job application | TRANSACTIONAL | ATS/Internal Job Board | Hướng dẫn process, không thay TA |
| 47 | WFH request thường lệ | MANAGER_DECISION | Manager + WFH Portal | Không tự approve WFH |
| 48 | WFH exception | HR_CASE | Manager + HRBP | Human-first |
| 49 | Cấp thiết bị làm việc | EXTERNAL_SYSTEM | IT/Admin System | Link/request nếu có ITSM |
| 50 | Access badge/văn phòng | EXTERNAL_SYSTEM | Admin/Security System | Không tự cấp quyền |
| 51 | Manager conflict | HR_CASE | HRBP/ER | Confidential handoff, tối thiểu dữ liệu |
| 52 | Harassment/discrimination concern | HR_CASE | ER/Legal/Hotline | Human-first, không điều tra trong chat |
| 53 | Hỏi grievance policy | KNOWLEDGE_ONLY | KB | Trả lời quyền và kênh |
| 54 | Formal grievance submission | HR_CASE | ER Case System | Confidential handoff nếu policy cho phép |
| 55 | Disciplinary action notice | HR_CASE | ER/Legal | Không tranh luận chứng cứ trong chat |
| 56 | Conflict of interest/ethics | HR_CASE | ER/Legal/Ethics Channel | Handoff đúng kênh |
| 57 | Stress/burnout/mental health support | HR_CASE | HRBP/EAP/Hotline | Chỉ hỏi kênh liên hệ và mức an toàn |
| 58 | Workplace safety incident | HR_CASE | Safety/Admin/Legal | Ưu tiên emergency channel |
| 59 | Business trip advance | TRANSACTIONAL | Finance System + Manager | Hướng dẫn form |
| 60 | Expense reimbursement | TRANSACTIONAL | Expense System | Hướng dẫn claim |
| 61 | Reference letter/employment confirmation | EMPLOYEE_PROFILE | HRIS + HR Ops | Hướng dẫn request |
| 62 | Data privacy/access correction request | HR_CASE | HR Ops/Legal | Không hiển thị dữ liệu nếu chưa có quyền |
| 63 | Change reporting line/supervisor | HR_CASE | HRBP + Business leader | Không tự giải thích quyết định cá nhân |
| 64 | Immigration/work permit/visa support | HR_CASE | Legal + HR Ops | Không thu passport/full document trong chat |

Ví dụ boundary bắt buộc:

- "Tôi được bao nhiêu ngày phép?" -> `KNOWLEDGE_ONLY`, source-of-truth là KB.
- "Tôi còn bao nhiêu ngày phép?" -> `TRANSACTIONAL`, source-of-truth là leave balance trong HRIS/Leave Portal.
- Nếu hệ thống chưa tích hợp HRIS/Leave Portal, assistant không được tự tính hoặc giả lập số dư phép cá nhân.

## System Action Boundary Matrix — Derived View

> Bảng này là view phân tích từ `Runtime-Revised Canonical Scenario Registry`, không phải source-of-truth độc lập.

| # | scenario | assistant_role | max_system_action | condition |
|---:|---|---|---|---|
| 1 | Hỏi số ngày phép năm theo chính sách | ANSWER | NONE | Trả lời từ KB |
| 2 | Hướng dẫn tạo đơn nghỉ phép thường | GUIDE | LINK_ONLY | Có Forms Registry/instruction; không đưa fake HR Portal URL |
| 3 | Nghỉ khẩn cấp trong ngày | GUIDE | LINK_ONLY | Ưu tiên liên hệ manager trước |
| 4 | Leave exception, thiếu số dư phép | HUMAN_FIRST | PREFILL_DRAFT | Draft cho trao đổi manager/HRBP, không submit tự động |
| 5 | Nghỉ ốm thông thường | GUIDE | LINK_ONLY | Không thu thông tin y tế chi tiết |
| 6 | Nghỉ thai sản/cha mẹ | PREPARE_AND_HANDOFF | CREATE_CASE | Chỉ case bảo mật cho C&B |
| 7 | Nghỉ không lương | HUMAN_FIRST | PREFILL_DRAFT | Chuẩn bị nội dung gặp manager/HRBP |
| 8 | Hỏi lịch nghỉ lễ | ANSWER | NONE | KB only |
| 9 | Manager chưa duyệt đơn nghỉ | GUIDE | READ_STATUS | Chỉ nếu có portal status integration |
| 10 | Hủy hoặc đổi đơn nghỉ đã duyệt | GUIDE | LINK_ONLY | `CREATE_REQUEST` chỉ khi portal hỗ trợ amendment |
| 11 | Quên chấm công | GUIDE | LINK_ONLY | `CREATE_REQUEST` sau khi có attendance workflow |
| 12 | Đi trễ | GUIDE | PREFILL_DRAFT | Draft báo manager nếu cần |
| 13 | Lỗi check-in khi WFH | GUIDE | CREATE_CASE | Case HR Ops/IT nếu policy cho phép |
| 14 | Đăng ký OT trước khi làm | GUIDE | LINK_ONLY | `CREATE_REQUEST` chỉ với OT workflow |
| 15 | Hỏi cách tính OT | ANSWER | NONE | Không tính payroll cá nhân |
| 16 | Đổi ca/lịch làm việc | HUMAN_FIRST | PREFILL_DRAFT | Draft trao đổi manager |
| 17 | Đơn bổ sung công bị từ chối | PREPARE_AND_HANDOFF | CREATE_CASE | HR Ops/HRBP case |
| 18 | Vắng mặt không báo trước | HUMAN_FIRST | PREFILL_DRAFT | Không tạo disciplinary workflow |
| 19 | Xem payslip | GUIDE | LINK_ONLY | `READ_STATUS`/read payslip chỉ khi có payroll RBAC |
| 20 | Payroll discrepancy | PREPARE_AND_HANDOFF | CREATE_CASE | C&B confidential payroll case |
| 21 | Đổi tài khoản ngân hàng nhận lương | GUIDE | LINK_ONLY | Không nhập full account vào chat |
| 22 | Hỏi chứng từ thuế TNCN | GUIDE | LINK_ONLY | Case nếu chứng từ thiếu |
| 23 | Hỏi thời điểm thưởng | ANSWER | NONE | Không đọc bonus cá nhân |
| 24 | Hỏi điều kiện phụ cấp | ANSWER | NONE | Nếu cá nhân hóa thì handoff C&B |
| 25 | Claim bảo hiểm sức khỏe | GUIDE | LINK_ONLY | Không upload hồ sơ qua chat |
| 26 | Đăng ký người phụ thuộc/bảo hiểm | GUIDE | LINK_ONLY | Secure form only |
| 27 | Hỏi khoản khấu trừ trong lương | PREPARE_AND_HANDOFF | CREATE_CASE | C&B case |
| 28 | Thiếu giấy tờ onboarding | GUIDE | CREATE_CASE | HR Ops case nếu missing docs |
| 29 | Probation sang chính thức | HUMAN_FIRST | PREFILL_DRAFT | Không đọc/kết luận trạng thái nếu chưa có quyền |
| 30 | Probation extension concern | HUMAN_FIRST | CREATE_CASE | HRBP/ER case nếu employee cần hỗ trợ |
| 31 | Gia hạn hợp đồng | HUMAN_FIRST | PREFILL_DRAFT | Không tạo contract change |
| 32 | Contract changes | HUMAN_FIRST | PREFILL_DRAFT | Handoff HRBP/Legal |
| 33 | Employee transfer | HUMAN_FIRST | PREFILL_DRAFT | Handoff HRBP/internal mobility |
| 34 | Đổi thông tin hồ sơ cá nhân | GUIDE | LINK_ONLY | `CREATE_REQUEST` chỉ với HRIS profile integration |
| 35 | Đổi emergency contact | GUIDE | LINK_ONLY | HRIS profile form |
| 36 | Resignation | HUMAN_FIRST | PREFILL_DRAFT | `CREATE_REQUEST` chỉ sau explicit employee confirmation và policy-defined resignation form |
| 37 | Exit handover | GUIDE | LINK_ONLY | `READ_STATUS` nếu offboarding checklist integrated |
| 38 | Final settlement | PREPARE_AND_HANDOFF | CREATE_CASE | C&B/Finance case |
| 39 | KPI goal clarification | GUIDE | PREFILL_DRAFT | Draft câu hỏi cho manager |
| 40 | KPI dispute | HUMAN_FIRST | CREATE_CASE | HRBP/ER case, không tự sửa rating |
| 41 | Quy trình performance review | ANSWER | NONE | KB only |
| 42 | Promotion/salary review | HUMAN_FIRST | PREFILL_DRAFT | Không tạo salary workflow tự động |
| 43 | Development plan | GUIDE | PREFILL_DRAFT | Draft career conversation |
| 44 | Đăng ký khóa đào tạo | GUIDE | LINK_ONLY | `CREATE_REQUEST` chỉ với LMS |
| 45 | Training budget/chứng chỉ | PREPARE_AND_HANDOFF | CREATE_CASE | L&D/Finance case |
| 46 | Internal job application | GUIDE | LINK_ONLY | `CREATE_REQUEST` nếu ATS integration |
| 47 | WFH request thường lệ | GUIDE | LINK_ONLY | `CREATE_REQUEST` nếu WFH workflow |
| 48 | WFH exception | HUMAN_FIRST | PREFILL_DRAFT | HRBP handoff nếu cần |
| 49 | Cấp thiết bị làm việc | GUIDE | CREATE_REQUEST | Chỉ với ITSM/Admin integration |
| 50 | Access badge/văn phòng | GUIDE | CREATE_REQUEST | Không tự cấp quyền, chỉ request |
| 51 | Manager conflict | HUMAN_FIRST | CREATE_CASE | Confidential HRBP/ER handoff |
| 52 | Harassment/discrimination concern | HUMAN_FIRST | CREATE_CASE | Confidential ER/Legal/hotline handoff |
| 53 | Hỏi grievance policy | ANSWER | NONE | KB only |
| 54 | Formal grievance submission | PREPARE_AND_HANDOFF | CREATE_CASE | Confidential ER case |
| 55 | Disciplinary action notice | HUMAN_FIRST | PREFILL_DRAFT | Handoff meeting, không workflow tự động |
| 56 | Conflict of interest/ethics | PREPARE_AND_HANDOFF | CREATE_CASE | Ethics/Legal channel |
| 57 | Stress/burnout/mental health support | HUMAN_FIRST | LINK_ONLY | Handoff EAP/HRBP/hotline theo policy |
| 58 | Workplace safety incident | HUMAN_FIRST | LINK_ONLY | Emergency/safety channel trước |
| 59 | Business trip advance | GUIDE | LINK_ONLY | `CREATE_REQUEST` nếu finance workflow |
| 60 | Expense reimbursement | GUIDE | LINK_ONLY | Expense system |
| 61 | Reference letter/employment confirmation | GUIDE | CREATE_REQUEST | HR Ops document request |
| 62 | Data privacy/access correction request | PREPARE_AND_HANDOFF | CREATE_CASE | Privacy/Legal case |
| 63 | Change reporting line/supervisor | HUMAN_FIRST | PREFILL_DRAFT | HRBP conversation |
| 64 | Immigration/work permit/visa support | PREPARE_AND_HANDOFF | CREATE_CASE | Legal/HR Ops confidential case |

## Normalized RACI And Decision Ownership

Nguyên tắc chuẩn hóa:

- Mỗi decision chỉ có một `A` duy nhất.
- Nếu workflow có nhiều quyết định, tách thành sub-decision.
- Assistant không bao giờ là `A`; tối đa là `C` hoặc công cụ ghi nhận/handoff.

| decision | accountable/final owner | responsible | consulted | informed | notes |
|---|---|---|---|---|---|
| Leave schedule approve/reject | Line Manager | Line Manager | Employee | HR Ops/C&B nếu cần | Quyết định theo vận hành đội |
| Leave balance calculation | C&B | C&B | HR Ops | Employee/Manager | Source-of-truth là leave/payroll system |
| Leave exception approval | HRBP | HRBP | Line Manager, C&B | Employee | Nếu policy giao C&B duyệt exception tài chính thì tách sub-decision riêng |
| Attendance correction fact confirmation | Line Manager | Line Manager | Employee | HR Ops | Manager xác nhận có làm việc |
| Attendance system update | HR Ops | HR Ops | Line Manager, C&B nếu payroll cutoff | Employee | HR Ops không tự xác nhận sự kiện công việc |
| OT business need approval | Line Manager | Line Manager | Employee | HR Ops/C&B | Trước khi OT |
| OT payroll treatment | C&B | C&B | Line Manager, Finance nếu cần | Employee | C&B tính theo rule và approved OT |
| WFH normal approval | Line Manager | Line Manager | Employee | HR Ops | Theo policy |
| WFH exception approval | HRBP | HRBP | Line Manager, Legal nếu nhạy cảm | Employee | Không để assistant tự phân xử |
| Payroll discrepancy resolution | C&B | C&B | Line Manager nếu liên quan công/OT, Finance nếu payment | Employee | C&B kết luận nghiệp vụ payroll |
| Insurance eligibility support | C&B | C&B | Insurer | Employee | Insurer có thể là final payer cho claim |
| Probation performance recommendation | Line Manager | Line Manager | Employee | HRBP | Manager đề xuất, chưa phải final employment action |
| Probation employment decision | HRBP | HRBP | Line Manager, Legal/ER nếu fail/extend rủi ro | HR Ops, Employee | HRBP bảo đảm fairness/process |
| HRIS lifecycle update | HR Ops | HR Ops | HRBP | Employee/Manager | Thực thi sau quyết định đã duyệt |
| KPI rating proposal | Line Manager | Line Manager | Employee | HRBP | Manager chịu trách nhiệm đánh giá ban đầu |
| KPI cycle governance | HRBP | HRBP | Business leader | Employees/Managers | HRBP quản trị process |
| KPI dispute outcome | HRBP | HRBP | Line Manager, ER nếu conflict | Employee | Committee có thể là A nếu policy lập committee |
| Promotion readiness recommendation | Line Manager | Line Manager | HRBP | Employee | Manager đề xuất |
| Promotion/salary review final approval | Business leader | Business leader | HRBP, C&B, Finance | HR Ops, Employee | C&B không tự duyệt tăng lương |
| Salary band/equity recommendation | C&B | C&B | HRBP, Finance | Business leader | Sub-decision chuyên môn C&B |
| Resignation submission | Employee | Employee | Line Manager/HRBP | HR Ops | Employee quyết định nộp |
| Last working day/notice exception | HRBP | HRBP | Line Manager, Legal nếu cần | Employee, HR Ops | Không để manager đơn phương miễn notice nếu rủi ro |
| Offboarding task completion | HR Ops | HR Ops | IT/Admin/C&B/Manager | Employee | Điều phối checklist |
| Asset/access revocation | IT/Admin | IT/Admin | HR Ops, Manager | Employee nếu cần | Theo offboarding trigger |
| Final settlement calculation | C&B | C&B | Finance, HR Ops | Employee | Finance hỗ trợ payment control |
| Grievance triage | ER | ER | HRBP/Legal nếu cần | Employee | Confidential |
| Investigation finding | ER | ER | Legal, involved manager only if appropriate | HRBP/Leadership theo need-to-know | Access restricted |
| Disciplinary final decision | Disciplinary committee chair | ER | Legal, Line Manager, HRBP | Employee | Policy phải chỉ định chair/owner cụ thể cho mỗi case |
| Training enrollment approval | Line Manager | Line Manager | L&D | Employee | Nếu khóa miễn phí/open thì L&D có thể auto-enroll |
| Training budget approval | L&D | L&D | Line Manager, Finance | Employee | Finance kiểm soát ngân sách |
| Internal job selection | Hiring Manager | Hiring Manager | TA, HRBP | Candidate/Current manager theo policy | TA điều phối process |
| Profile data correction | HR Ops | HR Ops | Employee, Legal nếu privacy | Employee | Source-of-truth là HRIS |
| Bank account update acceptance | C&B | C&B | Employee | Payroll | Qua kênh bảo mật |
| Privacy/data access decision | Legal | Legal | HR Ops | Employee | Tùy policy có DPO/Privacy owner |
| Work permit/visa decision | Legal | Legal | HR Ops, external counsel nếu có | Employee/Manager | Không xử lý qua chat |

## MVP Service Scope Derived From Business Model

MVP nên ưu tiên các service có source-of-truth là KB hoặc workflow đơn giản, ít nhạy cảm, ít rủi ro quyết định cá nhân.

| Scope | Service | Assistant role/action | Lý do chọn |
|---|---|---|---|
| MVP core | Policy/FAQ Q&A cho leave, attendance, OT, WFH, performance timeline, grievance policy | `ANSWER` + `NONE` | Giá trị cao, rủi ro thấp nếu KB chuẩn |
| MVP core | Hướng dẫn form/portal cho leave, attendance correction, OT, WFH, payslip, insurance claim, expense, training | `GUIDE` + `LINK_ONLY` | Giảm câu hỏi lặp lại mà không thay hệ thống nguồn |
| MVP core | HR directory, owner, SLA, escalation path | `ANSWER` + `NONE` | Giúp employee biết hỏi ai |
| MVP controlled | Payroll discrepancy draft | `PREPARE_AND_HANDOFF` + `CREATE_CASE` hoặc draft case | Cần C&B, nhưng có thể triage tốt |
| MVP controlled | Insurance claim support | `GUIDE` + `LINK_ONLY`; case C&B nếu thiếu thông tin | Có checklist rõ, dữ liệu nhạy cảm phải giữ ngoài chat |
| MVP controlled | Grievance/manager conflict confidential handoff | `HUMAN_FIRST`/`PREPARE_AND_HANDOFF` + `CREATE_CASE` theo policy | Giá trị cao nhưng cần guardrail chặt |
| MVP later | Read leave balance/payslip/status | `READ_STATUS` | Chỉ sau khi có HRIS/payroll integration và RBAC |
| MVP later | Create leave/OT/WFH request trực tiếp | `CREATE_REQUEST` | Chỉ sau khi workflow và approval được mô hình hóa |
| Out of MVP | Probation decision, promotion/salary approval, KPI dispute outcome, disciplinary outcome, contract changes, resignation acceptance | Human-owned | Quyết định con người/compliance, không tự động hóa |

## Data Architecture Canonicalization

Từ đây trở đi, tài liệu dùng các nguồn canonical sau:

- `Runtime-Revised Canonical Scenario Registry` là source-of-truth duy nhất cho physical schema, seed data, boundary/router behavior và evaluation.
- `Canonical Scenario Registry` conceptual bên dưới chỉ là design history, không dùng để derive schema/runtime.
- `Normalized RACI And Decision Ownership` là source-of-truth duy nhất cho decision ownership.
- `Employee-HR Interaction Boundary Matrix`, `Data Dependency Matrix` và `System Action Boundary Matrix` ở trên là derived views.
- `Manager-HR Operational Matrix` là baseline vận hành của V-Nova; SLA trong bảng là operating assumptions mặc định và sau này cần configurable theo tenant/service.

## Canonical Scenario Schema

```text
canonical_scenario {
  scenario_id
  scenario_name
  service_domain
  employee_intent
  normal_first_action
  assistant_role: ANSWER | GUIDE | PREPARE_AND_HANDOFF | HUMAN_FIRST
  data_dependency: KNOWLEDGE_ONLY | EMPLOYEE_PROFILE | TRANSACTIONAL | MANAGER_DECISION | HR_CASE | EXTERNAL_SYSTEM
  source_of_truth
  max_system_action: NONE | LINK_ONLY | PREFILL_DRAFT | CREATE_REQUEST | CREATE_CASE | READ_STATUS
  human_interaction_required
  sensitivity
  final_decision_owner
  allowed_data_collection
  expected_handoff
  mvp_phase: MVP_1 | MVP_2 | FUTURE | OUT_OF_MVP
}
```

## Canonical Scenario Registry — Deprecated Design History

> Registry conceptual này đã được thay thế bởi `Runtime-Revised Canonical Scenario Registry`. Chỉ giữ lại để giải thích lịch sử thiết kế; không dùng cho physical schema, seed data, boundary/router behavior hoặc evaluation.

| id | scenario | domain | role | data | source_of_truth | action | final owner | sensitivity | phase |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | Hỏi số ngày phép năm theo chính sách | Leave | ANSWER | KNOWLEDGE_ONLY | KB | NONE | C&B policy owner | Low | MVP_1 |
| 2 | Hướng dẫn tạo đơn nghỉ phép thường | Leave | GUIDE | TRANSACTIONAL | HRIS/Leave Portal | LINK_ONLY | Line Manager | Low | MVP_1 |
| 3 | Nghỉ khẩn cấp trong ngày | Leave | GUIDE | MANAGER_DECISION | Manager + Leave Portal | LINK_ONLY | Line Manager | Medium | MVP_1 |
| 4 | Leave exception, thiếu số dư phép | Leave | HUMAN_FIRST | HR_CASE | Manager + HRBP/C&B | PREFILL_DRAFT | HRBP | Medium | FUTURE |
| 5 | Nghỉ ốm thông thường | Leave | GUIDE | TRANSACTIONAL | Leave Portal + C&B | LINK_ONLY | C&B | Medium | MVP_1 |
| 6 | Nghỉ thai sản/cha mẹ | Leave/Benefits | PREPARE_AND_HANDOFF | HR_CASE | C&B + HRIS | CREATE_CASE | C&B | High | FUTURE |
| 7 | Nghỉ không lương | Leave/Lifecycle | HUMAN_FIRST | HR_CASE | Manager + HRBP | PREFILL_DRAFT | HRBP | Medium | FUTURE |
| 8 | Hỏi lịch nghỉ lễ | Leave | ANSWER | KNOWLEDGE_ONLY | KB | NONE | HR Ops | Low | MVP_1 |
| 9 | Manager chưa duyệt đơn nghỉ | Leave | GUIDE | TRANSACTIONAL | Leave Portal + Manager | READ_STATUS | Line Manager | Low | FUTURE |
| 10 | Hủy hoặc đổi đơn nghỉ đã duyệt | Leave | GUIDE | TRANSACTIONAL | Leave Portal | LINK_ONLY | Line Manager | Low | MVP_1 |
| 11 | Quên chấm công | Attendance | GUIDE | TRANSACTIONAL | Attendance System | LINK_ONLY | Line Manager | Low | MVP_1 |
| 12 | Đi trễ | Attendance | GUIDE | MANAGER_DECISION | Manager + Attendance | PREFILL_DRAFT | Line Manager | Low | MVP_1 |
| 13 | Lỗi check-in khi WFH | Attendance/IT | GUIDE | EXTERNAL_SYSTEM | Attendance + IT logs | CREATE_CASE | HR Ops | Medium | MVP_2 |
| 14 | Đăng ký OT trước khi làm | OT | GUIDE | MANAGER_DECISION | Manager + OT Portal | LINK_ONLY | Line Manager | Low | MVP_1 |
| 15 | Hỏi cách tính OT | OT/Payroll | ANSWER | KNOWLEDGE_ONLY | KB | NONE | C&B | Low | MVP_1 |
| 16 | Đổi ca/lịch làm việc | Attendance | HUMAN_FIRST | MANAGER_DECISION | Manager | PREFILL_DRAFT | Line Manager | Medium | FUTURE |
| 17 | Đơn bổ sung công bị từ chối | Attendance | PREPARE_AND_HANDOFF | HR_CASE | Attendance + HR Ops/HRBP | CREATE_CASE | HR Ops | Medium | MVP_2 |
| 18 | Vắng mặt không báo trước | Attendance/ER | HUMAN_FIRST | HR_CASE | Manager + HRBP/ER | PREFILL_DRAFT | HRBP | High | OUT_OF_MVP |
| 19 | Xem payslip | Payroll | GUIDE | EXTERNAL_SYSTEM | Payroll Portal | LINK_ONLY | C&B | Medium | MVP_1 |
| 20 | Payroll discrepancy | Payroll | PREPARE_AND_HANDOFF | HR_CASE | Payroll + C&B | CREATE_CASE | C&B | High | MVP_2 |
| 21 | Đổi tài khoản ngân hàng nhận lương | Payroll/Profile | GUIDE | EMPLOYEE_PROFILE | HRIS/Payroll | LINK_ONLY | C&B | High | MVP_1 |
| 22 | Hỏi chứng từ thuế TNCN | Payroll/Tax | GUIDE | TRANSACTIONAL | Payroll/Tax Portal | LINK_ONLY | C&B | Medium | MVP_1 |
| 23 | Hỏi thời điểm thưởng | Compensation | ANSWER | KNOWLEDGE_ONLY | KB/C&B announcement | NONE | C&B | Medium | MVP_1 |
| 24 | Hỏi điều kiện phụ cấp | Compensation | ANSWER | KNOWLEDGE_ONLY | KB | NONE | C&B | Medium | MVP_1 |
| 25 | Claim bảo hiểm sức khỏe | Benefits | GUIDE | EXTERNAL_SYSTEM | Insurer Portal + C&B | LINK_ONLY | C&B | High | MVP_1 |
| 26 | Đăng ký người phụ thuộc/bảo hiểm | Benefits/Profile | GUIDE | EMPLOYEE_PROFILE | HRIS/C&B Secure Form | LINK_ONLY | C&B | High | MVP_1 |
| 27 | Hỏi khoản khấu trừ trong lương | Payroll | PREPARE_AND_HANDOFF | HR_CASE | Payroll + C&B | CREATE_CASE | C&B | High | MVP_2 |
| 28 | Thiếu giấy tờ onboarding | Onboarding | GUIDE | TRANSACTIONAL | HRIS/Onboarding Checklist | CREATE_CASE | HR Ops | Medium | MVP_2 |
| 29 | Probation sang chính thức | Lifecycle | HUMAN_FIRST | MANAGER_DECISION | Manager + HRBP + HRIS | PREFILL_DRAFT | HRBP | High | OUT_OF_MVP |
| 30 | Probation extension concern | Lifecycle/ER | HUMAN_FIRST | HR_CASE | HRBP/ER | CREATE_CASE | HRBP | High | OUT_OF_MVP |
| 31 | Gia hạn hợp đồng | Lifecycle | HUMAN_FIRST | HR_CASE | HRBP + HR Ops | PREFILL_DRAFT | HRBP | High | OUT_OF_MVP |
| 32 | Contract changes | Lifecycle | HUMAN_FIRST | HR_CASE | HRBP + Legal + HRIS | PREFILL_DRAFT | HRBP | High | OUT_OF_MVP |
| 33 | Employee transfer | Lifecycle/Internal Mobility | HUMAN_FIRST | HR_CASE | HRBP + Business leaders + TA | PREFILL_DRAFT | Business leader | High | OUT_OF_MVP |
| 34 | Đổi thông tin hồ sơ cá nhân | Profile | GUIDE | EMPLOYEE_PROFILE | HRIS Profile | LINK_ONLY | HR Ops | Medium | MVP_1 |
| 35 | Đổi emergency contact | Profile | GUIDE | EMPLOYEE_PROFILE | HRIS Profile | LINK_ONLY | HR Ops | Medium | MVP_1 |
| 36 | Resignation | Offboarding | HUMAN_FIRST | HR_CASE | Employee submission + HRBP/HR Ops | PREFILL_DRAFT | HRBP | High | OUT_OF_MVP |
| 37 | Exit handover | Offboarding | GUIDE | TRANSACTIONAL | Offboarding Checklist + Manager | LINK_ONLY | HR Ops | Medium | MVP_1 |
| 38 | Final settlement | Offboarding/Payroll | PREPARE_AND_HANDOFF | HR_CASE | Payroll + C&B + Finance | CREATE_CASE | C&B | High | FUTURE |
| 39 | KPI goal clarification | Performance | GUIDE | MANAGER_DECISION | Manager + Performance System | PREFILL_DRAFT | Line Manager | Medium | MVP_1 |
| 40 | KPI dispute | Performance/ER | HUMAN_FIRST | HR_CASE | Performance System + HRBP/ER | CREATE_CASE | HRBP | High | OUT_OF_MVP |
| 41 | Quy trình performance review | Performance | ANSWER | KNOWLEDGE_ONLY | KB | NONE | HRBP | Low | MVP_1 |
| 42 | Promotion/salary review | Career/Compensation | HUMAN_FIRST | MANAGER_DECISION | Manager + HRBP/C&B | PREFILL_DRAFT | Business leader | High | OUT_OF_MVP |
| 43 | Development plan | L&D/Career | GUIDE | MANAGER_DECISION | Manager + L&D | PREFILL_DRAFT | Line Manager | Medium | MVP_1 |
| 44 | Đăng ký khóa đào tạo | L&D | GUIDE | TRANSACTIONAL | LMS | LINK_ONLY | L&D | Low | MVP_1 |
| 45 | Training budget/chứng chỉ | L&D/Finance | PREPARE_AND_HANDOFF | HR_CASE | L&D + Manager + Finance | CREATE_CASE | L&D | Medium | MVP_2 |
| 46 | Internal job application | TA/Internal Mobility | GUIDE | TRANSACTIONAL | ATS/Internal Job Board | LINK_ONLY | Hiring Manager | Medium | MVP_1 |
| 47 | WFH request thường lệ | WFH | GUIDE | MANAGER_DECISION | Manager + WFH Portal | LINK_ONLY | Line Manager | Low | MVP_1 |
| 48 | WFH exception | WFH | HUMAN_FIRST | HR_CASE | Manager + HRBP | PREFILL_DRAFT | HRBP | Medium/High | FUTURE |
| 49 | Cấp thiết bị làm việc | IT/Admin | GUIDE | EXTERNAL_SYSTEM | IT/Admin System | CREATE_REQUEST | IT/Admin | Low | FUTURE |
| 50 | Access badge/văn phòng | Admin/Security | GUIDE | EXTERNAL_SYSTEM | Admin/Security System | CREATE_REQUEST | Admin/Security | Medium | FUTURE |
| 51 | Manager conflict | ER | HUMAN_FIRST | HR_CASE | HRBP/ER | CREATE_CASE | ER | High | FUTURE |
| 52 | Harassment/discrimination concern | ER/Legal | HUMAN_FIRST | HR_CASE | ER/Legal/Hotline | CREATE_CASE | ER | Critical | FUTURE |
| 53 | Hỏi grievance policy | ER | ANSWER | KNOWLEDGE_ONLY | KB | NONE | ER | Medium | MVP_1 |
| 54 | Formal grievance submission | ER | PREPARE_AND_HANDOFF | HR_CASE | ER Case System | CREATE_CASE | ER | Critical | FUTURE |
| 55 | Disciplinary action notice | ER/Legal | HUMAN_FIRST | HR_CASE | ER/Legal | PREFILL_DRAFT | ER | Critical | OUT_OF_MVP |
| 56 | Conflict of interest/ethics | ER/Legal | PREPARE_AND_HANDOFF | HR_CASE | ER/Legal/Ethics Channel | CREATE_CASE | Legal | High | FUTURE |
| 57 | Stress/burnout/mental health support | HRBP/ER | HUMAN_FIRST | HR_CASE | HRBP/EAP/Hotline | LINK_ONLY | HRBP | Critical | MVP_1 |
| 58 | Workplace safety incident | Safety/Admin | HUMAN_FIRST | HR_CASE | Safety/Admin/Legal | LINK_ONLY | Safety/Admin | Critical | MVP_1 |
| 59 | Business trip advance | Finance | GUIDE | TRANSACTIONAL | Finance System + Manager | LINK_ONLY | Finance | Medium | MVP_1 |
| 60 | Expense reimbursement | Finance | GUIDE | TRANSACTIONAL | Expense System | LINK_ONLY | Finance | Medium | MVP_1 |
| 61 | Reference letter/employment confirmation | HR Ops | GUIDE | EMPLOYEE_PROFILE | HRIS + HR Ops | CREATE_REQUEST | HR Ops | Medium | FUTURE |
| 62 | Data privacy/access correction request | Privacy | PREPARE_AND_HANDOFF | HR_CASE | HR Ops/Legal | CREATE_CASE | Legal | High | FUTURE |
| 63 | Change reporting line/supervisor | Org | HUMAN_FIRST | HR_CASE | HRBP + Business leader | PREFILL_DRAFT | Business leader + HRBP | High | OUT_OF_MVP |
| 64 | Immigration/work permit/visa support | Legal/HR Ops | PREPARE_AND_HANDOFF | HR_CASE | Legal + HR Ops | CREATE_CASE | Legal | High | FUTURE |

## Conceptual ERD

```text
Identity & Organization
  employee -> organization_unit
  employee -> position
  reporting_relationship: manager employee -> subordinate employee
  hr_department -> service_owner

HR Service Catalog
  hr_service -> scenario
  scenario -> boundary_rule
  scenario -> allowed_data_field
  scenario -> allowed_action
  hr_service -> service_owner
  hr_service -> sla

Knowledge
  knowledge_document -> document_version -> knowledge_chunk
  knowledge_document -> applicability
  knowledge_document -> legal_basis
  knowledge_document -> hr_service

Case / Handoff
  hr_case -> case_type
  hr_case -> scenario
  hr_case -> handoff
  hr_case -> case_assignment
  hr_case -> case_event
  hr_case -> case_note
  hr_case -> sla_tracking

Workflow / Decision
  request -> approval -> approval_step
  request -> task
  request -> decision_record
  request -> status_history

Audit / Security
  audit_event -> actor employee/profile
  audit_event -> entity_type/entity_id
  access_scope -> role/department/sensitivity
  sensitivity -> scenario/document/case/comment
```

Conceptual MVP decision:

- MVP-1 không cần `request`, `approval`, `approval_step`, `task`, `decision_record`, `status_history` vì chưa làm direct `CREATE_REQUEST` hoặc `READ_STATUS`.
- MVP-2 cần `hr_case` nhưng không dùng `tickets` làm catch-all. `tickets` chỉ có thể giữ tạm như compatibility layer hoặc deprecated view.
- `policy`, `SOP`, `FAQ` không cần là bảng riêng ở MVP; dùng `knowledge_document.doc_type`. Chỉ tách bảng riêng nếu sau này cần lifecycle riêng cho từng loại tài liệu.

## Entity Dictionary

| entity | business reason | scenario cần | source-of-truth | phase | PII/sensitivity | relationships |
|---|---|---|---|---|---|---|
| employee | Định danh người dùng, employment context tối thiểu, RBAC | Tất cả scenario cá nhân, conversation, handoff | Auth/HRIS | MVP_1 | PII Medium | profile/user, org unit, position, reporting |
| organization_unit | Phòng ban/business unit để route và scope manager | Leave, transfer, reporting line, HRBP routing | HRIS/org master | FUTURE | Low | employee, service_owner |
| position | Chức danh/job family để applicability policy | Leave, benefits, promotion, transfer | HRIS | FUTURE | Medium | employee, applicability |
| reporting_relationship | Manager-subordinate chính thức | Leave, attendance, OT, WFH, KPI, resignation | HRIS/org master | MVP_1 minimal | Medium | employee to employee |
| hr_department | Chuẩn hóa HR Ops, C&B, HRBP, TA, L&D, ER, Finance, Legal, IT/Admin | Routing mọi handoff | Operating model config | MVP_1 | Low | service_owner, case_assignment |
| hr_service | Danh mục service theo domain/owner/SLA | Tất cả scenario | Service catalog | MVP_1 | Low | scenario, owner, SLA, KB docs |
| scenario | Runtime registry canonical 64 scenario | Tất cả scenario | Runtime-Revised Canonical Scenario Registry | MVP_1 | Low to Critical | service, boundary_rule, case/request |
| boundary_rule | Quyết định role/action/data dependency theo scenario | Tất cả scenario | Product policy | MVP_1 | Low | scenario, allowed_action, allowed_data |
| service_owner | Owner nghiệp vụ cho service | Routing/handoff/SLA | Operating model | MVP_1 | Low | hr_service, hr_department |
| sla | Baseline SLA configurable theo service | Operational matrix | V-Nova baseline config | MVP_1 | Low | hr_service, hr_case/sla_tracking |
| sensitivity | Phân loại Low/Medium/High/Critical | Tất cả scenario/case/doc | Security policy | MVP_1 | Low | scenario, case, document, access_scope |
| allowed_action | Giới hạn NONE/LINK_ONLY/PREFILL_DRAFT/CREATE_CASE... | Tất cả scenario | Boundary policy | MVP_1 | Low | boundary_rule |
| allowed_data_field | Data minimization per scenario | Profile/payroll/ER cases | Privacy policy | MVP_1 | Medium/High | scenario, case intake |
| knowledge_document | Tài liệu nội bộ user-facing/offline compliance | ANSWER/GUIDE | Document admin | MVP_1 | Low to High | version, chunk, service |
| document_version | Version/effective/status cho KB | Citation/versioning | Document admin | MVP_1 | Low | knowledge_document |
| knowledge_chunk | Retrieval evidence | ANSWER/GUIDE | Chroma/vector index mirror | MVP_1 | Depends on doc | document_version |
| applicability | Điều kiện áp dụng policy theo employee group | Leave, benefit, WFH, OT | Policy owner | MVP_1 | Low/Medium | document/service/position |
| legal_basis | Traceability compliance, không user-facing mặc định | Policy authoring | Law archive/compliance | MVP_1 | Low | document_version |
| case_type | Loại case administrative | Payroll, attendance dispute, onboarding docs | Service catalog | MVP_2 | Medium/High | hr_case |
| hr_case | Case handoff thay cho generic ticket | MVP-2 admin cases | Case management | MVP_2 | Medium/High | scenario, requester, assignment |
| handoff | Kết quả route từ assistant sang owner | PREPARE_AND_HANDOFF/HUMAN_FIRST | Boundary engine | MVP_2 | Medium/High | hr_case, service_owner |
| case_event | Audit timeline cho case | MVP-2 cases | Case management | MVP_2 | Medium/High | hr_case |
| case_assignment | Ai đang xử lý case | MVP-2 cases | Case management | MVP_2 | Medium | hr_case, employee/hr_department |
| case_note | Ghi chú có kiểm soát, thay cho chat tự do nhạy cảm | MVP-2 cases | Case management | MVP_2 | High/Critical | hr_case, access_scope |
| sla_tracking | Theo dõi due/escalation cho case | MVP-2 cases | SLA config + case events | MVP_2 | Medium | hr_case, sla |
| audit_event | Trace hành động và truy cập | Tất cả sensitive/action | System audit | MVP_1 | Medium/High | actor, entity |
| access_scope | RBAC/ABAC theo role, department, sensitivity | Sensitive case/doc | Security model | MVP_1 basic, MVP_2 stronger | High | role, employee, case/doc |
| request | Giao dịch HR tự động như leave/OT/WFH | Direct CREATE_REQUEST | HRIS/workflow | FUTURE | Medium/High | scenario, approval, task |
| approval | Container phê duyệt workflow | Leave/OT/WFH future | Workflow engine | FUTURE | Medium | request |
| approval_step | Từng bước duyệt | Workflow future | Workflow engine | FUTURE | Medium | approval |
| task | Task offboarding/IT/Admin | Offboarding/equipment future | Workflow/ITSM | FUTURE | Medium | request |
| decision_record | Ghi nhận quyết định final owner | Probation/KPI/promotion future | Human decision owner | FUTURE | High/Critical | request/case |
| status_history | Lịch sử trạng thái request/case | READ_STATUS future | Workflow/case system | FUTURE | Medium | request/case |

Entities loại khỏi MVP schema riêng:

- `policy`, `SOP`, `FAQ`: dùng `knowledge_document.doc_type` thay vì bảng riêng.
- `position` và `organization_unit`: giữ ở mức field/config nếu chưa có HRIS integration.
- `request`, `approval`, `approval_step`, `task`, `decision_record`, `status_history`: để future vì MVP-1/2 chưa cho direct transaction.

## Existing DB To Proposed DB Gap Analysis

| current table | decision | map to proposed | gap |
|---|---|---|---|
| `users` | KEEP | identity auth user | SQLAlchemy model có `users`, Supabase migration đang dùng `auth.users`; cần chốt một auth strategy |
| `profiles` | EXTEND | `employee` | Thiếu org unit chuẩn hóa, position, HR department membership, richer access scope |
| `conversations` | KEEP | conversation/session | Phục vụ chat UX, không phải HR business object |
| `messages` | EXTEND | message + audit input | Cần link tới scenario_id, boundary decision, action boundary; tránh lưu PII nhạy cảm |
| `chat_requests` | EXTEND | assistant request processing | Có trong model/runtime nhưng chưa có migration SQL; cần thêm boundary_result fields |
| `tickets` | REPLACE | `hr_case` hoặc compatibility view | Generic catch-all không đủ case_type, scenario, SLA, sensitivity, assignment/audit/privacy |
| `documents` | EXTEND | `knowledge_document` + `document_version` tối giản | Cần doc_type, visibility, service_id, applicability, version normalized, legal_basis link |
| `ingestion_jobs` | KEEP | ingestion job | Có trong model, chưa có migration SQL; phù hợp pipeline admin |
| `index_jobs` | KEEP | index job | Có trong model, chưa có migration SQL; phù hợp vector rebuild |
| `evaluation_runs` | KEEP | evaluation run | Có trong model, chưa có migration SQL; không thuộc HR operating model nhưng cần QA |

Quan sát kỹ thuật:

- Supabase SQL migration hiện có chỉ tạo `profiles`, `conversations`, `messages`, `tickets`, `documents`.
- Backend SQLAlchemy model có thêm `users`, `chat_requests`, `ingestion_jobs`, `index_jobs`, `evaluation_runs`.
- Trước migration thật cần reconciliation giữa migration SQL và SQLAlchemy metadata, tránh môi trường local tự `create_all` khác production Supabase.

## MVP-1 Tables

MVP-1 chỉ hỗ trợ `ANSWER`, `GUIDE`, `PREFILL_DRAFT`, `LINK_ONLY`. Không đọc trạng thái cá nhân, không tạo request giao dịch, không tạo confidential ER case.

| table | purpose | note |
|---|---|---|
| `users` hoặc Supabase `auth.users` | Auth identity | Chọn một strategy |
| `employees` hoặc extended `profiles` | Employee context tối thiểu | Có manager_id, role, department text nếu chưa chuẩn hóa |
| `hr_departments` | Danh mục HR Ops/C&B/HRBP/TA/L&D/ER/Finance/Legal/IT/Admin | Config nhỏ |
| `hr_services` | Service catalog | Domain, owner, baseline SLA, sensitivity |
| `scenarios` | Runtime-Revised Canonical Scenario Registry | 64 record |
| `boundary_rules` | Assistant role, data dependency, action boundary | Có thể denormalize trong `scenarios` nếu muốn đơn giản |
| `allowed_data_fields` | Data minimization | Per scenario |
| `knowledge_documents` hoặc extended `documents` | KB document metadata | doc_type, visibility, authority/provenance |
| `document_versions` | Version/effective/status | Có thể gộp vào documents ở MVP nhỏ |
| `knowledge_chunks` | Chunk metadata mirror | Vector vẫn ở Chroma |
| `legal_basis` | Compliance mapping | Offline/default non-user-facing |
| `conversations` | Chat session | Existing |
| `messages` | Chat messages | Thêm scenario/action metadata sau |
| `chat_requests` | Async RAG processing | Existing model, cần migration alignment |
| `audit_events` | Security/action audit | Tối thiểu: who, what, when, decision |
| `access_scopes` | Basic access model | Employee self, manager team, HR admin; chưa ER confidential |

## MVP-2 Tables

MVP-2 thêm controlled `CREATE_CASE` cho administrative cases ít nhạy cảm: payroll discrepancy, attendance dispute, missing onboarding docs, training budget, C&B/HR Ops cases. Sensitive ER/grievance vẫn chưa tạo confidential case nếu chưa có ACL/audit/privacy đầy đủ.

| table | purpose | allowed MVP-2 scenarios |
|---|---|---|
| `case_types` | Chuẩn hóa loại administrative case | Payroll discrepancy, attendance dispute, missing onboarding docs |
| `hr_cases` | Thay `tickets` làm business case | 13, 17, 20, 27, 28, 45 |
| `handoffs` | Lưu route từ assistant sang owner | PREPARE_AND_HANDOFF cases |
| `case_assignments` | Assignee/team xử lý | C&B, HR Ops, L&D, Finance |
| `case_events` | Timeline/audit event của case | Created, assigned, status changed, resolved |
| `case_notes` | Ghi chú nghiệp vụ có phân quyền | Không dùng cho ER confidential trong MVP-2 nếu ACL chưa đủ |
| `sla_tracking` | Due date, breach, escalation target | Administrative cases |

## Future/Integration Tables

| table | trigger để thêm | lý do chưa vào MVP |
|---|---|---|
| `organization_units` | Có HRIS/org master thật | MVP dùng department text/config |
| `positions` | Có job architecture/position master | Cần cho applicability sâu |
| `reporting_relationships` | Cần lịch sử reporting hoặc dotted-line | MVP dùng `manager_id` |
| `requests` | Cho phép direct `CREATE_REQUEST` | Cần integration HRIS/workflow |
| `approvals` | Có workflow approval engine | MVP không tự submit approve request |
| `approval_steps` | Multi-step approval | Future |
| `tasks` | Offboarding/IT/Admin automation | Future ITSM/Admin integration |
| `decision_records` | Ghi final human decision | Cần cho probation/KPI/promotion/disciplinary future |
| `status_history` | Cho phép `READ_STATUS` | Cần source-of-truth integration |
| `external_system_links` | Kết nối HRIS/Payroll/Attendance/LMS/ATS/ITSM | Future connector layer |

## PII And Security Classification

| class | examples | storage rule | access rule |
|---|---|---|---|
| Public/Internal low | Policy title, service owner, public holiday schedule | OK in KB | Authenticated employee |
| Employee profile medium | Department, manager, contract type, tenure band | Store minimal | Self, manager scope, HR Ops/HRBP as needed |
| Payroll high | Payslip issue, tax docs, bank update metadata | Do not store raw amounts/full bank in chat | C&B only, audit required |
| Health/benefits high | Insurance claim metadata, parental leave dates | No diagnosis/medical docs in chat | C&B restricted |
| ER critical | Grievance, harassment, discipline, manager conflict | No detailed testimony in assistant chat; confidential case system only | ER/Legal need-to-know |
| Legal/privacy critical | Work permit, privacy request, disciplinary legal risk | Case with strict ACL | Legal/HR Ops restricted |

Security rules:

- Assistant never fabricates personal state when source-of-truth is absent.
- Chat message retention must treat payroll/ER/health/legal terms as high-risk.
- `CREATE_CASE` requires scenario allowlist, sensitivity check, allowed data fields, and audit event.
- `READ_STATUS` and direct `CREATE_REQUEST` are blocked until external source-of-truth, RBAC and audit exist.

## Migration Strategy Plan

1. Freeze this document as business data contract.
2. Reconcile current SQL migration vs SQLAlchemy models; decide `auth.users` vs local `users`.
3. Add additive MVP-1 tables/config first: departments, services, scenarios, boundary rules, allowed data fields, access scopes, audit events.
4. Extend existing `documents` instead of replacing immediately: add doc_type, visibility, service_id, version/effective/status alignment, legal_basis relation.
5. Add scenario/action metadata to `chat_requests` and `messages`.
6. Introduce `hr_cases` in MVP-2 and keep `tickets` as read-only compatibility view or deprecated table during transition.
7. Backfill scenario registry from this document.
8. Backfill documents into knowledge/service mapping.
9. Add RLS/ACL before enabling any `CREATE_CASE`.
10. Only after MVP-2 passes audit, consider future `requests`, approvals, workflow tasks and external status reads.

## Knowledge Base Documents Derived From Schema

| KB document | derived from | purpose |
|---|---|---|
| HR Service Catalog | `hr_services`, `service_owner`, `sla` | Employee biết service nào, owner nào, SLA nào |
| Assistant Boundary Playbook | `scenarios`, `boundary_rules`, `allowed_action` | Kiểm soát khi nào answer/guide/handoff/human-first |
| Data Minimization Guide | `allowed_data_fields`, sensitivity | Biết field nào được phép hỏi trong chat |
| HR Operating Model | `hr_departments`, RACI | Giải thích vai trò HR Ops/C&B/HRBP/TA/L&D/ER |
| Manager Guide | Normalized RACI + manager-owned scenarios | Hướng dẫn manager trong leave, attendance, OT, WFH, KPI, probation, resignation |
| Policy Set | `knowledge_documents.doc_type=policy` | Source trả lời quyền lợi/quy định V-Nova |
| SOP Set | `knowledge_documents.doc_type=sop` | Source hướng dẫn thao tác |
| FAQ Set | `knowledge_documents.doc_type=faq` | Diễn giải câu hỏi thường gặp |
| Forms/Channels Registry | `allowed_action`, service catalog | Link portal/form/kênh handoff |
| Legal Basis Map | `legal_basis` | Compliance traceability, không user-facing mặc định |
| Security/Privacy Handling Guide | sensitivity, access_scope, audit_event | Guardrail cho payroll, health, ER, legal/privacy |

## V-Nova Runtime Reality Contract

Lớp này khóa thực tế runtime trước physical schema. Vì sản phẩm sẽ được deploy cho người ngoài trải nghiệm, assistant không được nói như thể V-Nova đã có HRIS, Payroll Portal, LMS, ATS, Leave Portal hoặc form thật nếu các surface đó chưa tồn tại trong chính product hoặc chưa tích hợp thật.

Nguyên tắc bắt buộc:

- Không đưa fake URL.
- Không giả lập số dư phép, payslip, trạng thái đơn, trạng thái claim, kết quả KPI, trạng thái thử việc hoặc trạng thái hồ sơ cá nhân.
- Nếu source-of-truth không tồn tại trong runtime, assistant chuyển sang knowledge guidance, in-product directory, prefill draft hoặc human handoff phù hợp.
- `READ_STATUS` và direct `CREATE_REQUEST` chỉ được bật khi có external integration, RBAC và audit.
- Sensitive ER/grievance trong MVP-1 chỉ `HUMAN_FIRST` hoặc `LINK_ONLY` tới kênh/hướng dẫn an toàn; chưa tạo confidential case cho đến khi có ACL/audit/privacy model đúng.

## Runtime Source Inventory

| source | runtime status | runtime contract |
|---|---|---|
| KB | KNOWLEDGE | Có thể trả lời từ tài liệu đã ingest/user-facing; không dùng để suy luận personal state. |
| HR Service Directory | SIMULATED_IN_PRODUCT | Có thể xây trong product như directory có owner/SLA/contact rõ ràng, không giả là HRIS. |
| Forms Registry | SIMULATED_IN_PRODUCT | Có thể xây registry hướng dẫn/form draft; không giả là form đã submit vào hệ thống thật. |
| Manager | HUMAN | Assistant chỉ chuẩn bị nội dung trao đổi hoặc nhắc liên hệ. |
| HR Ops | HUMAN | Handoff/contact guidance; CREATE_CASE chỉ MVP-2 cho administrative case ít nhạy cảm. |
| C&B | HUMAN | Handoff/contact guidance; CREATE_CASE MVP-2 cho payroll/attendance/admin case cho phép. |
| HRBP | HUMAN | Human-first cho lifecycle, performance, exception, conflict. |
| TA | HUMAN | Hướng dẫn kênh nội bộ; không giả lập ATS. |
| L&D | HUMAN | Hướng dẫn LMS/training; CREATE_CASE MVP-2 cho training budget nếu có case model. |
| ER | HUMAN | Sensitive; MVP-1 không tạo confidential case. |
| Finance | HUMAN | Hướng dẫn expense/advance; không giả lập Finance system. |
| Legal | HUMAN | Human handoff; không tư vấn pháp lý cuối cùng. |
| IT/Admin | HUMAN | Hướng dẫn contact/request; không giả lập ITSM/Admin system nếu chưa xây. |
| HRIS | EXTERNAL_ASSUMED | Có trong doanh nghiệp thật nhưng chưa tích hợp; không đọc/ghi dữ liệu. |
| Leave Portal | EXTERNAL_ASSUMED | Chưa có runtime thật; không fake URL, không tạo đơn thật. |
| Attendance System | EXTERNAL_ASSUMED | Không đọc/sửa công thật; chỉ hướng dẫn hoặc draft. |
| Payroll Portal | EXTERNAL_ASSUMED | Không đọc payslip/trạng thái lương; chỉ hướng dẫn. |
| LMS | EXTERNAL_ASSUMED | Không enroll thật; chỉ hướng dẫn hoặc draft. |
| ATS/Internal Job Board | EXTERNAL_ASSUMED | Không ứng tuyển thật; chỉ hướng dẫn. |
| Insurer Portal | EXTERNAL_ASSUMED | Không gửi claim thật; chỉ checklist/kênh human. |
| Finance/Expense System | EXTERNAL_ASSUMED | Không submit expense thật; chỉ hướng dẫn. |
| IT/Admin System | EXTERNAL_ASSUMED | Không tạo request thật nếu chưa có in-product request module. |
| ER Case System | NOT_AVAILABLE | Không tạo confidential ER case trong MVP-1. |
| Leave balance | NOT_AVAILABLE | Không trả số dư phép cá nhân. |
| Personal payroll state | NOT_AVAILABLE | Không trả số tiền, khấu trừ hoặc trạng thái chi trả cá nhân. |
| Performance status/rating | NOT_AVAILABLE | Không trả hoặc sửa rating cá nhân. |

## Runtime Reality Matrix

| source status | assistant được làm | assistant không được làm | fallback |
|---|---|---|---|
| IN_PRODUCT | Dùng chức năng thật đã build trong product. | Không vượt quyền action/sensitivity của scenario. | Audit event. |
| SIMULATED_IN_PRODUCT | Dùng surface trong product như directory, registry, draft. Đây là engineering metadata, không phải nhãn hiển thị cho user. | Không nói request đã được gửi vào hệ thống doanh nghiệp thật. UI dùng ngôn ngữ "Chuẩn bị yêu cầu", "Bản nháp", "Hướng dẫn gửi", "Người phụ trách". | Hướng dẫn gửi cho người/phòng ban. |
| EXTERNAL_REAL | Link/action tới hệ thống thật nếu đã cấu hình tenant. | Không dùng cho tenant/demo chưa cấu hình. | Nếu thiếu config, chuyển thành external assumed. |
| EXTERNAL_ASSUMED | Nêu đây là hệ thống/kênh doanh nghiệp thường có hoặc V-Nova baseline giả định. | Không fake URL, không đọc status, không submit request. | Knowledge guidance, prefill draft, human contact. |
| HUMAN | Chuẩn bị câu hỏi/context tối thiểu, route đúng owner. | Không quyết định thay người có thẩm quyền. | Directory/handoff. |
| KNOWLEDGE | Trả lời bằng KB nội bộ và citation. | Không suy ra dữ liệu cá nhân. | Nếu thiếu KB, nói chưa có thông tin. |
| NOT_AVAILABLE | Nói rõ chưa có quyền truy cập/tích hợp. | Không giả lập dữ liệu hoặc trạng thái. | Hướng dẫn kênh kiểm tra hoặc liên hệ owner. |

Ví dụ runtime:

- "Tôi được bao nhiêu ngày phép?" -> `KB=KNOWLEDGE` -> trả lời theo policy.
- "Tôi còn bao nhiêu ngày phép?" -> `Leave balance=NOT_AVAILABLE` -> nói chưa có quyền truy cập số dư cá nhân, hướng dẫn kiểm tra qua kênh leave/HR theo directory; không tự tính balance.
- "Payslip tháng này của tôi sai?" -> `Payroll=EXTERNAL_ASSUMED`, `Personal payroll state=NOT_AVAILABLE` -> tạo draft inquiry hoặc MVP-2 administrative case nếu bật; không kết luận đúng/sai.

## Simulated Surface Proposal

Chỉ xây surface tạo giá trị trải nghiệm cao, không biến toàn bộ HRIS thành project này.

| surface | business value | scenario coverage | data required | read/write behavior | phase |
|---|---|---|---|---|---|
| HR Service Directory | User biết hỏi đúng owner, giảm routing nhầm. | 1-64 | service, owner, SLA, sensitivity, contact label | Read-only in-product | MVP_1 |
| Forms Registry | Thay fake portal bằng registry form/kênh rõ ràng. | 2, 5, 10, 11, 14, 19, 22, 25, 26, 34, 35, 44, 46, 47, 59, 60 | form name, required fields, owner, privacy note | Read-only; no external submit | MVP_1 |
| Leave Request Instruction/Draft | Demo rõ GUIDE flow mà không cần Leave Portal thật. | 2, 3, 5, 10 | ngày nghỉ, loại nghỉ, bàn giao, manager | Prefill draft only | MVP_1 |
| Attendance Correction Instruction/Draft | Giảm tải câu hỏi chấm công, chuẩn bị dữ liệu đúng. | 11, 12, 13, 17 | ngày, ca, lý do, bằng chứng tùy chọn | Prefill draft; MVP-2 create admin case cho dispute/lỗi | MVP_1/MVP_2 |
| Payroll Inquiry Draft | Triage payroll discrepancy có kiểm soát. | 20, 27 | tháng lương, loại sai lệch, mã payslip nếu có | Prefill draft; MVP-2 create C&B case | MVP_1/MVP_2 |
| HR Contact/Escalation Directory | Hỗ trợ human-first đúng người. | 4, 6, 7, 18, 29-33, 36, 40, 42, 48, 51-58, 62-64 | owner, channel label, emergency note, sensitivity | Read-only/link to human guidance | MVP_1 |
| Administrative Case Intake | Tạo case ít nhạy cảm khi đã có ACL/audit cơ bản. | 13, 17, 20, 27, 28, 45 | scenario allowlist, allowed fields, requester, owner | Write `hr_case`; no ER confidential | MVP_2 |

## Runtime-Revised Canonical Scenario Registry

Bảng này là registry canonical sau khi áp Runtime Reality Contract. Nó supersede registry conceptual ở trên khi derive physical schema.

| id | scenario | owner | runtime source status | max runtime action | phase | runtime behavior |
|---:|---|---|---|---|---|---|
| 1 | Hỏi số ngày phép năm theo chính sách | C&B | KNOWLEDGE | NONE | MVP_1 | Trả lời từ KB. |
| 2 | Hướng dẫn tạo đơn nghỉ phép thường | Line Manager | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Dùng instruction/draft trong app, không nói đã submit Leave Portal. |
| 3 | Nghỉ khẩn cấp trong ngày | Line Manager | HUMAN | LINK_ONLY | MVP_1 | Nhắc báo manager trước, sau đó hướng dẫn ghi nhận. |
| 4 | Leave exception, thiếu số dư phép | HRBP | HUMAN | PREFILL_DRAFT | FUTURE | Chuẩn bị nội dung gặp manager/HRBP, không tạo workflow. |
| 5 | Nghỉ ốm thông thường | C&B | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Checklist chứng từ, không thu chẩn đoán. |
| 6 | Nghỉ thai sản/cha mẹ | C&B | HUMAN | LINK_ONLY | FUTURE | Hướng dẫn liên hệ C&B, chưa create case do dữ liệu nhạy cảm. |
| 7 | Nghỉ không lương | HRBP | HUMAN | PREFILL_DRAFT | FUTURE | Human-first với manager/HRBP. |
| 8 | Hỏi lịch nghỉ lễ | HR Ops | KNOWLEDGE | NONE | MVP_1 | Trả lời từ KB/thông báo. |
| 9 | Manager chưa duyệt đơn nghỉ | Line Manager | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Không đọc status; hướng dẫn nhắc manager/quá SLA hỏi HR Ops. |
| 10 | Hủy hoặc đổi đơn nghỉ đã duyệt | Line Manager | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Draft yêu cầu đổi/hủy, không sửa đơn thật. |
| 11 | Quên chấm công | Line Manager | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Draft attendance correction. |
| 12 | Đi trễ | Line Manager | HUMAN | PREFILL_DRAFT | MVP_1 | Draft báo manager nếu ảnh hưởng công. |
| 13 | Lỗi check-in khi WFH | HR Ops | EXTERNAL_ASSUMED | CREATE_CASE | MVP_2 | MVP-1 chỉ draft; MVP-2 tạo admin case HR Ops/IT. |
| 14 | Đăng ký OT trước khi làm | Line Manager | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Draft OT request, không submit OT portal. |
| 15 | Hỏi cách tính OT | C&B | KNOWLEDGE | NONE | MVP_1 | Trả lời rule chung, không tính payroll cá nhân. |
| 16 | Đổi ca/lịch làm việc | Line Manager | HUMAN | PREFILL_DRAFT | FUTURE | Human-first với manager. |
| 17 | Đơn bổ sung công bị từ chối | HR Ops | EXTERNAL_ASSUMED | CREATE_CASE | MVP_2 | Tạo admin case nếu allowlist, không tự sửa công. |
| 18 | Vắng mặt không báo trước | HRBP | HUMAN | LINK_ONLY | OUT_OF_MVP | Không tư vấn kết quả kỷ luật, hướng dẫn gặp HRBP/ER. |
| 19 | Xem payslip | C&B | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Không fake payroll portal URL; hướng dẫn kênh kiểm tra. |
| 20 | Payroll discrepancy | C&B | NOT_AVAILABLE | CREATE_CASE | MVP_2 | MVP-1 draft inquiry; MVP-2 C&B case, không kết luận đúng/sai. |
| 21 | Đổi tài khoản ngân hàng nhận lương | C&B | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn kênh bảo mật; không nhập full account trong chat. |
| 22 | Hỏi chứng từ thuế TNCN | C&B | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn cách xin chứng từ, không đọc tax portal. |
| 23 | Hỏi thời điểm thưởng | C&B | KNOWLEDGE | NONE | MVP_1 | Trả lời timeline chung, không hứa payout cá nhân. |
| 24 | Hỏi điều kiện phụ cấp | C&B | KNOWLEDGE | NONE | MVP_1 | Trả lời điều kiện chung; case cá nhân hỏi C&B. |
| 25 | Claim bảo hiểm sức khỏe | C&B | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Checklist claim, không upload hồ sơ y tế. |
| 26 | Đăng ký người phụ thuộc/bảo hiểm | C&B | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn secure channel, không thu CCCD/full PII. |
| 27 | Hỏi khoản khấu trừ trong lương | C&B | NOT_AVAILABLE | CREATE_CASE | MVP_2 | MVP-1 draft inquiry; MVP-2 C&B case. |
| 28 | Thiếu giấy tờ onboarding | HR Ops | SIMULATED_IN_PRODUCT | CREATE_CASE | MVP_2 | MVP-1 checklist; MVP-2 HR Ops case. |
| 29 | Probation sang chính thức | HRBP | HUMAN | LINK_ONLY | OUT_OF_MVP | Không báo trạng thái pass/fail, hướng dẫn gặp manager/HRBP. |
| 30 | Probation extension concern | HRBP | HUMAN | LINK_ONLY | OUT_OF_MVP | Không tạo case trong MVP; hướng dẫn HRBP/ER. |
| 31 | Gia hạn hợp đồng | HRBP | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Không hứa gia hạn. |
| 32 | Contract changes | HRBP | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Handoff HRBP/Legal, không tạo quyết định hợp đồng. |
| 33 | Employee transfer | Business leader | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Chuẩn bị career/internal mobility conversation. |
| 34 | Đổi thông tin hồ sơ cá nhân | HR Ops | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn HRIS/profile channel, không thu PII đầy đủ. |
| 35 | Đổi emergency contact | HR Ops | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn profile channel. |
| 36 | Resignation | HRBP | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Không submit/chấp nhận nghỉ việc. |
| 37 | Exit handover | HR Ops | SIMULATED_IN_PRODUCT | LINK_ONLY | MVP_1 | Checklist bàn giao, không đọc status. |
| 38 | Final settlement | C&B | NOT_AVAILABLE | LINK_ONLY | FUTURE | Không tính số tiền; hướng dẫn C&B/Finance. |
| 39 | KPI goal clarification | Line Manager | HUMAN | PREFILL_DRAFT | MVP_1 | Draft câu hỏi trao đổi manager. |
| 40 | KPI dispute | HRBP | HUMAN | LINK_ONLY | OUT_OF_MVP | Không create case MVP-1; hướng dẫn HRBP/ER. |
| 41 | Quy trình performance review | HRBP | KNOWLEDGE | NONE | MVP_1 | Trả lời process/timeline chung. |
| 42 | Promotion/salary review | Business leader | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Draft career conversation, không mở salary workflow. |
| 43 | Development plan | Line Manager | HUMAN | PREFILL_DRAFT | MVP_1 | Draft development conversation. |
| 44 | Đăng ký khóa đào tạo | L&D | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn LMS/kênh L&D, không enroll thật. |
| 45 | Training budget/chứng chỉ | L&D | HUMAN | CREATE_CASE | MVP_2 | MVP-1 draft; MVP-2 administrative L&D/Finance case. |
| 46 | Internal job application | Hiring Manager | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn internal job process, không fake ATS. |
| 47 | WFH request thường lệ | Line Manager | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | MVP_1 | Draft WFH request, không submit portal. |
| 48 | WFH exception | HRBP | HUMAN | PREFILL_DRAFT | FUTURE | Human-first manager/HRBP. |
| 49 | Cấp thiết bị làm việc | IT | EXTERNAL_ASSUMED | LINK_ONLY | FUTURE | Không tạo ITSM request nếu chưa có module. |
| 50 | Access badge/văn phòng | Admin | EXTERNAL_ASSUMED | LINK_ONLY | FUTURE | Không cấp quyền hoặc tạo request thật. |
| 51 | Manager conflict | ER | HUMAN | LINK_ONLY | FUTURE | MVP-1 chỉ kênh an toàn; create confidential case chỉ sau ACL. |
| 52 | Harassment/discrimination concern | ER | HUMAN | LINK_ONLY | FUTURE | Hướng dẫn hotline/ER, không lấy lời khai chi tiết. |
| 53 | Hỏi grievance policy | ER | KNOWLEDGE | NONE | MVP_1 | Trả lời policy/kênh khiếu nại. |
| 54 | Formal grievance submission | ER | NOT_AVAILABLE | LINK_ONLY | FUTURE | Chưa có ER Case System; chỉ hướng dẫn kênh an toàn. |
| 55 | Disciplinary action notice | ER | HUMAN | LINK_ONLY | OUT_OF_MVP | Hướng dẫn gặp ER/Legal, không workflow. |
| 56 | Conflict of interest/ethics | Legal | HUMAN | LINK_ONLY | FUTURE | Hướng dẫn ethics/legal channel, không tạo case MVP-1. |
| 57 | Stress/burnout/mental health support | HRBP | HUMAN | LINK_ONLY | MVP_1 | Hướng dẫn kênh hỗ trợ theo policy, không case. |
| 58 | Workplace safety incident | Safety Lead | HUMAN | LINK_ONLY | MVP_1 | Ưu tiên emergency/safety channel. |
| 59 | Business trip advance | Finance | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn finance process, không submit advance. |
| 60 | Expense reimbursement | Finance | EXTERNAL_ASSUMED | LINK_ONLY | MVP_1 | Hướng dẫn expense process, không submit claim. |
| 61 | Reference letter/employment confirmation | HR Ops | SIMULATED_IN_PRODUCT | PREFILL_DRAFT | FUTURE | Draft request; create request chỉ khi có HR Ops module. |
| 62 | Data privacy/access correction request | Legal | HUMAN | LINK_ONLY | FUTURE | Hướng dẫn privacy channel, không đọc dữ liệu. |
| 63 | Change reporting line/supervisor | Business leader | HUMAN | PREFILL_DRAFT | OUT_OF_MVP | Không giải thích quyết định cá nhân nếu không có owner. |
| 64 | Immigration/work permit/visa support | Legal | HUMAN | LINK_ONLY | FUTURE | Hướng dẫn Legal/HR Ops, không thu passport/full docs. |

## Inconsistencies Found And Resolved

| issue | resolution |
|---|---|
| Một số scenario cũ dùng `CREATE_REQUEST` cho IT/Admin, badge, training hoặc profile khi chưa có workflow thật. | Runtime registry hạ xuống `LINK_ONLY` hoặc `PREFILL_DRAFT`; direct `CREATE_REQUEST` chuyển future. |
| `READ_STATUS` từng xuất hiện cho leave/offboarding khi chưa có Leave Portal/HRIS integration. | Runtime registry hạ xuống `LINK_ONLY`; không đọc trạng thái cá nhân. |
| Sensitive ER/grievance từng cho `CREATE_CASE` ở conceptual future. | MVP-1 chuyển `LINK_ONLY`; confidential `CREATE_CASE` chỉ future sau ACL/audit/privacy. |
| Một số owner có dạng ghép như C&B/Finance, ER/Legal, HRBP/ER. | Runtime registry chuẩn hóa về một accountable owner; bên còn lại là consulted hoặc source hỗ trợ. |
| Portal/form external có nguy cơ bị hiểu là có URL thật. | Runtime contract cấm fake URL; dùng Forms Registry hoặc instruction/draft trong product. |
| Personal state như leave balance, payslip, KPI rating, final settlement chưa có source. | Runtime status `NOT_AVAILABLE`; assistant phải nói không có quyền truy cập/tích hợp. |

## Final Architecture Freeze Checklist

1. Freeze V-Nova operating assumptions.
2. Freeze Runtime Reality Contract.
3. Derive physical MVP-1/MVP-2 schema.
4. Derive KB/data specification.
5. Generate/research content.
6. Migration + seed + re-index.
7. E2E evaluation.
