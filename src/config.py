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

    # Agent RAG
    retrieval_top_k: int = 5
    retrieval_max_distance: float = 0.16
    max_rewrite_retries: int = 1
    max_hallucination_retries: int = 2
    low_confidence_threshold: float = 0.5

    # Chunking
    chunk_target_chars: int = 1200
    chunk_max_chars: int = 2000
    chunk_min_chars: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
