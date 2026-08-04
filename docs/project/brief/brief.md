PROJECT BRIEF

HR Document Intelligence Agent

## 1. Project Overview

HR Document Intelligence Agent là hệ thống hỏi–đáp tài liệu nội bộ, cho phép người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên thay vì tìm thủ công trong nhiều file PDF, Word hoặc Excel. Hệ thống truy xuất, tóm tắt các đoạn nội dung liên quan, tổng hợp câu trả lời, hiển thị nguồn và duy trì ngữ cảnh trong hội thoại nhiều lượt.

## 2. Problem Statement

Tài liệu HR phân tán ở nhiều file, định dạng và phiên bản khác nhau.

Tài liệu dài hoặc cần ngay thông tin gấp.

Nhân viên mất thời gian tìm đúng quy định hoặc phải hỏi HR cho các câu hỏi lặp lại.

Câu trả lời thủ công có thể thiếu nguồn, dùng nhầm phiên bản hoặc không nhất quán.

Tìm kiếm theo từ khóa không xử lý tốt câu hỏi diễn đạt tự nhiên, câu hỏi có điều kiện hoặc hội thoại tiếp nối.

Cơ hội: tạo một điểm truy cập thống nhất, có căn cứ, giúp tra cứu nhanh hơn nhưng không thay thế quyết định nghiệp vụ của HR.

## 3. Proposed Solution

Ứng dụng web tích hợp quy trình RAG: tiếp nhận câu hỏi, truy xuất nội dung từ kho tài liệu đã lập chỉ mục, tạo câu trả lời dựa trên bằng chứng và hiển thị trích dẫn gồm tên tài liệu, trang/mục, phiên bản và ngày hiệu lực khi có.

Hỏi–đáp bằng ngôn ngữ tự nhiên.

Trích dẫn có thể kiểm tra và mở rộng xem đoạn nguồn.

Hỗ trợ câu hỏi tiếp nối trong cùng phiên hội thoại.

Từ chối hoặc yêu cầu làm rõ khi dữ liệu không đủ/không nhất quán.

Phản hồi không phải tư vấn pháp lý hoặc quyết định chính thức của HR.

## 4. Project Objectives

## 5. Target Users

## 6. Stakeholders

## 7. Project Scope

### 7.1 In Scope — MVP

Kho 30–50 tài liệu HR đã chọn lọc; ưu tiên PDF, DOCX, XLSX có nội dung máy đọc được.

Ingestion, làm sạch, chia đoạn, metadata, embedding và lập chỉ mục.

Tìm kiếm ngữ nghĩa/hybrid, tổng hợp câu trả lời có căn cứ và trích dẫn.

Hội thoại nhiều lượt trong một phiên.

Cơ chế insufficient evidence, câu hỏi làm rõ và thông báo giới hạn.

Web demo; bộ 100–150 câu hỏi kiểm thử và đáp án chuẩn.

### 7.2 Out of Scope

Payroll, chấm công giao dịch, quản lý hồ sơ nhân sự, ERP/SAP/HRM.

Thực thi workflow, gửi email/thông báo hoặc phê duyệt nghiệp vụ.

Dữ liệu cá nhân nhạy cảm và phân quyền doanh nghiệp phức tạp.

OCR cho tài liệu scan chất lượng thấp; tích hợp hệ thống production.

Tư vấn pháp lý hoặc tự động đưa ra quyết định nhân sự.

## 8. Dataset Scope

## 9. Expected Deliverables

Ứng dụng web demo: hỏi, nhận câu trả lời, xem nguồn và tiếp tục hội thoại.

Pipeline xử lý và lập chỉ mục tài liệu HR.

Kho dữ liệu MVP đã chuẩn hóa cùng metadata.

Bộ đánh giá và báo cáo kết quả chất lượng.

Tài liệu dự án: Brief, PRD, kiến trúc, hướng dẫn cài đặt/chạy demo và báo cáo bàn giao.

## 10. Success Metrics

Lưu ý: đây là mục tiêu MVP để nhóm xác nhận sau khi có baseline; không phải số liệu đã đo.

## 11. Business Value

Kỳ vọng rút ngắn thời gian tra cứu một câu hỏi HR từ mức nhiều phút xuống dưới một phút đối với câu hỏi được bao phủ.

Giảm khối lượng câu hỏi FAQ lặp lại chuyển trực tiếp tới HR trong pilot.

Tăng khả năng kiểm chứng nhờ trích dẫn và thông tin phiên bản/ngày hiệu lực.

Tạo nền tảng kỹ thuật và bộ đánh giá có thể nhân rộng sang Legal, Finance, Operations.

Giá trị định lượng chính thức sẽ được đo trong pilot bằng baseline thời gian tìm kiếm và số lượng câu hỏi lặp lại.

## 12. Assumptions & Constraints

## 13. Key Risks & Mitigations

## 14. Future Expansion

Phân quyền theo vai trò, SSO, audit log và quản trị tài liệu.

OCR chất lượng cao, bảng/biểu mẫu phức tạp, đa ngôn ngữ.

Tích hợp DMS/Drive/SharePoint/HRM và quy trình cập nhật tự động.

Feedback loop, analytics, human handoff và mở rộng sang phòng ban khác.

## 15. Decisions to Confirm

Tên Product Owner/đại diện nghiệp vụ và danh sách thành viên/role.

Thời gian thực hiện chính thức và môi trường triển khai demo.

Nguồn tài liệu, quyền sử dụng và quy tắc ẩn danh dữ liệu.

Ngưỡng success metrics sau baseline và người duyệt ground truth.

Ngôn ngữ chính: tiếng Việt, tiếng Anh hay song ngữ.

## 16. Project Summary

MVP tập trung giải quyết một vấn đề rõ ràng: tìm và kiểm chứng thông tin trong tài liệu HR. Thành công của dự án không chỉ nằm ở chatbot trả lời được, mà ở khả năng truy xuất đúng bằng chứng, dẫn nguồn rõ ràng, từ chối an toàn và đo lường được chất lượng trên một bộ dữ liệu có kiểm soát.

## Table 1
| Tóm tắt điều hành
Xây dựng ứng dụng web sử dụng RAG để nhân viên và HR hỏi–đáp trên kho tài liệu HR nội bộ, nhận câu trả lời có trích dẫn và được cảnh báo/từ chối khi bằng chứng không đủ. |
| --- |

## Table 2
| Mục tiêu | Kết quả hướng tới |
| --- | --- |
| O1. Tra cứu nhanh | Giảm thời gian tìm thông tin HR so với quy trình tìm file thủ công. |
| O2. Có căn cứ | Mỗi câu trả lời có ít nhất một trích dẫn phù hợp hoặc hệ thống từ chối trả lời. |
| O3. Giảm tải HR | Giảm các câu hỏi chính sách lặp lại phải xử lý thủ công trong phạm vi thử nghiệm. |
| O4. Đo lường được | Có bộ câu hỏi, ground truth và quy trình đánh giá retrieval/answer/citation. |
| O5. Có thể mở rộng | Thiết kế dữ liệu và pipeline có thể tái sử dụng cho phòng ban khác. |

## Table 3
| Nhóm người dùng | Nhu cầu chính | Quyền trong MVP |
| --- | --- | --- |
| Nhân viên | Tra cứu chính sách, quy trình, quyền lợi và biểu mẫu. | Đặt câu hỏi; xem câu trả lời và nguồn. |
| Nhân sự/HR | Trả lời nhanh, kiểm tra căn cứ, phát hiện câu hỏi chưa được bao phủ. | Như nhân viên; tham gia review dữ liệu và đáp án chuẩn. |
| Quản trị viên | Quản lý tập dữ liệu thử nghiệm và theo dõi chất lượng. | Nạp/cập nhật dữ liệu theo quy trình kỹ thuật; xem log đánh giá cơ bản. |

## Table 4
| Stakeholder | Vai trò/quan tâm | Trách nhiệm dự kiến |
| --- | --- | --- |
| Mentor | Định hướng và review chất lượng dự án. | Phản biện phạm vi, kiến trúc, phương pháp đánh giá và demo. |
| Product Owner/đại diện nghiệp vụ | Xác nhận giá trị và mức đúng nghiệp vụ. | Ưu tiên use case; duyệt dữ liệu, ground truth và tiêu chí chấp nhận. |
| Nhóm dự án (4 người) | Phân tích, dữ liệu, RAG, backend/frontend, kiểm thử. | Xây dựng, tài liệu hóa, đánh giá và trình diễn. |
| Người dùng thử nghiệm | Tính hữu ích và dễ sử dụng. | Thực hiện kịch bản thử; phản hồi UX và độ tin cậy. |

## Table 5
| Nhóm | Nội dung |
| --- | --- |
| Chính sách/quy định | Nội quy lao động; quy chế nhân sự; nghỉ phép; làm thêm; chấm công; làm việc từ xa; bảo hiểm; phúc lợi. |
| Vòng đời nhân viên | Tuyển dụng; onboarding; thử việc; đánh giá; nghỉ việc. |
| Hướng dẫn hỗ trợ | Hướng dẫn nghiệp vụ HR; biểu mẫu; FAQ. |
| Metadata bắt buộc | document_id, title, category, version, effective_date, status; page/section; source_file. |
| Dữ liệu đánh giá | 50–100 FAQ; 100–150 câu hỏi; ground truth; trích dẫn chuẩn; nhóm câu hỏi không đủ dữ liệu. |

## Table 6
| Chỉ số MVP | Mục tiêu ban đầu | Cách đo |
| --- | --- | --- |
| Citation coverage | ≥ 95% câu trả lời có ít nhất một nguồn; 100% câu không có nguồn phải từ chối. | Chạy bộ test và kiểm tra tự động/thủ công. |
| Citation correctness | ≥ 85% trích dẫn thực sự hỗ trợ nội dung trả lời. | Human review theo rubric. |
| Answer correctness | ≥ 80% câu trả lời đạt mức đúng/đủ chấp nhận được. | So sánh ground truth + review HR/mentor. |
| Retrieval Recall@5 | ≥ 85% câu hỏi có đoạn bằng chứng chuẩn trong top 5. | Đối chiếu evidence label. |
| Latency | P95 ≤ 8 giây trong môi trường demo. | Log thời gian end-to-end. |
| Task success | ≥ 80% người thử hoàn thành kịch bản không cần hỗ trợ. | Usability test có quan sát. |

## Table 7
| Loại | Nội dung |
| --- | --- |
| Giả định | Nhóm được phép sử dụng bộ tài liệu mẫu/đã ẩn danh; tài liệu có nội dung đủ rõ và có thể trích xuất. |
| Giả định | Mentor hoặc đại diện nghiệp vụ có thể review một phần ground truth và các trường hợp mâu thuẫn. |
| Ràng buộc | Nhóm 4 người; phạm vi MVP; thời gian, hạ tầng và ngân sách mô hình có giới hạn. |
| Ràng buộc | Chưa có đối tác/production data chính thức; kết quả demo không đại diện cho triển khai doanh nghiệp. |
| Ràng buộc | Không xử lý PII nhạy cảm; không coi phản hồi của mô hình là quyết định HR chính thức. |

## Table 8
| Rủi ro | Ảnh hưởng | Giảm thiểu |
| --- | --- | --- |
| Tài liệu mâu thuẫn/cũ | Trả lời sai phiên bản. | Metadata version/effective date; ưu tiên tài liệu active; hiển thị cảnh báo. |
| Hallucination | Mất niềm tin/nguy cơ nghiệp vụ. | Grounded prompt; ngưỡng bằng chứng; bắt buộc citation; refusal. |
| Retrieval kém | Bỏ sót bằng chứng đúng. | Chunking theo cấu trúc; hybrid search; reranking; đánh giá Recall@k. |
| Thiếu ground truth | Không chứng minh được chất lượng. | Ưu tiên bộ test sớm; review theo mẫu; phân tầng câu hỏi. |
| Scope creep | Không hoàn thành MVP. | Giữ out-of-scope; backlog hóa tính năng nâng cao. |
