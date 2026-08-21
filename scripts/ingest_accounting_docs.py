#!/usr/bin/env python3
"""Script nhập bộ tài liệu phòng Kế toán vào hệ thống RAG P-153.

Các bước thực hiện:
1. Đọc toàn bộ tài liệu thô từ data/data_accounting (PDF, DOCX, Ảnh PNG/JPG scan).
2. Xử lý trích xuất văn bản (Text-layer / VLM / DOCX) và áp dụng cơ chế Chunking chuẩn của dự án.
3. Tự động gắn Metadata chuẩn (category, authority, provenance, tenant, publication_status, v.v.).
4. Tính toán Vector Embedding bằng mô hình FPT.AI (multilingual-e5-large, 1024 dims).
5. Xuất kết quả:
   - JSON chứa Text, Metadata và Vector Embeddings tại: data/data_accounting/process/
   - Local ChromaDB Persistent Database tại: data/data_accounting/db_hr/
6. In ra console tổng số file đã đọc, tổng số chunk đã tạo và 2 đoạn chunk mẫu.
"""

import json
import os
import sys
import time
from pathlib import Path

# Thêm root workspace vào sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

# Thiết lập stdout UTF-8 cho Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import chromadb
from src.config import get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.cleaners import clean_document
from src.ingestion.embeddings import embed_texts
from src.ingestion.extractors.documents import (
    UnsupportedDocumentError,
    extract_docx,
    extract_pdf_text_layer,
    has_real_text_layer,
)
from src.ingestion.extractors.pdf_extractor import extract_pdf
from src.ingestion.extractors.pdf_vlm import extract_page_markdown
from src.ingestion.metadata import Chunk, date_to_ymd_int, NO_EXPIRY_SENTINEL


def extract_raw_document(file_path: Path, processed_dir: Path) -> tuple[str, str]:
    """Trích xuất nội dung file thô sang Markdown text."""
    ext = file_path.suffix.lower()
    stem = file_path.stem
    md_out_path = processed_dir / f"{stem}.md"

    # Tái sử dụng file markdown đã trích xuất trước đó nếu có
    if md_out_path.exists():
        with open(md_out_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        if existing_content.strip():
            return existing_content, "cached_markdown"

    # 1. File DOCX
    if ext in (".docx", ".doc"):
        text = extract_docx(str(file_path), str(md_out_path))
        return text, "docx"

    # 2. File PDF
    if ext == ".pdf":
        if has_real_text_layer(str(file_path)):
            text = extract_pdf_text_layer(str(file_path), str(md_out_path))
            return text, "pdf_text_layer"
        else:
            print(f"   [VLM] Đang OCR tài liệu scan qua mô hình Vision-Language...")
            extract_pdf(str(file_path), str(md_out_path), force=True)
            with open(md_out_path, "r", encoding="utf-8") as f:
                return f.read(), "pdf_vlm"

    # 3. File Hình ảnh (PNG / JPG / JPEG)
    if ext in (".png", ".jpg", ".jpeg"):
        print(f"   [VLM] Đang OCR ảnh chứng từ/hóa đơn qua Vision-Language...")
        with open(file_path, "rb") as img_f:
            img_bytes = img_f.read()
        page_md = extract_page_markdown(img_bytes)
        if page_md.strip().startswith("#"):
            full_text = page_md.strip()
        else:
            full_text = f"# {stem}\n\n{page_md}"
        with open(md_out_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        return full_text, "image_vlm"

    # 4. File Markdown có sẵn
    if ext == ".md":
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        with open(md_out_path, "w", encoding="utf-8") as f:
            f.write(text)
        return text, "markdown"

    raise UnsupportedDocumentError(f"Định dạng không được hỗ trợ: {ext}")


def detect_document_metadata(stem: str, text: str) -> dict:
    """Tự động phân tích ngữ cảnh để gán metadata phù hợp với phòng kế toán."""
    stem_lower = stem.lower()
    text_lower = text[:1500].lower()

    # Nhận diện Tenant
    tenant = "cong-ty-abc"
    if "nexatech" in stem_lower or "nexatech" in text_lower:
        tenant = "nexatech"

    # Phân loại chuyên mục trong Kế toán
    category = "accounting_finance"
    if "luong" in stem_lower or "kpi" in stem_lower or "hoa-hong" in stem_lower:
        category = "payroll_and_compensation"
    elif "tam-ung" in stem_lower or "thanh-toan" in stem_lower:
        category = "advance_and_payment_sop"
    elif "mua-sam" in stem_lower or "ncc" in stem_lower or "don-dat-hang" in stem_lower or "mua-hang" in stem_lower:
        category = "procurement_and_purchasing"
    elif "chi-tieu" in stem_lower or "duyet-chi" in stem_lower or "qtcp" in stem_lower:
        category = "internal_expense_policy"
    elif "tscd" in stem_lower or "tai-san" in stem_lower or "bbgn" in stem_lower:
        category = "fixed_assets_management"
    elif "hddt" in stem_lower or "hoa-don" in stem_lower:
        category = "invoices_and_tax"

    # Nhận diện mã hiệu văn bản / số hiệu nếu có
    doc_code = None
    if "qc-ltk" in stem_lower:
        doc_code = "QC-LTK-01"
    elif "po-" in stem_lower:
        doc_code = stem.split("_")[0]
    elif "pr-" in stem_lower:
        doc_code = stem.split("_")[0]
    elif "bc-qtcp" in stem_lower:
        doc_code = "BC-QTCP-Q3-2026"
    elif "hddt" in stem_lower:
        doc_code = "HDDT-00000089"
    elif "bbgn" in stem_lower:
        doc_code = "BBGN-01/2026"
    elif "dntt" in stem_lower or "de_nghi_thanh_toan" in stem_lower:
        doc_code = "ĐNTT-2026/08-015"
    elif "sop-tckt" in stem_lower:
        doc_code = "SOP-TCKT-01"
    elif "sop-ms" in stem_lower:
        doc_code = "SOP-MS-01"
    elif "13-qd-abc" in stem_lower or "13/qd-abc" in stem_lower or "chi-tieu-noi-bo" in stem_lower:
        doc_code = "13/QĐ-ABC"

    return {
        "tenant": tenant,
        "category": category,
        "document_code": doc_code,
        "owner": "Phòng Kế toán & Tài chính",
        "authority": "tenant_official_policy",
        "provenance": "customer_provided",
        "source_type": "official_policy",
        "is_official_policy": True,
        "publication_status": "active",
        "artifact_state": "frozen",
        "retrieval_enabled": True,
    }


def main():
    start_time = time.time()
    settings = get_settings()

    # Đường dẫn thư mục
    input_dir = WORKSPACE_ROOT / "data" / "data_accounting"
    process_dir = input_dir / "process"
    db_hr_dir = input_dir / "db_hr"

    process_dir.mkdir(parents=True, exist_ok=True)
    db_hr_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("🚀 TIẾN TRÌNH INGESTION BỘ TÀI LIỆU KẾ TOÁN VÀO HỆ THỐNG RAG P-153")
    print("=" * 80)
    print(f"📂 Thư mục đầu vào       : {input_dir}")
    print(f"📄 Thư mục xuất Process  : {process_dir}")
    print(f"🗄️  Thư mục Local ChromaDB: {db_hr_dir}")
    print(f"🧠 Embedding Model       : {settings.embedding_model} via {settings.fpt_base_url}")
    print("-" * 80)

    # 1. Tìm tất cả các file hợp lệ trong input_dir (bỏ qua các thư mục con process và db_hr)
    supported_exts = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".md"}
    raw_files = [
        f for f in sorted(input_dir.iterdir())
        if f.is_file() and f.suffix.lower() in supported_exts
    ]

    print(f"🔍 Tìm thấy {len(raw_files)} file tài liệu thô trong thư mục data_accounting.\n")

    all_chunks: list[Chunk] = []
    chunks_with_embeddings: list[dict] = []
    processed_files_count = 0

    # 2. Vòng lặp trích xuất & Chunking từng file
    for idx, file_path in enumerate(raw_files, start=1):
        print(f"[{idx}/{len(raw_files)}] Đang xử lý: {file_path.name} ({file_path.stat().st_size / 1024:.1f} KB)...")
        try:
            raw_text, method = extract_raw_document(file_path, process_dir)
            meta_info = detect_document_metadata(file_path.stem, raw_text)

            # Sử dụng hàm chunking chuẩn hóa của project
            doc_chunks = build_chunks_from_text(
                raw_text,
                source_file=file_path.name,
                category=meta_info["category"],
                source_type=meta_info["source_type"],
                is_official_policy=meta_info["is_official_policy"],
                authority=meta_info["authority"],
                provenance=meta_info["provenance"],
                tenant=meta_info["tenant"],
                publication_status=meta_info["publication_status"],
                artifact_state=meta_info["artifact_state"],
                retrieval_enabled=meta_info["retrieval_enabled"],
                expiry_date=NO_EXPIRY_SENTINEL,
                settings=settings,
            )

            # Cập nhật thêm document_code và owner
            for c in doc_chunks:
                c.metadata.document_code = meta_info["document_code"]
                c.metadata.owner = meta_info["owner"]

            all_chunks.extend(doc_chunks)
            processed_files_count += 1
            print(f"   -> Trích xuất thành công bằng phương thức [{method}], tạo ra {len(doc_chunks)} chunks.")

        except Exception as e:
            print(f"   ❌ Lỗi khi xử lý file {file_path.name}: {e}")

    print(f"\n✅ Hoàn tất trích xuất & chunking: Đã đọc {processed_files_count}/{len(raw_files)} files -> Tạo {len(all_chunks)} chunks.")

    if not all_chunks:
        print("⚠️ Không có chunk nào được tạo. Dừng tiến trình.")
        return

    # 3. Tính toán Vector Embeddings theo batch
    print("\n🔢 Đang tính toán Vector Embeddings qua FPT.AI Gateway...")
    embedding_texts = [c.embedding_text for c in all_chunks]
    
    embeddings = embed_texts(
        embedding_texts,
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        batch_size=settings.embedding_batch_size,
        log=lambda msg: print(f"   {msg}"),
    )

    for c, emb in zip(all_chunks, embeddings):
        c.metadata.embedding_model = settings.embedding_model
        chunk_dict = c.model_dump()
        chunk_dict["embedding"] = emb
        chunk_dict["embedding_dim"] = len(emb)
        chunks_with_embeddings.append(chunk_dict)

    # 4. Xuất kết quả ra file JSON tại folder data/data_accounting/process/
    json_out_path = process_dir / "accounting_chunks_with_embeddings.json"
    print(f"\n💾 Đang ghi file JSON kết quả tại: {json_out_path}...")
    with open(json_out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_documents": processed_files_count,
                "total_chunks": len(all_chunks),
                "embedding_model": settings.embedding_model,
                "vector_dimension": len(embeddings[0]) if embeddings else 0,
                "chunks": chunks_with_embeddings,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"   -> Đã lưu thành công file JSON ({json_out_path.stat().st_size / 1024 / 1024:.2f} MB).")

    # 5. Lưu vào Local ChromaDB PersistentClient tại data/data_accounting/db_hr/
    print(f"\n🗄️ Đang khởi tạo và lưu trữ vào Local ChromaDB tại: {db_hr_dir}...")
    chroma_client = chromadb.PersistentClient(path=str(db_hr_dir))
    
    # Xóa collection cũ nếu tồn tại để tránh rác từ các tên file cũ
    for c_name in ("accounting_documents", "hr_documents"):
        try:
            chroma_client.delete_collection(name=c_name)
        except Exception:
            pass

    # Tạo 2 collection aliases (accounting_documents và hr_documents) để tương thích tối đa
    collection_accounting = chroma_client.get_or_create_collection(
        name="accounting_documents", metadata={"hnsw:space": "cosine"}
    )
    collection_hr = chroma_client.get_or_create_collection(
        name="hr_documents", metadata={"hnsw:space": "cosine"}
    )

    ids = [c.metadata.chunk_id for c in all_chunks]
    documents = [c.text for c in all_chunks]
    metadatas = [c.metadata.to_chroma_metadata() for c in all_chunks]

    for col in (collection_accounting, collection_hr):
        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    print(f"   -> Đã lưu thành công {len(all_chunks)} vectors vào Local ChromaDB!")
    print(f"   -> Collection 'accounting_documents' count: {collection_accounting.count()}")
    print(f"   -> Collection 'hr_documents' count        : {collection_hr.count()}")

    # 6. In kết quả tổng kết và 2 đoạn chunk mẫu ra console
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO TỔNG KẾT XỬ LÝ (INGESTION REPORT)")
    print("=" * 80)
    print(f"• Tổng số file đã đọc  : {processed_files_count} files")
    print(f"• Tổng số chunk đã tạo : {len(all_chunks)} chunks")
    print(f"• Kích thước vector    : {len(embeddings[0]) if embeddings else 0} dimensions (Cosine Metric)")
    print(f"• Thời gian hoàn thành : {elapsed:.2f} giây")
    print(f"• File JSON đã lưu     : {json_out_path}")
    print(f"• Local Chroma DB lưu  : {db_hr_dir}")
    print("=" * 80)

    # In 2 đoạn chunk mẫu
    sample_indices = [0, len(all_chunks) // 2] if len(all_chunks) >= 2 else [0]
    print("\n🎯 HIỂN THỊ 2 ĐOẠN CHUNK MẪU ĐƯỢC GẮN METADATA CHUẨN:")
    print("-" * 80)

    for i, s_idx in enumerate(sample_indices, start=1):
        s_chunk = all_chunks[s_idx]
        s_meta = s_chunk.metadata
        print(f"\n🔹 [CHUNK MẪU {i} / 2] (ID: {s_meta.chunk_id})")
        print(f"   • Tiêu đề (Title)          : {s_meta.title}")
        print(f"   • Nguồn file (Source File) : {s_meta.source_file}")
        print(f"   • Phân mục (Category)      : {s_meta.category}")
        print(f"   • Quyền hạn (Authority)    : {s_meta.authority}")
        print(f"   • Xuất xứ (Provenance)     : {s_meta.provenance}")
        print(f"   • Đơn vị (Tenant)          : {s_meta.tenant}")
        print(f"   • Đường dẫn mục (Heading)  : {s_meta.heading_path or '(Cấp tài liệu gốc)'}")
        print(f"   • Trang (Page Start-End)   : {s_meta.page_start} -> {s_meta.page_end}")
        print(f"   • Độ dài ký tự (Chars)     : {s_meta.char_count} ký tự")
        print(f"   • Model Embedding          : {s_meta.embedding_model} (1024 dims)")
        print(f"   • Nội dung trích dẫn (Text Snippet):")
        
        # In tối đa 4 dòng snippet
        snippet_lines = s_chunk.text.strip().splitlines()
        for line in snippet_lines[:6]:
            print(f"       | {line}")
        if len(snippet_lines) > 6:
            print(f"       | ... (còn {len(snippet_lines) - 6} dòng)")
        print("-" * 80)

    print("\n🎉 Hoàn thành xuất sắc toàn bộ quy trình Ingestion tài liệu Kế toán!")


if __name__ == "__main__":
    main()
