"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BookOpenCheck, Check, ChevronDown, CircleAlert, Copy, FileSearch, Link2, LoaderCircle, MessageCircleQuestion, RefreshCw, Send, ShieldAlert, Sparkles } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { ChatResult, CitationDetail, CitationSummary, ConversationDetail, ConversationMessage } from "@/lib/types";
import { useSystemDialog } from "./SystemDialog";

type UiMessage =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "assistant"; result: ChatResult };

type PendingChat = { conversationId: string; chatRequestId: string; pollAfterMs: number };

const TERMINAL_STATES = new Set(["COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"]);
const CONVERSATION_KEY = "hr_knowledge_active_conversation";
const PENDING_CHAT_KEY = "hr_knowledge_pending_chat";
const MAX_POLL_DURATION_MS = 120_000;
const MAX_POLL_INTERVAL_MS = 3_000;

export function clearChatRecovery() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CONVERSATION_KEY);
  window.localStorage.removeItem(PENDING_CHAT_KEY);
}

function abortableWait(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    function onAbort() {
      window.clearTimeout(timer);
      reject(new DOMException("Polling cancelled", "AbortError"));
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function waitUntilVisible(signal: AbortSignal) {
  if (!document.hidden) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    function cleanup() {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      signal.removeEventListener("abort", onAbort);
    }
    function onVisibilityChange() {
      if (document.hidden) return;
      cleanup();
      resolve();
    }
    function onAbort() {
      cleanup();
      reject(new DOMException("Polling cancelled", "AbortError"));
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function isAbortError(reason: unknown) {
  return reason instanceof DOMException && reason.name === "AbortError";
}

function processingLabel(state: string) {
  const labels: Record<string, string> = {
    QUEUED: "Đang xếp hàng",
    RETRIEVING: "Đang tìm tài liệu phù hợp",
    GENERATING: "Đang tổng hợp câu trả lời",
  };
  return labels[state] ?? state;
}

function historyToUi(message: ConversationMessage): UiMessage {
  if (message.role.toLowerCase() === "user") return { id: message.message_id, kind: "user", content: message.content };
  const clarification = message.answer_status === "CLARIFICATION_REQUIRED"
    ? { question: message.content, options: [] }
    : null;
  const state = message.answer_status === "CLARIFICATION_REQUIRED" ? "CLARIFICATION_REQUIRED"
    : message.answer_status === "INSUFFICIENT_EVIDENCE" ? "REFUSED"
      : "COMPLETED";
  return {
    id: message.message_id,
    kind: "assistant",
    result: {
      chat_request_id: message.chat_request_id ?? "",
      conversation_id: "",
      user_message_id: null,
      assistant_message_id: message.message_id,
      state,
      answer_status: message.answer_status ?? null,
      answer: clarification ? null : message.content,
      citations: message.citations ?? [],
      warnings: [],
      clarification,
      failure: null,
      latency_ms: null,
    },
  };
}

function titleFromQuestion(question: string) {
  const normalized = question.replace(/\s+/g, " ").trim();
  if (normalized.length <= 48) return normalized;
  const shortened = normalized.slice(0, 48).replace(/\s+\S*$/, "").replace(/[.,!?;:]+$/, "");
  return `${shortened}...`;
}

function readPendingChat(): PendingChat | null {
  try {
    const raw = window.localStorage.getItem(PENDING_CHAT_KEY);
    return raw ? JSON.parse(raw) as PendingChat : null;
  } catch {
    window.localStorage.removeItem(PENDING_CHAT_KEY);
    return null;
  }
}

function sourceLabel(sourceType: string | null, isOfficial: boolean) {
  const labels: Record<string, string> = {
    official_policy: "Chính sách nội bộ",
    government_law: "Văn bản pháp luật",
    public_template: "Template tham khảo",
    public_article: "Bài viết tham khảo",
    synthetic: "Tài liệu mẫu",
  };
  return sourceType && labels[sourceType] ? labels[sourceType] : isOfficial ? "Nguồn chính thức" : "Nguồn tham khảo";
}

function stripLegacyCitationFooter(answer: string) {
  return answer.replace(/\n\s*\nNguồn tham khảo:\s*\n[\s\S]*$/i, "").trimEnd();
}

function sameDocument(left: CitationSummary, right: CitationSummary) {
  return left.title === right.title
    && left.version === right.version
    && left.effective_date === right.effective_date
    && left.source_type === right.source_type;
}

function normalizeCitationDisplay(answer: string, citations: CitationSummary[]) {
  const documents: CitationSummary[] = [];
  const documentNumberByCitation = citations.map((citation) => {
    const existingIndex = documents.findIndex((document) => sameDocument(document, citation));
    if (existingIndex >= 0) return existingIndex + 1;
    documents.push(citation);
    return documents.length;
  });

  const normalizedAnswer = answer.replace(
    /\[(?:Nguồn\s*)?(\d+(?:\s*(?:,|;|và)\s*\d+)*)\]/gi,
    (marker, values: string) => {
      const documentNumbers = (values.match(/\d+/g) ?? [])
        .map((value) => documentNumberByCitation[Number(value) - 1])
        .filter((value, index, all): value is number => Boolean(value) && all.indexOf(value) === index);
      return documentNumbers.length
        ? documentNumbers.map((value) => `[Nguồn ${value}]`).join(" ")
        : marker;
    },
  );

  return { answer: normalizedAnswer, citations: documents };
}

type ChatViewProps = {
  newConversationSignal?: number;
  selectedConversationId?: string | null;
  conversations: ConversationDetail[];
  onConversationsChange: (conversations: ConversationDetail[]) => void;
  onConversationSelected: (conversationId: string) => void;
};

export function ChatView({
  newConversationSignal = 0,
  selectedConversationId = null,
  conversations,
  onConversationsChange,
  onConversationSelected,
}: ChatViewProps) {
  const { confirm } = useSystemDialog();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState("CREATING");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(true);
  const [processingState, setProcessingState] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [citation, setCitation] = useState<CitationDetail | null>(null);
  const [citationLoading, setCitationLoading] = useState(false);
  const mounted = useRef(true);
  const operationVersion = useRef(0);
  const newConversationSignalRef = useRef(newConversationSignal);
  const pollController = useRef<AbortController | null>(null);
  const activePollRequestId = useRef<string | null>(null);
  const conversationsRef = useRef(conversations);
  const onConversationsChangeRef = useRef(onConversationsChange);
  const onConversationSelectedRef = useRef(onConversationSelected);
  conversationsRef.current = conversations;
  onConversationsChangeRef.current = onConversationsChange;
  onConversationSelectedRef.current = onConversationSelected;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operationVersion.current += 1;
      pollController.current?.abort();
    };
  }, []);

  const poll = useCallback(async (pending: PendingChat, version: number) => {
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    activePollRequestId.current = pending.chatRequestId;
    const startedAt = Date.now();
    let pollCount = 0;
    let interval = Math.max(1_000, pending.pollAfterMs);

    try {
      while (!controller.signal.aborted) {
        await waitUntilVisible(controller.signal);
        if (Date.now() - startedAt >= MAX_POLL_DURATION_MS) {
          throw new ApiClientError(
            "Hệ thống vẫn đang xử lý câu hỏi. Bạn có thể tải lại trang để tiếp tục nhận kết quả.",
            "POLL_TIMEOUT",
            0,
            true,
          );
        }
        await abortableWait(interval, controller.signal);
        await waitUntilVisible(controller.signal);
        const result = await api.getChatRequest(pending.chatRequestId, controller.signal);
        pollCount += 1;
        if (!mounted.current || operationVersion.current !== version) return;
        setProcessingState(processingLabel(result.state));
        if (TERMINAL_STATES.has(result.state)) {
          window.localStorage.removeItem(PENDING_CHAT_KEY);
          setMessages((current) => {
            const id = result.assistant_message_id ?? pending.chatRequestId;
            if (current.some((item) => item.id === id)) return current;
            return [...current, { id, kind: "assistant", result }];
          });
          console.info("[chat-poll] completed", {
            chatRequestId: pending.chatRequestId,
            pollCount,
            durationMs: Date.now() - startedAt,
            state: result.state,
          });
          return;
        }
        interval = Math.min(MAX_POLL_INTERVAL_MS, interval + 1_000);
      }
    } finally {
      if (pollController.current === controller) pollController.current = null;
      if (activePollRequestId.current === pending.chatRequestId) activePollRequestId.current = null;
    }
  }, []);

  const createConversation = useCallback(async () => {
    const version = ++operationVersion.current;
    pollController.current?.abort();
    setBusy(true);
    setError("");
    setCitation(null);
    window.localStorage.removeItem(PENDING_CHAT_KEY);
    try {
      const created = await api.createConversation();
      if (!mounted.current || operationVersion.current !== version) return;
      window.localStorage.setItem(CONVERSATION_KEY, created.conversation_id);
      setConversationId(created.conversation_id);
      setConversationState(created.state);
      setMessages([]);
      onConversationsChangeRef.current([{
        conversation_id: created.conversation_id,
        title: created.title,
        state: created.state,
        created_at: created.created_at,
        ended_at: null,
        message_count: 0,
        last_message_at: null,
      }, ...conversationsRef.current.filter((item) => item.conversation_id !== created.conversation_id)]);
      onConversationSelectedRef.current(created.conversation_id);
    } catch (reason) {
      if (isAbortError(reason)) return;
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tạo cuộc hội thoại.");
    } finally {
      if (mounted.current && operationVersion.current === version) setBusy(false);
    }
  }, []);

  useEffect(() => {
    const version = ++operationVersion.current;
    async function restore() {
      const storedConversationId = window.localStorage.getItem(CONVERSATION_KEY);
      setBusy(true);
      try {
        const conversationList = await api.listConversations();
        if (!mounted.current || operationVersion.current !== version) return;
        onConversationsChangeRef.current(conversationList);
        const targetConversationId = storedConversationId && conversationList.some((item) => item.conversation_id === storedConversationId)
          ? storedConversationId
          : conversationList[0]?.conversation_id;
        if (!targetConversationId) {
          await createConversation();
          return;
        }
        const [conversation, history] = await Promise.all([
          api.getConversation(targetConversationId),
          api.getConversationMessages(targetConversationId),
        ]);
        if (!mounted.current || operationVersion.current !== version) return;
        window.localStorage.setItem(CONVERSATION_KEY, targetConversationId);
        setConversationId(targetConversationId);
        setConversationState(conversation.state);
        setMessages(history.messages.map(historyToUi));
        onConversationSelectedRef.current(targetConversationId);

        const pending = readPendingChat();
        if (pending?.conversationId === targetConversationId) {
          setProcessingState("Đang khôi phục yêu cầu");
          await poll(pending, version);
        }
      } catch (reason) {
        if (isAbortError(reason)) return;
        if (!mounted.current || operationVersion.current !== version) return;
        if (reason instanceof ApiClientError && [403, 404].includes(reason.status)) {
          clearChatRecovery();
          await createConversation();
          return;
        }
        setError(reason instanceof ApiClientError ? `${reason.message} Bạn có thể tải lại để tiếp tục phiên.` : "Không thể khôi phục cuộc hội thoại.");
      } finally {
        if (mounted.current && operationVersion.current === version) {
          setBusy(false);
          setProcessingState(null);
        }
      }
    }
    void restore();
  }, [createConversation, poll]);

  async function openConversation(targetConversationId: string) {
    if (busy || targetConversationId === conversationId) return;
    const version = ++operationVersion.current;
    pollController.current?.abort();
    setBusy(true);
    setError("");
    setCitation(null);
    setProcessingState(null);
    try {
      const [conversation, history] = await Promise.all([
        api.getConversation(targetConversationId),
        api.getConversationMessages(targetConversationId),
      ]);
      if (!mounted.current || operationVersion.current !== version) return;
      window.localStorage.setItem(CONVERSATION_KEY, targetConversationId);
      setConversationId(targetConversationId);
      setConversationState(conversation.state);
      setMessages(history.messages.map(historyToUi));
      onConversationSelectedRef.current(targetConversationId);
    } catch (reason) {
      if (isAbortError(reason)) return;
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở cuộc hội thoại cũ.");
    } finally {
      if (mounted.current && operationVersion.current === version) setBusy(false);
    }
  }

  useEffect(() => {
    if (!selectedConversationId || selectedConversationId === conversationId || busy) return;
    void openConversation(selectedConversationId);
    // The sidebar disables selection while the chat is busy.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedConversationId, busy]);

  async function sendQuestion(text: string) {
    const cleanQuestion = text.trim();
    if (!conversationId || !cleanQuestion || busy || conversationState !== "ACTIVE") return;
    const optimisticId = crypto.randomUUID();
    const version = operationVersion.current;
    let requestAccepted = false;
    setMessages((current) => [...current, { id: optimisticId, kind: "user", content: cleanQuestion }]);
    setQuestion("");
    setBusy(true);
    setError("");
    setProcessingState(processingLabel("QUEUED"));
    try {
      const created = await api.createChatRequest(conversationId, cleanQuestion);
      requestAccepted = true;
      const active = conversationsRef.current.find((item) => item.conversation_id === conversationId);
      if (active) {
        const updated = {
          ...active,
          title: active.title === "Hội thoại mới" ? titleFromQuestion(cleanQuestion) : active.title,
          message_count: active.message_count + 1,
          last_message_at: new Date().toISOString(),
        };
        onConversationsChangeRef.current([updated, ...conversationsRef.current.filter((item) => item.conversation_id !== conversationId)]);
      }
      const pending = { conversationId, chatRequestId: created.chat_request_id, pollAfterMs: created.poll_after_ms };
      window.localStorage.setItem(PENDING_CHAT_KEY, JSON.stringify(pending));
      await poll(pending, version);
    } catch (reason) {
      if (isAbortError(reason)) return;
      if (!requestAccepted) {
        setMessages((current) => current.filter((item) => item.id !== optimisticId));
        setQuestion(cleanQuestion);
      }
      const suffix = requestAccepted ? " Yêu cầu đã được lưu; tải lại trang để tiếp tục nhận kết quả." : "";
      setError((reason instanceof ApiClientError ? reason.message : "Không thể xử lý câu hỏi.") + suffix);
    } finally {
      if (mounted.current && operationVersion.current === version) {
        setBusy(false);
        setProcessingState(null);
      }
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await sendQuestion(question);
  }

  async function retry(chatRequestId: string) {
    if (!conversationId || busy) return;
    const version = operationVersion.current;
    setBusy(true);
    setError("");
    setProcessingState(processingLabel("QUEUED"));
    try {
      const created = await api.retryChatRequest(chatRequestId);
      const pending = { conversationId, chatRequestId: created.chat_request_id, pollAfterMs: created.poll_after_ms };
      window.localStorage.setItem(PENDING_CHAT_KEY, JSON.stringify(pending));
      await poll(pending, version);
    } catch (reason) {
      if (isAbortError(reason)) return;
      setError(reason instanceof ApiClientError ? reason.message : "Không thể thử lại yêu cầu.");
    } finally {
      if (mounted.current && operationVersion.current === version) {
        setBusy(false);
        setProcessingState(null);
      }
    }
  }

  useEffect(() => {
    if (newConversationSignal === newConversationSignalRef.current || busy) return;
    newConversationSignalRef.current = newConversationSignal;
    let cancelled = false;
    async function startNewConversation() {
      const accepted = messages.length === 0 || await confirm({
        title: "Bắt đầu hội thoại mới?",
        message: "Hội thoại hiện tại đã được lưu trong lịch sử. Bạn có thể mở lại bất cứ lúc nào từ thanh bên trái.",
        confirmLabel: "Tạo hội thoại mới",
        cancelLabel: "Ở lại hội thoại này",
      });
      if (!cancelled && accepted) await createConversation();
    }
    void startNewConversation();
    return () => { cancelled = true; };
  }, [newConversationSignal, busy, messages.length, createConversation, confirm]);

  async function openCitation(item: CitationSummary) {
    setCitationLoading(true);
    setError("");
    try {
      setCitation(await api.getCitation(item.citation_id));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở nguồn.");
    } finally {
      setCitationLoading(false);
    }
  }

  return (
    <div className="chat-workspace">
      <section className="chat-main">
        <div className="message-stream">
          {!messages.length && !busy && (
            <div className="empty-chat">
              <div className="empty-icon"><Sparkles size={27} /></div>
              <p className="eyebrow">HR DOCUMENT INTELLIGENCE</p>
              <h2>Chào bạn, tôi có thể giúp gì?</h2>
              <p>Hỏi về chính sách nhân sự để nhận câu trả lời có trích dẫn từ tài liệu nội bộ.</p>
              <div className="prompt-row">
                {[
                  ["Phép năm", "Nhân viên có bao nhiêu ngày phép năm?"],
                  ["Giờ làm việc", "Quy định về giờ làm việc như thế nào?"],
                  ["Thử việc", "Chính sách thử việc hiện tại là gì?"],
                  ["Lương & phúc lợi", "Chính sách lương và phúc lợi gồm những gì?"],
                ].map(([label, prompt]) => (
                  <button key={label} onClick={() => void sendQuestion(prompt)}><span>{label}</span><small>{prompt}</small></button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) => message.kind === "user"
            ? <div className="message user-message" key={message.id}><div className="message-body">{message.content}</div></div>
            : <AssistantMessage key={message.id} result={message.result} activeCitationId={citation?.citation_id ?? null} onCitation={openCitation} onRetry={retry} />)}
          {processingState && (
            <div className="message assistant-message"><div className="assistant-avatar"><LoaderCircle className="spin" size={18} /></div><div className="message-body processing"><strong>Đang xử lý</strong><span>{processingState}</span></div></div>
          )}
          {error && <div className="stream-error"><CircleAlert size={17} />{error}</div>}
        </div>

        <form className="composer" onSubmit={submit}>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} disabled={busy || conversationState !== "ACTIVE"} placeholder="Hỏi về chính sách, quy trình hoặc quyền lợi nhân sự..." />
          <div className="composer-footer"><span>AI chỉ trả lời dựa trên nguồn tìm thấy</span><button className="send-command" aria-label="Gửi câu hỏi" disabled={!question.trim() || busy}><Send size={18} /></button></div>
        </form>
      </section>

      <aside className={`citation-panel ${citation || citationLoading ? "open" : ""}`}>
        <header><div><p className="eyebrow">SOURCE VERIFICATION</p><h3>{citation?.document.title ?? (citationLoading ? "Đang tải nguồn..." : "Nguồn đối soát")}</h3></div><button className="icon-command" aria-label="Đóng nguồn đối soát" onClick={() => setCitation(null)}>×</button></header>
        {citationLoading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải chi tiết nguồn</div> : citation ? <div className="citation-detail">
          <div className="citation-badges"><span className={`status-pill ${citation.is_official_policy ? "success" : "warning"}`}>{sourceLabel(citation.source_type, citation.is_official_policy)}</span><span className="status-pill neutral">{citation.document.status}</span></div>
          {!citation.is_official_policy && <div className="inline-warning"><ShieldAlert size={17} />Đây là nguồn tham khảo, không phải chính sách chính thức của công ty.</div>}
          {citation.conflict_warning && <div className="inline-warning"><CircleAlert size={17} />Nguồn này có cảnh báo mâu thuẫn với tài liệu khác.</div>}
          <dl><div><dt>Loại nguồn</dt><dd>{sourceLabel(citation.source_type, citation.is_official_policy)}</dd></div><div><dt>Phiên bản</dt><dd>{citation.document.version ?? "—"}</dd></div><div><dt>Trang / mục</dt><dd>{citation.location.page ?? "—"} · {citation.location.section ?? "—"}</dd></div><div><dt>Hiệu lực</dt><dd>{citation.document.effective_date ?? "—"}</dd></div></dl>
          <blockquote>{citation.excerpt || "Nguồn đã được xác thực nhưng chưa có đoạn trích để hiển thị."}</blockquote>
        </div> : <div className="panel-empty"><FileSearch size={26} /><p>Mở một thẻ nguồn trong câu trả lời để kiểm tra tài liệu.</p></div>}
      </aside>
    </div>
  );
}

function AssistantMessage({ result, activeCitationId, onCitation, onRetry }: {
  result: ChatResult;
  activeCitationId: string | null;
  onCitation: (citation: CitationSummary) => void;
  onRetry: (requestId: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const citations = result.citations ?? [];
  const normalized = normalizeCitationDisplay(
    stripLegacyCitationFooter(result.answer ?? result.failure?.message ?? ""),
    citations,
  );
  const displayAnswer = normalized.answer;
  const listedCitations = normalized.citations;
  const hasCitations = Boolean(listedCitations.length);
  const verified = hasCitations && listedCitations.every((item) => item.is_official_policy);

  async function copyAnswer() {
    if (!result.answer) return;
    await navigator.clipboard.writeText(displayAnswer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return <div className="message assistant-message">
    <div className="assistant-avatar"><BookOpenCheck size={18} /></div>
    <div className="message-body answer-body">
      <div className="answer-meta">
        <span className="assistant-name">HR Intelligence</span>
        {result.latency_ms !== null && <span>{result.latency_ms.toLocaleString()} ms</span>}
      </div>
      {result.state === "COMPLETED" && verified && <div className="trust-banner verified"><Check size={16} /> Câu trả lời từ nguồn đã kiểm chứng</div>}
      {result.state === "COMPLETED" && hasCitations && !verified && <div className="trust-banner reference"><ShieldAlert size={16} /> Có sử dụng nguồn tham khảo</div>}
      {result.state === "REFUSED" && <div className="trust-banner limited"><CircleAlert size={16} /> Thông tin còn hạn chế</div>}
      {result.state === "CLARIFICATION_REQUIRED" ? <div className="clarification-copy"><MessageCircleQuestion size={20} /><div><strong>Cần làm rõ thêm</strong><p>{result.clarification?.question}</p><small>Nhập câu trả lời trong ô chat để tiếp tục cùng phiên.</small></div></div>
        : <AnswerContent answer={displayAnswer} citations={listedCitations} onCitation={onCitation} />}
      {(result.warnings ?? []).map((warning) => <div className="inline-warning" key={`${warning.type}-${warning.message}`}>{warning.message}</div>)}
      {hasCitations && <div className={`citation-list ${sourcesOpen ? "open" : ""}`}>
        <button className="citation-toggle" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen((current) => !current)}><span><Link2 size={15} /> Link tham khảo <small>{listedCitations.length} tài liệu</small></span><ChevronDown size={16} /></button>
        {sourcesOpen && <div className="citation-items">{listedCitations.map((item) => <button className={`${item.is_official_policy ? "" : "unofficial"} ${activeCitationId === item.citation_id ? "active" : ""}`} key={item.citation_id} onClick={() => onCitation(item)}><Link2 className="citation-link-icon" size={16} /><span><strong>{item.title}</strong><small>{sourceLabel(item.source_type, item.is_official_policy)} · {item.section ?? "Không rõ mục"} · Trang {item.page ?? "—"}</small></span>{!item.is_official_policy && <ShieldAlert size={16} />}</button>)}</div>}
      </div>}
      {result.state === "REFUSED" && <div className="escalation-note"><CircleAlert size={17} />Yêu cầu không đủ bằng chứng có thể đã được Backend chuyển thành ticket.</div>}
      {result.state === "FAILED" && result.failure?.retryable && <button className="secondary-command" onClick={() => onRetry(result.chat_request_id)}><RefreshCw size={16} /> Thử lại</button>}
      {result.answer && <div className="answer-actions"><button onClick={() => void copyAnswer()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Đã sao chép" : "Sao chép"}</button></div>}
    </div>
  </div>;
}

function AnswerContent({ answer, citations, onCitation }: {
  answer: string;
  citations: CitationSummary[];
  onCitation: (citation: CitationSummary) => void;
}) {
  const parts = answer.split(/(\[(?:Nguồn\s*)?\d+(?:\s*(?:,|;|và)\s*\d+)*\])/gi);
  return <p className="answer-copy">{parts.map((part, index) => {
    if (!/^\[(?:Nguồn\s*)?\d+(?:\s*(?:,|;|và)\s*\d+)*\]$/i.test(part)) return <span key={`${part}-${index}`}>{part}</span>;
    const numbers = part.match(/\d+/g) ?? [];
    return <span className="inline-citation-group" key={`${part}-${index}`}>{numbers.map((number) => {
      const citation = citations[Number(number) - 1];
      if (!citation) return <span key={number}>[{number}]</span>;
      return <button className="inline-citation" key={number} title={`Mở nguồn ${number}`} onClick={() => onCitation(citation)}>[{number}]</button>;
    })}</span>;
  })}</p>;
}
