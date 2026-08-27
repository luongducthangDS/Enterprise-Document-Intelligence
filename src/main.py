import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import get_settings
from src.workers.jobs import get_job_store


async def _warmup_retrieval() -> None:
    """Dựng sẵn client Chroma + chạy một truy vấn mồi ngay khi service khởi động.

    Đo được (scripts/profile_agent_latency.py, 2026-08-14): request ĐẦU TIÊN của
    mỗi tiến trình trả giá 3,2-3,7s dựng CloudClient cộng 13,6s cho truy vấn
    vector đầu tiên, trong khi các request sau chỉ tốn 0,3-1,7s cho cùng thao
    tác. Toàn bộ phần chênh đó là khởi tạo một lần, không phải chi phí truy vấn
    — đẩy nó về lúc startup thì người dùng đầu tiên không phải trả.

    Không dùng vector ngẫu nhiên: truy vấn mồi đi đúng đường mà retrieval_node
    đi (embed câu hỏi -> collection.query) nên làm nóng cả HTTP/TLS tới gateway
    embedding lẫn tới Chroma Cloud. Lỗi ở đây KHÔNG được làm chết service: mất
    warm-up chỉ khiến request đầu chậm như trước, còn chết lúc startup thì hỏng
    cả agent.
    """
    from src.agents.nodes.retrieval import _aembed_query, _bm25_index, _collection

    started = time.perf_counter()
    try:
        embedding = await _aembed_query("chính sách nghỉ phép")
        collection = await asyncio.to_thread(_collection)
        await asyncio.to_thread(collection.query, query_embeddings=[embedding], n_results=1)
        # Nạp trước BM25 Corpus vào bộ nhớ đệm ngay khi khởi động để loại bỏ cold-start
        await asyncio.to_thread(_bm25_index)
    # Log warm-up cố ý viết KHÔNG DẤU: nó chạy trong lifespan, và console
    # Windows mặc định cp1252 làm print tiếng Việt ném UnicodeEncodeError —
    # ở đây lỗi đó giết luôn startup của cả service.
    except Exception as e:  # noqa: BLE001 — warm-up hỏng không được chặn startup
        print(f"[warmup] skipped: {type(e).__name__}: {e}")
        return
    print(f"[warmup] retrieval and BM25 index ready in {round((time.perf_counter() - started) * 1000)}ms")


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
    await _warmup_retrieval()
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
