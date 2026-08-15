"""Sinh seed SQL cho config tables từ canonical scenario registry.

Chạy:
    python scripts/hr_registry/generate_seed_sql.py

Đầu vào duy nhất là `src/agents/resources/scenario_registry.json` — cùng file mà
boundary engine đọc lúc runtime. Mục đích là không bao giờ phải maintain 64
scenario ở hai nơi: DB seed và runtime luôn sinh ra từ một nguồn, còn nguồn đó
lại được `tests/test_scenario_registry.py` so khớp ngược với bảng markdown.

Script KHÔNG kết nối database và KHÔNG chạy migration. Nó chỉ ghi ra file SQL
idempotent (upsert theo khoá tự nhiên) để review trước khi chạy tay.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "src" / "agents" / "resources" / "scenario_registry.json"
OUTPUT_PATH = ROOT / "supabase" / "seeds" / "0001_hr_runtime_registry_seed.sql"


def sql_str(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def build_sql(registry: dict) -> str:
    lines: list[str] = [
        "-- SINH TỰ ĐỘNG bởi scripts/hr_registry/generate_seed_sql.py — không sửa tay.",
        "-- Nguồn: src/agents/resources/scenario_registry.json",
        f"-- Registry version: {registry['version']}",
        "-- Chạy sau migration 0005_hr_runtime_registry.sql.",
        "",
        "begin;",
        "",
        "-- 1. Departments",
    ]

    for dept in registry["departments"]:
        lines.append(
            "insert into public.hr_departments (code, name, description, default_contact_label, sensitivity_cap) "
            f"values ({sql_str(dept['code'])}, {sql_str(dept['name'])}, {sql_str(dept.get('description'))}, "
            f"{sql_str(dept.get('default_contact_label'))}, {sql_str(dept['sensitivity_cap'])}) "
            "on conflict (code) do update set name = excluded.name, description = excluded.description, "
            "default_contact_label = excluded.default_contact_label, "
            "sensitivity_cap = excluded.sensitivity_cap, updated_at = now();"
        )

    lines += ["", "-- 2. Services"]
    for service in registry["services"]:
        escalation = service.get("escalation_department")
        escalation_sql = (
            f"(select id from public.hr_departments where code = {sql_str(escalation)})" if escalation else "null"
        )
        lines.append(
            "insert into public.hr_services (code, name, domain, owner_department_id, default_sensitivity, "
            "default_escalation_department_id) values ("
            f"{sql_str(service['code'])}, {sql_str(service['name'])}, {sql_str(service['domain'])}, "
            f"(select id from public.hr_departments where code = {sql_str(service['owner_department'])}), "
            f"{sql_str(service['default_sensitivity'])}, {escalation_sql}) "
            "on conflict (code) do update set name = excluded.name, domain = excluded.domain, "
            "owner_department_id = excluded.owner_department_id, "
            "default_sensitivity = excluded.default_sensitivity, "
            "default_escalation_department_id = excluded.default_escalation_department_id, updated_at = now();"
        )

    lines += ["", "-- 3. Scenarios (64/64 theo Runtime-Revised Canonical Scenario Registry)"]
    ceiling = registry["mvp1_capability_ceiling"]
    for scenario in registry["scenarios"]:
        owner_dept = scenario.get("owner_department")
        owner_dept_sql = (
            f"(select id from public.hr_departments where code = {sql_str(owner_dept)})" if owner_dept else "null"
        )
        owner_role = scenario.get("owner_role")
        owner_role_name = None
        if owner_role:
            owner_role_name = next(
                item["name"] for item in registry["owner_roles"] if item["code"] == owner_role
            )
        runtime_action = (
            scenario["max_runtime_action"]
            if scenario["max_runtime_action"] in ceiling
            else [action for action in ("NONE", "LINK_ONLY", "PREFILL_DRAFT", "CREATE_CASE") if action in ceiling][-1]
        )
        action_label = registry["action_labels"][runtime_action]
        lines.append(
            "insert into public.scenarios (id, service_id, name, assistant_role, data_dependency, "
            "runtime_source_status, source_of_truth_label, max_runtime_action, final_owner_department_id, "
            "final_owner_role, sensitivity, mvp_phase, runtime_behavior, user_facing_action_label) values ("
            f"{scenario['id']}, "
            f"(select id from public.hr_services where code = {sql_str(scenario['service'])}), "
            f"{sql_str(scenario['name'])}, {sql_str(scenario['assistant_role'])}, "
            f"{sql_str(scenario['data_dependency'])}, {sql_str(scenario['runtime_source_status'])}, "
            f"{sql_str(registry['source_status_labels'][scenario['runtime_source_status']])}, "
            f"{sql_str(scenario['max_runtime_action'])}, {owner_dept_sql}, {sql_str(owner_role_name)}, "
            f"{sql_str(scenario['sensitivity'])}, {sql_str(scenario['mvp_phase'])}, "
            f"{sql_str(scenario['runtime_behavior'])}, {sql_str(action_label)}) "
            "on conflict (id) do update set service_id = excluded.service_id, name = excluded.name, "
            "assistant_role = excluded.assistant_role, data_dependency = excluded.data_dependency, "
            "runtime_source_status = excluded.runtime_source_status, "
            "source_of_truth_label = excluded.source_of_truth_label, "
            "max_runtime_action = excluded.max_runtime_action, "
            "final_owner_department_id = excluded.final_owner_department_id, "
            "final_owner_role = excluded.final_owner_role, sensitivity = excluded.sensitivity, "
            "mvp_phase = excluded.mvp_phase, runtime_behavior = excluded.runtime_behavior, "
            "user_facing_action_label = excluded.user_facing_action_label, updated_at = now();"
        )

    lines += ["", "-- 4. Allowed data fields (allowlist data minimization)"]
    catalog = registry["data_fields"]
    for scenario in registry["scenarios"]:
        required = set(scenario.get("required_for_prefill", []))
        for field_key in scenario.get("allowed_data_fields", []):
            spec = catalog[field_key]
            lines.append(
                "insert into public.scenario_allowed_data_fields (scenario_id, field_key, label, "
                "required_for_prefill, pii_class, storage_policy) values ("
                f"{scenario['id']}, {sql_str(field_key)}, {sql_str(spec['label'])}, "
                f"{str(field_key in required).lower()}, {sql_str(spec['pii_class'])}, "
                f"{sql_str(spec['storage_policy'])}) "
                "on conflict (scenario_id, field_key) do update set label = excluded.label, "
                "required_for_prefill = excluded.required_for_prefill, pii_class = excluded.pii_class, "
                "storage_policy = excluded.storage_policy;"
            )

    lines += [
        "",
        "-- Field không còn nằm trong allowlist của scenario thì phải biến mất khỏi DB,",
        "-- nếu không allowlist ở DB sẽ rộng hơn allowlist ở registry.",
        "delete from public.scenario_allowed_data_fields f where not exists (",
        "  select 1 from (values",
    ]
    pairs = [
        f"    ({scenario['id']}, {sql_str(field_key)})"
        for scenario in registry["scenarios"]
        for field_key in scenario.get("allowed_data_fields", [])
    ]
    lines.append(",\n".join(pairs))
    lines += [
        "  ) as allowed(scenario_id, field_key)",
        "  where allowed.scenario_id = f.scenario_id and allowed.field_key = f.field_key",
        ");",
        "",
        "commit;",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_sql(registry), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} ({len(registry['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
