"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, BookOpen, Database, FileText, FlaskConical, MessageSquare, Ticket } from "lucide-react";
import { api, clearSession, hasSession } from "@/lib/api";
import type { User } from "@/lib/types";
import { ChatView } from "./ChatView";
import { DocumentsView, OperationsView } from "./KnowledgeAdmin";
import { LoginView } from "./LoginView";
import { TicketsView } from "./TicketsView";

type View = "chat" | "tickets" | "documents" | "index" | "evaluation" | "monitoring";

const employeeItems = [{ id: "chat" as const, label: "Trợ lý AI HR", icon: MessageSquare }, { id: "tickets" as const, label: "Ticket của tôi", icon: Ticket }];
const adminItems = [{ id: "documents" as const, label: "Kho tài liệu", icon: FileText }, { id: "index" as const, label: "Index & RAG", icon: Database }, { id: "evaluation" as const, label: "Đánh giá chất lượng", icon: FlaskConical }, { id: "monitoring" as const, label: "Giám sát truy vấn", icon: Activity }];

export function HrKnowledgeApp() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("chat");
  const navigationRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const handleSessionCleared = () => setUser(null);
    window.addEventListener("hr-session-cleared", handleSessionCleared);
    if (!hasSession()) setCheckingSession(false);
    else api.me().then(setUser).catch(() => clearSession()).finally(() => setCheckingSession(false));
    return () => window.removeEventListener("hr-session-cleared", handleSessionCleared);
  }, []);

  useEffect(() => {
    const navigation = navigationRef.current;
    if (!navigation) return;
    const syncSlider = () => {
      const active = navigation.querySelector<HTMLButtonElement>("button.active");
      if (!active) return;
      navigation.style.setProperty("--navbar-active-x", `${active.offsetLeft}px`);
      navigation.style.setProperty("--navbar-active-width", `${active.offsetWidth}px`);
      navigation.style.setProperty("--navbar-active-center", `${active.offsetLeft + active.offsetWidth / 2}px`);
      navigation.style.setProperty("--navbar-active-opacity", "1");
    };
    syncSlider();
    const frame = window.requestAnimationFrame(syncSlider);
    const observer = new ResizeObserver(syncSlider);
    observer.observe(navigation);
    window.addEventListener("resize", syncSlider);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", syncSlider);
    };
  }, [user, view]);

  function logout() {
    clearSession();
    setUser(null);
    setView("chat");
  }

  if (checkingSession) return <div className="app-loading">Đang khôi phục phiên...</div>;
  if (!user) return <LoginView onAuthenticated={setUser} />;
  const isAdmin = ["HR_ADMIN", "SUPER_ADMIN"].includes(user.role);
  const items = isAdmin ? [...employeeItems, ...adminItems] : employeeItems;

  return <main className="next-app-shell" data-ui="cusion-shell">
    <section className="next-main">
      <header className="top-bar">
        <div className="top-brand"><span className="brand-mark"><BookOpen size={18} /></span><span><strong>HR Knowledge</strong><small>Kết nối Backend · Agent service riêng</small></span></div>
        <nav ref={navigationRef} className="top-navigation" aria-label="Điều hướng chính">{items.map((item) => { const Icon = item.icon; return <button className={view === item.id ? "active" : ""} aria-current={view === item.id ? "page" : undefined} aria-label={item.label} title={item.label} key={item.id} onClick={() => setView(item.id)} onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); event.currentTarget.style.setProperty("--navbar-tilt-y", `${((event.clientX - rect.left) / rect.width - .5) * 8}deg`); event.currentTarget.style.setProperty("--navbar-tilt-x", `${((event.clientY - rect.top) / rect.height - .5) * -7}deg`); }} onPointerLeave={(event) => { event.currentTarget.style.removeProperty("--navbar-tilt-x"); event.currentTarget.style.removeProperty("--navbar-tilt-y"); }}><Icon size={17} /><span>{item.label}</span></button>; })}</nav>
      </header>
      <div className="view-body">
        <ChatView user={user} onLogout={logout} hidden={view !== "chat"} />
        {view === "tickets" && <TicketsView user={user} />}
        {view === "documents" && <DocumentsView />}
        {view === "index" && <OperationsView mode="index" />}
        {view === "evaluation" && <OperationsView mode="evaluation" />}
        {view === "monitoring" && <DeferredView title="Giám sát truy vấn" detail="Monitoring được giữ lại cho phase sau theo quyết định hiện tại." />}
      </div>
    </section>
  </main>;
}

function DeferredView({ title, detail }: { title: string; detail: string }) {
  return <div className="content-page narrow-page animate__animated animate__fadeInUp motion-view"><div className="page-heading"><div><p className="eyebrow">CHƯA NỐI API</p><h2>{title}</h2><p>{detail}</p></div></div><section className="work-panel deferred-panel"><Activity size={28} /><strong>Giao diện đã sẵn sàng cho contract chính thức</strong><span>Không dùng dữ liệu mock để tránh nhầm với dữ liệu vận hành.</span></section></div>;
}
