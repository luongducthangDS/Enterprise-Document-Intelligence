"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Archive, CircleAlert, FileUp, LoaderCircle, RefreshCw, Search, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { DocumentDetail, DocumentListItem } from "@/lib/types";

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [filters, setFilters] = useState({ category: "", status: "", indexed: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadJob, setUploadJob] = useState<{ state: string; stage?: string; progress_percent: number } | null>(null);
  const [uploadForm, setUploadForm] = useState({ title: "", category: "GENERAL", department: "HR", version: "", effective_date: "" });
  const pollGeneration = useRef(0);

  useEffect(() => () => { pollGeneration.current += 1; }, []);


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

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadFile || uploading) return;
    const generation = ++pollGeneration.current;
    setUploading(true);
    setUploadJob({ state: "QUEUED", stage: "UPLOADING", progress_percent: 0 });
    setError("");
    try {
      const created = await api.uploadDocument(uploadFile, {
        ...uploadForm,
        access_scope: "DEPARTMENT",
        confidentiality: "INTERNAL",
        status: "ACTIVE",
      });
      for (let attempt = 0; attempt < 300 && generation === pollGeneration.current; attempt += 1) {
        const current = await api.getIngestionJob(created.ingestion_job_id);
        setUploadJob(current);
        if (["COMPLETED", "FAILED", "CANCELLED"].includes(current.state)) {
          if (current.state === "COMPLETED") {
            setUploadFile(null);
            setUploadForm((value) => ({ ...value, title: "", version: "", effective_date: "" }));
            await load();
          } else {
            const detail = current.error ? ` ${JSON.stringify(current.error)}` : "";
            setError(`Ingestion ${current.state.toLowerCase()}.${detail}`);
          }
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, current.poll_after_ms ?? 1000));
      }
      if (generation === pollGeneration.current) setError("Ingestion chưa hoàn tất trong thời gian chờ. Có thể tải lại trang để xem trạng thái.");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải tài liệu lên.");
    } finally {
      if (generation === pollGeneration.current) setUploading(false);
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
      <form className="work-panel upload-panel" onSubmit={upload}>
        <div className="panel-title"><FileUp size={22} /><div><strong>Upload tài liệu</strong><span>Chỉ index trong phòng ban đã chọn.</span></div></div>
        <label>Tệp<input type="file" accept=".pdf,.docx,.xlsx,.md,.txt" disabled={uploading} onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} /></label>
        <label>Tiêu đề<input value={uploadForm.title} disabled={uploading} placeholder={uploadFile?.name ?? "Tên tài liệu"} onChange={(event) => setUploadForm((value) => ({ ...value, title: event.target.value }))} /></label>
        <div className="two-fields">
          <label>Phòng ban<select value={uploadForm.department} disabled={uploading} onChange={(event) => setUploadForm((value) => ({ ...value, department: event.target.value }))}><option value="HR">HR</option><option value="ACCOUNTING">Accounting</option><option value="PRODUCT">Product</option></select></label>
          <label>Danh mục<input value={uploadForm.category} disabled={uploading} onChange={(event) => setUploadForm((value) => ({ ...value, category: event.target.value }))} /></label>
        </div>
        <div className="two-fields">
          <label>Phiên bản<input value={uploadForm.version} disabled={uploading} placeholder="v1.0" onChange={(event) => setUploadForm((value) => ({ ...value, version: event.target.value }))} /></label>
          <label>Ngày hiệu lực<input type="date" value={uploadForm.effective_date} disabled={uploading} onChange={(event) => setUploadForm((value) => ({ ...value, effective_date: event.target.value }))} /></label>
        </div>
        {uploadJob && <div><div className="job-summary"><span>{uploadJob.stage ?? uploadJob.state}</span><strong>{uploadJob.progress_percent}%</strong></div><div className="progress-track"><div style={{ width: `${uploadJob.progress_percent}%` }} /></div></div>}
        <button className="primary-command" type="submit" disabled={!uploadFile || uploading}>{uploading ? <><LoaderCircle className="spin" size={16} /> Đang xử lý</> : <><FileUp size={16} /> Upload và index</>}</button>
      </form>
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
  if (mode === "index") return <IndexOperationsView />;
  return <div className="content-page narrow-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">RAG OPERATIONS</p><h2>Đánh giá chất lượng Agent</h2><p>Evaluation API sẵn sàng; cần chọn bộ dữ liệu và model config đã được phê duyệt.</p></div></div>
    <section className="work-panel deferred-panel"><CircleAlert size={28} /><strong>Chưa có cấu hình pilot</strong><span>Thiết lập dataset ID, index version và model config trước khi chạy evaluation từ giao diện.</span></section>
  </div>;
}

function IndexOperationsView() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [job, setJob] = useState<{ state: string; stage?: string; progress_percent: number; active_index_version?: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.listDocuments({ status: "ACTIVE" })
      .then(setDocuments)
      .catch((reason) => setError(reason instanceof ApiClientError ? reason.message : "Không thể tải tài liệu."));
  }, []);

  function toggle(documentId: string) {
    setSelected((value) => value.includes(documentId) ? value.filter((id) => id !== documentId) : [...value, documentId]);
  }

  async function rebuild() {
    if (!selected.length || busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.startIndexRebuild(selected, "REPLACE");
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const current = await api.getIndexRebuild(created.job_id);
        setJob(current);
        if (["COMPLETED", "FAILED", "CANCELLED"].includes(current.state)) {
          if (current.state !== "COMPLETED") {
            const detail = current.error ? ` ${JSON.stringify(current.error)}` : "";
            setError(`Re-index ${current.state.toLowerCase()}.${detail}`);
          }
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, current.poll_after_ms ?? 1000));
      }
      setError("Re-index chưa hoàn tất trong thời gian chờ. Có thể tải lại trang để kiểm tra.");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể bắt đầu re-index.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="content-page narrow-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">RAG OPERATIONS</p><h2>Xây dựng lại Vector Index</h2><p>Chọn tài liệu và theo dõi worker đến khi index mới hoạt động.</p></div></div>
    <section className="work-panel">
      <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Chọn</th><th>Tài liệu</th><th>Ingestion</th><th>Index</th></tr></thead><tbody>
        {documents.map((item) => <tr key={item.document_id} onClick={() => toggle(item.document_id)}><td><input type="checkbox" checked={selected.includes(item.document_id)} readOnly aria-label={`Chọn ${item.title}`} /></td><td><strong>{item.title}</strong><small>{item.document_id}</small></td><td>{item.ingestion_state}</td><td>{item.indexed ? "INDEXED" : "PENDING"}</td></tr>)}
        {!documents.length && <tr><td className="empty-cell" colSpan={4}>Không có tài liệu ACTIVE.</td></tr>}
      </tbody></table></div>
      <div className="upload-panel">
        {job && <div><div className="job-summary"><span>{job.stage ?? job.state}</span><strong>{job.progress_percent}%</strong></div><div className="progress-track"><div style={{ width: `${job.progress_percent}%` }} /></div>{job.active_index_version && <small>Index đang hoạt động: {job.active_index_version}</small>}</div>}
        <button className="primary-command" disabled={!selected.length || busy} onClick={() => void rebuild()}>{busy ? <><LoaderCircle className="spin" size={16} /> Đang re-index</> : <><RefreshCw size={16} /> Re-index {selected.length} tài liệu</>}</button>
      </div>
    </section>
    {error && <div className="stream-error"><CircleAlert size={17} /><span>{error}</span></div>}
  </div>;
}
