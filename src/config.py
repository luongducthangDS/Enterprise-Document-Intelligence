from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    # Tên các công ty XUẤT HIỆN TRONG CHÍNH KHO TÀI LIỆU của mình — hỏi về chúng
    # là hỏi tài liệu nội bộ, không phải hỏi đối thủ. "V-NOVA" là công ty giả
    # định trong bộ chính sách synthetic (05/06/07/08_*.md); thiếu nó thì router
    # từ chối luôn các câu hỏi về chính sách WFH/đào tạo/nghỉ phép của mình.
    internal_company_names: list[str] = Field(
        default_factory=lambda: ["vingroup", "vinfast", "v-nova", "vnova"]
    )
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # Database (dữ liệu quan hệ: user/RBAC, chat history, ticket, document metadata)
    database_url: str = "sqlite:///./data/app.db"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Vector Store — "cloud" (Chroma Cloud, dùng chung cho cả team + server) hay
    # "local" (PersistentClient trên đĩa, chỉ dùng dev/test offline — KHÔNG sống
    # được trên Render vì free/standard tier không có persistent disk).
    vector_db_backend: Literal["cloud", "local"] = "cloud"
    chroma_persist_dir: str = "./storage/vector_db"
    chroma_collection_name: str = "hr_documents"
    chroma_cloud_api_key: str = ""
    chroma_cloud_tenant: str = ""
    chroma_cloud_database: str = ""

    # FPT.AI Marketplace (embedding/VLM/rerank/chat gateway)
    fpt_api_key: str = ""
    fpt_base_url: str = "https://mkp-api.fptcloud.com"
    embedding_model: str = "multilingual-e5-large"
    embedding_batch_size: int = 32
    llm_model: str = "GLM-5.2"
    # Model chấm điểm trong eval — PHẢI khác họ với `llm_model`. Nếu để cùng
    # model vừa sinh dữ liệu, vừa trả lời, vừa chấm thì phần lớn thứ đo được là
    # độ nhất quán của model với chính nó, không phải chất lượng hệ thống
    # (circular evaluation). Llama-3.3-70B khác họ với GLM và phản hồi nhanh.
    judge_model: str = "Llama-3.3-70B-Instruct"

    # Agent RAG
    retrieval_top_k: int = 25
    rerank_top_k: int = 10
    use_reranker: bool = True
    # Tên model trên FPT.AI Marketplace (endpoint /rerank) — KHÔNG phải repo id
    # HuggingFace: reranker chạy qua gateway, không tải model về máy.
    reranker_model: str = "bge-reranker-v2-m3"
    # Ngưỡng lọc trên relevance_score 0-1 của reranker (dùng ở grade_node).
    # Đo trên 140 câu eval (eval/results/rerank_score_distribution.json): top-1
    # score của in_scope có median 0.975 / p10 0.490, còn out_of_scope median
    # 0.010 và competitor 0.034 — tách bạch tốt hơn hẳn khoảng cách cosine.
    # 0.05 giữ lại 99% câu in_scope mà vẫn loại 67% câu out_of_scope.
    rerank_min_score: float = 0.05
    # Chỉ dùng khi reranker tắt/lỗi — ngưỡng khoảng cách cosine.
    retrieval_max_distance: float = 0.18
    # Neo cho confidence tính từ distance (nhánh fallback khi không có rerank
    # score) — lấy theo phân phối distance đo thực tế trên bộ eval.
    distance_confidence_near: float = 0.10
    distance_confidence_far: float = 0.22
    # Hybrid retrieval — trộn dense (Chroma) với BM25 local qua RRF trước khi
    # đưa vào reranker. Tắt mặc định để A/B: bật `use_hybrid=True` rồi so
    # Multi-chunk Recall@10 với baseline dense-only (69.1%). Không thêm lệnh
    # gọi mạng nào (BM25 chạy local) nên không đổi latency.
    use_hybrid: bool = False
    bm25_top_k: int = 25
    rrf_k: int = 60

    max_rewrite_retries: int = 1
    max_hallucination_retries: int = 2
    # Escalate khi confidence (= relevance_score của đoạn tốt nhất) dưới ngưỡng.
    # Hạ 0.5 -> 0.2 sau khi bóc tách 29 câu in_scope fail: 7 câu bị escalate oan
    # dù chunk ĐÚNG đã qua được grade, confidence chỉ 0.18-0.49. Theo phân phối
    # score thực đo (eval/results/rerank_score_distribution.json) chỉ 5/100 câu
    # in_scope có top-1 score < 0.2, so với 11/100 ở ngưỡng 0.5.
    #
    # Giá phải trả: out_of_scope lọt qua tăng 2/15 -> 3/15. Chấp nhận được vì
    # (a) router đã chặn nhóm đó trước với recall 0.96, (b) `answerable` ở
    # generate_node (sentinel [KHÔNG_ĐỦ_THÔNG_TIN]) kéo score xuống 0.1 khi
    # context không thực sự trả lời được câu hỏi — đó mới là lớp chặn chính cho
    # nhóm "reranker tự tin vào đoạn sai", vốn có score 0.78-1.00 nên ngưỡng
    # này dù cao tới đâu cũng không bắt được.
    low_confidence_threshold: float = 0.2

    # Chunking
    chunk_target_chars: int = 1200
    chunk_max_chars: int = 1500
    chunk_min_chars: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
