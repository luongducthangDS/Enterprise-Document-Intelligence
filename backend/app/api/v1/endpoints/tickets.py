from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def create_ticket():
    """Tạo HR Ticket hỗ trợ (Auto Escalation hoặc tạo thủ công)."""
    return {"message": "Create ticket endpoint"}


@router.get("/")
async def list_tickets():
    """HR Admin Dashboard: Danh sách ticket hỗ trợ."""
    return {"message": "List tickets endpoint"}
