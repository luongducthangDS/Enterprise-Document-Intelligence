"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, CircleAlert, Clock3, LoaderCircle, Plus, RefreshCw, Ticket, UserCheck, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import { DEPARTMENTS, escalateReasonLabel, priorityLabel } from "@/lib/labels";
import type { TicketItem, User } from "@/lib/types";
import { useSystemDialog } from "@/components/SystemDialog";

const STATUS_ORDER = ["open", "in_progress", "resolved", "closed"];
const STATUS_LABELS: Record<string, string> = {
  open: "Mới tiếp nhận",
  in_progress: "Đang xử lý",
  resolved: "Đã giải quyết",
  closed: "Đã đóng",
};

export function TicketsView({ user }: { user: User }) {
  const dialog = useSystemDialog();
  const [tickets, setTickets] = useState<TicketItem[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);
  const [selected, setSelected] = useState<TicketItem | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const isAdmin = ["DEPARTMENT_MANAGER", "SUPER_ADMIN"].includes(user.role.toUpperCase());

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setTickets(await api.listTickets({ status: statusFilter || undefined, priority: priorityFilter || undefined }));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải ticket.");
    } finally {
      setLoading(false);
    }
  }, [priorityFilter, statusFilter]);

  useEffect(() => { void load(); }, [load]);

  async function openTicket(ticketId: string) {
    setDetailLoading(true);
    setError("");
    try {
      setSelected(await api.getTicket(ticketId));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở ticket.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function createTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.createTicket({
        user_query: String(form.get("question") ?? ""),
        target_department: String(form.get("department") || "HR"),
        priority: String(form.get("priority") ?? "Medium"),
        category: String(form.get("category") ?? "GENERAL"),
      });
      setShowCreate(false);
      setSelected(created);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tạo ticket.");
    } finally {
      setSaving(false);
    }
  }

  async function applyUpdate(payload: { status?: string; priority?: string; resolution_note?: string }) {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateTicket(selected.id, payload);
      setSelected(updated);
      setTickets((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể cập nhật ticket.");
    } finally {
      setSaving(false);
    }
  }

  async function acceptTicket() {
    if (!selected) return;
    await applyUpdate({ status: "in_progress", priority: selected.priority });
  }

  async function resolveTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    await applyUpdate({
      status: "resolved",
      priority: String(form.get("priority") ?? selected.priority),
      resolution_note: String(form.get("resolution_note") ?? "").trim(),
    });
  }

  async function closeTicket() {
    if (!selected) return;
    const confirmed = await dialog.confirm({
      title: "Xác nhận đóng ticket",
      message: isAdmin
        ? "Ticket sẽ chuyển sang trạng thái đã đóng. Kết quả xử lý vẫn được lưu để đối soát."
        : "Bạn xác nhận yêu cầu này đã được giải quyết thỏa đáng?",
      confirmLabel: "Đóng ticket",
      cancelLabel: "Xem lại",
    });
    if (confirmed) await applyUpdate({ status: "closed" });
  }

  return <div className="content-page tickets-glass-page animate__animated animate__fadeInUp motion-view">
    <div className="ticket-glass-blob" aria-hidden="true" />
    <div className="page-heading ticket-heading"><div><p className="eyebrow">YÊU CẦU HỖ TRỢ</p><h2>{isAdmin ? "Hàng đợi ticket" : "Ticket của tôi"}</h2><p>{isAdmin ? "Tiếp nhận, xử lý và bàn giao kết quả rõ ràng." : "Theo dõi yêu cầu từ lúc tiếp nhận đến khi bạn xác nhận đóng."}</p></div><button className="primary-command" onClick={() => setShowCreate(true)}><Plus size={17} /> Tạo ticket</button></div>
    <section className="work-panel">
      <div className="filter-bar ticket-filter-bar"><select aria-label="Lọc trạng thái" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">Mọi trạng thái</option>{STATUS_ORDER.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}</select><select aria-label="Lọc ưu tiên" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="">Mọi ưu tiên</option><option value="High">{priorityLabel("High")}</option><option value="Medium">{priorityLabel("Medium")}</option><option value="Low">{priorityLabel("Low")}</option></select><button className="icon-command" title="Tải lại" onClick={() => void load()}><RefreshCw size={17} /></button></div>
      {loading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải ticket</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Mã</th><th>Yêu cầu</th><th>Phòng ban</th><th>Ưu tiên</th><th>Trạng thái</th><th>Cập nhật</th></tr></thead><tbody>
        {tickets.map((item) => <tr key={item.id} onClick={() => void openTicket(item.id)}><td><strong>{item.ticket_code}</strong></td><td className="ticket-question">{item.employee_question}</td><td>{item.target_department}</td><td><span className={`priority-mark priority-${item.priority.toLowerCase()}`}>{priorityLabel(item.priority)}</span></td><td><span className={`status-pill ${ticketStatusTone(item.status)}`}>{STATUS_LABELS[item.status] ?? item.status}</span></td><td>{new Date(item.updated_at).toLocaleString("vi-VN")}</td></tr>)}
        {!tickets.length && <tr><td className="empty-cell" colSpan={6}>{isAdmin ? "Chưa có yêu cầu hỗ trợ nào trong hàng đợi." : "Bạn chưa có yêu cầu hỗ trợ nào."}</td></tr>}
      </tbody></table></div>}
    </section>
    {error && <div className="stream-error"><CircleAlert size={17} /><span>{error}</span></div>}
    {detailLoading && <div className="ticket-detail-loading"><LoaderCircle className="spin" size={18} /> Đang mở ticket...</div>}

    {mounted && showCreate && createPortal(
      <div className="modal-layer animate__animated animate__fadeIn motion-fast" onMouseDown={() => setShowCreate(false)}>
        <form className="detail-modal ticket-form animate__animated animate__zoomIn motion-fast" onSubmit={createTicket} onMouseDown={(event) => event.stopPropagation()}>
          <header><div><p className="eyebrow">TICKET MỚI</p><h3>Gửi yêu cầu hỗ trợ</h3></div><button type="button" className="icon-command" aria-label="Đóng" onClick={() => setShowCreate(false)}><X size={18} /></button></header>
          <label>Nội dung<textarea name="question" minLength={5} maxLength={2000} required /></label>
          <label>Danh mục<input name="category" defaultValue="GENERAL" /></label>
          <div className="two-fields">
            <label>Phòng tiếp nhận<select name="department" defaultValue="HR">{DEPARTMENTS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>Ưu tiên<select name="priority"><option value="Medium">{priorityLabel("Medium")}</option><option value="Low">{priorityLabel("Low")}</option><option value="High">{priorityLabel("High")}</option></select></label>
          </div>
          <button className="primary-command" disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} /> : <Ticket size={17} />} Tạo ticket</button>
        </form>
      </div>,
      document.body
    )}

    {mounted && selected && !showCreate && createPortal(
      <div className="modal-layer animate__animated animate__fadeIn motion-fast" onMouseDown={() => setSelected(null)}>
        <section className="detail-modal ticket-detail animate__animated animate__zoomIn motion-fast" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><p className="eyebrow">{selected.ticket_code}</p><h3>{selected.employee_question}</h3></div><button className="icon-command" aria-label="Đóng" onClick={() => setSelected(null)}><X size={18} /></button></header>
          <TicketProgress status={selected.status} />
          <dl><div><dt>Phòng tiếp nhận</dt><dd>{selected.target_department}</dd></div><div><dt>Ưu tiên</dt><dd>{priorityLabel(selected.priority)}</dd></div><div><dt>Lý do chuyển tiếp</dt><dd>{escalateReasonLabel(selected.escalate_reason)}</dd></div><div><dt>Người xử lý</dt><dd>{selected.assignee_name ?? "Chưa phân công"}</dd></div>{selected.resolved_at && <div><dt>Giải quyết lúc</dt><dd>{new Date(selected.resolved_at).toLocaleString("vi-VN")}</dd></div>}{selected.closed_at && <div><dt>Đóng lúc</dt><dd>{new Date(selected.closed_at).toLocaleString("vi-VN")}</dd></div>}</dl>
          {selected.resolution_note && <div className="ticket-resolution"><CheckCircle2 size={18} /><div><strong>Kết quả xử lý</strong><p>{selected.resolution_note}</p></div></div>}
          {isAdmin && selected.status === "open" && <div className="ticket-next-action"><UserCheck size={19} /><div><strong>Bước tiếp theo</strong><p>Tiếp nhận ticket để ghi nhận người đang xử lý.</p></div><button className="primary-command" disabled={saving} onClick={() => void acceptTicket()}>{saving ? <LoaderCircle className="spin" size={16} /> : null} Tiếp nhận</button></div>}
          {isAdmin && selected.status === "in_progress" && <form className="ticket-form ticket-resolution-form" onSubmit={resolveTicket}><label>Kết quả xử lý<textarea name="resolution_note" minLength={3} required placeholder="Nêu rõ kết quả, hướng dẫn hoặc quyết định đã thống nhất..." /></label><label>Ưu tiên<select name="priority" defaultValue={selected.priority}><option value="Low">{priorityLabel("Low")}</option><option value="Medium">{priorityLabel("Medium")}</option><option value="High">{priorityLabel("High")}</option></select></label><button className="primary-command" disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />} Hoàn tất xử lý</button></form>}
          {selected.status === "resolved" && <div className="ticket-next-action"><CheckCircle2 size={19} /><div><strong>{isAdmin ? "Chờ xác nhận" : "Kết quả đã được gửi"}</strong><p>{isAdmin ? "Người yêu cầu có thể xác nhận và đóng ticket." : "Kiểm tra kết quả phía trên rồi xác nhận đóng ticket."}</p></div><button className="primary-command" disabled={saving} onClick={() => void closeTicket()}>Đóng ticket</button></div>}
          {selected.status === "closed" && <div className="ticket-closed-note"><CheckCircle2 size={18} /> Luồng hỗ trợ đã hoàn tất.</div>}
        </section>
      </div>,
      document.body
    )}
  </div>;
}

function TicketProgress({ status }: { status: string }) {
  const activeIndex = Math.max(0, STATUS_ORDER.indexOf(status));
  return <ol className="ticket-progress" aria-label="Tiến trình ticket">{STATUS_ORDER.map((step, index) => <li key={step} className={index <= activeIndex ? "complete" : ""} aria-current={step === status ? "step" : undefined}><span>{index < activeIndex ? <CheckCircle2 size={15} /> : index === activeIndex ? <Clock3 size={15} /> : index + 1}</span><small>{STATUS_LABELS[step]}</small></li>)}</ol>;
}

function ticketStatusTone(status: string) {
  if (["resolved", "closed"].includes(status)) return "success";
  if (status === "open") return "warning";
  return "neutral";
}
