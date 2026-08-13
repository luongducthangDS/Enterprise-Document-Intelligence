from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import get_settings
from src.workers.jobs import get_job_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # Job đang chạy dở lúc process chết không thể tiếp tục (task nằm trong RAM
    # của process cũ). Đánh dấu FAILED để Backend poll ra trạng thái kết thúc và
    # tự quyết retry, thay vì để job kẹt QUEUED/PROCESSING vĩnh viễn.
    recovered = get_job_store(settings).recover_stale()
    if recovered:
        print(f"Recovered {len(recovered)} stale agent job(s) -> FAILED: {', '.join(recovered)}")
    yield
    print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
