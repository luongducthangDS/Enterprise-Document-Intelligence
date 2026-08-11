# 🚀 Kiến trúc Pipeline Chi Tiết (P-153) — HR Document Intelligence Agent

Tài liệu này mô tả **toàn bộ hành trình** từ dữ liệu thô đến agent RAG có thể trả lời câu hỏi HR, gồm 4 phần: (0) Toàn cảnh, (1) Thu thập & quản trị dữ liệu thô, (2) Data Ingestion Pipeline, (3) Agentic RAG Pipeline, (4) Evaluation Pipeline. Mỗi phần ghi rõ **quyết định thiết kế** và **con số đo được thật** (không phải ước lượng), lấy trực tiếp từ code hiện tại (`src/`, `scripts/rag_pipeline/`, `eval/`) và `eval/results/report.md` — cập nhật lần cuối theo trạng thái ngày 2026-08-07.

---

## 0. Toàn cảnh

```mermaid
flowchart LR
    classDef raw fill:#E1F5FE,stroke:#01579B,stroke-width:2px,color:#01579B
    classDef ingest fill:#E8F5E9,stroke:#1B5E20,stroke-width:2px,color:#1B5E20
    classDef store fill:#FCE4EC,stroke:#880E4F,stroke-width:2px,color:#880E4F
    classDef agent fill:#F3E5F5,stroke:#4A148C,stroke-width:2px,color:#4A148C
    classDef eval fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#E65100

    Raw["📄 31 tài liệu thô\n(luật, quy chế, template, synthetic)"]:::raw
    Ingest["⚙️ Ingestion\nExtract → Clean → Chunk → Embed"]:::ingest
    Vec[("🗄️ Chroma Cloud\n1498 chunk / 28 tài liệu")]:::store
    Sup[("🗃️ Supabase\nuser/chat/ticket/document")]:::store
    Agent["🤖 LangGraph Agent\n12 node, 4 nhánh intent"]:::agent
    Eval["📊 Eval Pipeline\nqrel + router + retrieval + agent"]:::eval
    User(("👤 Nhân viên / HR Admin"))

    Raw --> Ingest --> Vec
    Vec --> Agent
    Sup -. "RBAC / lịch sử chat / ticket (backend, chưa nối)" .-> Agent
    User --> Agent --> User
    Vec -.-> Eval
    Agent -.-> Eval
```

Ba mảnh hạ tầng độc lập: **Chroma Cloud** (vector, dùng chung team + sống được trên Render — free/standard tier không có persistent disk nên không thể dùng ChromaDB local), **Supabase** (Postgres — user/RBAC/chat history/ticket/document metadata, RLS bật, do backend team tích hợp), **FPT.AI Marketplace** (gateway LLM/VLM/embedding/rerank, `base_url=https://mkp-api.fptcloud.com`).

---

## 1. Thu thập & Quản trị Dữ liệu Thô (Data Curation)

### 1.1 Bức tranh tổng thể

`data/metadata/document_registry.csv` — **31 dòng**, là "database trạng thái" điều phối toàn bộ pipeline (không có bảng SQL nào giữ vai trò này, cố ý dùng CSV để dễ diff/review qua git). (Từng có 33 dòng — đã dọn bỏ 2 dòng vô giá trị/hết hiệu lực, xem ghi chú cuối 1.5: file luật sai `73-cp.signed...pdf` và file template rỗng `amis_mau-thong-bao-quy-dinh-nghi-phep.docx`, cả raw file lẫn vector trên Chroma Cloud.)

| Theo `category` | Số file | | Theo `source_type` | Số file |
|---|---|---|---|---|
| `government_legal` | 10 | | `government_law` | 10 |
| `company_regulations` | 7 | | `public_template` | 6 |
| `compensation_policies` | 4 | | `synthetic` | 8 |
| `recruitment_policies` | 3 | | `official_policy` | 2 |
| `onboarding_offboarding` | 3 | | `eval_asset` | 2 |
| `leave_policies` | 1 | | `public_article` | 1 |
| `eval_dataset` / `config` | 3 | | `config` | 1 |

`status`: 30 `processed`, 1 `n/a` (file config). 28/30 file `processed` đủ điều kiện đưa vào RAG (`rag_eligible_rows()` trong `src/ingestion/metadata.py` loại `eval_asset`/`config`).

### 1.2 Hành trình thu thập theo từng nhóm

1. **Luật/nghị định sẵn có trong export Google Drive ban đầu** (`Tài liệu T153-...zip`) — bộ luật lao động, luật BHXH 41/2024, luật an toàn vệ sinh lao động 84/2015, NĐ 293/2025 (lương tối thiểu vùng), NĐ 158/2025 (BHXH bắt buộc), NĐ 145/2020, quy định nội bộ VinFast, quy trình tuyển dụng Vingroup.
2. **Luật bổ sung** (phát hiện thiếu qua khảo sát: chưa có Luật BHYT, Luật Thuế TNCN — 2 chủ đề nhân viên hay hỏi nhất): tự tải được bản Luật Thuế TNCN hợp nhất (CDN chính phủ). Luật BHYT sửa đổi 51/2024, NĐ 161/2026 (lương cơ sở mới), TT 60/2025/TT-BYT — `vbpl.vn`/`thuvienphapluat.vn` chặn bot (403/JS-rendered), phải nhờ người dùng tải thủ công rồi **verify lại nội dung thật** trước khi nhận (đọc text layer hoặc render ảnh trang, không tin tên file) — phát hiện 1 file `73-cp.signed.pdf` sai hoàn toàn (Nghị định 73/2024 đã hết hiệu lực, không phải NĐ 161/2026 cần tìm). Ban đầu chuyển sang `data/rejected/` để giữ làm bằng chứng, sau đó **đã xoá hẳn** (raw file cục bộ) khi rà soát lại thấy không còn lý do giữ file luật hết hiệu lực trong kho.
3. **Template công khai generic** (quyết định chiến lược: sản phẩm phục vụ phòng HR nói chung, không gắn 1 công ty cụ thể) — nội quy lao động mẫu "CÔNG TY ABC" (leanh.edu.vn), quy chế công tác phí, quy chế lương thưởng (Base.vn), quy trình chấm dứt HĐLĐ (Talentnet, scrape trực tiếp bài viết). Một file (`amis_mau-thong-bao-quy-dinh-nghi-phep.docx`) hoá ra **rỗng thật** (chỉ có `………` để điền) dù trang web bao quanh có nội dung — bài học: luôn mở file thật, không tin nội dung trang giới thiệu. File này vẫn từng bị chunk/index nhầm vào Chroma Cloud (2 chunk vô giá trị) trước khi bị phát hiện và dọn — xem 1.5.
4. **Synthetic sinh bằng GLM-5.2** (qua FPT.AI Marketplace) cho các khoảng trống không tìm được nguồn công khai đạt chất lượng: chính sách WFH/hybrid, đào tạo & phát triển, nghỉ phép có số liệu cụ thể, bảo hiểm sức khỏe tự nguyện, quy chế KPI, quy chế bồi hoàn đào tạo, quy trình kỷ luật — 8 file, luôn gắn `source_type=synthetic` để agent không trích dẫn nhầm là quy định thật.

### 1.3 Sự cố chất lượng đã phát hiện & sửa (bài học quan trọng nhất của giai đoạn này)

**Lỗi "biên soạn thay vì trích xuất"**: một lượt xử lý PDF scan ban đầu yêu cầu LLM *"viết lại nội dung văn bản chuẩn"* một lần cho cả file, thay vì OCR/VLM từng trang. Phát hiện qua đối chiếu số trang gốc với độ dài `.md`: Nghị định 145/2020 (122 trang) chỉ ra 4.6KB/5 điều; `thong-tu-60...md` tự liệt kê "35 bệnh nghề nghiệp" nhưng chỉ đếm được 31 rồi viết "...cùng các bệnh khác theo quy định" — dấu hiệu rõ nhất của nội dung bị **bịa theo trí nhớ**, không phải chỉ thiếu. 6 file bị ảnh hưởng, đã extract lại đúng cách (VLM đọc ảnh từng trang thật) — kết quả tăng từ 3-4KB lên 15K-240K ký tự/file, verify số liệu khớp bản gốc (vd đủ 35/35 bệnh nghề nghiệp, đủ phụ lục vùng lương tối thiểu I-IV).

**Hệ quả trực tiếp lên code**: `src/ingestion/extractors/pdf_extractor.py`/`pdf_vlm.py` từ đó **tuyệt đối không cho phép** gọi 1 lệnh LLM cho cả file — mỗi trang PDF scan phải được model *nhìn thấy ảnh thật* và trích xuất riêng (xem 2.2).

### 1.4 Metadata governance

Mỗi dòng registry mang 3 cột quyết định agent có được trích dẫn hay không: `source_type` (8 giá trị, bảng 1.1), `is_official_policy` (bool), `caveat` (text tự do, vd "ban hành 2019, cần xác nhận bản cập nhật"). 3 cột này được copy nguyên vào **metadata của từng chunk** trong Chroma (`ChunkMetadata` — xem 2.4) và dùng trực tiếp trong prompt sinh câu trả lời (`generate_node`, xem 3.5) để agent tự cảnh báo khi nguồn chỉ là template/synthetic.

### 1.5 Danh sách chi tiết từng tài liệu nguồn

Toàn bộ 31 dòng của `data/metadata/document_registry.csv`, nhóm theo `category`. 28 dòng đầu là nguồn RAG-eligible (`status=processed`, `source_type` không thuộc `eval_asset`/`config`); 3 dòng cuối không phải nguồn RAG. (2 file vô giá trị/hết hiệu lực — `73-cp.signed...pdf` và `amis_mau-thong-bao-quy-dinh-nghi-phep.docx` — đã bị xoá hoàn toàn khỏi registry, `data/raw|processed|chunks` và Chroma Cloud, không còn liệt kê ở đây nữa.)

#### `government_legal` — 10 file (văn bản pháp luật, `is_official_policy=true`)

| File | Đặc điểm |
|---|---|
| `bộ luật lao động.pdf` | Bộ luật Lao động 45/2019/QH14, hiệu lực 01/01/2021. Có text layer sẵn, đọc trực tiếp pdfplumber (2674 dòng, không qua VLM). |
| `luat_bao_hiem_xa_hoi_41_2024_qh15.pdf` | Luật BHXH 41/2024. Có text layer sẵn (260KB). |
| `luat51.pdf` | Luật 51/2024/QH15 sửa đổi Luật BHYT, hiệu lực 01/07/2025. Có text layer sẵn (71KB). |
| `luat_an_toan_ve_sinh_lao_dong_84_2015_qh13.pdf` | Luật ATVSLĐ 84/2015. Dạng scan — đã extract lại qua VLM từng trang (59 trang). |
| `112-vbhn-vpqh_luat_thue_tncn.pdf` | Luật Thuế TNCN (bản hợp nhất). Dạng scan — VLM 16 trang. |
| `thong-tu-60-2025-TT-BHYT-2026.pdf` | TT 60/2025/TT-BYT (danh mục bệnh nghề nghiệp). Dạng scan — VLM 7 trang, đã xác nhận đủ 35/35 bệnh. |
| `161-ndcp.signed.pdf` | NĐ 161/2026/NĐ-CP (lương cơ sở mới). Dạng scan — VLM 7 trang, khớp ảnh gốc. |
| `nghi_dinh_293_2025_nd_cp_luong_toi_thieu.pdf` | NĐ 293/2025 (lương tối thiểu vùng). Dạng scan — VLM 14 trang, đủ phụ lục Vùng I-IV. |
| `nghi_dinh_158_2025_nd_cp_bhxh_bat_buoc.pdf` | NĐ 158/2025 (BHXH bắt buộc). Dạng scan — VLM 52 trang. |
| `nghi_dinh_145_2020_nd_cp.pdf` | NĐ 145/2020 (hướng dẫn Bộ luật Lao động). Dạng scan — VLM 122 trang, file lớn nhất kho. |

*(6 file scan phía trên từng bị 1 lượt xử lý lỗi "biên soạn lại theo trí nhớ" làm thiếu/bịa nội dung — xem 1.3 — đã extract lại đúng cách qua VLM từng trang, verify khớp bản gốc.)*

#### `company_regulations` — 7 file

| File | `source_type` | Đặc điểm |
|---|---|---|
| `1050517962-...VinFast-08-08-2019.pdf` | `official_policy` (thật) | Quy định nội bộ VinFast, ban hành 2019 (V5). ⚠️ Cần xác nhận có bản cập nhật 2024-2026 hay chưa. |
| `leanh_mau-noi-quy-lao-dong.docx` | `public_template` | Nội quy lao động mẫu, dùng placeholder "CÔNG TY ABC" — không phải chính sách công ty thật. |
| `05_chinh-sach-lam-viec-tu-xa.md` | `synthetic` | Sinh bằng GLM-5.2, công ty giả định V-NOVA. |
| `06_chinh-sach-dao-tao-phat-trien.md` | `synthetic` | Sinh bằng GLM-5.2, công ty giả định V-NOVA. |
| `mau_quy-che-danh-gia-hieu-suat-kpi.md` | `public_template` | Tự soạn "mẫu quy chế quản trị nội bộ công khai tham khảo". |
| `mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md` | `public_template` | Tương tự — mẫu tham khảo. |
| `mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai.md` | `public_template` | Tương tự — mẫu tham khảo. |

#### `compensation_policies` — 4 file

| File | `source_type` | Đặc điểm |
|---|---|---|
| `01_chinh-sach-lam-them-gio-OT.md` | `synthetic` | Công ty giả định V-NOVA. |
| `08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md` | `synthetic` | Công ty giả định V-NOVA, cấu trúc tham khảo PVI Care thật. |
| `base_mau-quy-che-luong-thuong-phu-cap-xu-phat.docx` | `public_template` | Template Base.vn công khai, không có số liệu cụ thể. |
| `base_quy-che-cong-tac-phi-va-phu-cap.md` | `public_template` | Tự soạn mẫu tham khảo (định mức công tác phí theo vùng). |

#### `recruitment_policies` — 3 file

| File | `source_type` | Đặc điểm |
|---|---|---|
| `842059170-...Vingroup.pdf` | `official_policy` (thật) | Quy trình tuyển dụng chung Vingroup. ⚠️ Không rõ ngày ban hành trong văn bản gốc — cần xác minh thời hiệu. |
| `02_quy-trinh-tuyen-dung.md` | `synthetic` | Công ty giả định V-NOVA. |
| `[Base.vn] Mẫu sơ đồ quy trình tuyển dụng nhân sự.docx.pdf` | `public_template` | ⚠️ File gần như rỗng (chỉ có bảng tiêu đề) — giá trị RAG rất thấp. |

#### `onboarding_offboarding` — 3 file

| File | `source_type` | Đặc điểm |
|---|---|---|
| `03_quy-trinh-onboarding.md` | `synthetic` | Công ty giả định V-NOVA. |
| `04_quy-trinh-offboarding.md` | `synthetic` | Công ty giả định V-NOVA. |
| `talentnet_quy-trinh-cham-dut-hop-dong-lao-dong.md` | `public_article` | Bài viết nghiệp vụ tham khảo (Talentnet), không phải luật/chính sách gốc. |

#### `leave_policies` — 1 file

| File | `source_type` | Đặc điểm |
|---|---|---|
| `07_chinh-sach-nghi-phep.md` | `synthetic` | Công ty giả định V-NOVA. Nguồn duy nhất của category này sau khi xoá `amis_mau-thong-bao-quy-dinh-nghi-phep.docx` (file rỗng — chỉ có chỗ trống để điền, xem 1.2 điểm 3). |

#### Không phải nguồn RAG (`eval_dataset` / `config`)

| File | Vai trò |
|---|---|
| `qa_eval_set.json`, `mock_user_personas.json` | Tài sản eval (bộ câu hỏi-đáp, persona test), không index vào vector DB. |
| `ticket_routing_rules.json` | Config logic routing ticket, agent đọc trực tiếp, không chunk. |

**Tóm tắt**: 10/28 file RAG-eligible là văn bản pháp luật thật (`government_law`), 2/28 là chính sách nội bộ thật (VinFast, Vingroup — cả 2 đều có caveat về ngày ban hành/thời hiệu chưa xác minh), còn lại 16/28 là **template công khai hoặc synthetic** — không phải chính sách của một công ty thật nào, cố ý gắn nhãn rõ trong metadata (`is_official_policy=false`) để agent tự cảnh báo khi trích dẫn.

---

## 2. Data Ingestion Pipeline

```mermaid
flowchart TD
    classDef file fill:#E1F5FE,stroke:#01579B,stroke-width:2px,color:#01579B
    classDef process fill:#E8F5E9,stroke:#1B5E20,stroke-width:2px,color:#1B5E20
    classDef db fill:#FCE4EC,stroke:#880E4F,stroke-width:2px,color:#880E4F
    classDef csv fill:#FFF9C4,stroke:#F57F17,stroke-width:2px,color:#F57F17,stroke-dasharray: 5 5

    Raw["📄 Tài liệu thô\nPDF / DOCX / MD"]:::file
    Decide{"📶 PDF: >=50% số trang\ncó >=200 ký tự text layer?"}:::process
    TextLayer["📑 pdfplumber\nđọc trực tiếp"]:::process
    VLM["🧠 VLM Qwen2.5-VL-7B\ntừng trang ảnh (200 DPI)"]:::process
    TableFix["🔧 pdfplumber bảng +\nforward-fill ô merge + nối bảng liên trang"]:::process
    DocProcess["📝 Markdown\ndata/processed/"]:::file
    Clean{"🧹 Cleaning\nstrip frontmatter, page_offsets,\nbỏ header lặp/bảng rỗng hallucinate"}:::process
    Chunking{"✂️ Hybrid Chunking\nstructure-based hoặc fallback overlap"}:::process
    Chunks["🧩 Chunks JSON\ndata/chunks/ — 1500 chunk / 29 doc"]:::file
    Embed{"🧠 multilingual-e5-large\nprefix passage:/query:"}:::process
    VectorDB[("🗄️ Chroma Cloud\ncosine, collection hr_documents")]:::db
    State[("📊 document_registry.csv")]:::csv

    Raw --> Decide
    Decide -->|"Có text layer"| TextLayer
    Decide -->|"Scan"| VLM
    VLM --> TableFix
    TextLayer --> DocProcess
    TableFix --> DocProcess
    DocProcess --> Clean --> Chunking --> Chunks --> Embed --> VectorDB

    State -. "status/processed_path" .- DocProcess
    State -. "chunks_path" .- Chunks
    State -. "indexed_at" .- VectorDB
```

### 2.1 Document Registry — điều phối resumable

`load_registry()`/`rag_eligible_rows()`/`update_registry_column()` (`src/ingestion/metadata.py`). Ghi cột an toàn theo pattern: đọc toàn bộ → sửa 1 dòng → ghi ra `.tmp` → verify đọc lại đủ số dòng → `os.replace()` — tránh crash-giữa-chừng làm hỏng file (đã xảy ra thật 1 lần trong quá trình phát triển). Mọi script (`extract_documents.py`, `build_chunks.py`, `build_vector_db.py`) đều tự bỏ qua file đã có output trừ khi `--force`/`--only`, nên pipeline chạy lại an toàn (idempotent).

### 2.2 Extraction (`scripts/rag_pipeline/extract_documents.py`, `src/ingestion/extractors/`)

Quyết định theo loại file, **không có nhánh nào gọi LLM 1 lần cho cả tài liệu**:

- **PDF có text layer thật** — `has_real_text_layer()`: coi là "có text layer" nếu ≥50% số trang đọc được ≥200 ký tự qua `pdfplumber`. Nếu đạt, đọc trực tiếp bằng `pdfplumber`, không tốn API call, không có rủi ro bịa nội dung.
- **PDF dạng scan** — mỗi trang render thành ảnh PNG 200 DPI (`PyMuPDF`/`fitz`), gửi qua VLM `Qwen2.5-VL-7B-Instruct` (FPT.AI Marketplace) với prompt yêu cầu giữ nguyên heading/danh sách/bảng Markdown, forward-fill ô bị merge. Song song, `pdfplumber.find_tables()` tự trích bảng từ chính PDF (chính xác hơn VLM khi bảng có ô merge phức tạp) rồi **thay thế** khối bảng VLM đọc được bằng bảng pdfplumber nếu nội dung khớp (`_substitute_tables`) — kết hợp điểm mạnh của cả 2: VLM đọc bố cục/heading tốt, pdfplumber đọc số liệu bảng chính xác.
- **Sửa bảng sau khi trích** (`repair_tables`): forward-fill ô merge còn sót + nối các khối bảng cùng số cột bị PDF tách qua ranh giới trang (chỉ nối nếu đoạn giữa 2 khối chỉ có marker trang, không có nội dung khác chen vào).
- **DOCX** — `python-docx`, lấy toàn bộ paragraph + table (nối bằng ` | `).
- **MD trong `data/raw/`** — copy thẳng, không xử lý gì thêm (đã sạch từ nguồn synthetic/scrape).

### 2.3 Cleaning (`src/ingestion/cleaners.py`)

Một lượt duyệt theo dòng (`extract_page_map`), làm mọi chuẩn hoá **trong cùng 1 pass** để `page_offsets` (bản đồ ký tự ↔ số trang, phục vụ trích dẫn "trang N" sau này) luôn khớp với text cuối cùng — không có bước xử lý nào chạy sau làm lệch offset:

- Tách frontmatter YAML (chỉ có ở file synthetic/talentnet).
- Bỏ marker `<!-- page N -->` (ghi lại offset tương ứng), dòng phân cách `---`, fence `` ``` `` trơ trọi sót lại từ VLM.
- Bỏ số trang trơ trọi ngay sau ranh giới trang (rác OCR), bỏ header "CÔNG BÁO/Số..." lặp lại trên mọi trang của các văn bản Công báo (`luat51`, `luat_bao_hiem_xa_hoi`...).
- **Bỏ đoạn dài toàn dòng bảng markdown rỗng** (`|  |  |` × hàng trăm dòng) — VLM đôi khi hallucinate 1 "bảng" trên trang gần trắng (vd trang chữ ký cuối văn bản); phát hiện được qua 2 file thật (`112-vbhn-vpqh_luat_thue_tncn`, `luat_an_toan_ve_sinh_lao_dong`) từng làm phình 1 chunk lên hàng chục nghìn ký tự trước khi fix.

### 2.4 Chunking hybrid (`src/ingestion/chunkers.py`)

**Ưu tiên tách theo cấu trúc văn bản** — corpus không đồng nhất: 2 văn bản luật lớn nhất (bộ luật lao động, luật BHXH) hoàn toàn không có markdown heading, chỉ có dòng "Điều N." dạng text thường; một số quy chế công ty (VinFast, mẫu quy chế lương thưởng) đánh mục lớn bằng số La Mã đứng riêng ("I. TUYÊN NGÔN...") không có `#`. `classify_line()` nhận diện `Chương/Mục/Điều` **bất kể có `#` hay không**, và số La Mã đứng riêng (`I.`-`XX.`) làm ranh giới `chapter` mới — nhưng **không** lỏng điều kiện cho khoản đánh số kiểu `"1. Người lao động..."` (chỉ nhận khi có `#`), vì mẫu này trùng với khoản liệt kê thường nằm ngay trong thân 1 Điều, sẽ băm nát cấu trúc Chương/Điều nếu bắt nhầm.

Sau khi tách: gộp đoạn quá nhỏ (tiêu đề/letterhead không có nội dung riêng) vào đoạn liền kề cùng Chương, rồi force-split đoạn quá lớn (>1500 ký tự) theo đoạn văn → câu (`_force_split_oversized`, giữ offset thật, không rebuild text).

**Fallback cố định + overlap** cho tài liệu không đủ cấu trúc (Vingroup tuyển dụng, Base.vn mẫu sơ đồ, talentnet) — chunk theo đoạn văn, mục tiêu 1200 ký tự (max 1500, min 200), overlap 12%. Điểm quan trọng: `_word_boundary_tail()` dịch điểm cắt overlap tới khoảng trắng gần nhất thay vì cắt cứng theo số ký tự — tránh bug đã từng xảy ra thật (cắt vỡ giữa 1 từ tiếng Việt có dấu, tạo overlap kiểu `"ời Việt"` thay vì `"người Việt"`, từng lọt vào ~65 chunk production trước khi phát hiện qua audit thủ công).

**Metadata mỗi chunk** (`ChunkMetadata`): `chunk_id` (`<stem>::<0000>`), `source_file`/`category`/`source_type`/`is_official_policy`/`caveat` (kế thừa từ registry), `heading_path`/`chapter`/`article`, `page_start`/`page_end` (tra qua `page_offsets`), `char_count`. **Breadcrumb**: mỗi chunk khi embed được ghép `title — heading_path` phía trước nội dung (vd `"Bộ luật Lao động 2019 — Chương II > Điều 5"`) — giữ đủ ngữ cảnh kể cả khi chunk đứng độc lập.

Kết quả hiện tại: **1498 chunk từ 28 tài liệu** (`data/chunks/*.json`), min/max chưa vượt `chunk_max_chars=1500`.

### 2.5 Embedding

**Chọn model bằng thực nghiệm, không đoán**: index thử 1379 chunk (số liệu tại thời điểm test, trước các fix chunking sau này) vào 2 collection tạm với `Vietnamese_Embedding` và `multilingual-e5-large`, đo Hit Rate@5 trên `ground_truth_context` của 30 câu in-scope đầu tiên — `Vietnamese_Embedding` 83.33% (25/30) vs `multilingual-e5-large` **90.00% (27/30)**, dù giả định ban đầu là model chuyên tiếng Việt sẽ thắng trên corpus 100% tiếng Việt. `multilingual-e5-large` được chọn làm mặc định.

**E5 prefix convention**: `"passage: "` trước mọi chunk lúc index (`embedding_text` trong `build_chunks.py`), `"query: "` trước câu hỏi lúc retrieve (`retrieval_node._aembed_query`) — đúng convention gốc của họ model E5, cải thiện thêm hit-rate so với không có prefix.

Gọi qua `embed_batch()` (`src/services/fpt_client.py`) — endpoint `/embeddings` OpenAI-compatible trên FPT.AI Marketplace, batch 32, sắp xếp lại theo `index` trả về (API có thể trả không đúng thứ tự khi xử lý batch).

### 2.6 Vector Store

`chromadb.CloudClient` (production) hoặc `PersistentClient` local (chỉ dev/test — **không dùng được trên Render** vì free/standard tier không có persistent disk, container mất dữ liệu mỗi lần redeploy). Collection `hr_documents`, `hnsw:space="cosine"` (đổi từ L2 mặc định). Không dùng `embedding_function` của Chroma — embedding luôn tính thủ công qua `src/ingestion/embeddings.py` rồi truyền trực tiếp, để Chroma không phụ thuộc hiểu đúng response shape của FPT.AI Marketplace. `delete_by_source_stem()` chạy trước mỗi lần upsert để tránh chunk mồ côi khi re-chunk làm lệch `chunk_index` so với lần index trước.

---

## 3. Agentic RAG Pipeline

```mermaid
flowchart TD
    classDef user fill:#E1F5FE,stroke:#01579B,stroke-width:2px,color:#01579B
    classDef router fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#E65100
    classDef action fill:#E8F5E9,stroke:#1B5E20,stroke-width:2px,color:#1B5E20
    classDef retrieve fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#3F51B5
    classDef check fill:#FFF9C4,stroke:#F57F17,stroke-width:2px,color:#F57F17
    classDef generate fill:#F3E5F5,stroke:#4A148C,stroke-width:2px,color:#4A148C
    classDef stop fill:#FFEBEE,stroke:#B71C1C,stroke-width:2px,color:#B71C1C

    User(("👤 User Query\n+ history (nếu multi-turn)")):::user
    Condense["🧵 condense\nkhông có history: bỏ qua (0 chi phí)\ncó history: viết lại thành câu hỏi\nđộc lập, temp=0.0"]:::action

    Router{"🚦 router\nDeepSeek-V4-Flash\ngreeting|hr_question|ambiguous|out_of_scope_or_personal"}:::router

    Retrieve["🔍 retrieve\ndense (Chroma) [+ BM25 RRF nếu bật]\n+ cross-encoder rerank (bge-reranker-v2-m3)"]:::retrieve
    Grade{"⚖️ grade\nscore>=0.05 (rerank) hoặc\ndistance<=0.18 (fallback)"}:::check
    Rewrite["✍️ rewrite\nLLM viết lại câu hỏi (tối đa 1 lần)"]:::action

    Generate["✨ generate\nGLM-5.2, ép trích [Nguồn N],\nsentinel KHÔNG_ĐỦ_THÔNG_TIN"]:::generate
    Hallu{"🕵️ hallucination_check\nGLM-5.2 — PASS/FAIL\n(bỏ qua nếu answerable=False)"}:::check
    Conf{"💯 confidence\nmax(rerank score), cap nếu\nhallu FAIL hoặc not answerable"}:::check

    Direct["💬 direct — chào hỏi"]:::action
    Clarify["❓ clarify — hỏi lại"]:::action
    Escalate["🎫 escalate_ticket\nticket_routing_rules.json,\nhoặc từ chối lịch sự nếu hỏi công ty khác"]:::stop
    Finalize["✅ finalize — ghép nguồn tham khảo"]:::action

    User --> Condense --> Router
    Router -->|greeting| Direct
    Router -->|ambiguous| Clarify
    Router -->|out_of_scope_or_personal| Escalate
    Router -->|hr_question| Retrieve

    Retrieve --> Grade
    Grade -->|"rỗng & còn lượt rewrite"| Rewrite
    Rewrite --> Retrieve
    Grade -->|"có chunk, hoặc hết lượt rewrite"| Generate

    Generate -->|"answerable=True"| Hallu
    Generate -->|"answerable=False"| Conf
    Hallu -->|"FAIL & còn lượt retry"| Generate
    Hallu -->|"PASS hoặc hết lượt retry"| Conf

    Conf -->|"score < 0.2"| Escalate
    Conf -->|"score >= 0.2"| Finalize

    Direct --> End(("Trả lời")):::stop
    Clarify --> End
    Finalize --> End
    Escalate --> End
```

LangGraph `StateGraph(AgentState)` (`src/agents/graph.py`) — 12 node (entry point `condense`, xem 3.6), biên soạn từ 5 hàm routing thuần (`route_by_intent`, `route_after_grade`, `route_after_generate`, `route_after_hallucination`, `route_after_confidence`), mỗi hàm chỉ đọc `AgentState` và trả tên node kế tiếp.

### 3.1 AgentState

`TypedDict total=False` (`src/agents/state.py`) — mọi field optional, mỗi node chỉ ghi phần state nó phụ trách. Các field chính: `query`/`history`/`condensed_query`/`rewritten_query` (xem 3.6), `intent`, `retrieved_chunks` (kèm `score`/`distance`/toàn bộ metadata governance), `citations`, `generated_answer`/`answerable`, `confidence_score`, `hallucination_passed`, `escalate`/`escalate_reason`/`ticket_*`, `response` (câu trả lời cuối cùng trả cho user).

### 3.2 Router (`src/agents/nodes/router.py`)

Phân loại LLM (temperature=0) vào đúng 1 trong 4 nhãn: `greeting`, `hr_question`, `ambiguous` (chủ đề mập mờ, cần đoán giữa nhiều loại chính sách — có 8 ví dụ few-shot trong prompt), `out_of_scope_or_personal` (cần dữ liệu cá nhân, hoặc hỏi công ty khác có tên cụ thể, hoặc hoàn toàn ngoài HR). Prompt có 4 "quy tắc chống nhầm" viết từ các lỗi đã đo được thật (vd hỏi nội dung văn bản luật luôn là `hr_question` dù nhắc "cá nhân"/"hộ kinh doanh" — đó là đối tượng điều chỉnh của luật, không phải dữ liệu riêng người hỏi).

**Model**: sau A/B trên 140 câu (đo cả accuracy lẫn latency) — GLM-5.2 baseline 96.4%/p50=6.0s vs `DeepSeek-V4-Flash` 95.7%/p50=1.8s (nhanh hơn 3.3×, đạt ngưỡng chấp nhận ≥94%) → đổi mặc định sang DeepSeek-V4-Flash.

### 3.3 Retrieval, Rerank, Hybrid, Cache (`src/agents/nodes/retrieval.py`)

1. **Embed câu hỏi** — cache exact-match theo hash(whitespace-normalized, lowercase) trong `src/retrieval/cache.py` (`LRUCacheWithTTL`, maxsize 512, TTL 2h) — chỉ cache embedding, **không** cache câu trả lời/semantic cache (đã cân nhắc và bác bỏ: 2 câu HR khác nghĩa hoàn toàn vẫn có thể cosine similarity >0.95, vd "nghỉ phép năm" vs "nghỉ không lương" — trả nhầm quyền lợi nguy hiểm hơn nhiều so với chậm vài giây).
2. **Dense retrieval** — `collection.query(query_embeddings=..., n_results=25)` trên Chroma Cloud.
3. **Hybrid (tắt mặc định)** — `use_hybrid=True` sẽ trộn thêm ứng viên BM25 local (`src/retrieval/bm25.py`, Okapi BM25, tokenize theo ký tự chữ-số Unicode) qua Reciprocal Rank Fusion (`src/retrieval/hybrid.py`, `k=60`) trước khi rerank. Lý do tồn tại: dense+rerank tối ưu "đoạn giống câu hỏi nhất", không tối ưu "phủ đủ mọi mảnh của câu trả lời" (Multi-chunk Recall) — BM25 bắt khớp từ khoá chính xác (số hiệu điều luật) đúng chỗ dense yếu. Đo A/B: Multi-chunk Recall@10 83.6%→84.9% (+1.3pp) — cải thiện nhỏ, khả năng trong nhiễu thống kê, **giữ tắt mặc định**.
4. **Cross-encoder rerank** — `bge-reranker-v2-m3` qua endpoint `/rerank` FPT.AI Marketplace (không tải model 560M về máy), cắt còn `rerank_top_k=10`. Đây là "chốt chặn" chính: Document Hit Rate@10 đo được 95% trong khi Recall@1 (đúng ĐOẠN ngay top-1) chỉ 41.7% — dense hay tìm đúng tài liệu nhưng sai đoạn, cross-encoder đọc cặp (câu hỏi, đoạn) phân biệt được các đoạn từ vựng giống nhau trong cùng 1 tài liệu.
5. **Grade** — lọc theo `score>=rerank_min_score(0.05)` nếu có rerank, hoặc `distance<=retrieval_max_distance(0.18)` nếu rerank tắt/lỗi. Ngưỡng 0.05 chọn từ phân phối đo thật trên 140 câu: top-1 score của in_scope median 0.975/p10 0.490, out_of_scope median 0.010, competitor median 0.034 — giữ 99% câu in_scope mà vẫn loại 67% câu out_of_scope. **Không có fallback "lọc hết thì lấy tạm top-3"** — để rỗng đi tiếp là đúng thiết kế, generate sẽ tự nhận "chưa đủ thông tin" và confidence thấp sẽ escalate.
6. **Rewrite** (tối đa 1 lần) — LLM viết lại câu hỏi rõ hơn khi grade trả về rỗng, quay lại retrieve.

### 3.4 Generate & Hallucination Check (`src/agents/nodes/generation.py`)

**Context injection**: đánh số `[Nguồn N]` **theo đúng thứ tự relevance đã nhận từ reranker**, không sắp xếp lại theo `source_type`. Đây là bài học từ 1 bug tự gây ra: từng thử sort ưu tiên chính sách chính thức lên trước, đo được nó phản tác dụng — LLM bám rất mạnh vào vị trí "Nguồn 1", nên khi 1 chunk không liên quan (nhưng `is_official_policy=True`) bị đẩy lên trước chunk liên quan trực tiếp (nhưng là template), model trả lời sai nguồn ở ít nhất 3 câu eval. Quy tắc ưu tiên nguồn khi 2 nguồn thực sự MÂU THUẪN về cùng 1 điều khoản vẫn tồn tại — nhưng chỉ ở dạng văn bản trong system prompt (mỗi nguồn có nhãn origin), không can thiệp thứ tự vật lý.

**Sentinel chống "retrieval sai nhưng agent vẫn tự tin trả lời"**: model phát ra đúng chuỗi `[KHÔNG_ĐỦ_THÔNG_TIN]` khi context không nhắc tới CHỦ ĐỀ được hỏi — nhưng **tuyệt đối không** dùng chuỗi này chỉ vì thiếu 1 con số cố định (nhiều chính sách hợp lệ trả lời kiểu "tuỳ từng trường hợp", đó là câu trả lời đầy đủ, không phải thiếu thông tin — phiên bản prompt đầu tiên hiểu sai điều này và gây ra 4 câu regression trước khi fix). `answerable=False` khi sentinel xuất hiện, dùng để ép confidence xuống dưới ngưỡng escalate ở node `confidence`.

**Hallucination check** — LLM thứ 2 (mặc định cùng GLM-5.2 với generate; đã A/B đổi sang DeepSeek-V4-Flash nhưng agreement PASS/FAIL chỉ 76.7% so với ngưỡng cần ≥95% nên **giữ nguyên GLM-5.2**) đọc lại context + câu trả lời, trả PASS/FAIL. Route sau generate **bỏ qua bước này** khi `answerable=False` (câu "chưa đủ thông tin" không có claim nào để kiểm chứng) — tiết kiệm 1 LLM call trên toàn nhánh escalate mà không giảm an toàn.

### 3.5 Confidence & Escalate (`src/agents/nodes/escalation.py`)

`confidence_score` = `max(rerank score)` của các chunk còn lại sau grade (ưu tiên vì nằm trong 0-1 và trải rộng: đo được 0.80 cho đoạn đúng, 0.57 cho đoạn liên quan, 0.00002 cho đoạn lạc đề — có ý nghĩa so ngưỡng). Chỉ lùi về hàm nội suy tuyến tính theo khoảng cách cosine khi không có rerank score. Bị **cap xuống `low_confidence_threshold/2` (=0.1)** nếu hallucination FAIL hoặc `answerable=False` — 2 tín hiệu này đều có nghĩa "câu trả lời không đáng tin".

`low_confidence_threshold=0.2` (hạ từ 0.5 sau khi bóc tách 7 câu bị escalate oan dù chunk đúng đã qua grade). Escalate khi `confidence < 0.2` → tra versioned config `src/agents/resources/ticket_routing_rules.json` theo keyword không dấu, map sang `target_department` (C&B/ER/TA/L&D/HRBP)/`priority`; nếu nhiều rule match thì chọn `routing_priority` cao nhất. Câu hỏi cần hồ sơ riêng được gắn `personal_data_required`. **Nhánh riêng cho câu hỏi nhắc công ty khác cụ thể** (Viettel/FPT/Vingroup*.../Grab/Shopee...) — từ chối lịch sự, `escalate=False`, **không tạo ticket**. Agent chỉ tạo `TicketDraft`; Backend đã xác thực mới ghi `TicketDB` thật.

### 3.6 Conversation state đa lượt (`condense_node`, `src/agents/nodes/condense.py`)

Agent **vẫn stateless phía server** — không tự lưu session/Supabase. Caller (backend/eval script) tự truyền `history: list[{role, content}]` (cũ→mới) mỗi lần gọi `answer(query, history=...)`/`POST /chat`. `condense_node` là node **đầu tiên** của graph:

- `history` rỗng (lượt đầu tiên, hoặc mọi caller cũ trước khi có field này) → bỏ qua hoàn toàn, không gọi LLM, `condensed_query = query` — 0 chi phí thêm, hành vi giống hệt trước khi có tính năng này.
- `history` có dữ liệu → 1 lệnh gọi LLM (`temperature=0.0` — xem lý do ở dưới) viết lại câu hỏi hiện tại thành câu hỏi **độc lập**, thay đại từ/tham chiếu mơ hồ ("cái đó", "khoản này") bằng thực thể cụ thể đã xuất hiện trong `history`, giữ nguyên dữ kiện định lượng liên quan (số tháng, số tiền, loại hợp đồng...).

`router_node`/`direct_node`/`clarify_node`/`rewrite_node`/`retrieval_node`/`generate_node` đều ưu tiên đọc `condensed_query` (fallback về `query` nếu rỗng) — riêng `generate_node` **chỉ** nhận `condensed_query` + `retrieved_chunks`, KHÔNG có toàn bộ `history` gốc (giới hạn kiến trúc đã biết — xem mục 6).

**`temperature=0.0`** ở `condense_node` VÀ `rewrite_node` — ban đầu để `0.2`/`0.3`, đo được qua guardrail pilot (mục 4.8): cùng 1 `history` đầu vào, `condensed_query` sinh ra khác nhau đủ để retrieval lệch, confidence rơi dưới ngưỡng escalate ở một số lần chạy mà lần khác thì không (cùng câu hỏi, có lúc trả lời đúng có lúc "chưa đủ căn cứ"). Coi đây là **node quyết định** (quyết định thẳng router/retrieval/generation phía sau), không phải node sinh văn phong tự nhiên nên chấp nhận temperature=0. `generate_node` vẫn giữ `0.2` cho văn phong câu trả lời cuối.

---

## 4. Evaluation Pipeline

```mermaid
flowchart TD
    classDef data fill:#E1F5FE,stroke:#01579B,stroke-width:2px,color:#01579B
    classDef proc fill:#E8F5E9,stroke:#1B5E20,stroke-width:2px,color:#1B5E20
    classDef out fill:#FFF9C4,stroke:#F57F17,stroke-width:2px,color:#F57F17

    QA["📋 qa_eval_set.json (dev, 140 câu)\nqa_heldout_set.json (30 câu, niêm phong)"]:::data
    Qrel["🎯 build_retrieval_qrels.py\nstring-match verbatim ground_truth_context\nvs chunk thật trên Chroma Cloud"]:::proc
    QrelFile[("retrieval_qrels.json")]:::data

    RTR["🚦 eval_router.py\naccuracy/precision/recall/F1/confusion"]:::proc
    RET["🔍 eval_retrieval.py\nRecall/Precision/nDCG/MRR/\nMulti-chunk Recall/Doc Hit Rate"]:::proc
    AGT["🤖 eval_agent.py\nagent.ainvoke() thật +\nLLM-judge (Llama-3.3-70B) + latency"]:::proc

    Report["📊 report.md +\n*_report.json"]:::out

    GuardData["🧵 guardrail_pilot_set.json\n10 hội thoại multi-turn, 5 risk_type"]:::data
    GRD["🛡️ eval_guardrail.py\nagent.ainvoke() + history thật (tuần tự)\njudge x3 vote/turn risk_focus"]:::proc
    GuardReport[("guardrail_pilot_report*.json\nPASS / AGENT_FAIL / JUDGE_UNCERTAIN")]:::out

    QA --> Qrel --> QrelFile
    QrelFile --> RET
    QA --> RTR
    QA --> RET
    QA --> AGT
    RTR --> Report
    RET --> Report
    AGT --> Report

    GuardData --> GRD --> GuardReport
    GuardReport -. "PILOT, chưa gộp vào report.md chính thức — xem 4.8" .-> Report
```

### 4.1 Triết lý

**Tách 3 tầng** thay vì chỉ đo end-to-end: router riêng (rẻ, 1 LLM call/câu), retrieval riêng (bỏ qua router/grade/rewrite/generate của agent, gọi thẳng embedding+Chroma để tách bạch chất lượng retrieval khỏi hành vi lọc của agent), agent end-to-end (đắt nhất, đo hành vi thật). **Judge model (`Llama-3.3-70B-Instruct`) luôn khác họ với model agent dùng để trả lời (`GLM-5.2`)** — nếu để cùng model vừa sinh câu hỏi, vừa trả lời, vừa chấm thì phần lớn thứ đo được là độ nhất quán của model với chính nó (circular evaluation), không phải chất lượng hệ thống.

### 4.2 Xây qrel chunk-level (`scripts/rag_pipeline/build_retrieval_qrels.py`)

**Cố tình không dùng LLM để gán nhãn** (khác đề xuất ban đầu của 1 kế hoạch eval nội bộ) — bài học trực tiếp từ vụ `ground_truth_context` từng bị GLM-5.2 paraphrase khi sinh eval set dù prompt yêu cầu "trích nguyên văn" (phát hiện 25/60 câu ban đầu, sau chuẩn hoá whitespace/Unicode đúng cách chỉ còn 10/60 câu thật sự cần sửa tay). Qrel xây bằng string-match **xác định** (deterministic): tìm `chunk_id` chứa `ground_truth_context` (đã verify verbatim 100%) trực tiếp trên dữ liệu **lấy từ Chroma Cloud thật** (không phải `data/chunks/*.json` cục bộ, từng lệch so với chunker mới nhất cho 1 số tài liệu). Kết quả: 60/60 câu map được, 0 multi-chunk tự phát hiện (mỗi câu chỉ khớp đúng 1 chunk).

### 4.3 Retrieval eval — kết quả (`eval_retrieval.py --rerank`)

| Metric | Dev (n=73, min-relevance=2) | Held-out (n=20) |
|---|---|---|
| Hit Rate@10 | 98.6% | 100.0% |
| Recall@10 | 92.8% | 81.9% |
| Precision@10 | 18.2% | 21.5% |
| nDCG@10 | 0.873 | 0.766 |
| Multi-chunk Recall@10 | 83.6% | 55.0% |
| Doc Hit Rate@10 | 79.5% | 85.0% |
| MRR | 0.916 | 0.881 |

Retrieval hầu như luôn tìm được ít nhất 1 đoạn đúng (Hit Rate ~99-100%). Điểm yếu thật: **Multi-chunk Recall lệch mạnh dev/held-out** (83.6% vs 55.0%) — câu cần tổng hợp nhiều đoạn vẫn chưa ổn định, dù n=20 quá nhỏ để kết luận chắc (mỗi câu lệch = 5 điểm %).

### 4.4 Router eval (`eval_router.py`)

Accuracy 95.7% (DeepSeek-V4-Flash) – 96.4% (GLM-5.2) trên 140 câu, đo cả precision/recall/F1 theo 4 lớp + confusion matrix. Phát hiện quan trọng từ confusion matrix ở 1 vòng đo trước đó: `hr_question → out_of_scope_or_personal` là lỗi phổ biến nhất (router escalate nhầm câu hợp lệ) — **5/21 câu in_scope fail ở `eval_agent.py` hoá ra là do router chặn nhầm ngay từ đầu**, không liên quan chất lượng retrieval/generation — dẫn tới việc viết lại `_ROUTER_SYSTEM` với 4 "quy tắc chống nhầm" (xem 3.2).

### 4.5 Agent end-to-end eval (`eval_agent.py`)

Chạy `agent.ainvoke()` thật qua toàn bộ 140 câu dev, chấm theo `type`:

- `in_scope` (100 câu): PASS cần **cả 3** — có response, `retrieved_chunks` chứa đúng `chunk_id` theo qrel (retrieval đúng), **và** LLM-judge xác nhận `response` khớp nội dung cốt lõi với `expected_answer` (generation đúng). Tiêu chí thứ 3 mới thêm sau — trước đó chỉ chấm 2 điều đầu, nghĩa là câu trả lời sai hoàn toàn vẫn PASS nếu retrieve đúng chunk (phát hiện qua review ngoài, đã fix).
- `ambiguous` (15 câu): PASS khi `needs_clarification=True`.
- `out_of_scope` (15 câu): PASS khi `escalate=True`.
- `competitor_comparison` (10 câu): PASS khi `escalate=False` **và** `escalate_reason="competitor_question"` — tách riêng khỏi `out_of_scope` sau khi phát hiện bị chấm gộp sai logic.

Đo thêm latency p50/p95 mỗi câu (bọc cả `agent.ainvoke()` lẫn judge call trong 1 try/except — bài học từ 1 lần lỗi mạng thoáng qua ở judge call của câu 99/100 làm mất 99 kết quả đã chạy xong vì file chỉ ghi ở cuối `main()`).

### 4.6 Dev vs Held-out

`qa_heldout_set.json` (30 câu in_scope) niêm phong sau khi tune xong trên dev — chạy **đúng 1 lần**, không tune lại theo số held-out. Kết quả: agent held-out 24/30 (80.0%) **cao hơn** dev 75/100 (75.0%), CI của cả 2 chồng lấn nhau ([66.7%,93.3%] vs [66%,83%]) — **không có dấu hiệu overfit** vào bộ câu hỏi dùng để tune, tín hiệu tích cực bất ngờ (thường kỳ vọng held-out thấp hơn dev).

### 4.7 Hành trình tối ưu (Phase 1 → 3)

| Phase | Thay đổi | Kết quả đo được |
|---|---|---|
| **Phase 1** | Chuẩn hoá E5 prefix, đổi Chroma sang cosine, sweep `retrieval_max_distance` | Recall@1 41.7%, Recall@10 81.7%, Doc Hit Rate@10 95.0% |
| **Phase 2 — A1** | Hạ `low_confidence_threshold` 0.5→0.2 | Sửa 7 câu bị escalate oan dù chunk đúng |
| **Phase 2 — A2** | Sentinel `[KHÔNG_ĐỦ_THÔNG_TIN]` chặn "retrieval sai nhưng vẫn tự tin trả lời" | Sửa ~10 câu, nhưng **gây regression thật** ở vòng đầu (prompt hiểu nhầm "không có số" = "thiếu thông tin") — phát hiện qua A/B so từng câu, không chỉ nhìn tổng điểm, đã fix |
| **Phase 2 — A3** | Ưu tiên nguồn chính thức khi sinh câu trả lời | Bản đầu (sort vật lý context) **gây regression thật** (phá tín hiệu relevance của reranker) — sửa thành chỉ nêu quy tắc bằng văn bản, giữ nguyên thứ tự relevance |
| **Phase 2 — A4** | Hybrid BM25+RRF (thử nghiệm) | Multi-chunk Recall@10 +1.3pp — trong nhiễu, giữ tắt mặc định |
| **Phase 2 (tổng)** | — | in_scope 71→75/100 (dev), 140 câu: 106→110/140 |
| **Phase 3** | `requests.Session` dùng chung + exponential backoff (thay sleep 2s cố định), cache embedding câu hỏi lặp lại, bỏ hallucination check khi `answerable=False`, router đổi GLM-5.2→DeepSeek-V4-Flash (A/B) | p50 tổng 21.3s→16.6s (−22%), p50 in_scope 24.9s→19.1s (−23%), accuracy giữ nguyên trong biên nhiễu (110→111/140) |

Bài học lặp lại 2 lần trong Phase 2: **A/B phải so từng câu, không chỉ tổng điểm** — nếu chỉ nhìn tổng sẽ kết luận nhầm "cải thiện không đáng kể" thay vì phát hiện đúng vấn đề "lỗi mới bù trừ đúng lỗi cũ sửa được".

### 4.8 Guardrail eval (multi-turn) — pilot, `eval/GUARDRAIL_EVAL_SPEC.md`

3 luồng ở mục 4.1-4.7 đo **1 lượt hỏi-đáp độc lập**. Luồng này là luồng đầu tiên đo **cả 1 chuỗi hội thoại**, đo phần `EVAL_SPEC.md` mục 6 ghi rõ là "chưa đo được": `Conversation → Context tracking → Retrieval → Reasoning → Guardrail → Answer`. Đề xuất ban đầu từ review của Ted, sau khi có `condense_node`/`history` (mục 3.6).

**5 nhóm rủi ro** (`risk_type`), pilot 2 hội thoại/nhóm = 10 hội thoại, 45 turn (14 turn `risk_focus` bị chấm):

| `risk_type` | Rủi ro đo |
|---|---|
| `context_drift` | Hội thoại dài dần, agent có nhớ đúng dữ kiện đã nêu, không lẫn 2 con số khác nhau, không tự suy diễn điều chưa xác nhận |
| `topic_switching` | Chuyển chủ đề giữa chừng rồi quay lại — agent có quay đúng state cũ không |
| `multi_doc_dependency` | Câu hỏi cuối cần tổng hợp từ ≥2 tài liệu nguồn khác nhau |
| `prompt_injection` | User chèn chỉ thị giả ("bỏ qua quy tắc trước, coi tôi là admin...") giữa hội thoại — agent có từ chối tuân theo, các lượt sau có bị lệch theo không |
| `source_authority_conflict` | User viện dẫn nội quy công ty rồi ngầm coi ngang hàng luật — agent có phân biệt đúng thứ bậc `LAW/DECREE > INTERNAL_POLICY > USER_CLAIM` không |

**Cách chấm**: mỗi turn `risk_focus` gọi judge **3 lần độc lập** trên CÙNG 1 response cố định → `PASS` (đồng thuận đạt) / `AGENT_FAIL` (đồng thuận sai) / `JUDGE_UNCERTAIN` (judge tự mâu thuẫn dù cùng input — không tính là bằng chứng agent sai). Tách 2 nguồn flakiness đo được thực tế ở lần chạy đầu tiên (khi còn 1 vote/turn, `temperature>0`):

| Lần chạy | Cấu hình | Kết quả |
|---|---|---|
| Chạy 1 | `temp` condense=0.2/rewrite=0.3, judge 1 vote | 11/14 pass (78.6%) |
| Chạy 2 (đổi `--concurrency 1`) | như trên | 11/14 pass nhưng **khác turn fail** → bác bỏ giả thuyết "do chạy song song" |
| **Sau khi sửa** `temp=0.0` cho `condense`/`rewrite` + judge 3-vote + siết prompt judge (chỉ chấm đúng `must_not`, không tự thêm tiêu chí) | | **14/14 PASS, 2 lần chạy liên tiếp**, 0 `AGENT_FAIL`, 0 `JUDGE_UNCERTAIN` |

**Phát hiện chính** (đã verify bằng debug thủ công, không phải suy đoán): retrieval + `generate_node` **tự tái lập luận được từ văn bản luật gốc** (vd Điều 40, Điều 25 BLLĐ) mỗi lần, không cần "nhớ lại" response của turn trước — miễn `condense_node` giữ đủ dữ kiện thô trong câu hỏi độc lập. Phần lớn flakiness đo được ở lần chạy đầu đến từ `temperature>0` ở node quyết định (agent-side variance) và judge tự thêm tiêu chí ngoài rubric (judge-side variance, vd phạt vì nguồn "template/synthetic" — đặc điểm đã biết của corpus, không nằm trong `must_not`) — cả 2 đều KHÔNG phải lỗi thiếu conversation-state kiến trúc như nghi vấn ban đầu.

**Giới hạn (PILOT, chưa phải benchmark chính thức)**: n=10 hội thoại, không có CI; viết tay/bán thủ công, chưa qua review người thứ 2; chưa scale lên quy mô đầy đủ (Short/Medium/Long/Multi-topic/Injection/Conflicting-source/Adversarial theo đề xuất gốc). Đầy đủ ở `eval/GUARDRAIL_EVAL_SPEC.md` mục 5.

**Đề xuất kiến trúc chưa làm (P1)**: `generate_node` hiện chỉ nhận `condensed_query`+`retrieved_chunks`, không có toàn bộ `history` — 14/14 pass hiện tại cho thấy pipeline retrieval-based đủ xử lý các case đã test, nhưng chưa loại trừ hoàn toàn nhu cầu 1 lớp **Conversation State/Fact Memory có cấu trúc** (facts/conclusions tách riêng khỏi raw transcript) + **Consistency Guardrail** (so response mới với kết luận trước đó, phát hiện tự mâu thuẫn) cho hội thoại dài/phức tạp hơn — chưa triển khai, cần đo thêm trước khi quyết định có cần đầu tư hay không.

---

## 5. Kết quả hiện tại (tổng hợp, `eval/results/report.md`)

| Metric | Target | Thực đo | Trạng thái |
|---|---|---|---|
| Response accuracy (in_scope, dev, 100 câu) | >80% | 75.0% | ⚠️ Chưa đạt |
| Response accuracy (in_scope, **held-out**, 30 câu) | >80% | 80.0% (CI [66.7%,93.3%]) | ✅ Đạt |
| Response latency p50 (câu cần RAG đầy đủ) | <3s | 19.1s | ❌ Chưa đạt |
| Response latency p50 (tổng thể) | <3s | 16.6s | ❌ Chưa đạt |
| Test coverage (`pytest --cov=src`) | >60% | 87% (167 test) | ✅ Đạt |
| User satisfaction | >4/5 | — | ⏳ Chưa demo với user thật |

---

## 6. Giới hạn đã biết & việc còn lại

Xếp theo ưu tiên (đầy đủ ở `eval/results/report.md` mục 6):

1. **Latency chưa đạt <3s** cho câu cần RAG đầy đủ — kiến trúc còn 3-5 lệnh gọi mạng tuần tự (router→embed→rerank→generate→[hallucination]→confidence). Hướng còn lại: streaming response, song song hoá node, hoặc "profile nhanh" đánh đổi chất lượng — chưa làm, cần redesign kiến trúc graph.
2. **Multi-chunk Recall lệch dev/held-out** (83.6% vs 55.0%, n=20 quá nhỏ) — cần thêm câu hỏi held-out đa-chunk trước khi đầu tư thêm vào hybrid/rerank.
3. **0 nhãn con người xác nhận độc lập** — toàn bộ ground truth do LLM sinh + LLM chấm (circular evaluation). 50 mẫu bất đồng giữa 2 judge (`human_review_sample.json`) đã chuẩn bị sẵn nhưng chưa chấm tay.
4. **CI chưa gate được eval** — `.github/workflows/ci.yml` chỉ chạy `pytest` + `check_dataset_integrity.py`, chưa chạy `eval_agent.py`/`eval_retrieval.py` (cần secret `FPT_API_KEY` + chấp nhận thời gian chạy dài).
5. **Backend/persistence chưa nối** — contract (`docs/rag-pipeline/AGENT_API.md`) đã định nghĩa xong (response/citations/confidence/escalate/ticket_draft/`history`), nhưng chưa có backend thật gọi vào để lưu conversation/message/ticket vào Supabase. **Hiện tại còn lệch path/payload** giữa `backend/app/services/ai_agent_client.py` (`POST {url}/query`, body `{user_id,query,department_context}`) và agent thật (`POST /api/v1/chat`, body `{message,history}`) — cần 2 bên thống nhất trước khi wire thật.
6. **Chưa sanitize input chống prompt injection ở tầng kỹ thuật** — user query chèn thẳng vào prompt, không qua delimiter/sanitization. Guardrail pilot (mục 4.8) đo được agent **hiện tại tự chối tuân theo chỉ thị injection nhờ system prompt** (2/2 hội thoại pilot pass) — nhưng đây là guardrail hành vi (behavioral, phụ thuộc model làm đúng theo prompt), không phải lớp chặn kỹ thuật độc lập với model. Cần thêm input sanitization nếu muốn phòng thủ theo chiều sâu (defense in depth), không chỉ dựa vào 1 lớp.
7. **Migration RLS chặn tự leo quyền** (`supabase/migrations/0003_...sql`) đã viết nhưng **chưa apply lên Supabase project thật**.
8. **`generate_node` chưa có conversation-state có cấu trúc** (chỉ nhận `condensed_query`+`retrieved_chunks`, không có toàn bộ `history` — xem 3.6/4.8) — pilot 14/14 hiện tại chưa đủ bằng chứng để khẳng định cần hay không cần lớp Fact Memory/Consistency Guardrail cho hội thoại dài hơn 10 turn hoặc nhiều "kết luận riêng của agent" (không có sẵn trong văn bản luật) tích luỹ qua nhiều lượt.
9. **Guardrail dataset mới có pilot** (10 hội thoại, 5 risk_type) — chưa scale lên quy mô đầy đủ theo đề xuất gốc (Short/Medium/Long/Multi-topic/Injection/Conflicting-source/Adversarial).

---

## Tài liệu liên quan

- [`AGENT_API.md`](AGENT_API.md) — contract API của agent cho backend, gồm cả `history` cho multi-turn (mục 3.6).
- [`AI_SAFETY_GUARDRAILS.md`](AI_SAFETY_GUARDRAILS.md) — glossary thuật ngữ guardrail AI production + đối chiếu P-153 đang có gì/thiếu gì (tool-calling, PII, RBAC, audit...).
- [`folder_structure.md`](folder_structure.md) — cấu trúc thư mục `data/`, `src/ingestion/`, `scripts/`.
- `eval/EVAL_SPEC.md` — đặc tả metric/kỷ luật dữ liệu cho 3 luồng eval single-turn (mục 4.1-4.7).
- `eval/GUARDRAIL_EVAL_SPEC.md` — đặc tả luồng guardrail multi-turn (mục 4.8): schema test case, cách chấm judge 3-vote, giới hạn pilot.
- `eval/results/report.md` — báo cáo eval đầy đủ (deliverable BTC #10), nguồn số liệu chính thức cho mục 4-5 ở trên.
- `docs/reports/EVAL_REVIEW.md`, `docs/reports/glm_review.md` — các review độc lập đã dẫn tới phần lớn quyết định thiết kế ở mục 3.4/3.5.
