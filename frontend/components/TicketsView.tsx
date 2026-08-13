"use client";

import { useCallback, useEffect, useState } from "react";
import { CircleAlert, LoaderCircle, RefreshCw, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { TicketItem } from "@/lib/types";

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
  const [tickets, setTickets] = useState<TicketItem[]>([]);
  const [detail, setDetail] = useState<TicketItem | null>(null);
  const [filters, setFilters] = useState({ status: "", priority: "" });
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
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
      setDetail(await api.getTicket(item.id));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể mở ticket.");
    } finally {
      setDetailLoading(false);
    }
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
      <dl><div><dt>Bộ phận xử lý</dt><dd>{detail.target_department}</dd></div><div><dt>Mức ưu tiên</dt><dd>{detail.priority}</dd></div><div><dt>Lý do chuyển tiếp</dt><dd>{detail.escalate_reason}</dd></div><div><dt>Người xử lý</dt><dd>{detail.assignee_name ?? "Chưa phân công"}</dd></div><div><dt>Ngày tạo</dt><dd>{formatDate(detail.created_at)}</dd></div></dl>
      {detail.resolution_note && <div className="ticket-resolution"><strong>Kết quả xử lý</strong><p>{detail.resolution_note}</p></div>}
    </section></div>}
  </div>;
}
