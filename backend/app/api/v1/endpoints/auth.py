from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login():
    """Xác thực người dùng & cấp phát JWT Access Token / Refresh Token."""
    return {"message": "Login endpoint"}


@router.get("/me")
async def get_me():
    """Lấy thông tin người dùng hiện tại từ JWT Token."""
    return {"message": "Current user endpoint"}
