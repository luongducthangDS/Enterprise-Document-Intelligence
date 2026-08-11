/**
 * HR Document Intelligence Agent - Enterprise SaaS Mock Data (Vietnamese Version)
 */

window.MOCK_DATA = {
  currentUser: {
    name: "Alex Rivera",
    email: "alex.rivera@company.com",
    role: "Employee", // "Employee" | "HR Admin"
    avatar: "AR",
    department: "Bộ phận Kỹ thuật"
  },

  adminUser: {
    name: "Linh Tran",
    email: "linh.tran@company.com",
    role: "HR Admin",
    avatar: "LT",
    title: "Trưởng phòng Quản trị Nhân sự"
  },

  documents: [
    {
      id: "doc-1",
      name: "Chinh_Sach_Lam_Viec_Hybrid_2026.pdf",
      category: "Chính sách làm việc",
      version: "3.2",
      effectiveDate: "15/01/2026",
      owner: "Phòng Chính sách HR",
      fileType: "PDF",
      size: "2.4 MB",
      indexStatus: "Đã Index",
      lastIndexed: "2 giờ trước",
      status: "Active",
      chunks: 142,
      content: `Mục 2.1: Lịch làm việc Hybrid & Điều kiện áp dụng
Nhân viên đủ điều kiện được phép làm việc từ xa tối đa 2 ngày/tuần sau khi có sự phê duyệt của Quản lý trực tiếp. Các thành viên phải thống nhất lịch làm việc với quản lý và tham gia đầy đủ các cuộc họp trực tiếp bắt buộc. Khung giờ hợp tác cốt lõi tại tất cả văn phòng là 10:00 sáng - 4:00 chiều theo giờ địa phương.`
    },
    {
      id: "doc-2",
      name: "Quy_Dinh_Nghi_Phep_Nam_PTO_2026.pdf",
      category: "Chính sách nghỉ phép",
      version: "4.0",
      effectiveDate: "01/01/2026",
      owner: "Bộ phận Phúc lợi",
      fileType: "PDF",
      size: "1.8 MB",
      indexStatus: "Đã Index",
      lastIndexed: "1 ngày trước",
      status: "Active",
      chunks: 98,
      content: `Mục 1.3: Quyền lợi nghỉ phép năm có hưởng lương
Nhân viên chính thức làm việc toàn thời gian được hưởng 18 ngày phép năm có hưởng lương cho mỗi năm calendar. Tối đa 5 ngày phép chưa sử dụng có thể chuyển sang Quý 1 của năm tiếp theo.`
    },
    {
      id: "doc-3",
      name: "Quy_Trinh_Danh_Gia_Thu_Viec_SOP.pdf",
      category: "Onboarding & Thử việc",
      version: "2.1",
      effectiveDate: "10/11/2025",
      owner: "Đội ngũ Tuyển dụng & Onboarding",
      fileType: "PDF",
      size: "3.1 MB",
      indexStatus: "Đã Index",
      lastIndexed: "3 ngày trước",
      status: "Active",
      chunks: 115,
      content: `Mục 3.4: Lộ trình đánh giá thời gian thử việc
Thời gian thử việc tiêu chuẩn là 90 ngày. Các mốc đánh giá chính thức diễn ra vào ngày thứ 30, 60 và 90 do Quản lý trực tiếp thực hiện.`
    },
    {
      id: "doc-4",
      name: "Huong_Dan_Bao_Hiem_va_Chi_Tra_Luong.pdf",
      category: "Tài chính & Lương thưởng",
      version: "1.5",
      effectiveDate: "01/08/2025",
      owner: "Phòng Kế toán & Lương",
      fileType: "PDF",
      size: "1.2 MB",
      indexStatus: "Đã Index",
      lastIndexed: "5 ngày trước",
      status: "Active",
      chunks: 64,
      content: `Mục 4.2: Cập nhật thông tin tài khoản ngân hàng
Nhân viên phải gửi thông tin cập nhật tài khoản ngân hàng qua Cổng thông tin Tự dịch vụ Lương ít nhất 5 ngày làm việc trước ngày chốt sổ lương (ngày 20 hàng tháng).`
    }
  ],

  tickets: [
    {
      id: "HR-2048",
      employee: "Alex Rivera (Bộ phận Kỹ thuật)",
      employeeEmail: "alex.rivera@company.com",
      question: "Công ty có hỗ trợ chi phí lắp đặt tấm pin năng lượng mặt trời tại nhà không?",
      category: "Phúc lợi & Bồi hoàn",
      confidence: 31,
      priority: "Bình thường",
      assignee: "Linh Tran",
      sla: "18 giờ 42 phút",
      status: "New", // "New" | "In review" | "Waiting for info" | "Resolved"
      createdDate: "Hôm nay, 09:20",
      lastUpdated: "10 phút trước",
      expectedResponse: "Trong 1 ngày làm việc",
      reason: "Không tìm thấy văn bản chính sách phù hợp trong kho tri thức hiện tại (Độ tin cậy 31%).",
      response: "",
      responder: "",
      responseTimestamp: ""
    },
    {
      id: "HR-2045",
      employee: "Sarah Chen (Bộ phận Marketing)",
      employeeEmail: "sarah.chen@company.com",
      question: "Tôi có thể xin gia hạn thời gian nghỉ thai sản vượt hạn mức quy định không?",
      category: "Chính sách nghỉ phép",
      confidence: 45,
      priority: "Cao",
      assignee: "Minh HR",
      sla: "04 giờ 15 phút",
      status: "In review",
      createdDate: "Hôm qua, 14:15",
      lastUpdated: "1 giờ trước",
      expectedResponse: "Hôm nay, 17:00",
      reason: "Yêu cầu xem xét trường hợp ngoại lệ từ Ban Giám Đốc.",
      response: "",
      responder: "",
      responseTimestamp: ""
    },
    {
      id: "HR-2039",
      employee: "David Kim (Bộ phận Kinh doanh)",
      employeeEmail: "david.kim@company.com",
      question: "Hạn mức hỗ trợ học phí chứng chỉ chuyên môn là bao nhiêu?",
      category: "Đào tạo & Phát triển",
      confidence: 88,
      priority: "Thấp",
      assignee: "Linh Tran",
      sla: "Đã hoàn thành",
      status: "Resolved",
      createdDate: "03/08/2026",
      lastUpdated: "04/08/2026",
      expectedResponse: "Hoàn tất",
      reason: "Đã đối soát theo Quy định Đào tạo 2026.",
      response: "Hạn mức bồi hoàn học phí hàng năm cho các chứng chỉ chuyên môn liên quan đến công việc được duyệt là $2,500/nhân viên/năm.",
      responder: "Linh Tran (Chuyên viên HR)",
      responseTimestamp: "04/08/2026, 11:30"
    }
  ],

  ragResponses: {
    "hybrid": {
      confidence: 94,
      status: "Câu trả lời đã đối soát",
      answer: "Nhân viên đủ điều kiện được phép làm việc từ xa **tối đa 2 ngày/tuần** sau khi có sự phê duyệt của Quản lý trực tiếp. Các thành viên phải thống nhất lịch làm việc với quản lý và tham gia đầy đủ các cuộc họp trực tiếp bắt buộc. Khung giờ hợp tác cốt lõi tại tất cả văn phòng là **10:00 sáng – 4:00 chiều** theo giờ địa phương.",
      responseTime: "1.2 giây",
      requestId: "REQ-94812",
      citations: [
        {
          docId: "doc-1",
          title: "[1] Chính sách làm việc Hybrid 2026",
          section: "Mục 2.1",
          page: "Trang 4",
          version: "3.2",
          effectiveDate: "15/01/2026",
          excerpt: "Nhân viên đủ điều kiện được phép làm việc từ xa tối đa 2 ngày/tuần sau khi có sự phê duyệt của Quản lý trực tiếp. Các thành viên phải thống nhất lịch làm việc với quản lý và tham gia các cuộc họp trực tiếp bắt buộc."
        }
      ]
    },

    "solar_low": {
      confidence: 31,
      status: "Chưa xác minh",
      heading: "Tôi chưa thể xác minh thông tin này một cách chắc chắn",
      explanation: "Tôi đã tìm kiếm trong toàn bộ kho tài liệu chính sách HR đã duyệt, nhưng không thấy quy định nào đề cập đến chi phí hỗ trợ lắp đặt tấm pin năng lượng mặt trời tại nhà. Để đảm bảo thông tin chính xác và không bị hư cấu, câu hỏi này nên được Chuyên viên HR trực tiếp xem xét.",
      citations: []
    },

    "solar_reindexed": {
      confidence: 95,
      status: "Câu trả lời đã đối soát",
      answer: "Theo **Chính sách Hỗ trợ Năng lượng Xanh & Làm việc tại nhà 2026** mới cập nhật, nhân viên chính thức làm việc từ xa được hưởng **mức hỗ trợ 50% chi phí (tối đa $1,500)** cho việc lắp đặt tấm pin năng lượng mặt trời hoặc thiết bị lưu trữ năng lượng tại nhà.",
      responseTime: "0.9 giây",
      requestId: "REQ-99410",
      citations: [
        {
          docId: "doc-5",
          title: "[1] Chinh_Sach_Ho_Tro_Pin_Nang_Luong_Mat_Troi_2026.pdf",
          section: "Mục 4.1",
          page: "Trang 2",
          version: "1.0",
          effectiveDate: "05/08/2026",
          excerpt: "Nhân viên chính thức làm việc từ xa được hưởng mức hỗ trợ 50% chi phí (tối đa $1,500) cho việc lắp đặt tấm pin năng lượng mặt trời hoặc thiết bị lưu trữ năng lượng tại nhà."
        }
      ]
    }
  }
};
