"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Archive, FileUp, LoaderCircle, RefreshCw, Search, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { AsyncJob, DocumentDetail, DocumentListItem, EvaluationRun } from "@/lib/types";

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function pollWithLimit<T extends { state: string; poll_after_ms?: number }>(load: () => Promise<T>, initialDelay: number) {
  let current: T | null = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await wait(current?.poll_after_ms ?? initialDelay);
    current = await load();
    if (["COMPLETED", "FAILED"].includes(current.state)) return current;
  }
  throw new ApiClientError("Tác vụ vẫn đang chạy. Bạn có thể kiểm tra lại sau.", "POLL_TIMEOUT", 0, true);
}

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [filters, setFilters] = useState({ category: "", status: "", indexed: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<AsyncJob | null>(null);

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

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) return;
    setUploading(true);
    setError("");
    try {
      const created = await api.uploadDocument(file, {
        title: String(form.get("title") ?? ""),
        category: String(form.get("category") ?? "GENERAL"),
        version: String(form.get("version") ?? ""),
        effective_date: String(form.get("effective_date") ?? ""),
        confidentiality: String(form.get("confidentiality") ?? "INTERNAL"),
        status: "ACTIVE",
      });
      const completed = await pollWithLimit(() => api.getIngestionJob(created.ingestion_job_id), 1000);
      setJob(completed);
      await load();
      event.currentTarget.reset();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải tài liệu lên.");
    } finally {
      setUploading(false);
    }
  }

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

  return <div className="content-page">
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
        <div className="panel-title"><FileUp size={19} /><div><strong>Tải tài liệu mới</strong><span>PDF, DOCX hoặc XLSX · tối đa 25 MB</span></div></div>
        <label>Tệp<input name="file" type="file" accept=".pdf,.docx,.xlsx" required /></label>
        <label>Tiêu đề<input name="title" /></label>
        <label>Danh mục<input name="category" defaultValue="GENERAL" /></label>
        <div className="two-fields"><label>Phiên bản<input name="version" /></label><label>Ngày hiệu lực<input name="effective_date" type="date" /></label></div>
        <label>Mức bảo mật<select name="confidentiality"><option>INTERNAL</option><option>RESTRICTED</option><option>CONFIDENTIAL</option></select></label>
        <button className="primary-command" disabled={uploading}>{uploading ? <LoaderCircle className="spin" size={17} /> : <FileUp size={17} />}{uploading ? "Đang xử lý" : "Tải lên"}</button>
        {job && <div className="job-summary"><span>{job.state}</span><strong>{job.progress_percent}%</strong></div>}
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
  const [job, setJob] = useState<AsyncJob | EvaluationRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function runIndex() {
    setRunning(true); setError("");
    try {
      const created = await api.startIndexRebuild([], "REPLACE");
      setJob({ job_id: created.job_id, state: created.state, progress_percent: 0, poll_after_ms: created.poll_after_ms });
      setJob(await pollWithLimit(() => api.getIndexRebuild(created.job_id), created.poll_after_ms));
    } catch (reason) { setError(reason instanceof ApiClientError ? reason.message : "Không thể chạy re-index."); }
    finally { setRunning(false); }
  }

  async function runEvaluation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setRunning(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.startEvaluation(String(form.get("dataset")), String(form.get("index")), String(form.get("model")));
      setJob({ run_id: created.run_id, job_id: created.run_id, state: created.state, progress_percent: 0, poll_after_ms: created.poll_after_ms, metrics: null, quality_gate: null });
      setJob(await pollWithLimit(() => api.getEvaluation(created.run_id), created.poll_after_ms));
    } catch (reason) { setError(reason instanceof ApiClientError ? reason.message : "Không thể chạy evaluation."); }
    finally { setRunning(false); }
  }

  const evaluation = job && "run_id" in job ? job : null;
  return <div className="content-page narrow-page">
    <div className="page-heading"><div><p className="eyebrow">RAG OPERATIONS</p><h2>{mode === "index" ? "Xây dựng lại Vector Index" : "Đánh giá chất lượng Agent"}</h2><p>{mode === "index" ? "Tạo và theo dõi index job theo contract Backend." : "Chạy bộ đánh giá trên một phiên bản index xác định."}</p></div></div>
    {mode === "index" ? <section className="work-panel operation-panel"><label>Chiến lược<select><option>REPLACE</option></select></label><button className="primary-command" disabled={running} onClick={() => void runIndex()}><RefreshCw className={running ? "spin" : ""} size={17} /> Chạy re-index</button></section>
      : <form className="work-panel operation-panel" onSubmit={runEvaluation}><label>Dataset<input name="dataset" defaultValue="evalset_hr_v1" required /></label><label>Index version<input name="index" defaultValue="v1.0" /></label><label>Model config<input name="model" defaultValue="default" /></label><button className="primary-command" disabled={running}><RefreshCw className={running ? "spin" : ""} size={17} /> Chạy evaluation</button></form>}
    {job && <section className="work-panel result-panel"><div className="result-row"><span>Trạng thái</span><strong>{job.state}</strong></div><div className="progress-track"><div style={{ width: `${job.progress_percent}%` }} /></div><div className="result-row"><span>Tiến độ</span><strong>{job.progress_percent}%</strong></div>
      {evaluation?.metrics && <div className="metric-grid"><Metric label="Recall@5" value={evaluation.metrics.recall_at_5} /><Metric label="Answer correctness" value={evaluation.metrics.answer_correctness} /><Metric label="Citation coverage" value={evaluation.metrics.citation_coverage} /><Metric label="Citation correctness" value={evaluation.metrics.citation_correctness} /></div>}
    </section>}
    {error && <div className="stream-error">{error}</div>}
  </div>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><span>{label}</span><strong>{Math.round(value * 100)}%</strong></div>;
}
