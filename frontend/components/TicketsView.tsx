"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, LoaderCircle, PlayCircle, RefreshCw, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { TicketItem } from "@/lib/types";
import { useSystemDialog } from "./SystemDialog";

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusClass(status: string) {
  if (["resolved", "closed"].includes(status.toLowerCase())) return "success";
  if (status.toLowerCase() === "in_progress") return "warning";
  return "neutral";
}

export function TicketsView({ isAdmin = false }: { isAdmin?: boolean }) {
  const { confirm } = useSystemDialog();
  const [tickets, setTickets] = useState<TicketItem[]>([]);
  const [detail, setDetail] = useState<TicketItem | null>(null);
  const [filters, setFilters] = useState({ status: "", priority: "" });
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [resolutionNote, setResolutionNote] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setTickets(await api.listTickets(filters));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải danh sách ticket.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  async function openTicket(item: TicketItem) {
    setDetailLoading(true);
    setError("");
    try {
      const ticket = await api.getTicket(item.id);
      setDetail(ticket);
      setResolutionNote(ticket.resolution_note ?? "");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở ticket.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function updateTicket(update: { status: string; assignee_id?: string; resolution_note?: string }) {
    if (!detail || updating) return;
    setUpdating(true);
    setError("");
    try {
      const updated = await api.updateTicket(detail.id, update);
      setDetail(updated);
      setTickets((current) => current.map((item) => item.id === updated.id ? updated : item));
      setResolutionNote(updated.resolution_note ?? "");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể cập nhật ticket.");
    } finally {
      setUpdating(false);
    }
  }

  async function closeTicket() {
    const accepted = await confirm({
      title: isAdmin ? "Đóng ticket thay người tạo?" : "Xác nhận hoàn tất ticket?",
      message: isAdmin
        ? "Bạn đang đóng ticket thay cho người tạo. Kết quả xử lý và toàn bộ lịch sử vẫn được lưu để tra cứu."
        : "Hãy xác nhận khi kết quả xử lý đã phù hợp. Ticket sẽ chuyển sang Đã đóng và vẫn được lưu trong lịch sử của bạn.",
      confirmLabel: isAdmin ? "Đóng thay" : "Xác nhận & đóng",
      cancelLabel: "Xem lại",
    });
    if (accepted) await updateTicket({ status: "closed" });
  }

  return <div className="content-page">
    <div className="page-heading"><div><p className="eyebrow">HR SUPPORT WORKFLOW</p><h2>{isAdmin ? "Quản lý Ticket" : "Ticket của tôi"}</h2><p>{isAdmin ? "Theo dõi các câu hỏi cần HR tiếp nhận và xử lý." : "Theo dõi các yêu cầu đã được chuyển tới bộ phận HR."}</p></div><span className="page-context">{tickets.length} ticket trong danh sách</span></div>
    <section className="work-panel">
      <div className="ticket-filter-bar">
        <select aria-label="Lọc trạng thái ticket" value={filters.status} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}>
          <option value="">Mọi trạng thái</option><option value="open">OPEN</option><option value="in_progress">IN PROGRESS</option><option value="resolved">RESOLVED</option><option value="closed">CLOSED</option>
        </select>
        <select aria-label="Lọc mức ưu tiên" value={filters.priority} onChange={(event) => setFilters((value) => ({ ...value, priority: event.target.value }))}>
          <option value="">Mọi mức ưu tiên</option><option value="High">HIGH</option><option value="Medium">MEDIUM</option><option value="Low">LOW</option>
        </select>
        <button className="icon-command" aria-label="Tải lại ticket" title="Tải lại" disabled={loading} onClick={() => void load()}><RefreshCw className={loading ? "spin" : ""} size={17} /></button>
      </div>
      {loading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải ticket</div> : <div className="data-table-wrap"><table className="data-table ticket-table"><thead><tr><th>Mã ticket</th><th>Yêu cầu</th><th>Bộ phận</th><th>Ưu tiên</th><th>Trạng thái</th><th>Thời gian</th></tr></thead><tbody>
        {tickets.map((item) => <tr key={item.id} tabIndex={0} onClick={() => void openTicket(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") void openTicket(item); }}>
          <td><strong>{item.ticket_code}</strong></td><td className="ticket-question">{item.employee_question}</td><td>{item.target_department}</td><td>{item.priority}</td><td><span className={`status-pill ${statusClass(item.status)}`}>{item.status}</span></td><td>{formatDate(item.created_at)}</td>
        </tr>)}
        {!tickets.length && <tr><td colSpan={6} className="empty-cell">Chưa có ticket hỗ trợ.</td></tr>}
      </tbody></table></div>}
    </section>
    {error && <div className="stream-error"><CircleAlert size={17} />{error}</div>}
    {detailLoading && <div className="floating-loading"><LoaderCircle className="spin" size={18} /> Đang mở ticket</div>}
    {detail && <div className="modal-layer" onMouseDown={() => setDetail(null)}><section className="detail-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Chi tiết ${detail.ticket_code}`}>
      <header><div><p className="eyebrow">CHI TIẾT TICKET</p><h3>{detail.ticket_code}</h3></div><button className="icon-command" aria-label="Đóng chi tiết ticket" onClick={() => setDetail(null)}><X size={18} /></button></header>
      <div className="ticket-detail-copy"><span className={`status-pill ${statusClass(detail.status)}`}>{detail.status}</span><p>{detail.employee_question}</p></div>
      <dl><div><dt>Bộ phận xử lý</dt><dd>{detail.target_department}</dd></div><div><dt>Mức ưu tiên</dt><dd>{detail.priority}</dd></div><div><dt>Lý do chuyển tiếp</dt><dd>{detail.escalate_reason}</dd></div><div><dt>Người xử lý</dt><dd>{detail.assignee_name ?? "Chưa phân công"}</dd></div><div><dt>Ngày tạo</dt><dd>{formatDate(detail.created_at)}</dd></div>{detail.resolved_at && <div><dt>Ngày xử lý xong</dt><dd>{formatDate(detail.resolved_at)}</dd></div>}{detail.closed_at && <div><dt>Ngày đóng</dt><dd>{formatDate(detail.closed_at)}</dd></div>}</dl>
      {detail.resolution_note && <div className="ticket-resolution"><strong>Kết quả xử lý</strong><p>{detail.resolution_note}</p></div>}
      {isAdmin && !["resolved", "closed"].includes(detail.status.toLowerCase()) && <div className="ticket-admin-actions">
        {detail.status.toLowerCase() === "in_progress" && <label>Ghi chú xử lý<textarea value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} placeholder="Nhập kết quả xử lý trước khi hoàn tất ticket..." /></label>}
        <div className="ticket-admin-action-row">
          {detail.status.toLowerCase() === "open" && <button className="primary-command" disabled={updating} onClick={() => void updateTicket({ status: "in_progress" })}><PlayCircle size={16} /> Duyệt & tiếp nhận ticket</button>}
          {detail.status.toLowerCase() === "in_progress" && <button className="primary-command" disabled={updating || !resolutionNote.trim()} onClick={() => void updateTicket({ status: "resolved", resolution_note: resolutionNote.trim() })}><CheckCircle2 size={16} /> Hoàn tất xử lý</button>}
        </div>
      </div>}
      {detail.status.toLowerCase() === "resolved" && <div className="ticket-close-actions"><div><strong>{isAdmin ? "Đang chờ người tạo xác nhận" : "HR đã hoàn tất xử lý"}</strong><p>{isAdmin ? "Người tạo ticket có thể xác nhận kết quả và đóng ticket." : "Nếu kết quả đã phù hợp, bạn có thể xác nhận và đóng ticket."}</p></div><button className={isAdmin ? "secondary-command" : "primary-command"} disabled={updating} onClick={closeTicket}><CheckCircle2 size={16} /> {isAdmin ? "Đóng thay" : "Xác nhận & đóng ticket"}</button></div>}
      {detail.status.toLowerCase() === "closed" && <div className="ticket-closed-note"><CheckCircle2 size={18} /><div><strong>Ticket đã đóng</strong><p>Ticket và toàn bộ kết quả xử lý vẫn được lưu trong lịch sử để tra cứu.</p></div></div>}
    </section></div>}
  </div>;
}
