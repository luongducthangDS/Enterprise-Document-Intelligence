"use client";

import { useEffect, useState } from "react";
import {
  BookOpenCheck,
  CircleAlert,
  Database,
  FileText,
  FlaskConical,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  RefreshCw,
  ShieldCheck,
  Ticket,
  X,
} from "lucide-react";
import { api, ApiClientError, clearSession, hasSession } from "@/lib/api";
import type { User } from "@/lib/types";
import { ChatView, clearChatRecovery } from "./ChatView";
import { DocumentsView, OperationsView } from "./KnowledgeAdmin";
import { LoginView } from "./LoginView";
import { TicketsView } from "./TicketsView";

type View = "chat" | "tickets" | "documents" | "index" | "evaluation";

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

export function HrKnowledgeApp() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [view, setView] = useState<View>("chat");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [newConversationSignal, setNewConversationSignal] = useState(0);

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

  function logout() {
    clearSession();
    clearChatRecovery();
    setUser(null);
    setView("chat");
  }

  function requestNewConversation() {
    setView("chat");
    setMobileMenu(false);
    setNewConversationSignal((value) => value + 1);
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
          <div className="system-trust"><ShieldCheck size={15} /><span>Knowledge Base được bảo vệ</span></div>
        </header>
        <div className="view-body">
          {view === "chat" && <ChatView newConversationSignal={newConversationSignal} />}
          {view === "tickets" && <TicketsView isAdmin={isAdmin} />}
          {view === "documents" && <DocumentsView />}
          {view === "index" && <OperationsView mode="index" />}
          {view === "evaluation" && <OperationsView mode="evaluation" />}
        </div>
      </section>
    </main>
  );
}
