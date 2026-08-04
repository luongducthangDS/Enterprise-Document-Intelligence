import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import global_exception_handler
from app.core.logging import logger, setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.app_name} in {settings.app_env} mode...")
    yield
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.app_name,
    description="Independent Backend Service with JWT Auth, PostgreSQL & AI Agent REST Integration",
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


# Middleware 2: Logging & Request Process Time
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    logger.info(f"{request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration_ms:.2f}ms")
    response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
    return response


# Global Exception Handling
app.add_exception_handler(Exception, global_exception_handler)

# API Routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "env": settings.app_env,
    }
