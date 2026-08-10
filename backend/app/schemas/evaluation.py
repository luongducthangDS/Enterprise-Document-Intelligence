from typing import Any

from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    dataset_id: str = Field(
        ...,
        description="ID bộ dữ liệu test dùng để đánh giá RAG/LLM (ví dụ: evalset_hr_v1)",
    )
    index_version: str | None = Field(
        default=None,
        description="Phiên bản chỉ mục vector cần đánh giá (ví dụ: idxver_v1.0)",
    )
    model_config_id: str | None = Field(
        default=None,
        description="ID cấu hình mô hình LLM dùng để đo lường (ví dụ: modelcfg_gpt4o)",
    )


class EvaluationRunResponseData(BaseModel):
    run_id: str = Field(..., description="ID lượt đánh giá vừa khởi tạo")
    state: str = Field(default="QUEUED", description="Trạng thái khởi tạo (QUEUED)")
    poll_after_ms: int = Field(default=3000, description="Thời gian đề xuất FE poll lại (ms)")


class EvaluationMetricsDTO(BaseModel):
    recall_at_5: float | None = Field(default=None, description="Tỷ lệ thu hồi thông tin Top-5")
    answer_correctness: float | None = Field(default=None, description="Độ chính xác câu trả lời LLM")
    citation_coverage: float | None = Field(default=None, description="Tỷ lệ phủ trích dẫn tài liệu")
    citation_correctness: float | None = Field(default=None, description="Độ chính xác của đoạn trích dẫn")
    p95_latency_ms: int | float | None = Field(default=None, description="Độ trễ phản hồi P95 (ms)")


class EvaluationRunDetailResponseData(BaseModel):
    run_id: str = Field(..., description="ID lượt đánh giá")
    dataset_id: str = Field(..., description="ID bộ câu hỏi test")
    state: str = Field(..., description="Trạng thái (QUEUED, PROCESSING, COMPLETED, FAILED)")
    stage: str = Field(default="QUEUED", description="Giai đoạn chạy thử nghiệm")
    progress_percent: int = Field(default=0, description="Tiến độ thực hiện (%)")
    metrics: EvaluationMetricsDTO | dict[str, Any] | None = Field(default=None, description="Các chỉ số chất lượng RAG")
    quality_gate: str = Field(default="PENDING", description="Kết quả Quality Gate (PASSED, FAILED, PENDING)")
    error: str | None = Field(default=None, description="Thông tin lỗi nếu có")
    poll_after_ms: int = Field(default=3000, description="Thời gian đề xuất poll kiểm tra lại (ms)")
