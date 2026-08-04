from fastapi import APIRouter

router = APIRouter()


@router.post("/upload")
async def upload_document():
    """HR Admin Upload tài liệu chính sách mới & thiết lập quyền truy cập theo phòng ban."""
    return {"message": "Upload document endpoint"}
