import type {
  ApiResponse,
  AsyncJob,
  ChatResult,
  CitationDetail,
  ConversationMessage,
  ConversationListItem,
  ConversationDetail,
  DocumentDetail,
  DocumentListItem,
  EvaluationRun,
  TicketItem,
  User,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ACCESS_TOKEN_KEY = "hr_knowledge_access_token";
const REFRESH_TOKEN_KEY = "hr_knowledge_refresh_token";

export type ChatStreamEvent =
  | { type: "request"; chat_request_id: string; conversation_id: string; state: string; poll_after_ms: number }
  | { type: "heartbeat" }
  | { type: "status"; value: string }
  | { type: "tool_start" | "tool_end"; tool: string }
  | { type: "answer_delta"; content: string }
  | { type: "citation"; source: string; title: string; page_start: number | null; is_official_policy: boolean }
  | { type: "done"; answer?: unknown }
  | { type: "error"; code?: string; message: string; status?: number; retryable?: boolean }
  | { type: "result"; data: ChatResult };

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly code = "NETWORK_ERROR",
    readonly status = 0,
    readonly retryable = false,
  ) {
    super(message);
  }
}

function getStoredToken(key: string) {
  return typeof window === "undefined" ? null : window.localStorage.getItem(key);
}

function storeTokens(accessToken: string, refreshToken: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.dispatchEvent(new Event("hr-session-cleared"));
}

export function hasSession() {
  return Boolean(getStoredToken(ACCESS_TOKEN_KEY));
}

async function refreshSession() {
  const refreshToken = getStoredToken(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    throw new ApiClientError("Không thể kết nối tới Backend.", "NETWORK_ERROR", 0, true);
  }
  if (!response.ok) return false;
  const payload = (await response.json()) as ApiResponse<{
    access_token: string;
    refresh_token: string;
  }>;
  if (!payload.success || !payload.data) return false;
  storeTokens(payload.data.access_token, payload.data.refresh_token);
  return true;
}

async function request<T>(path: string, init: RequestInit = {}, auth = true, allowRefresh = true): Promise<ApiResponse<T>> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", crypto.randomUUID());
  if (auth) {
    const token = getStoredToken(ACCESS_TOKEN_KEY);
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 45_000);
  init.signal?.addEventListener("abort", () => controller.abort(), { once: true });
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal: controller.signal });
  } catch (reason) {
    if (controller.signal.aborted && !timedOut) throw reason;
    if (timedOut) {
      throw new ApiClientError("Backend phản hồi quá lâu. Vui lòng thử lại.", "REQUEST_TIMEOUT", 0, true);
    }
    throw new ApiClientError("Không thể kết nối tới Backend.", "NETWORK_ERROR", 0, true);
  } finally {
    window.clearTimeout(timeout);
  }

  if (response.status === 401 && auth && allowRefresh) {
    if (await refreshSession()) return request<T>(path, init, auth, false);
    clearSession();
  }

  let payload: ApiResponse<T>;
  try {
    payload = (await response.json()) as ApiResponse<T>;
  } catch {
    throw new ApiClientError("Backend trả về dữ liệu không hợp lệ.", "INVALID_RESPONSE", response.status);
  }
  if (!response.ok || !payload.success || payload.data === null) {
    throw new ApiClientError(
      payload.error?.message ?? "Yêu cầu không thành công.",
      payload.error?.code ?? `HTTP_${response.status}`,
      response.status,
      payload.error?.retryable ?? false,
    );
  }
  return payload;
}

function idempotencyHeaders() {
  return { "Idempotency-Key": crypto.randomUUID() };
}

async function streamRequest(
  path: string,
  body: unknown,
  onEvent: (event: ChatStreamEvent) => void,
  allowRefresh = true,
): Promise<void> {
  const headers = new Headers({
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    "X-Request-ID": crypto.randomUUID(),
    ...idempotencyHeaders(),
  });
  const token = getStoredToken(ACCESS_TOKEN_KEY);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiClientError("Không thể kết nối tới Backend.", "NETWORK_ERROR", 0, true);
  }

  if (response.status === 401 && allowRefresh && (await refreshSession())) {
    return streamRequest(path, body, onEvent, false);
  }
  if (!response.ok) {
    let payload: ApiResponse<unknown> | null = null;
    try {
      payload = (await response.json()) as ApiResponse<unknown>;
    } catch {
      // Một proxy có thể trả HTML khi endpoint streaming chưa được triển khai.
    }
    throw new ApiClientError(
      payload?.error?.message ?? "Không thể bắt đầu câu trả lời trực tiếp.",
      payload?.error?.code ?? `HTTP_${response.status}`,
      response.status,
      payload?.error?.retryable ?? response.status >= 500,
    );
  }
  if (!response.body) {
    throw new ApiClientError("Backend không trả về luồng dữ liệu.", "EMPTY_STREAM", response.status, true);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function consume(block: string) {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    try {
      const event = JSON.parse(data) as ChatStreamEvent;
      if (event.type === "error") {
        throw new ApiClientError(
          event.message,
          event.code ?? "STREAM_ERROR",
          event.status ?? 0,
          event.retryable ?? true,
        );
      }
      onEvent(event);
    } catch (error) {
      if (error instanceof ApiClientError) throw error;
      throw new ApiClientError("Luồng trả lời có dữ liệu không hợp lệ.", "INVALID_STREAM_EVENT", 0, true);
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    blocks.forEach(consume);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
}

export const api = {
  register: (email: string, password: string, fullName: string, department: string) =>
    request<User>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName, department }),
      },
      false,
    ).then((response) => response.data!),
  async login(email: string, password: string) {
    const response = await request<{ access_token: string; refresh_token: string; expires_in: number }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    );
    storeTokens(response.data!.access_token, response.data!.refresh_token);
    return response.data!;
  },
  me: () => request<User>("/auth/me").then((response) => response.data!),
  createConversation: (title: string | null = null) =>
    request<{ conversation_id: string; state: string; title: string; created_at: string }>("/conversations", {
      method: "POST",
      headers: idempotencyHeaders(),
      body: JSON.stringify({ title }),
    }).then((response) => response.data!),
  /** Backend contract: GET /conversations returns newest-updated conversations for current user. */
  listConversations: () =>
    request<ConversationListItem[]>("/conversations?limit=100").then((response) => response.data!),
  getConversation: (conversationId: string) =>
    request<ConversationDetail>(`/conversations/${conversationId}`).then((response) => response.data!),
  renameConversation: (conversationId: string, title: string) =>
    request<{ conversation_id: string; title: string; state: string }>(`/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }).then((response) => response.data!),
  deleteConversation: (conversationId: string) =>
    request<{ conversation_id: string; deleted: boolean }>(`/conversations/${conversationId}`, {
      method: "DELETE",
    }).then((response) => response.data!),
  endConversation: (conversationId: string) =>
    request<{ conversation_id: string; state: string; ended_at: string }>(`/conversations/${conversationId}/end`, {
      method: "POST",
    }).then((response) => response.data!),
  getConversationMessages: (conversationId: string) =>
    request<{ conversation_id: string; messages: ConversationMessage[] }>(`/conversations/${conversationId}/messages?limit=100`).then(
      (response) => response.data!,
    ),
  createChatRequest: (conversationId: string, question: string) =>
    request<{ chat_request_id: string; conversation_id: string; state: string; poll_after_ms: number }>("/chat/requests", {
      method: "POST",
      headers: idempotencyHeaders(),
      body: JSON.stringify({ conversation_id: conversationId, question }),
    }).then((response) => response.data!),
  streamChatRequest: (
    conversationId: string,
    question: string,
    onEvent: (event: ChatStreamEvent) => void,
  ) => streamRequest("/chat/requests/stream", { conversation_id: conversationId, question }, onEvent),
  getChatRequest: (chatRequestId: string, signal?: AbortSignal) =>
    request<ChatResult>(`/chat/requests/${chatRequestId}`, { signal }).then((response) => response.data!),
  retryChatRequest: (chatRequestId: string) =>
    request<{ chat_request_id: string; parent_chat_request_id: string; state: string; poll_after_ms: number }>(
      `/chat/requests/${chatRequestId}/retry`,
      { method: "POST", headers: idempotencyHeaders(), body: JSON.stringify({ reason: "USER_RETRY" }) },
    ).then((response) => response.data!),
  getCitation: (citationId: string) =>
    request<CitationDetail>(`/citations/${citationId}`).then((response) => response.data!),
  listTickets: (filters: { status?: string; department?: string; priority?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.department) params.set("department", filters.department);
    if (filters.priority) params.set("priority", filters.priority);
    const suffix = params.size ? `?${params.toString()}` : "";
    return request<TicketItem[]>(`/tickets${suffix}`).then((response) => response.data!);
  },
  getTicket: (ticketId: string) =>
    request<TicketItem>(`/tickets/${ticketId}`).then((response) => response.data!),
  createTicket: (payload: { user_query: string; target_department: string; priority: string; category?: string }) =>
    request<TicketItem>("/tickets", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.data!),
  updateTicket: (
    ticketId: string,
    payload: { status?: string; priority?: string; resolution_note?: string; assignee_id?: string },
  ) =>
    request<TicketItem>(`/tickets/${ticketId}`, { method: "PATCH", body: JSON.stringify(payload) }).then(
      (response) => response.data!,
    ),
  listDocuments: (filters: { category?: string; status?: string; indexed?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.category) params.set("category", filters.category);
    if (filters.status) params.set("doc_status", filters.status);
    if (filters.indexed) params.set("indexed", filters.indexed);
    const suffix = params.size ? `?${params.toString()}` : "";
    return request<DocumentListItem[]>(`/documents${suffix}`).then((response) => response.data!);
  },
  getDocument: (documentId: string) =>
    request<DocumentDetail>(`/documents/${documentId}`).then((response) => response.data!),
  updateDocumentMetadata: (documentId: string, metadata: Record<string, unknown>) =>
    request<{ document_id: string; metadata_updated: boolean; requires_reindex: boolean }>(
      `/documents/${documentId}/metadata`,
      { method: "PATCH", body: JSON.stringify(metadata) },
    ).then((response) => response.data!),
  archiveDocument: (documentId: string) =>
    request<{ document_id: string; status: string; requires_reindex: boolean }>(`/documents/${documentId}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason: "SUPERSEDED_BY_NEW_VERSION" }),
    }).then((response) => response.data!),
  uploadDocument: (file: File, metadata: Record<string, string>) => {
    const form = new FormData();
    form.append("file", file);
    Object.entries(metadata).forEach(([key, value]) => value && key !== "language" && form.append(key, value));
    return request<{ document_id: string; ingestion_job_id: string; status: string }>("/documents", {
      method: "POST",
      headers: idempotencyHeaders(),
      body: form,
    }).then((response) => response.data!);
  },
  getIngestionJob: (jobId: string) => request<AsyncJob>(`/ingestion-jobs/${jobId}`).then((response) => response.data!),
  startIndexRebuild: (documentIds: string[], strategy: string) =>
    request<{ job_id: string; state: string; poll_after_ms: number }>("/indexes/rebuilds", {
      method: "POST",
      headers: idempotencyHeaders(),
      body: JSON.stringify({ document_ids: documentIds, strategy }),
    }).then((response) => response.data!),
  getIndexRebuild: (jobId: string) => request<AsyncJob>(`/indexes/rebuilds/${jobId}`).then((response) => response.data!),
  startEvaluation: (datasetId: string, indexVersion: string, modelConfigId: string) =>
    request<{ run_id: string; state: string; poll_after_ms: number }>("/evaluation/runs", {
      method: "POST",
      headers: idempotencyHeaders(),
      body: JSON.stringify({ dataset_id: datasetId, index_version: indexVersion, model_config_id: modelConfigId }),
    }).then((response) => response.data!),
  getEvaluation: (runId: string) => request<EvaluationRun>(`/evaluation/runs/${runId}`).then((response) => response.data!),
};
