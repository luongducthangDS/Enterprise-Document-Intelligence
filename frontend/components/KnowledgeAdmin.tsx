"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Archive, CircleAlert, Database, FileUp, FlaskConical, LoaderCircle, RefreshCw, Search, X } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import { uploadToCloudinary } from "@/lib/cloudinary";
import type { AsyncJob, DocumentDetail, DocumentListItem, EvaluationRun } from "@/lib/types";
import { DEPARTMENTS, documentStatusLabel, jobStageLabel, jobStateLabel } from "@/lib/labels";

const JOB_TERMINAL_STATES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
const EVALUATION_DATASETS = ["evalset_hr_v1", "evalset_hr_v2", "evalset_default"];

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function friendlyError(reason: unknown, fallback: string) {
  return reason instanceof ApiClientError && reason.message ? reason.message : fallback;
}

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [filters, setFilters] = useState({ category: "", status: "", indexed: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadJob, setUploadJob] = useState<(AsyncJob & { file_name?: string; chunk_count?: number }) | null>(null);
  const [uploadError, setUploadError] = useState("");
  const uploadPollRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDocuments(await api.listDocuments(filters));
    } catch (reason) {
      setError(friendlyError(reason, "Không thể tải tài liệu."));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { uploadPollRef.current = false; }, []);

  async function pollIngestionJob(jobId: string, fileName: string) {
    uploadPollRef.current = true;
    try {
      while (uploadPollRef.current) {
        const job = await api.getIngestionJob(jobId);
        setUploadJob({ ...job, file_name: fileName });
        if (JOB_TERMINAL_STATES.has(job.state.toUpperCase())) {
          if (job.state.toUpperCase() === "COMPLETED") await load();
          return;
        }
        await wait(Math.max(500, job.poll_after_ms ?? 1000));
      }
    } catch (reason) {
      setUploadError(friendlyError(reason, "Không theo dõi được tiến độ xử lý. Danh sách tài liệu vẫn sẽ cập nhật khi tải lại."));
    }
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const fileInput = form.get("file");
    if (!(fileInput instanceof File) || !fileInput.name) {
      setUploadError("Vui lòng chọn PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP (tối đa 25MB).");
      return;
    }
    setUploadBusy(true);
    setUploadError("");
    setUploadJob(null);
    try {
      if (fileInput.size > 25 * 1024 * 1024) {
        setUploadError("Dung lượng file vượt quá giới hạn 25MB.");
        return;
      }
      let publicUrl = "";
      try {
        publicUrl = await uploadToCloudinary(fileInput);
      } catch (cloudinaryError) {
        if (fileInput.size > 4 * 1024 * 1024) throw cloudinaryError;
        console.warn("Cloudinary unavailable; using legacy upload for a small file.", cloudinaryError);
      }
      const created = await api.uploadDocument(fileInput, {
        title: String(form.get("title") ?? ""),
        category: String(form.get("category") ?? ""),
        department: String(form.get("department") ?? ""),
        version: String(form.get("version") ?? ""),
        effective_date: String(form.get("effective_date") ?? ""),
        access_scope: String(form.get("access_scope") ?? "RESTRICTED"),
        confidentiality: "INTERNAL",
        status: "ACTIVE",
        public_url: publicUrl,
      });
      formElement.reset();
      setUploadBusy(false);
      await pollIngestionJob(created.ingestion_job_id, fileInput.name);
    } catch (reason) {
      setUploadError(friendlyError(reason, "Không tải được tài liệu. Vui lòng thử lại."));
    } finally {
      setUploadBusy(false);
    }
  }

  async function archiveCurrent() {
    if (!detail) return;
    try {
      await api.archiveDocument(detail.document_id);
      setDetail(null);
      await load();
    } catch (reason) {
      setError(friendlyError(reason, "Không thể lưu trữ tài liệu."));
    }
  }

  return <div className="content-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">KHO TRI THỨC</p><h2>Tài liệu nội bộ</h2><p>Quản lý nguồn dữ liệu được Trợ lý AI sử dụng để trả lời.</p></div></div>
    <div className="document-layout">
      <section className="work-panel">
        <div className="filter-bar">
          <label><Search size={16} /><input placeholder="Lọc theo danh mục" value={filters.category} onChange={(event) => setFilters((value) => ({ ...value, category: event.target.value }))} /></label>
          <select aria-label="Lọc trạng thái" value={filters.status} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}><option value="">Mọi trạng thái</option><option value="ACTIVE">{documentStatusLabel("ACTIVE")}</option><option value="ARCHIVED">{documentStatusLabel("ARCHIVED")}</option></select>
          <select aria-label="Lọc chỉ mục" value={filters.indexed} onChange={(event) => setFilters((value) => ({ ...value, indexed: event.target.value }))}><option value="">Mọi chỉ mục</option><option value="true">Đã đánh chỉ mục</option><option value="false">Chưa đánh chỉ mục</option></select>
          <button className="icon-command" onClick={() => void load()} title="Tải lại"><RefreshCw size={17} /></button>
        </div>
        {loading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải tài liệu</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Tài liệu</th><th>Danh mục</th><th>Phiên bản</th><th>Xử lý</th><th>Chỉ mục</th><th>Trạng thái</th></tr></thead><tbody>
          {documents.map((item) => <tr key={item.document_id} onClick={() => void api.getDocument(item.document_id).then(setDetail).catch((reason) => setError(friendlyError(reason, "Không mở được chi tiết tài liệu.")))}>
            <td><strong>{item.title}</strong><small>{item.document_id}</small></td><td>{item.category ?? "—"}</td><td>{item.version ?? "—"}</td><td><span className={`status-pill ${item.ingestion_state === "COMPLETED" ? "success" : item.ingestion_state === "FAILED" ? "danger" : "neutral"}`}>{jobStateLabel(item.ingestion_state)}</span></td><td><span className={`status-pill ${item.indexed ? "success" : "warning"}`}>{item.indexed ? "Đã đánh chỉ mục" : "Chưa đánh chỉ mục"}</span></td><td>{documentStatusLabel(item.status)}</td>
          </tr>)}
          {!documents.length && <tr><td colSpan={6} className="empty-cell">Không có tài liệu phù hợp.</td></tr>}
        </tbody></table></div>}
      </section>
      <section className="work-panel">
        <form className="upload-panel" onSubmit={submitUpload}>
          <div className="panel-title"><FileUp size={18} /><div><strong>Thêm tài liệu</strong><span>PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP — tối đa 25MB.</span></div></div>
          <label>Chọn tệp<input type="file" name="file" accept=".pdf,.doc,.docx,.md,.png,.jpg,.jpeg,.webp" required /></label>
          <label>Tên hiển thị<input name="title" placeholder="Bỏ trống để dùng tên tệp" /></label>
          <div className="two-fields">
            <label>Danh mục<input name="category" placeholder="VD: company_regulations" /></label>
            <label>Phòng ban<select name="department" defaultValue="HR">{DEPARTMENTS.map((item) => <option key={item}>{item}</option>)}</select></label>
          </div>
          <div className="two-fields">
            <label>Phiên bản<input name="version" placeholder="VD: 1.0" /></label>
            <label>Hiệu lực từ<input name="effective_date" type="date" /></label>
          </div>
          <label>Phạm vi truy cập<select name="access_scope" defaultValue="RESTRICTED">
            <option value="RESTRICTED">Giới hạn — chỉ người có quyền</option>
            <option value="COMPANY_WIDE">Toàn công ty</option>
            <option value="DEPARTMENT">Phòng ban sở hữu</option>
          </select></label>
          <button className="primary-command" disabled={uploadBusy}>{uploadBusy ? <LoaderCircle className="spin" size={17} /> : <FileUp size={17} />} Tải lên kho</button>
          {uploadError && <div className="inline-error" role="alert"><CircleAlert size={15} /> {uploadError}</div>}
          {uploadJob && <div className="result-panel">
            <div className="job-summary"><span>{uploadJob.file_name}</span><span className={`status-pill ${uploadJob.state === "COMPLETED" ? "success" : uploadJob.state === "FAILED" ? "danger" : "warning"}`}>{jobStateLabel(uploadJob.state)}</span></div>
            <div className="progress-track"><div style={{ width: `${Math.min(100, Math.max(0, uploadJob.progress_percent))}%` }} /></div>
            <div className="job-summary"><span>{jobStageLabel(uploadJob.stage)}</span><span>{uploadJob.progress_percent}%</span></div>
            {uploadJob.state === "COMPLETED" && <p className="form-note">Đã ghi nhận {("chunk_count" in uploadJob ? uploadJob.chunk_count : 0) || 0} đoạn nội dung. Có thể hỏi ngay trên tài liệu này.</p>}
            {uploadJob.state === "FAILED" && <div className="inline-error" role="alert"><CircleAlert size={15} /> Xử lý thất bại{uploadJob.error ? `: ${String(uploadJob.error)}` : "."} Hãy kiểm tra tệp và tải lại.</div>}
          </div>}
        </form>
      </section>
    </div>
    {error && <div className="stream-error">{error}</div>}
    {detail && <div className="modal-layer" onMouseDown={() => setDetail(null)}><section className="detail-modal" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><p className="eyebrow">CHI TIẾT TÀI LIỆU</p><h3>{detail.title}</h3></div><button className="icon-command" onClick={() => setDetail(null)}><X size={18} /></button></header>
      <dl><div><dt>Tệp nguồn</dt><dd>{detail.source_file}</dd></div><div><dt>Danh mục</dt><dd>{detail.category ?? "—"}</dd></div><div><dt>Xử lý</dt><dd>{jobStateLabel(detail.ingestion.state)} · {detail.ingestion.chunk_count} đoạn</dd></div><div><dt>Chỉ mục</dt><dd>{detail.index.indexed ? detail.index.index_version : "Chưa đánh chỉ mục"}</dd></div><div><dt>Checksum</dt><dd><code>{detail.checksum}</code></dd></div></dl>
      <button className="danger-command" disabled={detail.status === "ARCHIVED"} onClick={() => void archiveCurrent()}><Archive size={16} /> Lưu trữ tài liệu</button>
    </section></div>}
  </div>;
}

export function OperationsView({ mode }: { mode: "index" | "evaluation" }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<AsyncJob | null>(null);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [dataset, setDataset] = useState(EVALUATION_DATASETS[0]);
  const pollRef = useRef(false);

  useEffect(() => () => { pollRef.current = false; }, []);

  async function pollIndexRebuild(jobId: string) {
    pollRef.current = true;
    try {
      while (pollRef.current) {
        const current = await api.getIndexRebuild(jobId);
        setJob(current);
        if (JOB_TERMINAL_STATES.has(current.state.toUpperCase())) return;
        await wait(Math.max(500, current.poll_after_ms ?? 2000));
      }
    } catch (reason) {
      setError(friendlyError(reason, "Không theo dõi được tiến độ tác vụ."));
    }
  }

  async function pollEvaluation(runId: string) {
    pollRef.current = true;
    try {
      while (pollRef.current) {
        const current = await api.getEvaluation(runId);
        setRun(current);
        if (JOB_TERMINAL_STATES.has(current.state.toUpperCase())) return;
        await wait(Math.max(500, current.poll_after_ms ?? 3000));
      }
    } catch (reason) {
      setError(friendlyError(reason, "Không theo dõi được tiến độ lượt đánh giá."));
    }
  }

  async function startIndexRebuild() {
    setBusy(true);
    setError("");
    setJob(null);
    try {
      const created = await api.startIndexRebuild([], "REPLACE");
      await pollIndexRebuild(created.job_id);
    } catch (reason) {
      setError(friendlyError(reason, "Không tạo được tác vụ tái lập chỉ mục. Nếu một tác vụ khác đang chạy, hãy chờ nó hoàn tất rồi thử lại."));
    } finally {
      setBusy(false);
    }
  }

  async function startEvaluationRun() {
    setBusy(true);
    setError("");
    setRun(null);
    try {
      const created = await api.startEvaluation(dataset, "", "");
      await pollEvaluation(created.run_id);
    } catch (reason) {
      setError(friendlyError(reason, "Không tạo được lượt đánh giá."));
    } finally {
      setBusy(false);
    }
  }

  return <div className="content-page narrow-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">{mode === "index" ? "CHỈ MỤC TÌM KIẾM" : "ĐÁNH GIÁ CHẤT LƯỢNG"}</p><h2>{mode === "index" ? "Tái lập chỉ mục tìm kiếm" : "Đánh giá chất lượng Trợ lý AI"}</h2><p>{mode === "index" ? "Chạy lại toàn bộ quy trình đánh chỉ mục kho tài liệu. Chỉ một tác vụ chạy cùng lúc." : "Chạy bộ câu hỏi chuẩn để đo chất lượng trả lời và trích dẫn của Trợ lý AI."}</p></div></div>
    <section className="work-panel">
      {mode === "index" ? <div className="operation-panel">
        <div className="panel-title"><Database size={18} /><div><strong>Tái lập toàn bộ</strong><span>Xây lại chỉ mục cho toàn bộ tài liệu đang áp dụng (chiến lược REPLACE).</span></div></div>
        <button className="primary-command" disabled={busy} onClick={() => void startIndexRebuild()}>{busy && !job ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />} Bắt đầu</button>
      </div> : <div className="operation-panel">
        <label>Bộ câu hỏi chuẩn<select value={dataset} onChange={(event) => setDataset(event.target.value)}>{EVALUATION_DATASETS.map((item) => <option key={item}>{item}</option>)}</select></label>
        <div className="panel-title"><FlaskConical size={18} /><div><strong>Chạy đánh giá</strong><span>Đo Recall, độ chính xác câu trả lời và trích dẫn trên chỉ mục đang dùng.</span></div></div>
        <button className="primary-command" disabled={busy} onClick={() => void startEvaluationRun()}>{busy && !run ? <LoaderCircle className="spin" size={17} /> : <FlaskConical size={17} />} Bắt đầu</button>
      </div>}
      {error && <div className="stream-error"><CircleAlert size={17} /><span>{error}</span></div>}
      {mode === "index" && job && <div className="result-panel">
        <div className="job-summary"><span>Tác vụ tái lập chỉ mục</span><span className={`status-pill ${job.state === "COMPLETED" ? "success" : job.state === "FAILED" ? "danger" : "warning"}`}>{jobStateLabel(job.state)}</span></div>
        <div className="progress-track"><div style={{ width: `${Math.min(100, Math.max(0, job.progress_percent))}%` }} /></div>
        <div className="job-summary"><span>{jobStageLabel(job.stage)}</span><span>{job.progress_percent}%</span></div>
        {job.active_index_version && <div className="job-summary"><span>Phiên bản chỉ mục</span><span>{job.active_index_version}</span></div>}
        {job.state === "FAILED" && <div className="inline-error" role="alert"><CircleAlert size={15} /> Tác vụ thất bại{job.error ? `: ${String(job.error)}` : "."}</div>}
      </div>}
      {mode === "evaluation" && run && <div className="result-panel">
        <div className="job-summary"><span>Lượt đánh giá {run.run_id.slice(0, 8)}</span><span className={`status-pill ${run.state === "COMPLETED" ? "success" : run.state === "FAILED" ? "danger" : "warning"}`}>{jobStateLabel(run.state)}</span></div>
        {run.state !== "COMPLETED" && <div className="progress-track"><div style={{ width: `${Math.min(100, Math.max(0, run.progress_percent))}%` }} /></div>}
        {run.state !== "COMPLETED" && <div className="job-summary"><span>{jobStageLabel(run.stage)}</span><span>{run.progress_percent}%</span></div>}
        {run.state === "COMPLETED" && run.metrics && <div className="metric-grid">
          <div><span>Recall@5</span><strong>{formatMetric(run.metrics.recall_at_5, true)}</strong></div>
          <div><span>Độ chính xác câu trả lời</span><strong>{formatMetric(run.metrics.answer_correctness, true)}</strong></div>
          <div><span>Phủ trích dẫn</span><strong>{formatMetric(run.metrics.citation_coverage, true)}</strong></div>
          <div><span>Độ trễ P95</span><strong>{run.metrics.p95_latency_ms ? `${Math.round(Number(run.metrics.p95_latency_ms) / 100) / 10}s` : "—"}</strong></div>
        </div>}
        {run.state === "FAILED" && <div className="inline-error" role="alert"><CircleAlert size={15} /> Lượt đánh giá thất bại{run.error ? `: ${String(run.error)}` : "."}</div>}
      </div>}
    </section>
  </div>;
}

function formatMetric(value: number | null | undefined, percentage: boolean) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const numeric = Number(value);
  return percentage ? `${Math.round(numeric * 100)}%` : numeric.toLocaleString("vi-VN");
}
