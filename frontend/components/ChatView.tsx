"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BookOpenCheck, CircleAlert, FileSearch, LoaderCircle, MessageCircleQuestion, RefreshCw, Send, Square, Trash2 } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { ChatResult, CitationDetail, CitationSummary, ConversationMessage } from "@/lib/types";

type UiMessage =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "assistant"; result: ChatResult };

const TERMINAL_STATES = new Set(["COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"]);

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function historyToUi(message: ConversationMessage): UiMessage {
  if (message.role === "USER") return { id: message.message_id, kind: "user", content: message.content };
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

export function ChatView() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState("CREATING");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [processingState, setProcessingState] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [citation, setCitation] = useState<CitationDetail | null>(null);
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  const startConversation = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const created = await api.createConversation();
      if (!mounted.current) return;
      setConversationId(created.conversation_id);
      setConversationState(created.state);
      setMessages([]);
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tạo cuộc hội thoại.");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }, []);

  useEffect(() => { void startConversation(); }, [startConversation]);

  async function poll(chatRequestId: string, pollAfterMs: number) {
    let result: ChatResult;
    do {
      await wait(Math.max(350, pollAfterMs));
      result = await api.getChatRequest(chatRequestId);
      if (!mounted.current) return;
      setProcessingState(result.state);
    } while (!TERMINAL_STATES.has(result.state));
    setMessages((current) => [...current, { id: result.assistant_message_id ?? chatRequestId, kind: "assistant", result }]);
  }

  async function sendQuestion(text: string) {
    const cleanQuestion = text.trim();
    if (!conversationId || !cleanQuestion || busy || conversationState !== "ACTIVE") return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), kind: "user", content: cleanQuestion }]);
    setQuestion("");
    setBusy(true);
    setError("");
    setProcessingState("QUEUED");
    try {
      const created = await api.createChatRequest(conversationId, cleanQuestion);
      await poll(created.chat_request_id, created.poll_after_ms);
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể xử lý câu hỏi.");
    } finally {
      if (mounted.current) {
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
    setBusy(true);
    setError("");
    setProcessingState("QUEUED");
    try {
      const created = await api.retryChatRequest(chatRequestId);
      await poll(created.chat_request_id, created.poll_after_ms);
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể thử lại yêu cầu.");
    } finally {
      setBusy(false);
      setProcessingState(null);
    }
  }

  async function reloadHistory() {
    if (!conversationId) return;
    setBusy(true);
    try {
      const history = await api.getConversationMessages(conversationId);
      setMessages(history.messages.map(historyToUi));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải lịch sử.");
    } finally {
      setBusy(false);
    }
  }

  async function endConversation() {
    if (!conversationId) return;
    try {
      const ended = await api.endConversation(conversationId);
      setConversationState(ended.state);
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể kết thúc phiên.");
    }
  }

  async function openCitation(item: CitationSummary) {
    try {
      setCitation(await api.getCitation(item.citation_id));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở nguồn.");
    }
  }

  return (
    <div className="chat-workspace">
      <section className="chat-main">
        <header className="workspace-toolbar">
          <div><p className="eyebrow">PHIÊN HỘI THOẠI</p><strong>{conversationId ?? "Đang tạo..."}</strong></div>
          <span className={`status-pill ${conversationState === "ACTIVE" ? "success" : "neutral"}`}>{conversationState}</span>
          <div className="toolbar-actions">
            <button className="icon-command" title="Tải lại lịch sử" onClick={() => void reloadHistory()}><RefreshCw size={17} /></button>
            <button className="icon-command" title="Kết thúc phiên" onClick={() => void endConversation()} disabled={conversationState !== "ACTIVE"}><Square size={16} /></button>
            <button className="icon-command" title="Tạo phiên mới" onClick={() => void startConversation()}><Trash2 size={17} /></button>
          </div>
        </header>

        <div className="message-stream">
          {!messages.length && !busy && (
            <div className="empty-chat">
              <div className="empty-icon"><BookOpenCheck size={28} /></div>
              <h2>Bạn cần tra cứu chính sách nào?</h2>
              <p>Đặt câu hỏi cụ thể để nhận câu trả lời kèm nguồn tài liệu.</p>
              <div className="prompt-row">
                {["Quy định làm việc hybrid như thế nào?", "Nhân viên có bao nhiêu ngày phép năm?"].map((item) => (
                  <button key={item} onClick={() => void sendQuestion(item)}>{item}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) => message.kind === "user"
            ? <div className="message user-message" key={message.id}><div className="message-body">{message.content}</div></div>
            : <AssistantMessage key={message.id} result={message.result} onCitation={openCitation} onRetry={retry} />)}
          {processingState && (
            <div className="message assistant-message"><div className="assistant-avatar"><LoaderCircle className="spin" size={18} /></div><div className="message-body processing"><strong>Đang xử lý</strong><span>{processingState}</span></div></div>
          )}
          {error && <div className="stream-error"><CircleAlert size={17} />{error}</div>}
        </div>

        <form className="composer" onSubmit={submit}>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} disabled={busy || conversationState !== "ACTIVE"} placeholder="Nhập câu hỏi HR hoặc câu trả lời làm rõ..." />
          <div className="composer-footer"><span>{question.length.toLocaleString()} / 2.000</span><button className="send-command" disabled={!question.trim() || busy}><Send size={18} /></button></div>
        </form>
      </section>

      <aside className={`citation-panel ${citation ? "open" : ""}`}>
        <header><div><p className="eyebrow">NGUỒN ĐỐI SOÁT</p><h3>{citation?.document.title ?? "Chọn một trích dẫn"}</h3></div><button className="icon-command" onClick={() => setCitation(null)}>×</button></header>
        {citation ? <div className="citation-detail">
          <span className="status-pill success">{citation.document.status}</span>
          <dl><div><dt>Phiên bản</dt><dd>{citation.document.version ?? "—"}</dd></div><div><dt>Trang / mục</dt><dd>{citation.location.page ?? "—"} · {citation.location.section ?? "—"}</dd></div><div><dt>Hiệu lực</dt><dd>{citation.document.effective_date ?? "—"}</dd></div></dl>
          <blockquote>{citation.excerpt || "Nguồn đã được xác thực nhưng chưa có đoạn trích để hiển thị."}</blockquote>
          {citation.caveat && <div className="inline-warning">{citation.caveat}</div>}
        </div> : <div className="panel-empty"><FileSearch size={26} /><p>Mở một thẻ nguồn trong câu trả lời để kiểm tra tài liệu.</p></div>}
      </aside>
    </div>
  );
}

function AssistantMessage({ result, onCitation, onRetry }: {
  result: ChatResult;
  onCitation: (citation: CitationSummary) => void;
  onRetry: (requestId: string) => void;
}) {
  return <div className="message assistant-message">
    <div className="assistant-avatar"><BookOpenCheck size={18} /></div>
    <div className="message-body answer-body">
      <div className="answer-meta">
        <span className={`status-pill ${result.state === "COMPLETED" ? "success" : result.state === "FAILED" ? "danger" : "warning"}`}>{result.answer_status ?? result.state}</span>
        {result.latency_ms !== null && <span>{result.latency_ms.toLocaleString()} ms</span>}
      </div>
      {result.state === "CLARIFICATION_REQUIRED" ? <div className="clarification-copy"><MessageCircleQuestion size={20} /><div><strong>Cần làm rõ thêm</strong><p>{result.clarification?.question}</p><small>Nhập câu trả lời trong ô chat để tiếp tục cùng phiên.</small></div></div>
        : <p className="answer-copy">{result.answer ?? result.failure?.message}</p>}
      {(result.warnings ?? []).map((warning) => <div className="inline-warning" key={`${warning.type}-${warning.message}`}>{warning.message}</div>)}
      {!!result.citations?.length && <div className="citation-list">{result.citations.map((item) => <button key={item.citation_id} onClick={() => onCitation(item)}><BookOpenCheck size={16} /><span><strong>{item.title}</strong><small>{item.section ?? "Không rõ mục"} · Trang {item.page ?? "—"}</small></span></button>)}</div>}
      {result.state === "REFUSED" && <div className="escalation-note"><CircleAlert size={17} />Yêu cầu không đủ bằng chứng có thể đã được Backend chuyển thành ticket theo kết quả Agent.</div>}
      {result.state === "FAILED" && result.failure?.retryable && <button className="secondary-command" onClick={() => onRetry(result.chat_request_id)}><RefreshCw size={16} /> Thử lại</button>}
    </div>
  </div>;
}
