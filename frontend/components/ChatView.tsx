"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { BookOpenCheck, CircleAlert, FileSearch, LoaderCircle, LogOut, MessageCircleQuestion, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, Pencil, Plus, RefreshCw, Send, Square, Trash2 } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import { chatStateLabel, conversationStateLabel, roleLabel, sourceTypeLabel } from "@/lib/labels";
import type { ChatResult, CitationDetail, CitationSummary, ConversationListItem, ConversationMessage, User } from "@/lib/types";
import { useSystemDialog } from "@/components/SystemDialog";
import { DocumentViewer } from "@/components/DocumentViewer";

type UiMessage =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "assistant"; result: ChatResult };

const TERMINAL_STATES = new Set(["COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"]);

type StarterPrompt = {
  label: string;
  question: string;
};

const DEFAULT_STARTER_PROMPTS: StarterPrompt[] = [
  { label: "Chính sách hybrid", question: "Quy định làm việc hybrid như thế nào?" },
  { label: "Phép năm", question: "Nhân viên có bao nhiêu ngày phép năm?" },
];

const PRODUCT_DEMO_PROMPTS: StarterPrompt[] = [
  {
    label: "Đa nguồn + ảnh scan",
    question: "Recommendation System đã đủ điều kiện mở rộng beta chưa? Hãy đối chiếu PRD, báo cáo tuần và báo cáo latency scan; nêu từng gate còn thiếu và dẫn nguồn.",
  },
  {
    label: "Bảng + biểu đồ funnel",
    question: "Checkout Redesign có nên rollout 100% chưa? Hãy tổng hợp biểu đồ funnel, bảng experiment, guardrail và blocker; so sánh số liệu hiện tại với target và dẫn nguồn.",
  },
  {
    label: "Bảng experiment + research",
    question: "Search Improvements nên ưu tiên accent-insensitive hay fuzzy search? Hãy đối chiếu bảng experiment, phản hồi người dùng và mục tiêu trong PRD rồi giải thích trade-off.",
  },
];

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function isAbortError(reason: unknown) {
  return reason instanceof DOMException && reason.name === "AbortError";
}

function historyToUi(message: ConversationMessage): UiMessage {
  if (message.role.toUpperCase() === "USER") {
    return { id: message.message_id, kind: "user", content: message.content };
  }
  const clarification = message.answer_status === "CLARIFICATION_REQUIRED"
    ? { question: message.content, options: [] }
    : null;
  const state = message.answer_status === "CLARIFICATION_REQUIRED" ? "CLARIFICATION_REQUIRED"
    : message.answer_status === "INSUFFICIENT_EVIDENCE" ? "REFUSED"
      : "COMPLETED";
  const quickPrompts = (message.quick_prompts && message.quick_prompts.length > 0)
    ? message.quick_prompts
    : (message.content && (message.content.includes("trợ lý tri thức nội bộ") || message.content.includes("chọn một gợi ý bên dưới")))
      ? [
        "Nhân viên có bao nhiêu ngày phép năm?",
        "Quy định làm việc hybrid như thế nào?",
        "Quy định về bảo hiểm sức khỏe tự nguyện cho nhân viên như thế nào?",
      ]
      : null;
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
      quick_prompts: quickPrompts,
    },
  };
}

export function ChatView({ user, onLogout, hidden = false }: { user: User; onLogout: () => void; hidden?: boolean }) {
  const dialog = useSystemDialog();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState("CREATING");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [processingState, setProcessingState] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [citation, setCitation] = useState<CitationDetail | null>(null);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [conversationPanelOpen, setConversationPanelOpen] = useState(false);
  const [conversationPanelVisible, setConversationPanelVisible] = useState(true);
  const [compactLayout, setCompactLayout] = useState(false);
  const [conversationPanelWidth, setConversationPanelWidth] = useState(292);
  const [citationPanelWidth, setCitationPanelWidth] = useState(580);
  const mounted = useRef(true);
  const creatingConversation = useRef(false);
  const initializingConversation = useRef(false);
  const loadingConversations = useRef(false);
  const conversationList = useRef<HTMLDivElement>(null);
  const conversationPanelResize = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  const citationPanelResize = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const storageKey = `hr_knowledge_active_conversation:${user.id}`;
  const starterPrompts = user.department.trim().toUpperCase() === "PRODUCT"
    ? PRODUCT_DEMO_PROMPTS
    : DEFAULT_STARTER_PROMPTS;

  useEffect(() => {
    const savedWidth = Number(window.localStorage.getItem("hr_knowledge_conversation_panel_width"));
    if (Number.isFinite(savedWidth) && savedWidth >= 240 && savedWidth <= 420) setConversationPanelWidth(savedWidth);
    const savedCitationWidth = Number(window.localStorage.getItem("hr_knowledge_citation_panel_width"));
    if (Number.isFinite(savedCitationWidth) && savedCitationWidth >= 320 && savedCitationWidth <= 1200) {
      setCitationPanelWidth(savedCitationWidth);
    } else {
      setCitationPanelWidth(580);
    }
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 980px)");
    const syncLayout = () => setCompactLayout(media.matches);
    syncLayout();
    media.addEventListener("change", syncLayout);
    return () => media.removeEventListener("change", syncLayout);
  }, []);

  function toggleConversationPanel() {
    if (compactLayout) {
      setConversationPanelVisible(true);
      setConversationPanelOpen((open) => !open);
      return;
    }
    setConversationPanelOpen(false);
    setConversationPanelVisible((visible) => !visible);
  }

  function updateConversationPanelWidth(width: number) {
    const nextWidth = Math.min(420, Math.max(240, Math.round(width)));
    setConversationPanelWidth(nextWidth);
    window.localStorage.setItem("hr_knowledge_conversation_panel_width", String(nextWidth));
  }

  function beginConversationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    conversationPanelResize.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: conversationPanelWidth };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveConversationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    const resize = conversationPanelResize.current;
    if (!resize || resize.pointerId !== event.pointerId) return;
    updateConversationPanelWidth(resize.startWidth + event.clientX - resize.startX);
  }

  function endConversationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (conversationPanelResize.current?.pointerId === event.pointerId) conversationPanelResize.current = null;
  }

  function resizeConversationPanelWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    updateConversationPanelWidth(conversationPanelWidth + (event.key === "ArrowRight" ? 12 : -12));
  }

  function updateCitationPanelWidth(width: number) {
    const maxWidth = typeof window !== "undefined" ? Math.min(1100, Math.round(window.innerWidth * 0.75)) : 950;
    const nextWidth = Math.min(maxWidth, Math.max(320, Math.round(width)));
    setCitationPanelWidth(nextWidth);
    window.localStorage.setItem("hr_knowledge_citation_panel_width", String(nextWidth));
  }

  function beginCitationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    citationPanelResize.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: citationPanelWidth };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveCitationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    const resize = citationPanelResize.current;
    if (!resize || resize.pointerId !== event.pointerId) return;
    updateCitationPanelWidth(resize.startWidth - (event.clientX - resize.startX));
  }

  function endCitationPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (citationPanelResize.current?.pointerId === event.pointerId) citationPanelResize.current = null;
  }

  function resizeCitationPanelWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    updateCitationPanelWidth(citationPanelWidth + (event.key === "ArrowLeft" ? 16 : -16));
  }


  const updateConversationStack = useCallback(() => {
    const list = conversationList.current;
    if (!list) return;
    const styles = window.getComputedStyle(list);
    const stackInset = Number.parseFloat(styles.getPropertyValue("--conversation-stack-inset")) || 0;
    const stackStep = Number.parseFloat(styles.getPropertyValue("--conversation-stack-step")) || 5;
    const cardGap = Number.parseFloat(styles.getPropertyValue("--conversation-card-gap")) || 7;
    const cards = Array.from(list.querySelectorAll<HTMLElement>(".conversation-item"));
    cards.forEach((card, index) => {
      const content = card.querySelector<HTMLElement>(".conversation-item-content");
      if (!content) return;
      const stickyTop = stackInset + Math.min(index, 6) * stackStep;
      const pinAt = stackInset + index * (card.offsetHeight + cardGap) - stickyTop;
      const progress = Math.min(1, Math.max(0, (list.scrollTop - pinAt) / Math.max(card.offsetHeight, 1)));
      content.style.setProperty("--conversation-stack-scale-y", String(1 - progress * .035));
      content.style.setProperty("--conversation-stack-lift", `${progress * -4}px`);
      content.style.setProperty("--conversation-stack-tilt", `${progress * -6}deg`);
      content.style.setProperty("--conversation-stack-brightness", String(1 - progress * .16));
    });
  }, []);

  const loadConversations = useCallback(async () => {
    if (loadingConversations.current) return;
    loadingConversations.current = true;
    setListLoading(true);
    setListError("");
    try {
      setConversations(await api.listConversations());
    } catch (reason) {
      setListError(reason instanceof ApiClientError && reason.status === 404
        ? "Chưa tải được danh sách hội thoại."
        : reason instanceof ApiClientError ? reason.message : "Không thể tải danh sách hội thoại.");
    } finally {
      loadingConversations.current = false;
      if (mounted.current) setListLoading(false);
    }
  }, []);

  const startConversation = useCallback(async () => {
    if (creatingConversation.current) return;
    creatingConversation.current = true;
    pollController.current?.abort();
    setBusy(true);
    setError("");
    setConversationId(null);
    setConversationState("CREATING");
    try {
      const created = await api.createConversation();
      if (!mounted.current) return;
      setConversationId(created.conversation_id);
      setConversationState(created.state);
      setMessages([]);
      window.localStorage.setItem(storageKey, created.conversation_id);
      setConversations((current) => [
        {
          conversation_id: created.conversation_id,
          title: created.title ?? "Hội thoại mới",
          state: created.state,
          created_at: created.created_at || new Date().toISOString(),
          updated_at: created.created_at || new Date().toISOString(),
          ended_at: null,
          message_count: 0,
          last_message_at: null,
        },
        ...current.filter((c) => c.conversation_id !== created.conversation_id),
      ]);
    } catch (reason) {
      if (mounted.current) {
        setError(reason instanceof ApiClientError ? reason.message : "Không thể tạo cuộc hội thoại.");
      }
    } finally {
      creatingConversation.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [storageKey]);

  const openConversation = useCallback(async (selectedId: string) => {
    if (selectedId === conversationId) {
      setConversationPanelOpen(false);
      return;
    }
    pollController.current?.abort();
    setBusy(true);
    setError("");
    setCitation(null);
    try {
      const [conversation, history] = await Promise.all([
        api.getConversation(selectedId),
        api.getConversationMessages(selectedId),
      ]);
      if (!mounted.current) return;
      setConversationId(conversation.conversation_id);
      setConversationState(conversation.state);
      setMessages(history.messages.map(historyToUi));
      window.localStorage.setItem(storageKey, conversation.conversation_id);
      setConversationPanelOpen(false);
    } catch (reason) {
      if (mounted.current) setError(reason instanceof ApiClientError ? reason.message : "Không thể mở cuộc hội thoại.");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }, [conversationId, storageKey]);

  const initializeConversation = useCallback(async () => {
    if (initializingConversation.current) return;
    initializingConversation.current = true;
    const savedConversationId = window.localStorage.getItem(storageKey);
    if (!savedConversationId) {
      await startConversation();
      initializingConversation.current = false;
      return;
    }

    setBusy(true);
    setError("");
    try {
      const [conversation, history] = await Promise.all([
        api.getConversation(savedConversationId),
        api.getConversationMessages(savedConversationId),
      ]);
      if (!mounted.current) return;
      setConversationId(conversation.conversation_id);
      setConversationState(conversation.state);
      setMessages(history.messages.map(historyToUi));
    } catch (reason) {
      if (reason instanceof ApiClientError && [403, 404].includes(reason.status)) {
        window.localStorage.removeItem(storageKey);
        await startConversation();
      } else if (mounted.current) {
        setError(reason instanceof ApiClientError ? reason.message : "Không thể khôi phục cuộc hội thoại.");
      }
    } finally {
      initializingConversation.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [startConversation, storageKey]);

  useEffect(() => {
    mounted.current = true;
    void initializeConversation();
    void loadConversations();
    return () => {
      mounted.current = false;
      pollController.current?.abort();
    };
  }, [initializeConversation, loadConversations]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(updateConversationStack);
    return () => window.cancelAnimationFrame(frame);
  }, [conversations, updateConversationStack]);

  async function poll(chatRequestId: string, pollAfterMs: number, placeholderMessageId?: string) {
    const controller = new AbortController();
    pollController.current?.abort();
    pollController.current = controller;
    let result: ChatResult;
    const deadline = Date.now() + 5 * 60 * 1000;
    do {
      if (Date.now() >= deadline) {
        throw new ApiClientError("Agent xử lý quá lâu. Hãy tải lại lịch sử hoặc thử lại yêu cầu.", "POLL_TIMEOUT", 0, true);
      }
      await wait(Math.max(350, pollAfterMs));
      result = await api.getChatRequest(chatRequestId, controller.signal);
      if (!mounted.current) return;
      setProcessingState(result.state);
    } while (!TERMINAL_STATES.has(result.state));

    const finalMessageId = result.assistant_message_id ?? chatRequestId;
    setMessages((current) => {
      if (placeholderMessageId) {
        const index = current.findIndex((m) => m.id === placeholderMessageId);
        if (index !== -1) {
          const next = [...current];
          next[index] = { id: finalMessageId, kind: "assistant", result };
          return next;
        }
      }
      const existingIdx = current.findIndex((m) => m.id === finalMessageId);
      if (existingIdx !== -1) {
        const next = [...current];
        next[existingIdx] = { id: finalMessageId, kind: "assistant", result };
        return next;
      }
      return [...current, { id: finalMessageId, kind: "assistant", result }];
    });
    void loadConversations();
    if (pollController.current === controller) pollController.current = null;
  }

  async function sendQuestion(text: string) {
    const cleanQuestion = text.trim();
    if (!conversationId || !cleanQuestion || busy || conversationState !== "ACTIVE") return;
    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    setMessages((current) => [
      ...current,
      { id: userMsgId, kind: "user", content: cleanQuestion },
    ]);
    setQuestion("");
    setBusy(true);
    setError("");
    setProcessingState("QUEUED");

    const controller = new AbortController();
    pollController.current?.abort();
    pollController.current = controller;

    let activeChatRequestId: string | null = null;
    let accumulatedAnswer = "";
    let receivedResult = false;
    const accumulatedCitations: CitationSummary[] = [];

    try {
      await api.streamChatRequest(
        conversationId,
        cleanQuestion,
        (event) => {
          if (!mounted.current) return;
          if (event.type === "request") {
            activeChatRequestId = event.chat_request_id;
            setProcessingState(event.state || "QUEUED");
          } else if (event.type === "status") {
            setProcessingState(event.value);
          } else if (event.type === "answer_delta") {
            accumulatedAnswer += event.content;
            setMessages((current) => {
              const existingIdx = current.findIndex((m) => m.id === assistantMsgId);
              const streamingResult: ChatResult = {
                chat_request_id: activeChatRequestId || "",
                conversation_id: conversationId,
                user_message_id: userMsgId,
                assistant_message_id: assistantMsgId,
                state: "GENERATING",
                answer_status: null,
                answer: accumulatedAnswer,
                citations: accumulatedCitations,
                warnings: [],
                clarification: null,
                failure: null,
                latency_ms: null,
              };
              if (existingIdx !== -1) {
                const next = [...current];
                next[existingIdx] = { id: assistantMsgId, kind: "assistant", result: streamingResult };
                return next;
              }
              return [...current, { id: assistantMsgId, kind: "assistant", result: streamingResult }];
            });
          } else if (event.type === "citation") {
            accumulatedCitations.push({
              citation_id: event.document_id || crypto.randomUUID(),
              title: event.title,
              page: event.page_start,
              sheet: null,
              section: event.section || null,
              version: null,
              effective_date: null,
              source_type: "internal_policy",
              is_official_policy: event.is_official_policy,
              public_url: event.public_url || null,
              document_id: event.document_id || null,
              excerpt: event.excerpt || undefined,
            });
            setMessages((current) => {
              const existingIdx = current.findIndex((m) => m.id === assistantMsgId);
              if (existingIdx !== -1 && current[existingIdx].kind === "assistant") {
                const prevResult = (current[existingIdx] as { result: ChatResult }).result;
                const next = [...current];
                next[existingIdx] = {
                  ...current[existingIdx],
                  result: { ...prevResult, citations: [...accumulatedCitations] },
                };
                return next;
              }
              return current;
            });
          } else if (event.type === "result") {
            receivedResult = true;
            const result = event.data;
            const finalId = result.assistant_message_id ?? activeChatRequestId ?? assistantMsgId;
            setMessages((current) => {
              const existingIdx = current.findIndex((m) => m.id === assistantMsgId || m.id === finalId);
              if (existingIdx !== -1) {
                const next = [...current];
                next[existingIdx] = { id: finalId, kind: "assistant", result };
                return next;
              }
              return [...current, { id: finalId, kind: "assistant", result }];
            });
            // Cập nhật sidebar ngầm (Non-blocking)
            void loadConversations();
          }
        },
        controller.signal,
      );

      // Nếu stream kết thúc mà chưa nhận được event result hoàn chỉnh, fallback sang poll
      if (!receivedResult && activeChatRequestId) {
        await poll(activeChatRequestId, 1000, assistantMsgId);
      }
    } catch (reason) {
      if (isAbortError(reason) || controller.signal.aborted) return;

      // Fallback sang Polling nếu stream bị gián đoạn và đã có chat_request_id
      if (activeChatRequestId && !receivedResult) {
        try {
          await poll(activeChatRequestId, 1000, assistantMsgId);
          return;
        } catch (pollReason) {
          if (isAbortError(pollReason)) return;
          setError(pollReason instanceof ApiClientError ? pollReason.message : "Không thể xử lý câu hỏi.");
        }
      } else {
        setError(reason instanceof ApiClientError ? reason.message : "Không thể xử lý câu hỏi.");
      }
    } finally {
      if (mounted.current) {
        setBusy(false);
        setProcessingState(null);
      }
      if (pollController.current === controller) pollController.current = null;
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await sendQuestion(question);
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (question.trim() && !busy && conversationState === "ACTIVE") void sendQuestion(question);
  }

  async function retry(chatRequestId: string) {
    setBusy(true);
    setError("");
    setProcessingState("QUEUED");
    try {
      const created = await api.retryChatRequest(chatRequestId);
      await poll(created.chat_request_id, created.poll_after_ms);
      void loadConversations();
    } catch (reason) {
      if (isAbortError(reason)) return;
      setError(reason instanceof ApiClientError ? reason.message : "Không thể thử lại yêu cầu.");
    } finally {
      if (mounted.current) {
        setBusy(false);
        setProcessingState(null);
      }
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
      await loadConversations();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể kết thúc phiên.");
    }
  }

  async function renameConversation(item: ConversationListItem) {
    const title = await dialog.prompt({
      title: "Đổi tên hội thoại",
      message: "Tên ngắn, rõ nội dung sẽ giúp tìm lại nhanh hơn.",
      inputLabel: "Tên hội thoại",
      initialValue: item.title?.trim() || "Hội thoại mới",
      confirmLabel: "Lưu tên",
    });
    if (!title) return;
    try {
      const updated = await api.renameConversation(item.conversation_id, title);
      setConversations((current) => current.map((conversation) => conversation.conversation_id === item.conversation_id
        ? { ...conversation, title: updated.title, updated_at: new Date().toISOString() }
        : conversation));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể đổi tên hội thoại.");
    }
  }

  async function deleteConversation(item: ConversationListItem) {
    const confirmed = await dialog.confirm({
      title: "Xóa khỏi lịch sử?",
      message: `“${item.title?.trim() || "Hội thoại chưa đặt tên"}” sẽ biến mất khỏi danh sách. Dữ liệu audit liên quan vẫn được giữ.`,
      confirmLabel: "Xóa hội thoại",
      cancelLabel: "Giữ lại",
      tone: "danger",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteConversation(item.conversation_id);
      setConversations((current) => current.filter((conversation) => conversation.conversation_id !== item.conversation_id));
      if (item.conversation_id === conversationId) {
        pollController.current?.abort();
        window.localStorage.removeItem(storageKey);
        setConversationId(null);
        setMessages([]);
        setConversationState("CREATING");
      }
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể xóa hội thoại.");
      return;
    } finally {
      setBusy(false);
    }
    if (item.conversation_id === conversationId) await startConversation();
  }

  async function openCitation(item: CitationSummary) {
    // Nếu citation đã có sẵn public_url hoặc excerpt trong câu trả lời -> Mở ngay lập tức không cần đợi BE!
    if (item.public_url || item.excerpt) {
      setCitation({
        citation_id: item.citation_id,
        public_url: item.public_url ?? null,
        document: {
          document_id: item.document_id || `doc_${item.citation_id}`,
          title: item.title,
          version: item.version ?? null,
          effective_date: item.effective_date ?? null,
          status: "ACTIVE",
          is_official_policy: item.is_official_policy,
          source_type: item.source_type,
          public_url: item.public_url ?? null,
        },
        location: {
          page: item.page ?? null,
          sheet: item.sheet ?? null,
          section: item.section ?? null,
          chunk_id: item.chunk_id ?? null,
        },
        excerpt: item.excerpt || "",
        is_official_policy: item.is_official_policy,
        source_type: item.source_type,
      });
      return;
    }

    try {
      setCitation(await api.getCitation(item.citation_id));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở nguồn.");
    }
  }

  return (
    <div className={`chat-workspace${conversationPanelVisible ? "" : " conversation-panel-collapsed"}${conversationPanelOpen ? " conversation-panel-open" : ""}${hidden ? "" : " animate__animated animate__fadeInUp motion-view"}`} style={{ ...(hidden ? { display: "none" } : {}), "--conversation-panel-width": `${conversationPanelWidth}px` } as CSSProperties}>
      <button className="conversation-menu-command icon-command" aria-label={compactLayout ? (conversationPanelOpen ? "Đóng danh sách hội thoại" : "Mở danh sách hội thoại") : (conversationPanelVisible ? "Đóng danh sách hội thoại" : "Mở danh sách hội thoại")} aria-expanded={compactLayout ? conversationPanelOpen : conversationPanelVisible} title={compactLayout ? (conversationPanelOpen ? "Đóng lịch sử hội thoại" : "Mở lịch sử hội thoại") : (conversationPanelVisible ? "Đóng lịch sử hội thoại" : "Mở lịch sử hội thoại")} onClick={toggleConversationPanel}>{(compactLayout ? conversationPanelOpen : conversationPanelVisible) ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}</button>
      {conversationPanelOpen && <button className="conversation-overlay" aria-label="Đóng danh sách hội thoại" onClick={() => setConversationPanelOpen(false)} />}
      <aside className={`conversation-panel ${conversationPanelOpen ? "open" : ""} ${conversationPanelVisible ? "" : "collapsed"}`} style={{ "--conversation-panel-width": `${conversationPanelWidth}px` } as CSSProperties} aria-label="Danh sách hội thoại" data-ui="community-feed">
        <button className="primary-command new-conversation-command" onClick={() => void startConversation()} disabled={busy}><Plus size={17} /> Hội thoại mới</button>
        <div ref={conversationList} className="conversation-list" aria-live="polite" onScroll={updateConversationStack}>
          {listLoading && <div className="conversation-list-state"><LoaderCircle className="spin" size={18} /> Đang tải...</div>}
          {!listLoading && listError && <div className="conversation-list-state error"><CircleAlert size={18} /><span>{listError}</span><button className="secondary-command" onClick={() => void loadConversations()}><RefreshCw size={15} /> Thử lại</button></div>}
          {!listLoading && !listError && !conversations.length && <div className="conversation-list-state"><MessageSquarePlus size={21} /><span>Chưa có hội thoại.</span></div>}
          {conversations.map((item, index) => {
            const current = item.conversation_id === conversationId;
            return <div key={item.conversation_id} className={`conversation-item ${current ? "current" : ""}`} style={{ "--conversation-stack-index": Math.min(index, 6) } as CSSProperties}>
              <div className="conversation-item-content">
                <button className="conversation-open-command" aria-current={current ? "true" : undefined} onClick={() => void openConversation(item.conversation_id)}>
                  <span className="conversation-item-top"><strong>{item.title?.trim() || "Hội thoại chưa đặt tên"}</strong><span className={`status-pill ${item.state === "ACTIVE" ? "success" : "neutral"}`}>{conversationStateLabel(item.state)}</span></span>
                  <span className="conversation-item-time">Cập nhật {formatUpdatedAt(item.updated_at || item.last_message_at || item.created_at)}</span>
                </button>
                <span className="conversation-item-actions">
                  <button aria-label={`Đổi tên ${item.title || "hội thoại"}`} title="Đổi tên" onClick={() => void renameConversation(item)}><Pencil size={13} /></button>
                  <button className="danger" aria-label={`Xóa ${item.title || "hội thoại"}`} title="Xóa khỏi lịch sử" onClick={() => void deleteConversation(item)}><Trash2 size={13} /></button>
                </span>
              </div>
            </div>;
          })}
        </div>
        <div className="conversation-account"><span className="profile-avatar">{user.full_name.split(" ").map((part) => part[0]).slice(-2).join("")}</span><span className="conversation-account-copy"><strong>{user.full_name}</strong><small>{roleLabel(user.role)}</small></span><button className="icon-command top-logout" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout}><LogOut size={17} /></button></div>
        <div className="bar-resizer conversation-resizer" role="separator" aria-label="Điều chỉnh chiều rộng lịch sử hội thoại" aria-orientation="vertical" aria-valuemin={240} aria-valuemax={420} aria-valuenow={conversationPanelWidth} tabIndex={0} onPointerDown={beginConversationPanelResize} onPointerMove={moveConversationPanelResize} onPointerUp={endConversationPanelResize} onPointerCancel={endConversationPanelResize} onKeyDown={resizeConversationPanelWithKeyboard} />
      </aside>
      <section className="chat-main" data-ui="dashboard">
        <div className="chat-glass-blob" aria-hidden="true" />
        <header className="workspace-toolbar">
          <div><p className="eyebrow">PHIÊN HỘI THOẠI</p><strong>{conversations.find((item) => item.conversation_id === conversationId)?.title || conversationId || "Đang tạo..."}</strong></div>
          <span className={`status-pill ${conversationState === "ACTIVE" ? "success" : "neutral"}`}>{conversationStateLabel(conversationState)}</span>
          <div className="toolbar-actions">
            <button className="icon-command" title="Tải lại lịch sử" onClick={() => void reloadHistory()} disabled={!conversationId || busy}><RefreshCw size={17} /></button>
            <button className="icon-command" title="Kết thúc phiên" onClick={() => void endConversation()} disabled={conversationState !== "ACTIVE"}><Square size={16} /></button>
            <button className="icon-command" title="Tạo hội thoại mới" aria-label="Tạo hội thoại mới" onClick={() => void startConversation()} disabled={busy}><Plus size={17} /></button>
          </div>
        </header>

        <div className="message-stream">
          {!messages.length && !busy && (
            <div className="empty-chat animate__animated animate__zoomIn motion-view">
              <div className="empty-icon"><BookOpenCheck size={28} /></div>
              <h2>Bạn cần tra cứu thông tin nào?</h2>
              <p>{user.department.trim().toUpperCase() === "PRODUCT"
                ? "Chọn một tình huống khó để tổng hợp dữ liệu từ nhiều tài liệu, bảng, biểu đồ và ảnh scan kèm nguồn đối soát."
                : "Đặt câu hỏi cụ thể về quy trình, quy định hoặc chính sách nội bộ để nhận câu trả lời kèm nguồn tài liệu."}</p>
              <div className="prompt-row">
                {starterPrompts.map((item) => (
                  <button key={item.label} onClick={() => void sendQuestion(item.question)}>
                    <strong>{item.label}</strong>
                    <span>{item.question}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) => message.kind === "user"
            ? <div className="message user-message" key={message.id}><div className="message-body">{message.content}</div></div>
            : <AssistantMessage key={message.id} result={message.result} onCitation={openCitation} onRetry={retry} onQuickPrompt={(q) => void sendQuestion(q)} />)}
          {processingState && !messages.some((m) => m.kind === "assistant" && m.result.state === "GENERATING") && (
            <div className="message assistant-message animate__animated animate__fadeInLeft motion-message"><div className="assistant-avatar"><LoaderCircle className="spin" size={18} /></div><div className="message-body processing processing-pulse animate__animated animate__pulse animate__infinite"><strong>Đang xử lý</strong><span>{chatStateLabel(processingState)}</span></div></div>
          )}
          {error && <div className="stream-error"><CircleAlert size={17} /><span>{error}</span>{!conversationId && !busy && <button className="secondary-command" onClick={() => void startConversation()}><RefreshCw size={16} /> Thử lại</button>}</div>}
        </div>

        <form className="composer" onSubmit={submit} data-ui="membership-card">
          <textarea aria-label="Câu hỏi" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleQuestionKeyDown} disabled={busy || conversationState !== "ACTIVE"} placeholder="Nhập câu hỏi về tài liệu nội bộ hoặc câu trả lời làm rõ..." />
          <div className="composer-footer"><span>Enter gửi · Shift+Enter xuống dòng</span><button className="send-command" aria-label="Gửi câu hỏi" data-ui="primary-action" disabled={!question.trim() || busy || conversationState !== "ACTIVE"}><Send size={18} /></button></div>
        </form>
      </section>

      <aside className={`citation-panel ${citation ? "open" : ""}`} style={{ "--citation-panel-width": `${citationPanelWidth}px` } as CSSProperties}>
        <div className="bar-resizer citation-resizer" role="separator" aria-label="Điều chỉnh chiều rộng nguồn đối soát" aria-orientation="vertical" aria-valuemin={320} aria-valuemax={1100} aria-valuenow={citationPanelWidth} tabIndex={citation ? 0 : -1} onPointerDown={beginCitationPanelResize} onPointerMove={moveCitationPanelResize} onPointerUp={endCitationPanelResize} onPointerCancel={endCitationPanelResize} onKeyDown={resizeCitationPanelWithKeyboard} />
        <header><div><p className="eyebrow">NGUỒN ĐỐI SOÁT</p><h3>{citation?.document.title ?? "Chọn một trích dẫn"}</h3></div><button className="icon-command" onClick={() => setCitation(null)}>×</button></header>
        {citation ? <div className="citation-detail animate__animated animate__slideInRight motion-view" style={{ overflowY: "auto", height: "calc(100% - 64px)" }}>
          {/* <div className="citation-trust-row shrink-0">
            <span className={`status-pill ${isOfficialCitation(citation) ? "success" : "warning"}`}>
              {isOfficialCitation(citation) ? <><ShieldCheck size={12} /> Chính sách chính thức</> : "Nguồn tham khảo"}
            </span>
            <span className="source-type">{formatSourceType(citation.source_type ?? citation.document.source_type)}</span>
          </div> */}
          <dl>
            <div><dt>Trang / mục</dt><dd className="truncate" title={`${citation.location.page ?? "—"} · ${citation.location.section ?? "—"}`}>{citation.location.page ?? "—"} · {citation.location.section ?? "—"}</dd></div>
            <div><dt>Hiệu lực</dt><dd className="truncate" title={citation.document.effective_date ?? "—"}>{citation.document.effective_date ?? "—"}</dd></div>
            <div><dt>Trạng thái</dt><dd className="truncate" title={citation.document.status}>{citation.document.status}</dd></div>
            <div><dt>Phiên bản</dt><dd className="truncate" title={citation.document.version ?? "1.0"}>{citation.document.version ?? "1.0"}</dd></div>
          </dl>
          <DocumentViewer key={citation.document.document_id || citation.public_url || citation.document.title} citation={citation} />
          {(citation.caveat || citation.conflict_warning)
            && <div className="inline-warning shrink-0">{citation.caveat ?? "Nguồn này có thông tin cần đối soát thêm."}
            </div>}
        </div> : <div className="panel-empty"><FileSearch size={26} /><p>Mở một thẻ nguồn trong câu trả lời để kiểm tra tài liệu.</p></div>}



      </aside>
    </div>
  );
}

function formatUpdatedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function isOfficialCitation(item: CitationSummary | CitationDetail) {
  if ("document" in item) return item.is_official_policy ?? item.document.is_official_policy ?? false;
  return item.is_official_policy ?? false;
}

function formatSourceType(value: string | null | undefined) {
  return sourceTypeLabel(value);
}

function AssistantMessage({ result, onCitation, onRetry, onQuickPrompt }: {
  result: ChatResult;
  onCitation: (citation: CitationSummary) => void;
  onRetry: (requestId: string) => void;
  onQuickPrompt: (question: string) => void;
}) {
  const isGenerating = result.state === "GENERATING";
  return <div className="message assistant-message">
    <div className="assistant-avatar"><BookOpenCheck size={18} /></div>
    <div className="message-body answer-body">
      <div className="answer-meta">
        <span className={`status-pill ${result.state === "COMPLETED" ? "success" : result.state === "FAILED" ? "danger" : isGenerating ? "neutral" : "warning"}`}>{chatStateLabel(result.answer_status ?? result.state)}</span>
        {result.latency_ms !== null && <span>{formatLatency(result.latency_ms)}</span>}
      </div>
      {result.state === "CLARIFICATION_REQUIRED" ? <div className="clarification-copy"><MessageCircleQuestion size={20} /><div><strong>Cần làm rõ thêm</strong><p>{result.clarification?.question}</p><small>Nhập câu trả lời trong ô chat để tiếp tục cùng phiên.</small></div></div>
        : <AnswerMarkdown content={result.answer ?? result.failure?.message ?? ""} />}
      {isGenerating && <span className="typing-cursor" style={{ opacity: 0.8, animation: "pulse 1s infinite" }}> ▌</span>}
      {(result.warnings ?? []).map((warning) => <div className="inline-warning" key={`${warning.type}-${warning.message}`}>{warning.message}</div>)}
      {!!result.citations?.length && <div className="citation-list">{result.citations.map((item) => <button key={item.citation_id} onClick={() => onCitation(item)}><BookOpenCheck size={16} /><span><strong>{item.title}</strong><small>{item.section ?? "Không rõ mục"} · {item.sheet ? `Sheet ${item.sheet}` : `Trang ${item.page ?? "—"}`}</small><em className={isOfficialCitation(item) ? "official" : "reference"}>{isOfficialCitation(item) ? "Chính thức" : formatSourceType(item.source_type)}</em></span></button>)}</div>}
      {!!result.quick_prompts?.length && (
        <div className="quick-prompt-row">
          <small className="quick-prompt-label">Gợi ý câu hỏi:</small>
          <div className="quick-prompt-chips">
            {result.quick_prompts.map((prompt) => (
              <button key={prompt} className="quick-prompt-chip" onClick={() => onQuickPrompt(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}
      {result.state === "REFUSED" && <div className="escalation-note"><CircleAlert size={17} />Kho tài liệu hiện chưa đủ căn cứ để trả lời câu hỏi này. Hệ thống không tự tạo yêu cầu hỗ trợ — nếu bạn vẫn cần câu trả lời chính thức, hãy tạo ticket ở mục Ticket để người phụ trách xử lý.</div>}
      {result.state === "FAILED" && result.failure?.retryable && <button className="secondary-command" onClick={() => onRetry(result.chat_request_id)}><RefreshCw size={16} /> Thử lại</button>}
    </div>
  </div>;
}

function formatLatency(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds.toLocaleString("vi-VN")} ms`;
  return `${(milliseconds / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} giây`;
}

function inlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    return part;
  });
}

function AnswerMarkdown({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let list: string[] = [];

  function flushList() {
    if (!list.length) return;
    blocks.push(<ul key={`list-${blocks.length}`}>{list.map((item, index) => <li key={index}>{inlineMarkdown(item)}</li>)}</ul>);
    list = [];
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    const item = line.match(/^[-*]\s+(.+)$/);
    if (item) {
      list.push(item[1]);
      return;
    }
    flushList();
    if (!line) return;
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    blocks.push(heading
      ? <h4 key={`heading-${blocks.length}`}>{inlineMarkdown(heading[1])}</h4>
      : <p key={`paragraph-${blocks.length}`}>{inlineMarkdown(line)}</p>);
  });
  flushList();
  return <div className="answer-copy">{blocks}</div>;
}
