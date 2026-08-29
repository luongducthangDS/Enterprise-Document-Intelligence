"""Boundary engine — dịch câu hỏi của nhân viên sang canonical runtime decision.

Vì sao tồn tại: router cũ chỉ trả 4 nhãn intent (`greeting`/`hr_question`/
`ambiguous`/`out_of_scope_or_personal`). Nhãn đó KHÔNG nói được assistant được
phép làm gì — nó không phân biệt "trả lời từ KB" với "chỉ được hướng dẫn kênh"
hay "phải để người phụ trách xử lý". Hệ quả là mọi câu không trả lời được đều
rơi vào một nhánh escalate duy nhất và tự tạo ticket, kể cả với scenario mà
thiết kế nghiệp vụ đã chốt là human-first/link-only.

Runtime decision ở đây lấy nguyên văn từ `Runtime-Revised Canonical Scenario
Registry` (docs/project/hr_interaction_boundary_plan.md) thông qua
`resources/scenario_registry.json`. Code KHÔNG suy luận nghiệp vụ từ tên
scenario: mọi trường hành vi (assistant_role, max_runtime_action, owner,
sensitivity, phase) đều đọc thẳng từ registry.

Hai mức action được phân biệt rõ:

    max_runtime_action  — trần theo registry (có thể là CREATE_CASE ở MVP-2).
    runtime_action      — mức thực sự được phép NGAY BÂY GIỜ, sau khi cắt theo
                          capability ceiling của MVP-1 (NONE/LINK_ONLY/
                          PREFILL_DRAFT). CREATE_CASE luôn bị hạ xuống
                          PREFILL_DRAFT — đúng như runtime_behavior của
                          scenario 13/17/20/27/28/45 mô tả ("MVP-1 chỉ draft").

Khi không khớp scenario nào, engine KHÔNG đoán bừa: nó trả về quyết định
fallback bảo thủ (không owner giả, action tối đa LINK_ONLY) để không bịa ra
người phụ trách hay hành động mà hệ thống không có.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent / "resources" / "scenario_registry.json"

# Thứ tự tăng dần về mức can thiệp vào hệ thống. Dùng để cắt trần, không phải
# để so sánh "tốt/xấu".
ACTION_ORDER = ("NONE", "LINK_ONLY", "PREFILL_DRAFT", "CREATE_CASE")

_DIACRITIC_MAP = str.maketrans({"đ": "d", "Đ": "D"})


def _normalize(text: str) -> str:
    text = text.translate(_DIACRITIC_MAP)
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    return " ".join(stripped.lower().split())


@lru_cache
def load_registry() -> dict[str, Any]:
    with REGISTRY_PATH.open(encoding="utf-8") as file:
        registry = json.load(file)
    scenarios = registry.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 64:
        raise ValueError("Scenario registry must contain exactly 64 scenarios")
    return registry


@lru_cache
def _scenarios_by_id() -> dict[int, dict[str, Any]]:
    return {int(item["id"]): item for item in load_registry()["scenarios"]}


@lru_cache
def _services_by_code() -> dict[str, dict[str, Any]]:
    return {item["code"]: item for item in load_registry()["services"]}


@lru_cache
def _departments_by_code() -> dict[str, dict[str, Any]]:
    return {item["code"]: item for item in load_registry()["departments"]}


@lru_cache
def _roles_by_code() -> dict[str, dict[str, Any]]:
    return {item["code"]: item for item in load_registry()["owner_roles"]}


@lru_cache
def _normalized_keywords() -> tuple[tuple[int, str], ...]:
    pairs: list[tuple[int, str]] = []
    for scenario in load_registry()["scenarios"]:
        for keyword in scenario.get("keywords", []):
            pairs.append((int(scenario["id"]), _normalize(keyword)))
    return tuple(pairs)


def get_scenario(scenario_id: int) -> dict[str, Any] | None:
    return _scenarios_by_id().get(scenario_id)


@dataclass(frozen=True)
class BoundaryDecision:
    """Canonical runtime decision đi kèm mọi câu trả lời của assistant."""

    scenario_id: int | None
    scenario_name: str | None
    service_code: str | None
    service_name: str | None
    assistant_role: str
    sensitivity: str
    runtime_source_status: str
    source_of_truth_label: str
    max_runtime_action: str
    runtime_action: str
    mvp_phase: str
    handoff_target: dict[str, str] | None
    user_facing_action_label: str | None
    allowed_data_fields: list[dict[str, Any]] = field(default_factory=list)
    runtime_behavior: str = ""
    resolution: str = "registry"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "service_code": self.service_code,
            "service_name": self.service_name,
            "assistant_role": self.assistant_role,
            "sensitivity": self.sensitivity,
            "runtime_source_status": self.runtime_source_status,
            "source_of_truth_label": self.source_of_truth_label,
            "max_runtime_action": self.max_runtime_action,
            "runtime_action": self.runtime_action,
            "mvp_phase": self.mvp_phase,
            "handoff_target": self.handoff_target,
            "user_facing_action_label": self.user_facing_action_label,
            "allowed_data_fields": self.allowed_data_fields,
            "runtime_behavior": self.runtime_behavior,
            "resolution": self.resolution,
        }


def match_scenario(query: str) -> int | None:
    """Khớp câu hỏi với scenario bằng keyword của registry.

    Cố ý deterministic (không LLM): bước này chạy trên mọi request, và một
    classifier sai nhưng "nghe hợp lý" nguy hiểm hơn hẳn việc trả về None —
    None chỉ mất phần metadata, còn sai scenario có thể gán nhầm owner hoặc
    nới trần action cho một câu hỏi nhạy cảm.

    Ưu tiên keyword dài nhất khớp được (cụ thể hơn thì thắng); nếu hai scenario
    khác nhau cùng độ cụ thể thì trả None thay vì chọn bừa.
    """
    normalized = _normalize(query)
    if not normalized:
        return None

    best_id: int | None = None
    best_length = 0
    best_hits = 0
    ambiguous = False
    hits_by_id: dict[int, int] = {}
    longest_by_id: dict[int, int] = {}

    for scenario_id, keyword in _normalized_keywords():
        if keyword and keyword in normalized:
            hits_by_id[scenario_id] = hits_by_id.get(scenario_id, 0) + 1
            longest_by_id[scenario_id] = max(longest_by_id.get(scenario_id, 0), len(keyword))

    for scenario_id, hits in hits_by_id.items():
        length = longest_by_id[scenario_id]
        if length > best_length or (length == best_length and hits > best_hits):
            best_id, best_length, best_hits, ambiguous = scenario_id, length, hits, False
        elif length == best_length and hits == best_hits and scenario_id != best_id:
            ambiguous = True

    return None if ambiguous else best_id


def cap_action(max_action: str) -> str:
    """Cắt trần theo capability thật của MVP-1.

    CREATE_CASE nằm trong registry như trần MVP-2; MVP-1 chưa có ACL/audit/case
    model nên mọi scenario CREATE_CASE chỉ được chạy tới PREFILL_DRAFT — đúng
    nguyên văn runtime_behavior của các scenario đó.
    """
    ceiling = load_registry()["mvp1_capability_ceiling"]
    if max_action in ceiling:
        return max_action
    allowed = [action for action in ACTION_ORDER if action in ceiling]
    return allowed[-1] if allowed else "NONE"


def _handoff_target(scenario: dict[str, Any]) -> dict[str, str] | None:
    department_code = scenario.get("owner_department")
    if department_code:
        department = _departments_by_code()[department_code]
        return {
            "type": "department",
            "code": department["code"],
            "name": department["name"],
            "contact_label": department["default_contact_label"],
        }
    role_code = scenario.get("owner_role")
    if role_code:
        role = _roles_by_code()[role_code]
        return {"type": "role", "code": role["code"], "name": role["name"], "contact_label": role["name"]}
    return None


def _allowed_fields(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = load_registry()["data_fields"]
    required = set(scenario.get("required_for_prefill", []))
    fields: list[dict[str, Any]] = []
    for key in scenario.get("allowed_data_fields", []):
        spec = catalog[key]
        fields.append(
            {
                "field_key": key,
                "label": spec["label"],
                "required_for_prefill": key in required,
                "pii_class": spec["pii_class"],
                "storage_policy": spec["storage_policy"],
            }
        )
    return fields


def decision_for_scenario(scenario_id: int) -> BoundaryDecision:
    scenario = _scenarios_by_id()[scenario_id]
    registry = load_registry()
    service = _services_by_code()[scenario["service"]]
    runtime_action = cap_action(scenario["max_runtime_action"])
    return BoundaryDecision(
        scenario_id=scenario_id,
        scenario_name=scenario["name"],
        service_code=service["code"],
        service_name=service["name"],
        assistant_role=scenario["assistant_role"],
        sensitivity=scenario["sensitivity"],
        runtime_source_status=scenario["runtime_source_status"],
        source_of_truth_label=registry["source_status_labels"][scenario["runtime_source_status"]],
        max_runtime_action=scenario["max_runtime_action"],
        runtime_action=runtime_action,
        mvp_phase=scenario["mvp_phase"],
        handoff_target=_handoff_target(scenario),
        user_facing_action_label=registry["action_labels"][runtime_action],
        allowed_data_fields=_allowed_fields(scenario),
        runtime_behavior=scenario["runtime_behavior"],
        resolution="registry",
    )


def _fallback_decision(intent: str) -> BoundaryDecision:
    """Quyết định khi không khớp scenario nào.

    Không bịa owner cho nhánh trả lời được (KB tự nói lên nguồn). Với nhánh
    không trả lời được, hướng về HR Ops — bộ phận sở hữu service group
    `Knowledge & Directory` theo Derived HR Service Catalog, chứ không phải một
    phòng ban chọn theo cảm tính.
    """
    registry = load_registry()
    # pure_statutory dùng chung nhánh conservative với out_of_scope_or_personal/
    # ambiguous: không bịa owner, action tối đa LINK_ONLY. Trong thực tế
    # out_of_scope_node (escalation.py) trả response cố định riêng và không đi
    # qua decision này để hiển thị cho user — boundary vẫn được gán để giữ state
    # nhất quán/audit được, không phải nguồn hiển thị chính cho nhánh này.
    if intent in ("out_of_scope_or_personal", "ambiguous", "pure_statutory", "capability_discovery"):
        department = _departments_by_code()["HR_OPS"]
        return BoundaryDecision(
            scenario_id=None,
            scenario_name=None,
            service_code=None,
            service_name=None,
            assistant_role="PREPARE_AND_HANDOFF",
            sensitivity="Medium",
            runtime_source_status="NOT_AVAILABLE",
            source_of_truth_label=registry["source_status_labels"]["NOT_AVAILABLE"],
            max_runtime_action="LINK_ONLY",
            runtime_action="LINK_ONLY",
            mvp_phase="MVP_1",
            handoff_target={
                "type": "department",
                "code": department["code"],
                "name": department["name"],
                "contact_label": department["default_contact_label"],
            },
            user_facing_action_label=registry["action_labels"]["LINK_ONLY"],
            allowed_data_fields=[],
            runtime_behavior="Chưa xác định được scenario canonical; hướng dẫn liên hệ đầu mối HR Ops.",
            resolution="fallback",
        )
    return BoundaryDecision(
        scenario_id=None,
        scenario_name=None,
        service_code=None,
        service_name=None,
        assistant_role="ANSWER",
        sensitivity="Medium",
        runtime_source_status="KNOWLEDGE",
        source_of_truth_label=registry["source_status_labels"]["KNOWLEDGE"],
        max_runtime_action="NONE",
        runtime_action="NONE",
        mvp_phase="MVP_1",
        handoff_target=None,
        user_facing_action_label=None,
        allowed_data_fields=[],
        runtime_behavior="Chưa xác định được scenario canonical; chỉ trả lời từ tài liệu nội bộ.",
        resolution="fallback",
    )


def resolve_boundary(query: str, intent: str = "hr_question") -> BoundaryDecision:
    """Điểm vào duy nhất: câu hỏi + intent -> canonical runtime decision."""
    if intent == "greeting":
        return _fallback_decision("greeting")
    scenario_id = match_scenario(query)
    if scenario_id is None:
        return _fallback_decision(intent)
    return decision_for_scenario(scenario_id)


def is_field_allowed(scenario_id: int | None, field_key: str) -> bool:
    """Data minimization là allowlist: field không có trong registry là không được thu."""
    if scenario_id is None:
        return False
    scenario = _scenarios_by_id().get(scenario_id)
    return bool(scenario) and field_key in scenario.get("allowed_data_fields", [])
