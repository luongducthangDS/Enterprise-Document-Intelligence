# Folder Structure — Data Ingestion Pipeline

> Cấu trúc thư mục cho pipeline xử lý tài liệu (extract → clean → chunk → embed → index) và vị trí của nó trong project. Bản cập nhật sau review — đã xử lý 4 điểm tồn đọng ở cuối file.

```
P-153/
├── src/
│   ├── agents/                     # (đã có) LangGraph agent
│   ├── api/                        # (đã có) FastAPI routes
│   ├── models/                     # (đã có) Pydantic schemas
│   ├── services/                   # (đã có) LLM client, v.v. — embeddings gọi qua đây, không tạo client riêng
│   ├── ingestion/                  # MỚI — pipeline xử lý tài liệu
│   │   ├── __init__.py
│   │   ├── extractors/             # Đọc PDF, DOCX, XLSX, OCR (kế thừa logic extract.py + pdf_vlm_utils.py)
│   │   ├── cleaners.py             # Làm sạch văn bản
│   │   ├── chunkers.py             # Chia tài liệu thành chunk
│   │   ├── metadata.py             # Chuẩn hoá metadata (nguồn, ngày ban hành, loại văn bản...)
│   │   ├── embeddings.py           # Tạo embedding — gọi src/services/llm.py
│   │   └── indexer.py              # Đưa dữ liệu vào Vector DB
│   ├── config.py                   # (đã có)
│   └── main.py                     # (đã có)
│
├── data/                           # gitignored toàn bộ nội dung (trừ document_registry.csv nếu cần track)
│   ├── raw/                        # Tài liệu gốc, không chỉnh sửa
│   │   ├── company_regulations/    # Quy định nội bộ chung (VinFast, văn hoá, lương/thưởng tổng quát)
│   │   ├── government_legal/       # Luật lao động, BHXH, an toàn lao động, nghị định — nguồn thẩm quyền cao nhất
│   │   ├── recruitment_policies/   # Quy trình tuyển dụng (Vingroup, Base.vn)
│   │   ├── onboarding_offboarding/ # Chính sách onboarding/offboarding
│   │   ├── leave_policies/         # Chính sách nghỉ phép
│   │   └── compensation_policies/  # Lương, thưởng, OT
│   ├── processed/                  # Văn bản đã extract + làm sạch (gộp 2 bước, không tách "extracted/" riêng)
│   ├── chunks/                     # Các chunk chuẩn bị tạo embedding
│   ├── metadata/
│   │   └── document_registry.csv   # Lineage: file gốc → processed → chunk → trạng thái index
│   └── rejected/                   # File lỗi, trùng, không hợp lệ (vd: 798377906-CHƯƠNG-1.pdf — lạc đề, đã loại)
│
├── scripts/                        # CLI mỏng, gọi vào src/ingestion/*
│   ├── collect_data.py             # Thu thập/tải dữ liệu
│   ├── extract_documents.py
│   ├── build_chunks.py
│   └── build_vector_db.py
│
├── storage/                        # gitignored — Vector DB local (Chroma), tạo ở bước build_vector_db
│   └── vector_db/
│
├── eval/
│   ├── datasets/                   # Câu hỏi và đáp án đánh giá
│   └── scripts/
└── ...
```

## Đã xử lý so với đề xuất ban đầu

| # | Vấn đề | Fix |
|---|--------|-----|
| 1 | `agent/` (số ít) và `core/` mới không khớp `src/` hiện tại (`agents/`, `services/`, `config.py`) | Bỏ `core/`, giữ nguyên `agents/`, `services/`, `config.py` sẵn có; chỉ thêm `ingestion/` như package mới |
| 2 | Taxonomy `raw/` thiếu category cho văn bản pháp luật và tuyển dụng — không khớp dữ liệu thật đã kiểm tra | Thêm `government_legal/`, `recruitment_policies/`, `onboarding_offboarding/` |
| 3 | `storage/vector_db/` chưa có trong `.gitignore` | Đã thêm `storage/` vào `.gitignore` |
| 4 | 3 tầng đĩa `extracted/ → processed/ → chunks/` hơi nặng cho quy mô ~15-20 tài liệu | Gộp `extracted/` vào `processed/` (khớp với cách `extract.py` hiện tại đã làm — extract và clean trong 1 bước) |

## Ghi chú

- `document_registry.csv` nằm trong `data/` nên đang bị `.gitignore` chặn theo rule `data/`. Nếu muốn track lineage qua git (khuyến nghị, vì file nhỏ và hữu ích để review), cần thêm exception: `!data/metadata/document_registry.csv`.
- Đây là tài liệu thiết kế — chưa scaffold thư mục/file thật. Khi bắt đầu implement ingestion pipeline, tạo `src/ingestion/` theo cấu trúc trên.
