"""Tool registry: một chỗ khai báo mọi tool agent được gọi.

Mỗi tool có: tên, mô tả cho model, schema tham số (pydantic -> JSON schema gửi
cho LLM và dùng để kiểm tham số model trả về), cờ `writes` (tool có ghi ra hệ
thống ngoài hay không: tool ghi phải qua người duyệt), timeout.

Hàm thực thi nằm ở nơi dùng (react node, MCP server) vì cần state/danh tính;
registry chỉ giữ hợp đồng, để agent, MCP và eval cùng đọc một nguồn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, ValidationError

LEAVE_JOB_TYPES = ("normal", "heavy_or_hazardous", "minor_or_disabled", "very_heavy_or_hazardous")


class QueryArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="Câu truy vấn tiếng Việt, cụ thể")


class LeaveArgs(BaseModel):
    job_type: Literal[LEAVE_JOB_TYPES]  # type: ignore[valid-type]
    years_of_service: float = Field(ge=0, le=60, description="Số năm làm việc")


# Tên file, không phải đường dẫn: chặn "../" và "/" ngay ở schema.
def _plain_file_name(v: str) -> str:
    if "/" in v or "\\" in v or ".." in v:
        raise ValueError("chỉ nhận tên file, không nhận đường dẫn")
    return v


SourceFile = Annotated[str, Field(min_length=3, max_length=200), AfterValidator(_plain_file_name)]
_FILE = Field(description="Tên file nguồn, lấy từ kết quả search_policies (phần 'file:')")


class DocArgs(BaseModel):
    source_file: SourceFile = _FILE


class CompareArgs(BaseModel):
    source_files: list[SourceFile] = Field(min_length=2, max_length=3, description="2-3 tên file nguồn cần so")
    aspect: str = Field(min_length=2, max_length=200, description="Khía cạnh cần so, vd 'mức phụ cấp', 'thời hạn nộp chứng từ'")


class ExtractArgs(BaseModel):
    source_file: SourceFile = _FILE
    fields: list[str] = Field(min_length=1, max_length=8, description="Tên các trường cần trích, vd ['hạn nộp', 'người duyệt']")


class EscalateArgs(BaseModel):
    kind: Literal["personal_data", "missing_evidence"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: type[BaseModel]
    writes: bool = False
    timeout_s: float = 30.0

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": _clean(self.args.model_json_schema())},
        }


def _clean(schema: dict) -> dict:
    """Bỏ "title" pydantic tự sinh: thừa token, và một số gateway (Gemini) chỉ nhận tập con OpenAPI."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


REGISTRY: dict[str, ToolSpec] = {
    t.name: t
    for t in [
        ToolSpec(
            "search_policies",
            "Tìm đoạn trích trong kho tài liệu nội bộ (HR, Kế toán, Sản phẩm) mà người dùng được phép xem. "
            "Gọi nhiều lần với query khác nhau nếu câu hỏi có nhiều ý hoặc lần đầu không thấy kết quả.",
            QueryArgs,
        ),
        ToolSpec(
            "lookup_structured_policy",
            "Tra bảng định mức có cấu trúc (hiện có: định mức khách sạn/công tác phí theo địa điểm và chức danh). "
            "Trả về con số chính xác nếu tra được.",
            QueryArgs,
        ),
        ToolSpec(
            "calculate_annual_leave",
            "Tính số ngày phép năm cho một trường hợp cụ thể (loại công việc + số năm thâm niên). "
            "Dùng khi người hỏi nêu thâm niên/loại công việc của họ; không tự cộng nhẩm.",
            LeaveArgs,
        ),
        ToolSpec(
            "get_document",
            "Đọc toàn bộ một tài liệu (khi đoạn trích của search_policies chưa đủ, hoặc cần cả quy trình/bảng).",
            DocArgs,
        ),
        ToolSpec(
            "compare_documents",
            "So sánh 2-3 tài liệu theo một khía cạnh; trả về các mục liên quan của từng tài liệu đặt cạnh nhau.",
            CompareArgs,
        ),
        ToolSpec(
            "extract_structured",
            "Trích các trường cụ thể từ một tài liệu thành dữ liệu có cấu trúc; mỗi giá trị kèm câu trích làm căn cứ, "
            "giá trị không có căn cứ trong tài liệu bị bỏ.",
            ExtractArgs,
            timeout_s=60.0,
        ),
        ToolSpec(
            "escalate_to_human",
            "Chuyển cho người phụ trách khi câu hỏi cần dữ liệu cá nhân, quyết định của con người, "
            "hoặc đã tìm mà tài liệu không có.",
            EscalateArgs,
        ),
    ]
}


def openai_tools(names: list[str] | None = None) -> list[dict]:
    return [REGISTRY[n].openai_schema() for n in (names or REGISTRY)]


class ToolArgsError(ValueError):
    """Tham số model gửi không khớp schema. Nội dung lỗi được trả lại cho model để nó sửa."""


def parse_call(name: str, raw_arguments: str | None) -> tuple[ToolSpec, BaseModel]:
    spec = REGISTRY.get(name)
    if spec is None:
        raise ToolArgsError(f"Tool không tồn tại: {name}. Tool hợp lệ: {', '.join(REGISTRY)}")
    try:
        data = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as e:
        raise ToolArgsError(f"arguments không phải JSON hợp lệ: {e.msg}") from e
    try:
        return spec, spec.args.model_validate(data)
    except ValidationError as e:
        errs = "; ".join(f"{'.'.join(map(str, x['loc'])) or '(root)'}: {x['msg']}" for x in e.errors())
        raise ToolArgsError(f"Tham số {name} không hợp lệ: {errs}") from e
