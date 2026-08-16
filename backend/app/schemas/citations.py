from pydantic import BaseModel, Field


class CitationDocumentDTO(BaseModel):
    document_id: str = Field(..., description="ID tài liệu nguồn")
    title: str = Field(..., description="Tên tài liệu")
    version: str | None = Field(default=None, description="Phiên bản tài liệu (null nếu không có)")
    effective_date: str | None = Field(default=None, description="Ngày có hiệu lực (null nếu không có)")
    status: str = Field(default="ACTIVE", description="Trạng thái tài liệu (ACTIVE, ARCHIVED, ...)")
    is_official_policy: bool = Field(
        default=True, description="Cờ xác định tài liệu chính thức hay không"
    )
    source_type: str | None = Field(default=None, description="Loại nguồn tài liệu")


class CitationLocationDTO(BaseModel):
    page: int | None = Field(default=None, description="Trang chứa trích dẫn")
    section: str | None = Field(default=None, description="Mục / Điều khoản chứa trích dẫn")
    chunk_id: str | None = Field(default=None, description="ID chunk trong vector DB")


class CitationDetailDTO(BaseModel):
    citation_id: str = Field(..., description="ID trích dẫn")
    document: CitationDocumentDTO = Field(..., description="Thông tin tài liệu trích dẫn")
    location: CitationLocationDTO = Field(..., description="Vị trí trích dẫn trong tài liệu")
    excerpt: str = Field(..., description="Đoạn văn bản trích dẫn chi tiết")
    conflict_warning: bool = Field(default=False, description="Cảnh báo mâu thuẫn chính sách")
    is_official_policy: bool = Field(
        default=True, description="Cờ xác định tài liệu chính thức hay không"
    )
    source_type: str | None = Field(default=None, description="Loại nguồn tài liệu")

