"""Khoá canonical scenario registry vào các ràng buộc đã freeze.

Registry JSON là biểu diễn machine-readable; bảng markdown trong
`docs/project/hr_interaction_boundary_plan.md` vẫn là business source-of-truth.
Test đầu tiên ở đây so khớp ngược hai nguồn để JSON không âm thầm trở thành
nguồn thứ hai cạnh tranh. Các test còn lại khoá invariant runtime: nếu ai đó
nới trần action cho một scenario nhạy cảm hoặc để lộ nhãn kỹ thuật ra UI thì
build phải đỏ.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.boundary import ACTION_ORDER, cap_action, load_registry

BOUNDARY_DOC = Path(__file__).resolve().parents[1] / "docs" / "project" / "hr_interaction_boundary_plan.md"
REGISTRY_HEADING = "## Runtime-Revised Canonical Scenario Registry"

# Từ kỹ thuật không được xuất hiện trong bất kỳ chuỗi nào có thể hiển thị cho
# người dùng. `SIMULATED_IN_PRODUCT` là engineering metadata, không phải nhãn UI.
FORBIDDEN_UI_WORDS = ("simulated", "synthetic", "demo", "mô phỏng", "mo phong")


@pytest.fixture(scope="module")
def registry() -> dict:
    return load_registry()


def _markdown_rows() -> dict[int, dict[str, str]]:
    text = BOUNDARY_DOC.read_text(encoding="utf-8")
    section = text.split(REGISTRY_HEADING, 1)[1].split("\n## ", 1)[0]
    rows: dict[int, dict[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        rows[int(cells[0])] = {
            "name": cells[1],
            "owner": cells[2],
            "runtime_source_status": cells[3],
            "max_runtime_action": cells[4],
            "mvp_phase": cells[5],
            "runtime_behavior": cells[6],
        }
    return rows


def test_markdown_table_parses_all_64_rows():
    assert len(_markdown_rows()) == 64


def test_registry_matches_markdown_source_of_truth(registry):
    """Các cột markdown sở hữu phải khớp từng ký tự với JSON.

    Đây là parity verification một chiều: markdown xác nhận JSON, KHÔNG bổ sung
    dữ liệu cho JSON. Runtime/seed/eval không đọc file markdown này.
    """
    rows = _markdown_rows()
    # Cột nào thuộc markdown là do registry tự khai, để danh sách không trôi
    # khỏi test khi ai đó thêm/bớt field.
    owned = registry["field_ownership"]["verified_against_markdown"]
    column_of = {
        "id": "id",
        "name": "name",
        "owner_raw": "owner",
        "runtime_source_status": "runtime_source_status",
        "max_runtime_action": "max_runtime_action",
        "mvp_phase": "mvp_phase",
        "runtime_behavior": "runtime_behavior",
    }
    assert set(owned) == set(column_of), "field_ownership khai không khớp với cột markdown thực có"
    for scenario in registry["scenarios"]:
        row = rows[scenario["id"]]
        for field in owned:
            if field == "id":
                continue
            assert scenario[field] == row[column_of[field]], f"scenario {scenario['id']}: {field} lệch"


def test_registry_is_self_contained_for_runtime(registry):
    """Mọi field runtime cần phải có sẵn trong JSON.

    Nếu một scenario thiếu key, runtime sẽ buộc phải đi tìm nguồn khác — đúng
    thứ kiến trúc freeze cấm. Test này khoá lại: canonical registry đủ dùng một
    mình.
    """
    ownership = registry["field_ownership"]
    expected_keys = set(ownership["verified_against_markdown"]) | set(ownership["canonical_here"])
    for scenario in registry["scenarios"]:
        assert set(scenario) == expected_keys, f"scenario {scenario['id']} có key lệch so với field_ownership"


def test_divergence_resolutions_are_reflected_in_the_data(registry):
    """Mỗi divergence đã chốt phải khớp dữ liệu thật, không phải ghi chú suông."""
    resolutions = {(item["scenario_id"], item["field"]): item for item in registry["divergence_resolutions"]}
    assert (48, "sensitivity") in resolutions
    assert (55, "allowed_data_fields.process_question") in resolutions
    for item in registry["divergence_resolutions"]:
        assert item["rationale"] and item["doc_reference"], "resolution phải nêu lý do và nguồn tài liệu"

    scenarios = {scenario["id"]: scenario for scenario in registry["scenarios"]}
    assert scenarios[48]["sensitivity"] == "High"
    assert "process_question" in scenarios[55]["allowed_data_fields"]
    assert "question_summary" not in scenarios[55]["allowed_data_fields"]
    process_question = registry["data_fields"]["process_question"]
    assert process_question["pii_class"] == "High"
    assert process_question["storage_policy"] == "store_case_only"


def test_exactly_64_scenarios_without_duplicate_or_missing_id(registry):
    ids = [scenario["id"] for scenario in registry["scenarios"]]
    assert len(ids) == 64
    assert len(set(ids)) == 64
    assert sorted(ids) == list(range(1, 65))


def test_every_owner_is_normalized_to_one_accountable_target(registry):
    departments = {item["code"] for item in registry["departments"]}
    roles = {item["code"] for item in registry["owner_roles"]}
    for scenario in registry["scenarios"]:
        department, role = scenario.get("owner_department"), scenario.get("owner_role")
        assert bool(department) != bool(role), f"scenario {scenario['id']} phải có đúng 1 owner"
        assert department is None or department in departments
        assert role is None or role in roles


def test_services_and_fields_resolve(registry):
    services = {item["code"] for item in registry["services"]}
    departments = {item["code"] for item in registry["departments"]}
    catalog = registry["data_fields"]
    for service in registry["services"]:
        assert service["owner_department"] in departments
        escalation = service.get("escalation_department")
        assert escalation is None or escalation in departments
    for scenario in registry["scenarios"]:
        assert scenario["service"] in services
        for field_key in scenario["allowed_data_fields"]:
            assert field_key in catalog, f"scenario {scenario['id']}: field {field_key} không có trong catalog"
        assert set(scenario["required_for_prefill"]) <= set(scenario["allowed_data_fields"])


def test_data_field_catalog_has_no_orphan_entry(registry):
    """Catalog thừa field là cách âm thầm nới allowlist khi ai đó copy field key."""
    used = {key for scenario in registry["scenarios"] for key in scenario["allowed_data_fields"]}
    assert set(registry["data_fields"]) == used


def test_no_read_status_or_create_request_anywhere(registry):
    """Hai action này đã bị runtime contract chuyển sang future integration."""
    actions = {scenario["max_runtime_action"] for scenario in registry["scenarios"]}
    assert actions <= set(ACTION_ORDER)
    assert "READ_STATUS" not in actions
    assert "CREATE_REQUEST" not in actions


def test_create_case_limited_to_mvp2_allowlist(registry):
    allowlist = set(registry["mvp2_create_case_allowlist"])
    for scenario in registry["scenarios"]:
        if scenario["max_runtime_action"] == "CREATE_CASE":
            assert scenario["id"] in allowlist, f"scenario {scenario['id']} không nằm trong allowlist CREATE_CASE"
            assert scenario["mvp_phase"] == "MVP_2"
            assert scenario["sensitivity"] != "Critical", "scenario Critical không được phép tạo case"
            assert scenario["assistant_role"] != "HUMAN_FIRST"


def test_mvp1_runtime_never_reaches_create_case(registry):
    for scenario in registry["scenarios"]:
        assert cap_action(scenario["max_runtime_action"]) != "CREATE_CASE"


def test_answer_role_cannot_take_system_action(registry):
    for scenario in registry["scenarios"]:
        if scenario["assistant_role"] == "ANSWER":
            assert scenario["max_runtime_action"] == "NONE"


def test_human_first_never_creates_workflow(registry):
    for scenario in registry["scenarios"]:
        if scenario["assistant_role"] == "HUMAN_FIRST":
            assert scenario["max_runtime_action"] in ("NONE", "LINK_ONLY", "PREFILL_DRAFT")


def test_sensitive_scenarios_have_restricted_data_collection(registry):
    """Scenario Critical chỉ được thu field triage, không thu nội dung chi tiết."""
    catalog = registry["data_fields"]
    for scenario in registry["scenarios"]:
        if scenario["sensitivity"] != "Critical":
            continue
        assert scenario["required_for_prefill"] == [], f"scenario {scenario['id']} không được bắt buộc nhập field"
        for field_key in scenario["allowed_data_fields"]:
            assert catalog[field_key]["pii_class"] in ("High", "Critical")
            assert catalog[field_key]["storage_policy"] in ("do_not_store", "store_case_only")


def test_user_facing_strings_have_no_engineering_labels(registry):
    surfaces = [
        *(label for label in registry["action_labels"].values() if label),
        *registry["source_status_labels"].values(),
        *(item["name"] for item in registry["departments"]),
        *(item["default_contact_label"] for item in registry["departments"]),
        *(item["name"] for item in registry["owner_roles"]),
        *(item["name"] for item in registry["services"]),
        *(spec["label"] for spec in registry["data_fields"].values()),
        *(scenario["name"] for scenario in registry["scenarios"]),
    ]
    for text in surfaces:
        lowered = text.lower()
        for word in FORBIDDEN_UI_WORDS:
            assert word not in lowered, f"chuỗi user-facing chứa từ kỹ thuật {word!r}: {text}"


def test_registry_contains_no_urls(registry):
    """Không fake portal URL: registry không được chứa bất kỳ link nào."""
    blob = str(registry)
    assert not re.search(r"https?://", blob)
