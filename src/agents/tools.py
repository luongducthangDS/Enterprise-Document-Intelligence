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
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

LEAVE_JOB_TYPES = ("normal", "heavy_or_hazardous", "minor_or_disabled", "very_heavy_or_hazardous")


class QueryArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="Câu truy vấn tiếng Việt, cụ thể")


class LeaveArgs(BaseModel):
    job_type: Literal[LEAVE_JOB_TYPES]  # type: ignore[valid-type]
    years_of_service: float = Field(ge=0, le=60, description="Số năm làm việc")


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
