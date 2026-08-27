import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import uvicorn
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    global_exception_handler,
    validation_exception_handler,
)
from app.core.logging import logger, setup_logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.app_name} in {settings.app_env} mode...")

    # 1. Warmup / Health Check tới AI Agent Service (chạy 1 lần duy nhất khi Backend khởi động)
    try:
        from app.services.warmup_service import WarmupService
        await WarmupService.check_and_warmup_on_startup(max_wait_seconds=25.0)
    except Exception as e:
        logger.warning(f"[Startup Lifespan] Warmup AI Agent gặp lỗi: {e}")

    # 2. Chat Job Durability: Tự động phục hồi các request bị gián đoạn khi Backend khởi động lại
    try:
        from app.services.chat_service import ChatService
        recovered = await ChatService.recover_pending_requests()
        if recovered > 0:
            logger.info(f"[Chat Durability] Recovered {recovered} pending chat request(s) on startup.")
    except Exception as e:
        logger.error(f"[Chat Durability] Failed to recover pending chat requests on startup: {e}")

    try:
        yield
    finally:

        try:
            from app.services.chat_service import ChatService
            await ChatService.cancel_background_tasks()
        except Exception as e:
            logger.warning(f"[Chat Durability] Error cancelling background tasks on shutdown: {e}")
        await engine.dispose()
        logger.info("Shutting down application...")


app = FastAPI(
    title=settings.app_name,
    description="Backend Service with Supabase PostgreSQL and AI Agent REST Integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware 1: CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware 2: Logging & Request ID / Process Time
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = request_id
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration_ms:.2f}ms"
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
    return response


# Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# API Routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Endpoint kiểm tra sức khoẻ Backend."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "env": settings.app_env,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
