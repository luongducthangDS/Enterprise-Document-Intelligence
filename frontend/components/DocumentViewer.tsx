"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  LoaderCircle,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  AlertCircle,
  Sparkles,
  Maximize2,
} from "lucide-react";
import type { CitationDetail } from "@/lib/types";

interface DocumentViewerProps {
  citation: CitationDetail;
}

type FileType = "docx" | "pdf" | "image" | "fallback";

/**
 * Nhận diện định dạng file chính xác 100%:
 * 1. Ưu tiên kiểm tra DOCX / DOC
 * 2. Ưu tiên kiểm tra PDF (Kể cả khi URL Cloudinary nằm trong thư mục /image/upload/)
 * 3. Kiểm tra Hình ảnh (PNG, JPG, JPEG, WEBP, GIF)
 * 4. Fallback an toàn
 */
function detectFileType(
  url?: string | null,
  sourceFile?: string | null,
  title?: string | null
): FileType {
  if (!url && !sourceFile && !title) return "fallback";

  const rawString = `${url || ""} ${sourceFile || ""} ${title || ""}`.toLowerCase();
  const cleanUrl = (url || "").toLowerCase().split("?")[0];

  // 1. DOCX / DOC
  if (
    cleanUrl.endsWith(".docx") ||
    cleanUrl.endsWith(".doc") ||
    rawString.includes(".docx") ||
    rawString.includes(".doc") ||
    rawString.includes("wordprocessingml") ||
    rawString.includes("msword")
  ) {
    return "docx";
  }

  // 2. PDF (Kiểm tra TRƯỚC image/upload để không nhận nhầm file PDF trên Cloudinary)
  if (
    cleanUrl.endsWith(".pdf") ||
    rawString.includes(".pdf") ||
    rawString.includes("application/pdf")
  ) {
    return "pdf";
  }

  // 3. Hình ảnh
  if (
    cleanUrl.endsWith(".png") ||
    cleanUrl.endsWith(".jpg") ||
    cleanUrl.endsWith(".jpeg") ||
    cleanUrl.endsWith(".webp") ||
    cleanUrl.endsWith(".gif") ||
    rawString.includes(".png") ||
    rawString.includes(".jpg") ||
    rawString.includes(".jpeg") ||
    rawString.includes(".webp") ||
    rawString.includes(".gif") ||
    rawString.includes("image/upload")
  ) {
    return "image";
  }

  // 4. Raw docx upload
  if (cleanUrl.includes("/raw/upload/")) {
    return "docx";
  }

  return "fallback";
}
// Thêm hàm helper này ở ngoài component (cùng chỗ với normalizeText)
function flattenMarkdownExcerpt(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")               // bỏ code block
    .replace(/`([^`]+)`/g, "$1")                    // bỏ inline code
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")        // ảnh -> giữ alt text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")         // link -> giữ text
    .replace(/^#{1,6}\s+/gm, "")                     // heading
    .replace(/^>\s?/gm, "")                          // blockquote
    .replace(/^[-*+]\s+/gm, "")                      // bullet list
    .replace(/^\d+\.\s+/gm, "")                      // numbered list
    .replace(/\*\*([^*]+)\*\*/g, "$1")               // bold
    .replace(/\*([^*]+)\*/g, "$1")                   // italic *
    .replace(/_{1,2}([^_]+)_{1,2}/g, "$1")           // italic/bold _
    .replace(/\s*\|\s*/g, " · ")                     // biến cột bảng thành dấu chấm phân cách sạch
    .replace(/\r?\n+/g, "  \n")                      // giữ ngắt dòng nhẹ giữa các ý
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function extractKeywords(text: string): string[] {
  if (!text) return [];
  const clean = text
    .replace(/[*_#>`~|]/g, " ")
    .replace(/[-]{2,}/g, " ")
    .replace(/[.,/#!$%^&*;:{}=\-_`~()?"'’“”]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  if (!clean || clean.length < 3) return [];

  const words = clean.split(/\s+/).filter((w) => w.length > 1);
  const phrases: string[] = [];

  // Trích xuất các cụm 3-4 từ liên tiếp
  for (let i = 0; i < words.length; i += 2) {
    const chunk = words.slice(i, i + 4).join(" ");
    if (chunk.length >= 6) {
      phrases.push(chunk);
    }
  }

  if (phrases.length === 0 && clean.length >= 3) {
    phrases.push(clean);
  }

  return phrases;
}

export function DocumentViewer({ citation }: DocumentViewerProps) {
  const publicUrl = citation.public_url || citation.document?.public_url;
  const sourceFile = citation.document?.source_type || citation.location?.chunk_id;
  const title = citation.document?.title;

  const fileType = detectFileType(publicUrl, sourceFile, title);

  return (
    <div className="document-viewer-container flex flex-col w-full gap-3">
      {/* ─────────────────────────────────────────────────────────────
          1. ĐOẠN TRÍCH DẪN ĐỐI SOÁT (NỀN TRẮNG, BO GÓC, CLICK TIÊU ĐỀ MỞ FILE GỐC)
          ───────────────────────────────────────────────────────────── */}
      <div
        className="citation-excerpt-top-card"
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          backgroundColor: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: "10px",
          padding: "10px 12px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            marginBottom: "6px",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              fontSize: "12px",
              fontWeight: 600,
              color: "#475569",
            }}
          >
            <Sparkles size={13} color="#047857" style={{ flexShrink: 0 }} />
            <span>Đoạn trích dẫn đối soát</span>
          </span>

          {publicUrl && (
            <a
              href={publicUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                fontSize: "12px",
                fontWeight: 700,
                color: "#047857",
                textDecoration: "underline",
                textUnderlineOffset: "2px",
                backgroundColor: "#ecfdf5",
                border: "1px solid #a7f3d0",
                padding: "3px 9px",
                borderRadius: "6px",
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
              title="Nhấn để mở file gốc ở tab mới"
            >
              <ExternalLink size={12} color="#047857" style={{ flexShrink: 0 }} />
              <span>Mở file gốc</span>
            </a>
          )}
        </div>

        <div
          style={{
            fontSize: "12px",
            color: "#334155",
            lineHeight: 1.5,
            maxHeight: "90px",
            overflowY: "auto",
            whiteSpace: "normal",
          }}
        >
          {citation.excerpt
            ? flattenMarkdownExcerpt(citation.excerpt)
            : "Nguồn đã được ghi nhận nhưng chưa có đoạn trích để hiển thị."}
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          2. TOÀN BỘ TÀI LIỆU GỐC (FULL DOCUMENT VIEWPORT VỚI THANH CUỘN ĐỘC LẬP)
          ───────────────────────────────────────────────────────────── */}
      <div className="document-viewport-wrapper w-full bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col">
        {fileType === "docx" && publicUrl && (
          <DocxViewer url={publicUrl} excerpt={citation.excerpt} />
        )}

        {fileType === "pdf" && publicUrl && (
          <PdfViewer
            url={publicUrl}
            initialPage={citation.location?.page || 1}
            excerpt={citation.excerpt}
          />
        )}

        {fileType === "image" && publicUrl && (
          <ImageViewer url={publicUrl} />
        )}

        {fileType === "fallback" && (
          <div className="citation-fallback-box p-8 text-center text-slate-500 text-xs flex flex-col items-center justify-center gap-2">
            <FileText size={28} className="text-slate-400" />
            <span>Tài liệu này chưa có bản xem trực tiếp trên trình duyệt.</span>
            {publicUrl && (
              <a
                href={publicUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="open-raw-link mt-2 inline-flex items-center gap-1.5"
              >
                <ExternalLink size={13} /> Mở tải xuống file gốc
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// -------------------------------------------------------------
// DOCX VIEWER COMPONENT (SUPER ACCURATE HIGHLIGHTING & AUTO-SCROLL)
// -------------------------------------------------------------
function DocxViewer({
  url,
  excerpt = "",
}: {
  url: string;
  excerpt?: string;
}) {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError("");

    async function loadAndRenderDocx() {
      try {
        const docxPreview = await import("docx-preview");
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const blob = await response.blob();
        if (isCancelled) return;

        if (containerRef.current) {
          containerRef.current.innerHTML = "";
          await docxPreview.renderAsync(blob, containerRef.current, undefined, {
            inWrapper: true,
            ignoreWidth: true,
            ignoreHeight: true,
            renderChanges: false,
            renderHeaders: true,
            renderFooters: true,
          });

          // Quét và bôi vàng highlight ở nhiều thời điểm đảm bảo DOM đã render 100%
          if (excerpt && excerpt.trim().length > 3) {
            [120, 350, 750, 1400].forEach((delay) => {
              setTimeout(() => {
                if (!isCancelled && containerRef.current) {
                  highlightAndScrollDocx(containerRef.current, excerpt);
                }
              }, delay);
            });
          }
        }
        setLoading(false);
      } catch (err: unknown) {
        if (isCancelled) return;
        console.error("Docx render error:", err);
        setError("Không thể tải hoặc render trực tiếp file Word.");
        setLoading(false);
      }
    }

    loadAndRenderDocx();

    return () => {
      isCancelled = true;
    };
  }, [url, excerpt]);

  function highlightAndScrollDocx(root: HTMLElement, textToFind: string) {
    if (!textToFind || textToFind.trim().length < 3) return;

    // Xóa sạch các highlight cũ nếu có
    root.querySelectorAll(".docx-notebook-highlight").forEach((el) => {
      el.classList.remove("docx-notebook-highlight");
      (el as HTMLElement).style.removeProperty("background-color");
      (el as HTMLElement).style.removeProperty("border-left");
      (el as HTMLElement).style.removeProperty("padding");
      (el as HTMLElement).style.removeProperty("border-radius");
      (el as HTMLElement).style.removeProperty("color");
    });

    const searchPhrases = extractKeywords(textToFind);
    if (searchPhrases.length === 0) return;

    // CHỈ quét các thẻ đoạn văn cấp thấp (KHÔNG quét section, div container lớn, table cha)
    const elements = root.querySelectorAll<HTMLElement>(
      "p, .docx_paragraph, tr, li, h1, h2, h3, h4, h5, h6, blockquote"
    );

    const matchedElements: { el: HTMLElement; score: number }[] = [];
    let highestScore = 0;

    elements.forEach((el) => {
      const elText = (el.innerText || el.textContent || "")
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();

      if (!elText || elText.length < 5) return;

      // Tính điểm match: Đếm số lượng cụm từ khóa nằm trong đoạn văn này
      let score = 0;
      searchPhrases.forEach((phrase) => {
        if (elText.includes(phrase)) {
          score += phrase.length; // Trọng số theo độ dài cụm từ khớp
        }
      });

      if (score >= 6) {
        matchedElements.push({ el, score });
      }
      if (score > highestScore) {
        highestScore = score;
      }
    });

    // Bôi vàng TẤT CẢ các đoạn văn đạt ngưỡng điểm tốt (từ 35% điểm cao nhất trở lên)
    const minThreshold = Math.max(6, highestScore * 0.35);
    const qualifying = matchedElements.filter((m) => m.score >= minThreshold);

    if (qualifying.length > 0) {
      qualifying.forEach(({ el }) => {
        el.classList.add("docx-notebook-highlight");
        el.style.setProperty("background-color", "#fef08a", "important");
        el.style.setProperty("border-left", "4px solid #eab308", "important");
        el.style.setProperty("padding", "4px 8px", "important");
        el.style.setProperty("border-radius", "4px", "important");

        // Bôi vàng các thẻ chữ con bên trong đoạn văn đó
        el.querySelectorAll<HTMLElement>("span, b, strong, em, i, a").forEach((child) => {
          child.classList.add("docx-notebook-highlight");
          child.style.setProperty("background-color", "#fef08a", "important");
          child.style.setProperty("color", "#000000", "important");
        });
      });

      // Tự động cuộn đến đoạn văn đầu tiên trong danh sách highlight
      const firstTarget = qualifying[0].el;
      const viewport = root.closest(".docx-viewport-container") as HTMLElement | null;
      if (viewport) {
        const vRect = viewport.getBoundingClientRect();
        const elRect = firstTarget.getBoundingClientRect();
        const scrollTarget = viewport.scrollTop + (elRect.top - vRect.top) - (viewport.clientHeight / 3);
        viewport.scrollTo({
          top: Math.max(0, scrollTarget),
          behavior: "smooth",
        });
      } else {
        firstTarget.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    }
  }


  return (
    <div className="docx-viewer-wrapper flex flex-col w-full">
      <div className="docx-toolbar flex items-center justify-between px-3 py-2 border-b bg-white">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
          <FileText size={15} className="text-emerald-700" />
          <span>Toàn bộ tài liệu Word gốc (.docx)</span>
        </div>
      </div>

      {/* VIEWPORT DOCX CÓ THANH CUỘN RIÊNG BIỆT */}
      <div className="docx-viewport-container p-4 bg-slate-50 flex justify-center overflow-y-auto max-h-[650px] min-h-[400px]">
        {loading && (
          <div className="docx-loading-state flex flex-col items-center justify-center p-12 text-slate-500 gap-3">
            <LoaderCircle className="spin" size={28} />
            <p className="text-xs">Đang nạp toàn bộ nội dung tài liệu Word...</p>
          </div>
        )}

        {error && (
          <div className="docx-error-state flex flex-col items-center justify-center p-8 text-rose-600 gap-2">
            <AlertCircle size={24} />
            <p className="text-xs">{error}</p>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="open-raw-link mt-2"
            >
              <ExternalLink size={13} /> Mở file Word trực tiếp
            </a>
          </div>
        )}

        <div
          ref={containerRef}
          className="docx-render-container w-full"
          style={{ display: loading || error ? "none" : "block" }}
        />
      </div>
    </div>
  );
}

// -------------------------------------------------------------
// PDF VIEWER COMPONENT (RETINA HD, RESIZE OBSERVER, SCROLLABLE VIEWPORT)
// -------------------------------------------------------------
interface PdfTextItem {
  str?: string;
  transform?: number[];
  width?: number;
  height?: number;
}

interface PdfRenderTask {
  promise: Promise<void>;
  cancel: () => void;
}

interface PdfPageViewport {
  width: number;
  height: number;
  scale: number;
  transform: number[];
  convertToViewportPoint: (x: number, y: number) => [number, number];
}

interface PdfPageProxy {
  rotate: number;
  getViewport: (options: { scale: number; rotation?: number }) => PdfPageViewport;
  render: (context: {
    canvasContext: CanvasRenderingContext2D;
    viewport: PdfPageViewport;
    transform?: number[];
  }) => PdfRenderTask;
  getTextContent: () => Promise<{ items: PdfTextItem[] }>;
}

interface PdfDocumentProxy {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageProxy>;
}

function PdfViewer({
  url,
  initialPage = 1,
  excerpt = "",
}: {
  url: string;
  initialPage?: number;
  excerpt?: string;
}) {
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(initialPage || 1);
  const [userZoom, setUserZoom] = useState<number>(1.25);
  const [containerWidth, setContainerWidth] = useState<number>(500);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  const viewportContainerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const pdfDocRef = useRef<PdfDocumentProxy | null>(null);
  const activeRenderTaskRef = useRef<PdfRenderTask | null>(null);

  // Reset state khi URL hoặc initialPage thay đổi
  useEffect(() => {
    setCurrentPage(initialPage || 1);
    setUserZoom(1.25);
  }, [url, initialPage]);

  // ResizeObserver: Tự động phát hiện khi kéo dãn/thu nhỏ sidebar để render lại canvas
  useEffect(() => {
    const container = viewportContainerRef.current;
    if (!container) return;

    let resizeTimer: NodeJS.Timeout | null = null;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = entry.contentRect.width;
        if (width > 50) {
          if (resizeTimer) clearTimeout(resizeTimer);
          resizeTimer = setTimeout(() => {
            setContainerWidth(width);
          }, 100);
        }
      }
    });

    observer.observe(container);
    return () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError("");

    async function loadPdf() {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version || "4.10.38"}/pdf.worker.min.mjs`;

        const loadingTask = pdfjs.getDocument({
          url,
          cMapUrl: `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version || "4.10.38"}/cmaps/`,
          cMapPacked: true,
        });

        const pdf = (await loadingTask.promise) as unknown as PdfDocumentProxy;
        if (isCancelled) return;

        pdfDocRef.current = pdf;
        setNumPages(pdf.numPages);
        const targetPage = Math.min(Math.max(1, initialPage || 1), pdf.numPages);
        setCurrentPage(targetPage);
        setLoading(false);
      } catch (err: unknown) {
        if (isCancelled) return;
        console.error("PDF load error:", err);
        setError("Không thể tải file PDF trực tuyến.");
        setLoading(false);
      }
    }

    loadPdf();

    return () => {
      isCancelled = true;
      if (activeRenderTaskRef.current) {
        activeRenderTaskRef.current.cancel();
        activeRenderTaskRef.current = null;
      }
    };
  }, [url, initialPage]);

  const renderPage = useCallback(async () => {
    if (!pdfDocRef.current || currentPage < 1 || loading) return;

    // Hủy tác vụ render cũ nếu đang vẽ
    if (activeRenderTaskRef.current) {
      activeRenderTaskRef.current.cancel();
      activeRenderTaskRef.current = null;
    }

    try {
      const page = await pdfDocRef.current.getPage(currentPage);
      const canvas = canvasRef.current;
      const textLayer = textLayerRef.current;
      if (!canvas) return;

      const unscaledViewport = page.getViewport({ scale: 1.0 });
      const targetWidth = Math.max(containerWidth - 36, 360);
      const baseScale = targetWidth / unscaledViewport.width;
      const effectiveScale = Math.max(baseScale * userZoom, 0.85);

      const viewport = page.getViewport({ scale: effectiveScale });
      const outputScale = typeof window !== "undefined" ? Math.max(window.devicePixelRatio || 1, 2) : 2;

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;

      const ctx = canvas.getContext("2d", { alpha: false });
      if (!ctx) return;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const transformMatrix = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;

      const renderContext = {
        canvasContext: ctx,
        transform: transformMatrix,
        viewport: viewport,
      };

      const renderTask = page.render(renderContext);
      activeRenderTaskRef.current = renderTask;
      await renderTask.promise;
      activeRenderTaskRef.current = null;

      if (textLayer) {
        textLayer.innerHTML = "";
        textLayer.style.width = `${Math.floor(viewport.width)}px`;
        textLayer.style.height = `${Math.floor(viewport.height)}px`;

        const textContent = await page.getTextContent();
        const searchPhrases = extractKeywords(excerpt);

        textContent.items.forEach((item: PdfTextItem) => {
          if (!item.str || !item.transform) return;
          const itemText = item.str;
          const normItem = itemText.toLowerCase().replace(/\s+/g, " ").trim();
          const isMatch =
            searchPhrases.length > 0 &&
            normItem.length >= 6 &&
            searchPhrases.some((p) => p.length >= 6 && (normItem.includes(p) || p.includes(normItem)));

          const [vx, vy] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
          const fontHeight = Math.sqrt(item.transform[0] * item.transform[0] + item.transform[1] * item.transform[1]) * effectiveScale;

          const span = document.createElement("span");
          span.textContent = itemText;
          span.className = isMatch ? "pdf-text-match" : "pdf-text-item";
          span.style.left = `${Math.floor(vx)}px`;
          span.style.top = `${Math.floor(vy - fontHeight)}px`;
          span.style.fontSize = `${Math.max(fontHeight, 10)}px`;
          span.style.position = "absolute";
          span.style.lineHeight = "1";
          span.style.whiteSpace = "pre";
          if (isMatch) {
            span.style.backgroundColor = "#fef08a";
            span.style.color = "#000000";
            span.style.fontWeight = "bold";
            span.style.borderRadius = "2px";
          }
          textLayer.appendChild(span);
        });

        // Tự động cuộn đến đoạn match trong viewport PDF
        setTimeout(() => {
          const matchSpan = textLayer.querySelector(".pdf-text-match") as HTMLElement | null;
          const viewportContainer = viewportContainerRef.current;
          if (matchSpan && viewportContainer) {
            const vRect = viewportContainer.getBoundingClientRect();
            const sRect = matchSpan.getBoundingClientRect();
            viewportContainer.scrollTo({
              top: Math.max(0, viewportContainer.scrollTop + (sRect.top - vRect.top) - 100),
              behavior: "smooth",
            });
          }
        }, 150);
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "name" in err && err.name !== "RenderingCancelledException") {
        console.error("PDF render error:", err);
      }
    }
  }, [currentPage, userZoom, containerWidth, loading, excerpt]);


  useEffect(() => {
    renderPage();
  }, [renderPage]);

  return (
    <div className="pdf-viewer-wrapper flex flex-col w-full">
      {/* ─────────────────────────────────────────────────────────────
          THANH ĐIỀU KHIỂN CHUYỂN TRANG PDF
          ───────────────────────────────────────────────────────────── */}
      <div className="pdf-toolbar flex items-center justify-between px-3 py-2 border-b bg-white shadow-xs">
        <div className="pdf-pagination flex items-center gap-1.5">
          <button
            type="button"
            className="tool-btn"
            disabled={currentPage <= 1 || loading}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            title="Trang trước"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="page-indicator text-xs font-bold text-slate-700 px-2 py-0.5 bg-slate-100 rounded">
            Trang {currentPage} / {numPages || "—"}
          </span>
          <button
            type="button"
            className="tool-btn"
            disabled={currentPage >= numPages || loading}
            onClick={() => setCurrentPage((p) => Math.min(numPages, p + 1))}
            title="Trang sau"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        <div className="pdf-zoom flex items-center gap-1">
          <button
            type="button"
            className="tool-btn"
            onClick={() => setUserZoom((z) => Math.max(0.8, Number((z - 0.2).toFixed(2))))}
            title="Thu nhỏ"
          >
            <ZoomOut size={15} />
          </button>
          <span className="zoom-indicator text-xs font-semibold text-slate-600 px-1.5">{Math.round(userZoom * 100)}%</span>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setUserZoom((z) => Math.min(2.8, Number((z + 0.2).toFixed(2))))}
            title="Phóng to"
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setUserZoom(1.35)}
            title="Kích thước tối ưu"
            style={{ marginLeft: "4px" }}
          >
            <RotateCcw size={13} />
          </button>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          VÙNG HIỂN THỊ TRANG PDF CÓ THANH CUỘN ĐỘC LẬP KHI ZOOM
          ───────────────────────────────────────────────────────────── */}
      <div
        ref={viewportContainerRef}
        className="pdf-viewport-container p-4 flex justify-center bg-slate-600 overflow-auto max-h-[650px] min-h-[400px]"
      >
        {loading && (
          <div className="pdf-loading-state flex flex-col items-center justify-center p-12 text-white gap-3">
            <LoaderCircle className="spin" size={28} />
            <p className="text-xs">Đang tải toàn bộ tài liệu PDF...</p>
          </div>
        )}

        {error && (
          <div className="pdf-error-state flex flex-col items-center justify-center p-8 text-rose-300 gap-2">
            <AlertCircle size={24} />
            <p className="text-xs">{error}</p>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="open-raw-link mt-2 text-white bg-slate-700 border-slate-600"
            >
              <ExternalLink size={13} /> Mở PDF trong tab mới
            </a>
          </div>
        )}

        <div
          className="pdf-page-container relative shadow-2xl bg-white rounded-sm"
          style={{ display: loading || error ? "none" : "inline-block" }}
        >
          <canvas ref={canvasRef} className="pdf-canvas block" />
          <div ref={textLayerRef} className="pdf-text-layer" />
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------
// IMAGE VIEWER COMPONENT (CLEAN HD, ONERROR FALLBACK & SCROLLABLE VIEWPORT)
// -------------------------------------------------------------
function ImageViewer({ url }: { url: string }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [imageZoom, setImageZoom] = useState(1.0);

  useEffect(() => {
    setLoading(true);
    setError(false);
    setImageZoom(1.0);
  }, [url]);

  return (
    <div className="image-viewer-wrapper flex flex-col w-full">
      <div className="image-toolbar flex items-center justify-between px-3 py-2 border-b bg-white">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <span>Hình ảnh tài liệu</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="tool-btn"
            onClick={() => setImageZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))))}
            title="Thu nhỏ ảnh"
          >
            <ZoomOut size={15} />
          </button>
          <span className="zoom-indicator text-xs font-semibold px-2">{Math.round(imageZoom * 100)}%</span>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setImageZoom((z) => Math.min(3.5, Number((z + 0.25).toFixed(2))))}
            title="Phóng to ảnh"
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setImageZoom(1.0)}
            title="Đặt lại 100%"
          >
            <RotateCcw size={13} />
          </button>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="tool-btn"
            title="Mở ảnh gốc trong tab mới"
          >
            <Maximize2 size={13} />
          </a>
        </div>
      </div>

      <div className="image-viewport p-4 flex justify-center items-start bg-slate-100 overflow-auto max-h-[600px] min-h-[380px]">
        {loading && !error && (
          <div className="image-loading flex flex-col items-center justify-center p-12 text-slate-500 gap-3">
            <LoaderCircle className="spin" size={24} />
            <p className="text-xs">Đang tải hình ảnh tài liệu...</p>
          </div>
        )}

        {error && (
          <div className="image-error-state flex flex-col items-center justify-center p-8 text-rose-600 gap-2">
            <AlertCircle size={24} />
            <p className="text-xs">Không thể tải hình ảnh tài liệu.</p>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="open-raw-link mt-2"
            >
              <ExternalLink size={13} /> Mở link ảnh trực tiếp
            </a>
          </div>
        )}

        {!error && (
          <div
            className="transition-transform duration-150 flex justify-center w-full"
            style={{
              transform: `scale(${imageZoom})`,
              transformOrigin: "top center",
              display: loading ? "none" : "flex",
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url}
              alt="Tài liệu đính kèm"
              className="document-image cursor-zoom-in"
              onClick={() => setImageZoom((z) => (z >= 2.0 ? 1.0 : Number((z + 0.5).toFixed(2))))}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false);
                setError(true);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}