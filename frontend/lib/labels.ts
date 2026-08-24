/**
 * Thuật ngữ hiển thị tập trung cho toàn bộ UI.
 * Nguyên tắc: giá trị gửi/nhận với Backend luôn giữ enum gốc;
 * chỉ lớp hiển thị được dịch sang ngôn ngữ người dùng.
 * Nguồn các enum: lib/types.ts, backend agent_answer_adapter.py,
 * ticket_service.py, document_service.py, src/workers/*.py.
 */

export const CHAT_STATE_LABELS: Record<string, string> = {
  CREATING: "Đang khởi tạo",
  QUEUED: "Đang chờ xử lý",
  RETRIEVING: "Đang tra cứu tài liệu",
  GENERATING: "Đang soạn câu trả lời",
  COMPLETED: "Hoàn tất",
  ANSWERED: "Đã trả lời",
  REFUSED: "Không đủ bằng chứng",
  INSUFFICIENT_EVIDENCE: "Không đủ bằng chứng",
  CLARIFICATION_REQUIRED: "Cần làm rõ thêm",
  FAILED: "Lỗi xử lý",
};

export const CONVERSATION_STATE_LABELS: Record<string, string> = {
  ACTIVE: "Đang mở",
  ENDED: "Đã kết thúc",
};

export const JOB_STATE_LABELS: Record<string, string> = {
  QUEUED: "Đang chờ",
  PROCESSING: "Đang xử lý",
  COMPLETED: "Hoàn tất",
  FAILED: "Thất bại",
};

export const JOB_STAGE_LABELS: Record<string, string> = {
  UPLOADED: "Đã tải lên",
  STARTED: "Đã bắt đầu",
  EXTRACTING: "Đang trích xuất văn bản",
  CHUNKING: "Đang chia đoạn nội dung",
  EMBEDDING: "Đang tạo vector ngữ nghĩa",
  INDEXING: "Đang ghi vào chỉ mục",
  PREPARING: "Đang chuẩn bị",
  LOADING_DATASET: "Đang nạp bộ câu hỏi đánh giá",
  RUNNING: "Đang chạy đánh giá",
  SCORING: "Đang chấm điểm",
  COMPLETED: "Hoàn tất",
  FAILED: "Thất bại",
  CANCELLED: "Đã huỷ",
};

export const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Đang áp dụng",
  ARCHIVED: "Đã lưu trữ",
};

export const ROLE_LABELS: Record<string, string> = {
  EMPLOYEE: "Nhân viên",
  DEPARTMENT_MANAGER: "Quản lý phòng ban",
  SUPER_ADMIN: "Quản trị hệ thống",
};

export const ESCALATE_REASON_LABELS: Record<string, string> = {
  low_confidence: "Độ tin cậy thấp",
  out_of_scope: "Ngoài phạm vi kho tài liệu",
  personal_data_required: "Cần dữ liệu cá nhân",
  user_requested_human: "Người dùng yêu cầu hỗ trợ",
  competitor_question: "Câu hỏi về công ty khác",
};

export const PRIORITY_LABELS: Record<string, string> = {
  HIGH: "Cao",
  MEDIUM: "Trung bình",
  LOW: "Thấp",
};

export const ACCESS_SCOPE_LABELS: Record<string, string> = {
  COMPANY_WIDE: "Toàn công ty",
  DEPARTMENT: "Phòng ban",
  ROLE: "Theo vai trò",
  RESTRICTED: "Giới hạn (chỉ người có quyền)",
};

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  INTERNAL_POLICY: "Chính sách nội bộ",
  LAW: "Văn bản pháp luật",
  REFERENCE: "Tài liệu tham khảo",
  TEMPLATE: "Tài liệu mẫu",
  SYNTHETIC: "Dữ liệu mô phỏng",
};

/** Danh sách phòng ban dùng chung cho đăng ký, ticket và upload (khớp danh mục phân quyền). */
export const DEPARTMENTS = ["HR", "Product", "Engineering", "IT", "Finance", "Accounting", "Sales", "Marketing", "Operations", "Legal"];

export function chatStateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return CHAT_STATE_LABELS[value.toUpperCase()] ?? value;
}

export function conversationStateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return CONVERSATION_STATE_LABELS[value.toUpperCase()] ?? chatStateLabel(value);
}

export function jobStateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return JOB_STATE_LABELS[value.toUpperCase()] ?? value;
}

export function jobStageLabel(value: string | null | undefined): string {
  if (!value) return "Đang xử lý";
  return JOB_STAGE_LABELS[value.toUpperCase()] ?? value.replaceAll("_", " ").toLowerCase();
}

export function documentStatusLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return DOCUMENT_STATUS_LABELS[value.toUpperCase()] ?? value;
}

export function roleLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return ROLE_LABELS[value.toUpperCase()] ?? value;
}

export function escalateReasonLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return ESCALATE_REASON_LABELS[value.toLowerCase()] ?? value;
}

export function priorityLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return PRIORITY_LABELS[value.toUpperCase()] ?? value;
}

export function sourceTypeLabel(value: string | null | undefined): string {
  if (!value) return "Chưa phân loại";
  return SOURCE_TYPE_LABELS[value.toUpperCase()] ?? value.replaceAll("_", " ");
}
