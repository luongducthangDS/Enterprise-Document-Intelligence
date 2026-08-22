
from pydantic import BaseModel, Field


class DocumentUploadResponseData(BaseModel):
    document_id: str = Field(..., description="ID của tài liệu vừa tạo")
    ingestion_job_id: str = Field(..., description="ID của tác vụ xử lý ingestion bất đồng bộ")
    status: str = Field(default="UPLOADED", description="Trạng thái khởi tạo của tài liệu")


class DocumentListItem(BaseModel):
    document_id: str = Field(..., description="ID tài liệu")
    title: str = Field(..., description="Tiêu đề tài liệu")
    category: str = Field(..., description="Phân loại tài liệu")
    version: str | None = Field(default=None, description="Phiên bản tài liệu")
    effective_date: str | None = Field(default=None, description="Ngày có hiệu lực")
    status: str = Field(..., description="Trạng thái tài liệu (ACTIVE, ARCHIVED...)")
    ingestion_state: str = Field(..., description="Trạng thái trích xuất/xử lý (QUEUED, PROCESSING, COMPLETED...)")
    indexed: bool = Field(default=False, description="Tài liệu đã lập chỉ mục vector hay chưa")
    created_at: str = Field(..., description="Thời gian tạo")


class DocumentIngestionDTO(BaseModel):
    job_id: str | None = Field(default=None, description="ID tác vụ ingestion gần nhất")
    state: str = Field(default="QUEUED", description="Trạng thái ingestion")
    chunk_count: int = Field(default=0, description="Số lượng chunks đã tạo")
    last_ingested_at: str | None = Field(default=None, description="Thời gian hoàn thành ingestion gần nhất")
    error: str | None = Field(default=None, description="Thông tin lỗi nếu có")


class DocumentIndexDTO(BaseModel):
    indexed: bool = Field(default=False, description="Đã index trên Vector DB chưa")
    index_version: str | None = Field(default=None, description="Phiên bản chỉ mục vector")


class DocumentDetailData(BaseModel):
    document_id: str = Field(..., description="ID tài liệu")
    title: str = Field(..., description="Tiêu đề tài liệu")
    category: str = Field(..., description="Danh mục tài liệu")
    version: str | None = Field(default=None, description="Phiên bản tài liệu")
    effective_date: str | None = Field(default=None, description="Ngày có hiệu lực")
    status: str = Field(..., description="Trạng thái (ACTIVE, ARCHIVED...)")
    language: str = Field(default="vi", description="Ngôn ngữ chính")
    source_file: str = Field(..., description="Tên/đường dẫn file gốc")
    checksum: str | None = Field(default=None, description="Mã hash checksum của file")
    confidentiality: str = Field(..., description="Mức độ bảo mật (INTERNAL, RESTRICTED...)")
    ingestion: DocumentIngestionDTO = Field(..., description="Thông tin tác vụ trích xuất & xử lý")
    index: DocumentIndexDTO = Field(..., description="Thông tin chỉ mục Vector DB")


class DocumentMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, description="Tiêu đề mới")
    category: str | None = Field(default=None, description="Phân loại mới")
    version: str | None = Field(default=None, description="Phiên bản mới")
    effective_date: str | None = Field(default=None, description="Ngày có hiệu lực mới")
    status: str | None = Field(default=None, description="Trạng thái mới")
    language: str | None = Field(default=None, description="Ngôn ngữ tài liệu")
    confidentiality: str | None = Field(default=None, description="Cấp độ bảo mật")
    department: str | None = Field(default=None, min_length=1, max_length=128)
    access_scope: str | None = Field(default=None, min_length=1, max_length=32)
    authorized_role: str | None = Field(default=None, max_length=64)


class DocumentMetadataUpdateResponseData(BaseModel):
    document_id: str = Field(..., description="ID tài liệu")
    metadata_updated: bool = Field(default=True, description="Cập nhật thành công")
    requires_reindex: bool = Field(default=True, description="Yêu cầu chạy lại chỉ mục vector")
    updated_at: str = Field(..., description="Thời gian cập nhật")


class DocumentArchiveRequest(BaseModel):
    reason: str | None = Field(default=None, description="Lý do lưu trữ / thay thế tài liệu")


class DocumentArchiveResponseData(BaseModel):
    document_id: str = Field(..., description="ID tài liệu")
    status: str = Field(default="ARCHIVED", description="Trạng thái sau lưu trữ")
    requires_reindex: bool = Field(default=True, description="Cần re-index lại vector DB")
    archived_at: str = Field(..., description="Thời gian lưu trữ")


class IngestionJobResponseData(BaseModel):
    job_id: str = Field(..., description="ID tác vụ ingestion")
    document_id: str = Field(..., description="ID tài liệu liên quan")
    state: str = Field(..., description="Trạng thái tác vụ (QUEUED, PROCESSING, COMPLETED, FAILED)")
    stage: str = Field(..., description="Giai đoạn hiện tại (UPLOADED, EXTRACTING, CHUNKING, EMBEDDING, INDEXING)")
    progress_percent: int = Field(default=0, description="Tiến độ thực hiện (%)")
    error: str | None = Field(default=None, description="Nội dung lỗi nếu thất bại")
    poll_after_ms: int = Field(default=1000, description="Thời gian FE đề xuất poll lại (ms)")
