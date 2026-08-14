"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  BookOpenCheck,
  CircleAlert,
  Database,
  FileText,
  FlaskConical,
  History,
  LogOut,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Pencil,
  RefreshCw,
  Ticket,
  Trash2,
  X,
} from "lucide-react";
import { api, ApiClientError, clearSession, hasSession } from "@/lib/api";
import type { ConversationDetail, User } from "@/lib/types";
import { ChatView, clearChatRecovery } from "./ChatView";
import { DocumentsView, OperationsView } from "./KnowledgeAdmin";
import { LoginView } from "./LoginView";
import { TicketsView } from "./TicketsView";
import { useSystemDialog } from "./SystemDialog";

type View = "chat" | "tickets" | "documents" | "index" | "evaluation";
type ConversationMenu = { conversationId: string; top: number; left: number };

const employeeItems = [
  { id: "chat" as const, label: "AI Assistant", icon: MessageSquare },
  { id: "tickets" as const, label: "Ticket của tôi", icon: Ticket },
];

const adminItems = [
  { id: "documents" as const, label: "Kho tài liệu", icon: FileText },
  { id: "index" as const, label: "Index & RAG", icon: Database },
  { id: "evaluation" as const, label: "Đánh giá chất lượng", icon: FlaskConical },
];

function roleLabel(role: string) {
  if (role === "SUPER_ADMIN") return "Super Admin";
  if (role === "HR_ADMIN") return "HR Admin";
  return "Nhân viên";
}

function conversationDate(conversation: ConversationDetail) {
  return new Date(conversation.last_message_at ?? conversation.created_at);
}

function conversationGroup(conversation: ConversationDetail) {
  const date = conversationDate(conversation);
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayDifference = Math.floor((startOfToday - startOfDate) / 86_400_000);
  if (dayDifference <= 0) return "Hôm nay";
  if (dayDifference === 1) return "Hôm qua";
  if (dayDifference <= 7) return "7 ngày qua";
  return "Cũ hơn";
}

function conversationMeta(conversation: ConversationDetail) {
  return `${conversationDate(conversation).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} · ${conversation.message_count} tin nhắn`;
}

const conversationGroups = ["Hôm nay", "Hôm qua", "7 ngày qua", "Cũ hơn"];
const HISTORY_PAGE_SIZE = 8;

export function HrKnowledgeApp() {
  const dialog = useSystemDialog();
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [view, setView] = useState<View>("chat");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [newConversationSignal, setNewConversationSignal] = useState(0);
  const [conversations, setConversations] = useState<ConversationDetail[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(HISTORY_PAGE_SIZE);
  const [conversationMenu, setConversationMenu] = useState<ConversationMenu | null>(null);

  async function restoreSession() {
    if (!hasSession()) {
      setCheckingSession(false);
      return;
    }
    setCheckingSession(true);
    setSessionError("");
    try {
      setUser(await api.me());
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 401) {
        clearSession();
        clearChatRecovery();
      } else {
        setSessionError(reason instanceof ApiClientError ? reason.message : "Không thể khôi phục phiên đăng nhập.");
      }
    } finally {
      setCheckingSession(false);
    }
  }

  useEffect(() => {
    void restoreSession();
  }, []);

  useEffect(() => {
    if (!conversationMenu) return;
    function closeMenu(event: KeyboardEvent | Event) {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      setConversationMenu(null);
    }
    window.addEventListener("keydown", closeMenu);
    window.addEventListener("resize", closeMenu);
    window.addEventListener("scroll", closeMenu, true);
    return () => {
      window.removeEventListener("keydown", closeMenu);
      window.removeEventListener("resize", closeMenu);
      window.removeEventListener("scroll", closeMenu, true);
    };
  }, [conversationMenu]);

  function logout() {
    clearSession();
    clearChatRecovery();
    setUser(null);
    setView("chat");
    setConversations([]);
    setSelectedConversationId(null);
    setVisibleHistoryCount(HISTORY_PAGE_SIZE);
    setConversationMenu(null);
  }

  function requestNewConversation() {
    setView("chat");
    setMobileMenu(false);
    setSelectedConversationId(null);
    setConversationMenu(null);
    setNewConversationSignal((value) => value + 1);
  }

  const handleConversationsChange = useCallback((next: ConversationDetail[]) => {
    setConversations(next);
  }, []);

  const handleConversationSelected = useCallback((conversationId: string) => {
    setSelectedConversationId(conversationId);
  }, []);

  function selectConversation(conversationId: string) {
    setView("chat");
    setMobileMenu(false);
    setSelectedConversationId(conversationId);
    setConversationMenu(null);
  }

  async function refreshConversations() {
    try {
      setConversations(await api.listConversations());
    } catch (reason) {
      await dialog.alert({ title: "Chưa tải được lịch sử", message: reason instanceof ApiClientError ? reason.message : "Không thể tải danh sách hội thoại.", confirmLabel: "Đã hiểu" });
    }
  }

  async function renameConversation(conversation: ConversationDetail) {
    setConversationMenu(null);
    const title = await dialog.prompt({
      title: "Đổi tên hội thoại",
      message: "Đặt một tên ngắn gọn để bạn dễ tìm lại trong lịch sử.",
      inputLabel: "Tên hội thoại",
      initialValue: conversation.title === "Hội thoại mới" ? "" : conversation.title,
      placeholder: "Ví dụ: Chính sách nghỉ phép",
      confirmLabel: "Lưu tên",
    });
    if (!title?.trim() || title.trim() === conversation.title) return;
    try {
      const updated = await api.renameConversation(conversation.conversation_id, title.trim());
      setConversations((current) => current.map((item) => item.conversation_id === conversation.conversation_id
        ? { ...item, title: updated.title }
        : item));
    } catch (reason) {
      await dialog.alert({ title: "Chưa đổi được tên", message: reason instanceof ApiClientError ? reason.message : "Không thể đổi tên cuộc hội thoại." });
    }
  }

  async function deleteConversation(conversation: ConversationDetail) {
    setConversationMenu(null);
    if (!await dialog.confirm({
      title: "Xóa hội thoại khỏi lịch sử?",
      message: `Hội thoại “${conversation.title || "Hội thoại mới"}” sẽ không còn xuất hiện trong danh sách của bạn.`,
      confirmLabel: "Xóa hội thoại",
      cancelLabel: "Giữ lại",
      tone: "danger",
    })) return;
    try {
      await api.deleteConversation(conversation.conversation_id);
      setConversations((current) => current.filter((item) => item.conversation_id !== conversation.conversation_id));
      if (selectedConversationId === conversation.conversation_id) requestNewConversation();
    } catch (reason) {
      await dialog.alert({ title: "Chưa xóa được hội thoại", message: reason instanceof ApiClientError ? reason.message : "Không thể xóa cuộc hội thoại." });
    }
  }

  function loadMoreHistory(event: React.UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    if (element.scrollHeight - element.scrollTop - element.clientHeight > 36) return;
    setVisibleHistoryCount((current) => Math.min(current + HISTORY_PAGE_SIZE, conversations.length));
  }

  function toggleConversationMenu(event: React.MouseEvent<HTMLButtonElement>, conversationId: string) {
    if (conversationMenu?.conversationId === conversationId) {
      setConversationMenu(null);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const menuWidth = 126;
    const menuHeight = 82;
    const top = rect.bottom + menuHeight + 6 <= window.innerHeight
      ? rect.bottom + 4
      : Math.max(8, rect.top - menuHeight - 4);
    setConversationMenu({
      conversationId,
      top,
      left: Math.max(8, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8)),
    });
  }

  if (checkingSession) {
    return <div className="app-loading"><RefreshCw className="spin" size={20} /> Đang khôi phục phiên làm việc...</div>;
  }

  if (sessionError && hasSession()) {
    return (
      <div className="session-recovery">
        <CircleAlert size={30} />
        <h2>Chưa thể kết nối hệ thống</h2>
        <p>{sessionError}</p>
        <button className="primary-command" onClick={() => void restoreSession()}><RefreshCw size={17} /> Thử lại</button>
      </div>
    );
  }

  if (!user) return <LoginView onAuthenticated={setUser} />;

  const isAdmin = ["HR_ADMIN", "SUPER_ADMIN"].includes(user.role);
  const items = isAdmin
    ? [employeeItems[0], { ...employeeItems[1], label: "Quản lý Ticket" }, ...adminItems]
    : employeeItems;
  const currentItem = items.find((item) => item.id === view);
  const initials = user.full_name.split(" ").filter(Boolean).map((part) => part[0]).slice(-2).join("");
  const visibleConversations = conversations.slice(0, visibleHistoryCount);
  const menuConversation = conversationMenu
    ? conversations.find((conversation) => conversation.conversation_id === conversationMenu.conversationId) ?? null
    : null;

  return (
    <main className="next-app-shell">
      <aside className={`next-sidebar ${mobileMenu ? "open" : ""}`}>
        <header className="sidebar-brand">
          <div className="brand-mark"><BookOpenCheck size={19} /></div>
          <div><strong>HR Intelligence</strong><span>Document Intelligence</span></div>
          <button className="mobile-close" onClick={() => setMobileMenu(false)} aria-label="Đóng menu"><X size={18} /></button>
        </header>

        <div className="sidebar-content">
          <button className="new-conversation" onClick={requestNewConversation}>
            <Plus size={17} />
            <span>Cuộc hội thoại mới</span>
          </button>

          <nav aria-label="Điều hướng chính">
            <p className="nav-label">Không gian làm việc</p>
            {items.slice(0, 2).map((item) => {
              const Icon = item.icon;
              return <button className={view === item.id ? "active" : ""} key={item.id} onClick={() => { setView(item.id); setMobileMenu(false); }}><Icon size={18} /><span>{item.label}</span></button>;
            })}
            {isAdmin && <p className="nav-label admin-nav-label">Quản trị tri thức</p>}
            {isAdmin && items.slice(2).map((item) => {
              const Icon = item.icon;
              return <button className={view === item.id ? "active" : ""} key={item.id} onClick={() => { setView(item.id); setMobileMenu(false); }}><Icon size={18} /><span>{item.label}</span></button>;
            })}
          </nav>

          <section className="sidebar-history" aria-label="Lịch sử hội thoại">
            <header className="sidebar-history-heading">
              <div><History size={15} /><span>Lịch sử hội thoại</span></div>
              <button className="sidebar-history-refresh" aria-label="Tải lại lịch sử hội thoại" title="Tải lại" onClick={() => void refreshConversations()}><RefreshCw size={14} /></button>
            </header>
            <div className="sidebar-history-list" onScroll={loadMoreHistory}>
              {conversationGroups.map((group) => {
                const groupItems = visibleConversations.filter((conversation) => conversationGroup(conversation) === group);
                if (!groupItems.length) return null;
                return (
                  <div className="sidebar-history-group" key={group}>
                    <p>{group}</p>
                    {groupItems.map((conversation) => (
                      <div className={`sidebar-history-item ${selectedConversationId === conversation.conversation_id ? "active" : ""}`} key={conversation.conversation_id}>
                        <button className="sidebar-history-main" onClick={() => selectConversation(conversation.conversation_id)} disabled={view === "chat" && selectedConversationId === conversation.conversation_id}>
                          <span>{conversation.title || "Hội thoại mới"}</span>
                          <small>{conversationMeta(conversation)}</small>
                        </button>
                        <div className="sidebar-history-menu-wrap">
                          <button className="sidebar-history-menu-button" aria-label={`Mở tùy chọn cho ${conversation.title}`} aria-haspopup="menu" aria-expanded={conversationMenu?.conversationId === conversation.conversation_id} onClick={(event) => toggleConversationMenu(event, conversation.conversation_id)}><MoreHorizontal size={15} /></button>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
              {!conversations.length && <p className="sidebar-history-empty">Chưa có hội thoại nào</p>}
            </div>
          </section>
        </div>

        <footer>
          <div className="profile-avatar">{initials}</div>
          <div><strong>{user.full_name}</strong><span>{roleLabel(user.role)} · {user.department}</span></div>
          <button className="icon-command sidebar-logout" title="Đăng xuất" aria-label="Đăng xuất" onClick={logout}><LogOut size={17} /></button>
        </footer>
      </aside>

      {mobileMenu && <button className="sidebar-overlay" onClick={() => setMobileMenu(false)} aria-label="Đóng menu" />}

      <section className="next-main">
        <header className="top-bar">
          <button className="menu-command" aria-label="Mở menu" onClick={() => setMobileMenu(true)}><Menu size={20} /></button>
          <div className="top-bar-title"><strong>{currentItem?.label}</strong><span>{view === "chat" ? "Tra cứu chính sách từ nguồn đã kiểm chứng" : "HR Document Intelligence Platform"}</span></div>
        </header>
        <div className="view-body">
          {view === "chat" && <ChatView
            newConversationSignal={newConversationSignal}
            selectedConversationId={selectedConversationId}
            conversations={conversations}
            onConversationsChange={handleConversationsChange}
            onConversationSelected={handleConversationSelected}
          />}
          {view === "tickets" && <TicketsView isAdmin={isAdmin} />}
          {view === "documents" && <DocumentsView />}
          {view === "index" && <OperationsView mode="index" />}
          {view === "evaluation" && <OperationsView mode="evaluation" />}
        </div>
      </section>
      {conversationMenu && menuConversation && createPortal(<>
        <button className="conversation-menu-backdrop" aria-label="Đóng tùy chọn hội thoại" onClick={() => setConversationMenu(null)} />
        <div className="sidebar-history-menu conversation-menu-popover" role="menu" style={{ top: conversationMenu.top, left: conversationMenu.left }}>
          <button role="menuitem" onClick={() => void renameConversation(menuConversation)}><Pencil size={13} /> Đổi tên</button>
          <button role="menuitem" className="danger" onClick={() => void deleteConversation(menuConversation)}><Trash2 size={13} /> Xóa</button>
        </div>
      </>, document.body)}
    </main>
  );
}
