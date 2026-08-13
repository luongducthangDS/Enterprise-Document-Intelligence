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
  role: "EMPLOYEE" | "HR_ADMIN" | "SUPER_ADMIN" | string;
  department: string;
};

export type CitationSummary = {
  citation_id: string;
  title: string;
  page: number | null;
  section: string | null;
  version: string | null;
  effective_date: string | null;
  is_official_policy: boolean;
  source_type: string | null;
};

export type CitationDetail = {
  citation_id: string;
  document: {
    document_id: string;
    title: string;
    version: string | null;
    effective_date: string | null;
    status: string;
    is_official_policy: boolean;
    source_type: string | null;
  };
  location: { page: number | null; section: string | null; chunk_id?: string | null };
  excerpt: string;
  conflict_warning: boolean;
  is_official_policy: boolean;
  source_type: string | null;
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
};

export type ConversationMessage = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  chat_request_id: string | null;
  answer_status?: string | null;
  citations?: CitationSummary[] | null;
  created_at: string;
};

export type ConversationDetail = {
  conversation_id: string;
  title: string;
  state: string;
  created_at: string;
  ended_at: string | null;
  message_count: number;
  last_message_at: string | null;
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
};

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
