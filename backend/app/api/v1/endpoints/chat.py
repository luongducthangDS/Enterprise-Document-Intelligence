from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def send_chat_message():
    """Gửi câu hỏi từ Frontend, Backend sẽ gọi REST Client tới AI Agent Service để xử lý RAG."""
    return {"message": "Chat endpoint"}


@router.get("/history")
async def get_chat_history():
    """Lấy lịch sử hội thoại của người dùng từ PostgreSQL."""
    return {"message": "Chat history endpoint"}
