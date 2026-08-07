from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, documents, tickets

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_v1_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_v1_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
