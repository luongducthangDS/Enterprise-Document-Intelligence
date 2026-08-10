# scripts/rag_pipeline/

> CLI scripts cho luồng Data Ingestion → Chunking → Embedding → Vector DB → Eval
> (đọc thêm ở [`docs/rag-pipeline/`](../../docs/rag-pipeline/)). Chạy từ root project,
> vd: `python scripts/rag_pipeline/build_chunks.py --force`.

Script khác ở `scripts/` (setup môi trường, AI-log hook) là hạ tầng chung của cả team,
không thuộc phần này nên vẫn nằm ở `scripts/` gốc.

## Data pipeline (thứ tự chạy)

| Script | Việc gì |
|---|---|
| `collect_data.py` | Sinh policy doc synthetic + bộ câu hỏi eval qua GLM-5.2 (FPT.AI Marketplace) |
| `extract_documents.py` | Extract PDF/DOCX trong `data/raw/` → Markdown sạch trong `data/processed/` (pdfplumber cho text layer, VLM cho scan) |
| `verify_processed.py` | Gate kiểm tra `data/processed/` đủ nội dung (so mật độ ký tự/trang với PDF gốc) |
| `build_chunks.py` | Chunk `data/processed/*.md` → `data/chunks/*.json` |
| `build_vector_db.py` | Embed + index chunks vào Chroma Cloud (collection `hr_documents`) |
| `import_documents_to_supabase.py` | Đồng bộ `document_registry.csv` → bảng `documents` trên Supabase |

## Eval dataset & qrel

| Script | Việc gì |
|---|---|
| `backfill_eval_source_file.py` | Suy ra `source_file` cho từng câu eval từ `ground_truth_context` |
| `fix_eval_ground_truth.py` | Kiểm tra/sửa `ground_truth_context` chưa đúng nguyên văn |
| `shorten_eval_ground_truth.py` | Rút ngắn bằng chứng dài để dễ match |
| `build_retrieval_qrels.py` | Xây qrel chunk-level (deterministic string match, không dùng LLM) |
| `build_retrieval_eval_set.py` / `merge_judgments.py` / `remap_qrels.py` | Bộ 3 script cho qrel mở rộng bằng LLM-judge (pooling ứng viên → judge → merge → remap khi chunk đổi) |
| `make_human_review_sample.py` | Lấy mẫu ngẫu nhiên để review tay chất lượng judgment |
