from pydantic import BaseModel, Field


class IndexRebuildRequest(BaseModel):
    document_ids: list[str] | None = Field(
        default=None,
        description="Danh sách ID tài liệu cần re-index (null nếu rebuild toàn bộ)",
    )
    strategy: str = Field(
        default="REPLACE",
        description="Chiến lược tái lập chỉ mục (REPLACE, INCREMENTAL, FULL)",
    )


class IndexRebuildResponseData(BaseModel):
    job_id: str = Field(..., description="ID tác vụ tái lập chỉ mục vừa khởi tạo")
    state: str = Field(default="QUEUED", description="Trạng thái khởi tạo tác vụ (QUEUED)")
    poll_after_ms: int = Field(default=2000, description="Thời gian đề xuất FE poll kiểm tra lại (ms)")


class IndexJobDetailResponseData(BaseModel):
    job_id: str = Field(..., description="ID tác vụ re-index")
    state: str = Field(..., description="Trạng thái tác vụ (QUEUED, PROCESSING, COMPLETED, FAILED)")
    stage: str = Field(default="INDEXING", description="Giai đoạn hiện tại")
    progress_percent: int = Field(default=0, description="Tiến độ hoàn thành (%)")
    active_index_version: str = Field(default="v1.0", description="Phiên bản chỉ mục vector active")
    error: str | None = Field(default=None, description="Thông tin lỗi nếu gặp sự cố")
    poll_after_ms: int = Field(default=2000, description="Thời gian đề xuất poll lại (ms)")
