export type ApiError = {
  code: string;
  message: string;
  details?: Array<{ field?: string; message: string }> | null;
  retryable?: boolean;
  retry_after_ms?: number | null;
};

export type ApiResponse<T> = {
  request_id: string;
  success: boolean;
  data: T | null;
  error: ApiError | null;
  meta: {
    timestamp: string;
    api_version: string;
    pagination?: { limit: number; next_cursor: string | null } | null;
  };
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "EMPLOYEE" | "DEPARTMENT_MANAGER" | "SUPER_ADMIN" | string;
  department: string;
};

export type CitationSummary = {
  citation_id: string;
  title: string;
  page: number | null;
  sheet?: string | null;
  section: string | null;
  version: string | null;
  effective_date: string | null;
  is_official_policy?: boolean;
  source_type?: string | null;
  excerpt?: string;
};

export type CitationDetail = {
  citation_id: string;
  document_code?: string | null;
  document: {
    document_id: string;
    title: string;
    version: string | null;
    effective_date: string | null;
    status: string;
    is_official_policy?: boolean;
    source_type?: string | null;
  };
  location: { page: number | null; sheet?: string | null; section: string | null; chunk_id?: string | null };
  excerpt: string;
  caveat?: string | null;
  conflict_warning?: boolean;
  is_official_policy?: boolean;
  source_type?: string | null;
};

export type TicketItem = {
  id: string;
  ticket_code: string;
  conversation_id: string | null;
  message_id: string | null;
  requester_id: string;
  requester_name: string | null;
  employee_question: string;
  escalate_reason: string;
  confidence_score: number | null;
  category: string | null;
  target_department: string;
  priority: string;
  status: string;
  assignee_id: string | null;
  assignee_name: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  closed_at: string | null;
};

export type Warning = {
  type: string;
  severity: "INFO" | "WARNING" | "BLOCKING" | string;
  message: string;
  citation_ids?: string[] | null;
  recommended_action?: string | null;
};

export type ChatState =
  | "QUEUED"
  | "RETRIEVING"
  | "GENERATING"
  | "COMPLETED"
  | "REFUSED"
  | "CLARIFICATION_REQUIRED"
  | "FAILED";

export type AssistantRole = "ANSWER" | "GUIDE" | "PREPARE_AND_HANDOFF" | "HUMAN_FIRST";
export type RuntimeAction = "NONE" | "LINK_ONLY" | "PREFILL_DRAFT" | "CREATE_CASE";

export type AllowedDataField = {
  field_key: string;
  label: string;
  required_for_prefill: boolean;
  pii_class: "Low" | "Medium" | "High" | "Critical";
  storage_policy: "do_not_store" | "store_case_only" | "store_message_ok" | "store_metadata_only";
};

/**
 * Canonical runtime decision từ agent (Runtime-Revised Canonical Scenario Registry).
 * UI render theo `runtime_action` — mức được phép NGAY BÂY GIỜ — chứ không phải
 * `max_runtime_action` (trần theo registry, có thể là CREATE_CASE ở MVP-2) và
 * cũng không suy diễn từ nội dung câu trả lời.
 */
export type BoundaryDecision = {
  scenario_id: number | null;
  scenario_name: string | null;
  service_code: string | null;
  service_name: string | null;
  assistant_role: AssistantRole;
  sensitivity: "Low" | "Medium" | "High" | "Critical";
  runtime_source_status: string;
  source_of_truth_label: string;
  max_runtime_action: RuntimeAction;
  runtime_action: RuntimeAction;
  mvp_phase: "MVP_1" | "MVP_2" | "FUTURE" | "OUT_OF_MVP";
  handoff_target: { type?: string; code?: string; name?: string; contact_label?: string } | null;
  user_facing_action_label: string | null;
  allowed_data_fields: AllowedDataField[];
  runtime_behavior: string;
  resolution: "registry" | "fallback";
};

export type ChatResult = {
  chat_request_id: string;
  conversation_id: string;
  user_message_id: string | null;
  assistant_message_id: string | null;
  state: ChatState;
  answer_status: string | null;
  answer: string | null;
  citations: CitationSummary[] | null;
  warnings: Warning[] | null;
  clarification: { question: string; options: string[] } | null;
  failure: { code: string; message: string; retryable: boolean } | null;
  latency_ms: number | null;
  // null khi tải lại lịch sử hoặc poll: decision hiện chỉ đi kèm event `result`
  // của lượt chat đang chạy (chat_requests chưa có cột lưu boundary).
  boundary?: BoundaryDecision | null;
};

export type ConversationMessage = {
  message_id: string;
  role: "user" | "assistant" | "USER" | "ASSISTANT";
  content: string;
  chat_request_id: string | null;
  answer_status?: string | null;
  citations?: CitationSummary[] | null;
  created_at: string;
};

/** GET /conversations item. Kept explicit so Backend can implement the list contract without UI changes. */
export type ConversationListItem = {
  conversation_id: string;
  title: string | null;
  state: "ACTIVE" | "ENDED" | string;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
  message_count: number;
  last_message_at: string | null;
};

export type ConversationDetail = ConversationListItem;

export type DocumentListItem = {
  document_id: string;
  title: string;
  category: string | null;
  version: string | null;
  effective_date: string | null;
  status: string;
  ingestion_state: string;
  indexed: boolean;
  created_at: string;
};

export type DocumentDetail = {
  document_id: string;
  title: string;
  category: string | null;
  version: string | null;
  effective_date: string | null;
  status: string;
  language: string;
  source_file: string;
  checksum: string;
  confidentiality: string;
  ingestion: {
    job_id: string | null;
    state: string;
    chunk_count: number;
    last_ingested_at: string | null;
    error: unknown;
  };
  index: { indexed: boolean; index_version: string | null };
};

export type AsyncJob = {
  job_id: string;
  state: string;
  stage?: string;
  progress_percent: number;
  poll_after_ms?: number;
  error?: unknown;
  active_index_version?: string | null;
};

export type EvaluationRun = AsyncJob & {
  run_id: string;
  metrics: {
    recall_at_5: number;
    answer_correctness: number;
    citation_coverage: number;
    citation_correctness: number;
    p95_latency_ms: number;
  } | null;
  quality_gate: string | null;
};

export type AccessModel = {
  roles: Record<string, string[]>;
  scopes: string[];
};

export type AccessUser = {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  department: string;
};

export type AuditLog = {
  audit_id: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};