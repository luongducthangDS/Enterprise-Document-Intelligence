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
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM — placeholder từ template gốc (ChatOpenAI qua src/services/llm.py),
    # CHƯA được trỏ vào stack thật đang dùng cho phần còn lại của dự án
    # (GLM-5.2 qua FPT.AI Marketplace, xem fpt_api_key/fpt_base_url bên dưới).
    # Cần chốt lại khi implement agent RAG (src/agents/) — có thể đổi hẳn sang
    # gọi qua fpt_client.chat_completion() thay vì ChatOpenAI, hoặc trỏ
    # openai_api_key/model_name vào endpoint OpenAI-compatible của FPT.AI.
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

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

    # FPT.AI Marketplace (embedding/VLM/rerank gateway)
    fpt_api_key: str = ""
    fpt_base_url: str = "https://mkp-api.fptcloud.com"
    embedding_model: str = "multilingual-e5-large"
    embedding_batch_size: int = 32

    # Chunking
    chunk_target_chars: int = 1200
    chunk_max_chars: int = 2000
    chunk_min_chars: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
