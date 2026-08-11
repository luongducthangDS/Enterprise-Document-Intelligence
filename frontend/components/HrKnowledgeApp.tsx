"use client";

import { useEffect, useState } from "react";
import { Activity, BookOpen, Database, FileText, FlaskConical, LogOut, Menu, MessageSquare, Search, Ticket, X } from "lucide-react";
import { api, clearSession, hasSession } from "@/lib/api";
import type { User } from "@/lib/types";
import { ChatView } from "./ChatView";
import { DocumentsView, OperationsView } from "./KnowledgeAdmin";
import { LoginView } from "./LoginView";

type View = "chat" | "tickets" | "documents" | "index" | "evaluation" | "monitoring";

const employeeItems = [{ id: "chat" as const, label: "Trợ lý AI HR", icon: MessageSquare }, { id: "tickets" as const, label: "Ticket của tôi", icon: Ticket }];
const adminItems = [{ id: "documents" as const, label: "Kho tài liệu", icon: FileText }, { id: "index" as const, label: "Index & RAG", icon: Database }, { id: "evaluation" as const, label: "Đánh giá chất lượng", icon: FlaskConical }, { id: "monitoring" as const, label: "Giám sát truy vấn", icon: Activity }];

export function HrKnowledgeApp() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("chat");
  const [mobileMenu, setMobileMenu] = useState(false);

  useEffect(() => {
    if (!hasSession()) { setCheckingSession(false); return; }
    api.me().then(setUser).catch(() => clearSession()).finally(() => setCheckingSession(false));
  }, []);

  function logout() {
    clearSession();
    setUser(null);
    setView("chat");
  }

  if (checkingSession) return <div className="app-loading">Đang khôi phục phiên...</div>;
  if (!user) return <LoginView onAuthenticated={setUser} />;
  const isAdmin = ["HR_ADMIN", "SUPER_ADMIN"].includes(user.role);
  const items = isAdmin ? [...employeeItems, ...adminItems] : employeeItems;

  return <main className="next-app-shell">
    <aside className={`next-sidebar ${mobileMenu ? "open" : ""}`}>
      <header><div className="brand-mark"><BookOpen size={19} /></div><strong>HR Knowledge</strong><button className="mobile-close" onClick={() => setMobileMenu(false)}><X size={18} /></button></header>
      <nav>{items.map((item) => { const Icon = item.icon; return <button className={view === item.id ? "active" : ""} key={item.id} onClick={() => { setView(item.id); setMobileMenu(false); }}><Icon size={18} /><span>{item.label}</span></button>; })}</nav>
      <footer><div className="profile-avatar">{user.full_name.split(" ").map((part) => part[0]).slice(-2).join("")}</div><div><strong>{user.full_name}</strong><span>{user.role} · {user.department}</span></div><button className="icon-command sidebar-logout" title="Đăng xuất" onClick={logout}><LogOut size={17} /></button></footer>
    </aside>
    {mobileMenu && <button className="sidebar-overlay" onClick={() => setMobileMenu(false)} aria-label="Đóng menu" />}
    <section className="next-main">
      <header className="top-bar"><button className="menu-command" onClick={() => setMobileMenu(true)}><Menu size={20} /></button><div><strong>{items.find((item) => item.id === view)?.label}</strong><span>Kết nối Backend · Agent service riêng</span></div><label className="global-search"><Search size={16} /><input placeholder="Tìm kiếm trong màn hình hiện tại" /></label></header>
      <div className="view-body">
        {view === "chat" && <ChatView />}
        {view === "tickets" && <DeferredView title="Ticket hỗ trợ" detail="Agent và Backend đã tạo ticket thật khi escalation. Public Ticket API cần được chốt trước khi nối màn hình này." />}
        {view === "documents" && <DocumentsView />}
        {view === "index" && <OperationsView mode="index" />}
        {view === "evaluation" && <OperationsView mode="evaluation" />}
        {view === "monitoring" && <DeferredView title="Giám sát truy vấn" detail="Monitoring được giữ lại cho phase sau theo quyết định hiện tại." />}
      </div>
    </section>
  </main>;
}

function DeferredView({ title, detail }: { title: string; detail: string }) {
  return <div className="content-page narrow-page"><div className="page-heading"><div><p className="eyebrow">CHƯA NỐI API</p><h2>{title}</h2><p>{detail}</p></div></div><section className="work-panel deferred-panel"><Activity size={28} /><strong>Giao diện đã sẵn sàng cho contract chính thức</strong><span>Không dùng dữ liệu mock để tránh nhầm với dữ liệu vận hành.</span></section></div>;
}
