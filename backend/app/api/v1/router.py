from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    chat,
    citations,
    conversations,
    documents,
    evaluation,
    indexes,
    ingestion,
    tickets,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(admin.router, prefix="/admin", tags=["Access Administration"] )
api_v1_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_v1_router.include_router(citations.router, prefix="/citations", tags=["Citations"])
api_v1_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_v1_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_v1_router.include_router(ingestion.router, prefix="/ingestion-jobs", tags=["Ingestion Jobs"])
api_v1_router.include_router(indexes.router, prefix="/indexes", tags=["Indexes"])
api_v1_router.include_router(evaluation.router, prefix="/evaluation", tags=["Evaluation"])



