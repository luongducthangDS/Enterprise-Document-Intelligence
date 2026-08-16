"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, CircleAlert, LoaderCircle, RefreshCw, Search, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { DocumentDetail, DocumentListItem } from "@/lib/types";

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [filters, setFilters] = useState({ category: "", status: "", indexed: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDocuments(await api.listDocuments(filters));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải tài liệu.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  async function archiveCurrent() {
    if (!detail) return;
    try {
      await api.archiveDocument(detail.document_id);
      setDetail(null);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể lưu trữ tài liệu.");
    }
  }

  return <div className="content-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">KHO TRI THỨC</p><h2>Tài liệu chính sách</h2><p>Quản lý nguồn dữ liệu được Agent sử dụng để trả lời.</p></div></div>
    <div className="document-layout">
      <section className="work-panel">
        <div className="filter-bar">
          <label><Search size={16} /><input placeholder="Lọc theo danh mục" value={filters.category} onChange={(event) => setFilters((value) => ({ ...value, category: event.target.value }))} /></label>
          <select value={filters.status} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}><option value="">Mọi trạng thái</option><option value="ACTIVE">ACTIVE</option><option value="ARCHIVED">ARCHIVED</option></select>
          <select value={filters.indexed} onChange={(event) => setFilters((value) => ({ ...value, indexed: event.target.value }))}><option value="">Mọi index</option><option value="true">Đã index</option><option value="false">Chưa index</option></select>
          <button className="icon-command" onClick={() => void load()} title="Tải lại"><RefreshCw size={17} /></button>
        </div>
        {loading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải tài liệu</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Tài liệu</th><th>Danh mục</th><th>Phiên bản</th><th>Ingestion</th><th>Index</th><th>Trạng thái</th></tr></thead><tbody>
          {documents.map((item) => <tr key={item.document_id} onClick={() => void api.getDocument(item.document_id).then(setDetail).catch((reason) => setError(reason.message))}>
            <td><strong>{item.title}</strong><small>{item.document_id}</small></td><td>{item.category ?? "—"}</td><td>{item.version ?? "—"}</td><td><span className="status-pill neutral">{item.ingestion_state}</span></td><td><span className={`status-pill ${item.indexed ? "success" : "warning"}`}>{item.indexed ? "INDEXED" : "PENDING"}</span></td><td>{item.status}</td>
          </tr>)}
          {!documents.length && <tr><td colSpan={6} className="empty-cell">Không có tài liệu phù hợp.</td></tr>}
        </tbody></table></div>}
      </section>
      <section className="work-panel deferred-panel compact-deferred"><CircleAlert size={25} /><strong>Upload tạm khóa</strong><span>Backend hiện chỉ tạo metadata và job QUEUED; worker trích xuất/chunk/index chưa được triển khai. Chức năng được khóa để tránh tạo job không bao giờ hoàn tất.</span></section>
    </div>
    {error && <div className="stream-error">{error}</div>}
    {detail && <div className="modal-layer" onMouseDown={() => setDetail(null)}><section className="detail-modal" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><p className="eyebrow">CHI TIẾT TÀI LIỆU</p><h3>{detail.title}</h3></div><button className="icon-command" onClick={() => setDetail(null)}><X size={18} /></button></header>
      <dl><div><dt>Tệp nguồn</dt><dd>{detail.source_file}</dd></div><div><dt>Danh mục</dt><dd>{detail.category ?? "—"}</dd></div><div><dt>Ingestion</dt><dd>{detail.ingestion.state} · {detail.ingestion.chunk_count} đoạn</dd></div><div><dt>Index</dt><dd>{detail.index.indexed ? detail.index.index_version : "Chưa index"}</dd></div><div><dt>Checksum</dt><dd><code>{detail.checksum}</code></dd></div></dl>
      <button className="danger-command" disabled={detail.status === "ARCHIVED"} onClick={() => void archiveCurrent()}><Archive size={16} /> Lưu trữ tài liệu</button>
    </section></div>}
  </div>;
}

export function OperationsView({ mode }: { mode: "index" | "evaluation" }) {
  return <div className="content-page narrow-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">RAG OPERATIONS</p><h2>{mode === "index" ? "Xây dựng lại Vector Index" : "Đánh giá chất lượng Agent"}</h2><p>Contract API đã có nhưng Backend chưa có worker thực thi.</p></div></div>
    <section className="work-panel deferred-panel"><CircleAlert size={28} /><strong>Chức năng tạm khóa</strong><span>{mode === "index" ? "Re-index hiện chỉ tạo job QUEUED và chưa xử lý Vector Store." : "Evaluation hiện chỉ tạo run QUEUED và chưa chạy dataset thật."}</span></section>
  </div>;
}
