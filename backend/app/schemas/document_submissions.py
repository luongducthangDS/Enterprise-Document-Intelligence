from pydantic import BaseModel, Field


class SubmissionReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class SubmissionMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    department: str | None = Field(default=None, min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    effective_date: str | None = Field(default=None, max_length=32)
    access_scope: str | None = Field(default=None, min_length=1, max_length=32)
    authorized_role: str | None = Field(default=None, max_length=64)


class DocumentPublicUrlUpdate(BaseModel):
    public_url: str = Field(..., min_length=1, description="Public CDN URL (Cloudinary/S3)")


class DocumentSubmissionFromUrlRequest(BaseModel):
    source_file: str = Field(..., min_length=1, max_length=255, description="Tên file gốc")
    public_url: str = Field(..., min_length=1, description="Public CDN URL (Cloudinary)")
    title: str | None = Field(default=None, max_length=255, description="Tiêu đề tài liệu")
    category: str | None = Field(default=None, max_length=128, description="Danh mục tài liệu")
    department: str | None = Field(default=None, max_length=128, description="Phòng ban")
    version: str | None = Field(default=None, max_length=64, description="Phiên bản")
    effective_date: str | None = Field(default=None, max_length=32, description="Ngày hiệu lực")
    confidentiality: str | None = Field(default=None, max_length=64, description="Mức độ bảo mật")
    access_scope: str = Field(default="RESTRICTED", max_length=32, description="Phạm vi truy cập")
    authorized_role: str | None = Field(default=None, max_length=64, description="Vai trò được phân quyền")

