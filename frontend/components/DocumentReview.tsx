"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  Archive,
  CheckCircle2,
  CircleAlert,
  FileSearch,
  FileUp,
  LoaderCircle,
  RefreshCw,
  Search,
  X,
  XCircle,
} from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import { uploadToCloudinary } from "@/lib/cloudinary";
import type {
  DocumentDetail,
  DocumentListItem,
  DocumentSubmissionDetail,
  DocumentSubmissionSummary,
  User,
} from "@/lib/types";
import { DEPARTMENTS, documentStatusLabel, jobStageLabel, jobStateLabel } from "@/lib/labels";

const SUBMISSION_TERMINAL_STATES = new Set([
  "PENDING_REVIEW",
  "PUBLISHED",
  "ANALYSIS_FAILED",
  "PUBLISH_FAILED",
  "REJECTED",
  "CHANGES_REQUESTED",
]);

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function friendlyError(reason: unknown, fallback: string) {
  return reason instanceof ApiClientError && reason.message ? reason.message : fallback;
}

function submissionLabel(value: string) {
  const labels: Record<string, string> = {
    ANALYZING: "Đang phân tích",
    PENDING_REVIEW: "Chờ duyệt",
    APPROVING: "Đang phê duyệt",
    PUBLISHING: "Đang xuất bản",
    PUBLISHED: "Đã xuất bản",
    ANALYSIS_FAILED: "Phân tích thất bại",
    PUBLISH_FAILED: "Xuất bản thất bại",
    CHANGES_REQUESTED: "Cần chỉnh sửa",
    REJECTED: "Đã từ chối",
  };
  return labels[value.toUpperCase()] ?? value;
}

function statusTone(value: string) {
  if (["PUBLISHED"].includes(value)) return "success";
  if (["ANALYSIS_FAILED", "PUBLISH_FAILED", "REJECTED"].includes(value)) return "danger";
  if (value === "PENDING_REVIEW") return "warning";
  return "neutral";
}

export function DocumentReview({ user }: { user: User }) {
  const [mode, setMode] = useState<"review" | "published">("review");
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [submissions, setSubmissions] = useState<DocumentSubmissionSummary[]>([]);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [submissionDetail, setSubmissionDetail] = useState<DocumentSubmissionDetail | null>(null);
  const [filters, setFilters] = useState({ category: "", status: "", indexed: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [activeSubmission, setActiveSubmission] = useState<DocumentSubmissionDetail | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const pollRef = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [submissionRows, documentRows] = await Promise.all([
        api.listDocumentSubmissions(),
        api.listDocuments(filters),
      ]);
      setSubmissions(submissionRows);
      setDocuments(documentRows);
    } catch (reason) {
      setError(friendlyError(reason, "Không thể tải kho tài liệu."));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    pollRef.current = true;
    void load();
    return () => {
      pollRef.current = false;
    };
  }, [load]);

  async function pollSubmission(submissionId: string) {
    while (pollRef.current) {
      const current = await api.getDocumentSubmission(submissionId);
      setActiveSubmission(current);
      if (submissionDetail?.submission_id === submissionId) setSubmissionDetail(current);
      if (SUBMISSION_TERMINAL_STATES.has(current.status.toUpperCase())) {
        await load();
        return current;
      }
      await wait(Math.max(700, current.poll_after_ms ?? 1000));
    }
    return null;
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const fileInput = form.get("file");
    if (!(fileInput instanceof File) || !fileInput.name) {
      setUploadError("Vui lòng chọn PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP.");
      return;
    }
    if (fileInput.size > 25 * 1024 * 1024) {
      setUploadError("Dung lượng file vượt quá giới hạn 25MB.");
      return;
    }

    setUploadBusy(true);
    setUploadError("");
    setSuccessMessage("");
    setActiveSubmission(null);
    try {
      // Upload object storage trước để Backend chỉ gửi URL sang worker, tránh base64 phình RAM.
      let publicUrl = "";
      try {
        publicUrl = await uploadToCloudinary(fileInput);
      } catch (cloudinaryError) {
        if (fileInput.size > 4 * 1024 * 1024) throw cloudinaryError;
        console.warn("Cloudinary unavailable; using legacy upload for a small file.", cloudinaryError);
      }
      const created = await api.uploadDocumentSubmission(fileInput, {
        title: String(form.get("title") ?? ""),
        category: String(form.get("category") ?? ""),
        department: String(form.get("department") ?? ""),
        version: String(form.get("version") ?? ""),
        effective_date: String(form.get("effective_date") ?? ""),
        access_scope: String(form.get("access_scope") ?? "RESTRICTED"),
        confidentiality: "INTERNAL",
        public_url: publicUrl,
      });

      formElement.reset();
      const finalAnalysis = await pollSubmission(created.submission_id);
      if (finalAnalysis?.status === "PENDING_REVIEW") {
        setSuccessMessage(`Phân tích tài liệu "${finalAnalysis.title}" thành công! Tài liệu đã sẵn sàng để kiểm duyệt.`);
      }
    } catch (reason) {
      setUploadError(friendlyError(reason, "Không thể tải lên và phân tích tài liệu."));
    } finally {
      setUploadBusy(false);
    }
  }

  async function openSubmission(id: string) {
    try {
      setSubmissionDetail(await api.getDocumentSubmission(id));
      setReviewNote("");
      setError("");
      setSuccessMessage("");
    } catch (reason) {
      setError(friendlyError(reason, "Không mở được tài liệu chờ duyệt."));
    }
  }

  async function approveSubmission() {
    if (!submissionDetail) return;
    setReviewBusy(true);
    setError("");
    setSuccessMessage("");
    try {
      const current = await api.approveDocumentSubmission(submissionDetail.submission_id, reviewNote);
      setSubmissionDetail(current);
      setActiveSubmission(current);
      const result = await pollSubmission(current.submission_id);
      if (result?.status === "PUBLISH_FAILED") {
        setError(result.error || "Không thể xuất bản tài liệu vào kho chính thức.");
      } else if (result?.status === "PUBLISHED") {
        setSuccessMessage(`Đã duyệt và xuất bản tài liệu "${result.title}" thành công vào kho tri thức!`);
        setSubmissionDetail(null);
        setActiveSubmission(null);
        await load();
      }
    } catch (reason) {
      setError(friendlyError(reason, "Không thể duyệt và xuất bản tài liệu."));
    } finally {
      setReviewBusy(false);
    }
  }

  async function rejectSubmission() {
    if (!submissionDetail) return;
    setReviewBusy(true);
    setError("");
    setSuccessMessage("");
    try {
      const current = await api.rejectDocumentSubmission(submissionDetail.submission_id, reviewNote);
      setSuccessMessage(`Đã từ chối tài liệu "${current.title}".`);
      setSubmissionDetail(null);
      setActiveSubmission(null);
      await load();
    } catch (reason) {
      setError(friendlyError(reason, "Không thể từ chối tài liệu."));
    } finally {
      setReviewBusy(false);
    }
  }

  async function archiveCurrent() {
    if (!documentDetail) return;
    try {
      await api.archiveDocument(documentDetail.document_id);
      setSuccessMessage(`Đã lưu trữ tài liệu "${documentDetail.title}".`);
      setDocumentDetail(null);
      await load();
    } catch (reason) {
      setError(friendlyError(reason, "Không thể lưu trữ tài liệu."));
    }
  }

  const visibleSubmissions = submissions.filter((item) => item.status !== "PUBLISHED");

  return <div className="content-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading">
      <div>
        <p className="eyebrow">KHO TRI THỨC</p>
        <h2>Kiểm duyệt tài liệu</h2>
        <p>Tài liệu được phân tích trong vùng riêng và chỉ được Trợ lý AI sử dụng sau khi phê duyệt.</p>
      </div>
    </div>

    {error && (
      <div className="error-banner animate__animated animate__fadeIn">
        <CircleAlert size={18} />
        <span>{error}</span>
        <button type="button" onClick={() => setError("")} aria-label="Đóng" style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "inherit" }}><X size={16} /></button>
      </div>
    )}

    {successMessage && (
      <div className="success-banner animate__animated animate__fadeIn" style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.75rem 1rem", borderRadius: "8px", background: "rgba(34, 197, 94, 0.15)", border: "1px solid rgba(34, 197, 94, 0.3)", color: "#15803d", marginBottom: "1rem" }}>
        <CheckCircle2 size={18} />
        <span>{successMessage}</span>
        <button type="button" onClick={() => setSuccessMessage("")} aria-label="Đóng" style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "inherit" }}><X size={16} /></button>
      </div>
    )}

    <div className="document-tabs" role="tablist">
      <button className={mode === "review" ? "active" : ""} onClick={() => setMode("review")}>
        Chờ duyệt <span>{visibleSubmissions.length}</span>
      </button>
      <button className={mode === "published" ? "active" : ""} onClick={() => setMode("published")}>
        Đang áp dụng <span>{documents.filter((item) => item.status === "ACTIVE").length}</span>
      </button>
    </div>

    <div className="document-layout">
      <section className="work-panel">
        {mode === "published" && <div className="filter-bar">
          <label><Search size={16} /><input placeholder="Lọc theo danh mục" value={filters.category} onChange={(event) => setFilters((value) => ({ ...value, category: event.target.value }))} /></label>
          <select aria-label="Lọc trạng thái" value={filters.status} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}><option value="">Mọi trạng thái</option><option value="ACTIVE">{documentStatusLabel("ACTIVE")}</option><option value="ARCHIVED">{documentStatusLabel("ARCHIVED")}</option></select>
          <select aria-label="Lọc chỉ mục" value={filters.indexed} onChange={(event) => setFilters((value) => ({ ...value, indexed: event.target.value }))}><option value="">Mọi chỉ mục</option><option value="true">Đã đánh chỉ mục</option><option value="false">Chưa đánh chỉ mục</option></select>
          <button className="icon-command" onClick={() => void load()} title="Tải lại"><RefreshCw size={17} /></button>
        </div>}
        {mode === "review" && <div className="review-bar">
          <div><FileSearch size={17} /><span><strong>Hàng đợi kiểm duyệt</strong><small>Extract và các đoạn tìm kiếm được lưu ở staging, chưa đi vào kho chính thức.</small></span></div>
          <button className="icon-command" onClick={() => void load()} title="Tải lại"><RefreshCw size={17} /></button>
        </div>}

        {loading ? <div className="panel-loading"><LoaderCircle className="spin" /> Đang tải tài liệu</div> : mode === "review" ? <div className="data-table-wrap">
          <table className="data-table"><thead><tr><th>Tài liệu</th><th>Phòng ban</th><th>Extract</th><th>Số đoạn</th><th>Trạng thái</th></tr></thead><tbody>
            {visibleSubmissions.map((item) => <tr key={item.submission_id} onClick={() => void openSubmission(item.submission_id)}>
              <td><strong>{item.title}</strong><small>{item.source_file}</small></td>
              <td>{item.department}</td>
              <td>{item.extract_method ?? jobStageLabel(item.stage)}</td>
              <td>{item.chunk_count || "—"}</td>
              <td><span className={"status-pill " + statusTone(item.status)}>{submissionLabel(item.status)}</span></td>
            </tr>)}
            {!visibleSubmissions.length && <tr><td colSpan={5} className="empty-cell">Không có tài liệu đang chờ duyệt.</td></tr>}
          </tbody></table>
        </div> : <div className="data-table-wrap">
          <table className="data-table"><thead><tr><th>Tài liệu</th><th>Danh mục</th><th>Phiên bản</th><th>Xử lý</th><th>Chỉ mục</th><th>Trạng thái</th></tr></thead><tbody>
            {documents.map((item) => <tr key={item.document_id} onClick={() => void api.getDocument(item.document_id).then(setDocumentDetail).catch((reason) => setError(friendlyError(reason, "Không mở được chi tiết tài liệu.")))}>
              <td><strong>{item.title}</strong><small>{item.document_id}</small></td><td>{item.category ?? "—"}</td><td>{item.version ?? "—"}</td><td><span className={"status-pill " + (item.ingestion_state === "COMPLETED" ? "success" : item.ingestion_state === "FAILED" ? "danger" : "neutral")}>{jobStateLabel(item.ingestion_state)}</span></td><td><span className={"status-pill " + (item.indexed ? "success" : "warning")}>{item.indexed ? "Đã đánh chỉ mục" : "Chưa đánh chỉ mục"}</span></td><td>{documentStatusLabel(item.status)}</td>
            </tr>)}
            {!documents.length && <tr><td colSpan={6} className="empty-cell">Không có tài liệu phù hợp.</td></tr>}
          </tbody></table>
        </div>}
      </section>

      <section className="work-panel">
        <form className="upload-panel" onSubmit={submitUpload}>
          <div className="panel-title"><FileUp size={18} /><div><strong>Thêm tài liệu để kiểm duyệt</strong><span>PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP — tối đa 25MB.</span></div></div>
          <label>Chọn tệp<input type="file" name="file" accept=".pdf,.doc,.docx,.md,.png,.jpg,.jpeg,.webp" required /></label>
          <label>Tên hiển thị<input name="title" placeholder="Bỏ trống để dùng tên tệp" /></label>
          <div className="two-fields">
            <label>Danh mục<input name="category" placeholder="VD: company_regulations" /></label>
            <label>Phòng ban<select name="department" defaultValue={user.department}>{(user.role === "DEPARTMENT_MANAGER" ? [user.department] : DEPARTMENTS).map((item) => <option key={item}>{item}</option>)}</select></label>
          </div>
          <div className="two-fields">
            <label>Phiên bản<input name="version" placeholder="VD: 1.0" /></label>
            <label>Hiệu lực từ<input name="effective_date" type="date" /></label>
          </div>
          <label>Phạm vi truy cập<select name="access_scope" defaultValue="RESTRICTED">
            <option value="RESTRICTED">Chỉ người tải</option>
            <option value="DEPARTMENT">Phòng ban sở hữu</option>
            {user.role === "SUPER_ADMIN" && <option value="COMPANY_WIDE">Toàn công ty</option>}
          </select></label>
          <button className="primary-command" disabled={uploadBusy}>{uploadBusy ? <LoaderCircle className="spin" size={17} /> : <FileUp size={17} />} Tải lên và phân tích</button>
          {uploadError && <div className="inline-error" role="alert"><CircleAlert size={15} /> {uploadError}</div>}
          {activeSubmission && <div className="result-panel">
            <div className="job-summary"><span>{activeSubmission.source_file}</span><span className={"status-pill " + statusTone(activeSubmission.status)}>{submissionLabel(activeSubmission.status)}</span></div>
            {!SUBMISSION_TERMINAL_STATES.has(activeSubmission.status) && <div className="progress-track"><div style={{ width: Math.min(100, Math.max(0, activeSubmission.progress_percent)) + "%" }} /></div>}
            <div className="job-summary"><span>{jobStageLabel(activeSubmission.stage)}</span><span>{activeSubmission.progress_percent}%</span></div>
            {activeSubmission.status === "PENDING_REVIEW" && <p className="form-note">Đã extract {activeSubmission.analysis.character_count.toLocaleString("vi-VN")} ký tự và tạo {activeSubmission.chunk_count} đoạn. Tài liệu đang chờ duyệt, AI chưa sử dụng.</p>}
            {activeSubmission.status === "ANALYSIS_FAILED" && <div className="inline-error" role="alert"><CircleAlert size={15} /> Không thể phân tích tài liệu. Hãy kiểm tra file và thử lại.</div>}
          </div>}
        </form>
      </section>
    </div>

    {error && <div className="stream-error"><CircleAlert size={17} /><span>{error}</span></div>}

    {submissionDetail && <div className="modal-layer" onMouseDown={() => setSubmissionDetail(null)}>
      <section className="detail-modal submission-detail-modal" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><p className="eyebrow">TÀI LIỆU CHỜ DUYỆT</p><h3>{submissionDetail.title}</h3></div><button className="icon-command" onClick={() => setSubmissionDetail(null)}><X size={18} /></button></header>
        <div className="submission-review-status"><span className={"status-pill " + statusTone(submissionDetail.status)}>{submissionLabel(submissionDetail.status)}</span><span>AI chưa sử dụng tài liệu khi chưa xuất bản thành công.</span></div>

        <h4>1. Thông tin đã khai báo</h4>
        <dl className="submission-metadata">
          <div><dt>Tệp nguồn</dt><dd>{submissionDetail.metadata.source_file}</dd></div>
          <div><dt>Danh mục</dt><dd>{submissionDetail.metadata.category}</dd></div>
          <div><dt>Phòng ban</dt><dd>{submissionDetail.metadata.department}</dd></div>
          <div><dt>Phiên bản</dt><dd>{submissionDetail.metadata.version ?? "—"}</dd></div>
          <div><dt>Ngày hiệu lực</dt><dd>{submissionDetail.metadata.effective_date ?? "—"}</dd></div>
          <div><dt>Phạm vi</dt><dd>{submissionDetail.metadata.access_scope}</dd></div>
        </dl>

        <h4>2. Kết quả extract</h4>
        <div className="extract-stats">
          <span><strong>{submissionDetail.analysis.character_count.toLocaleString("vi-VN")}</strong> ký tự</span>
          <span><strong>{submissionDetail.analysis.chunk_count}</strong> đoạn</span>
          <span><strong>{submissionDetail.analysis.extract_method ?? "—"}</strong> phương thức</span>
        </div>
        <pre className="extract-preview">{submissionDetail.analysis.extracted_text || "Chưa có nội dung extract."}</pre>

        <h4>3. Các đoạn tìm kiếm</h4>
        <div className="chunk-review-list">
          {submissionDetail.analysis.chunks.map((chunk) => <details key={chunk.chunk_index}>
            <summary>Đoạn {chunk.chunk_index + 1}{chunk.heading_path ? " · " + chunk.heading_path : ""}<span>{chunk.char_count} ký tự</span></summary>
            <p>{chunk.content}</p>
          </details>)}
          {!submissionDetail.analysis.chunks.length && <p className="form-note">Chưa có đoạn nội dung.</p>}
        </div>

        {submissionDetail.status === "PENDING_REVIEW" && <div className="review-actions">
          <label>Ghi chú kiểm duyệt<textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Nhập lý do nếu từ chối hoặc lưu ghi chú phê duyệt" /></label>
          <div>
            <button className="danger-command" disabled={reviewBusy} onClick={() => void rejectSubmission()}><XCircle size={16} /> Từ chối</button>
            <button className="primary-command" disabled={reviewBusy} onClick={() => void approveSubmission()}>{reviewBusy ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />} Duyệt và xuất bản</button>
          </div>
        </div>}
      </section>
    </div>}

    {documentDetail && <div className="modal-layer" onMouseDown={() => setDocumentDetail(null)}><section className="detail-modal" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><p className="eyebrow">CHI TIẾT TÀI LIỆU</p><h3>{documentDetail.title}</h3></div><button className="icon-command" onClick={() => setDocumentDetail(null)}><X size={18} /></button></header>
      <dl><div><dt>Tệp nguồn</dt><dd>{documentDetail.source_file}</dd></div><div><dt>Danh mục</dt><dd>{documentDetail.category ?? "—"}</dd></div><div><dt>Xử lý</dt><dd>{jobStateLabel(documentDetail.ingestion.state)} · {documentDetail.ingestion.chunk_count} đoạn</dd></div><div><dt>Chỉ mục</dt><dd>{documentDetail.index.indexed ? documentDetail.index.index_version : "Chưa đánh chỉ mục"}</dd></div></dl>
      <button className="danger-command" disabled={documentDetail.status === "ARCHIVED"} onClick={() => void archiveCurrent()}><Archive size={16} /> Lưu trữ tài liệu</button>
    </section></div>}
  </div>;
}
