#!/usr/bin/env python3
"""Đo boundary engine: scenario mapping + các chiều của canonical runtime decision.

Khác với eval_router.py (đo 4 nhãn intent, tốn 1 LLM call/câu), runner này
KHÔNG gọi LLM: boundary engine là deterministic, nên eval chạy được trong CI,
miễn phí và lặp lại được.

Đo 5 chiều thay vì chỉ scenario accuracy, vì mức thiệt hại của lỗi rất khác
nhau: map nhầm 20 -> 27 (cùng C&B, cùng PREPARE_AND_HANDOFF) chỉ sai nhãn, còn
map nhầm một scenario ER Critical sang scenario hành chính là hỏng ranh giới.
Hai loại lỗi đó phải nhìn thấy tách nhau.

Ngoài accuracy còn kiểm tra invariant: không quyết định nào được vượt trần
MVP-1, và scenario human-first/Critical không được sinh ra action tạo workflow.

LƯU Ý VỀ ĐỘ TIN CẬY: bộ câu hỏi hiện tại do tác giả registry viết nên có thiên
lệch về đúng từ khóa đã khai. Nó dùng làm regression baseline, chưa phải ước
lượng accuracy khách quan — cần bộ held-out do người khác viết (xem báo cáo).

Chạy: python eval/scripts/eval_boundary.py [--dataset ...] [--out ...]
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.boundary import decision_for_scenario, load_registry, resolve_boundary  # noqa: E402

DEFAULT_DATASET = "eval/datasets/boundary_eval_set.json"
DEFAULT_OUT = "eval/results/boundary_eval_report.json"


def _owner_code(decision) -> str | None:
    target = decision.handoff_target or {}
    return target.get("code")


def evaluate(dataset: list[dict]) -> dict:
    rows = []
    dimensions = Counter()
    totals = Counter()
    violations = []

    for item in dataset:
        expected_id = item["expected_scenario_id"]
        # Intent giả định là hr_question cho mọi câu: runner này đo riêng lớp
        # boundary, không đo router. Câu negative vẫn phải ra scenario None.
        decision = resolve_boundary(item["question"], "hr_question")
        predicted_id = decision.scenario_id

        row = {
            "id": item["id"],
            "expected_scenario_id": expected_id,
            "predicted_scenario_id": predicted_id,
            "scenario_ok": predicted_id == expected_id,
        }

        totals["scenario"] += 1
        dimensions["scenario"] += int(row["scenario_ok"])

        if expected_id is not None:
            expected = decision_for_scenario(expected_id)
            for name, actual, wanted in (
                ("assistant_role", decision.assistant_role, expected.assistant_role),
                ("runtime_action", decision.runtime_action, expected.runtime_action),
                ("max_runtime_action", decision.max_runtime_action, expected.max_runtime_action),
                ("sensitivity", decision.sensitivity, expected.sensitivity),
                ("handoff_owner", _owner_code(decision), _owner_code(expected)),
            ):
                totals[name] += 1
                dimensions[name] += int(actual == wanted)
                row[name] = {"expected": wanted, "predicted": actual}

        if decision.runtime_action == "CREATE_CASE":
            violations.append({"id": item["id"], "rule": "mvp1_no_create_case"})
        if decision.assistant_role == "HUMAN_FIRST" and decision.runtime_action not in ("NONE", "LINK_ONLY", "PREFILL_DRAFT"):
            violations.append({"id": item["id"], "rule": "human_first_no_workflow"})
        if decision.sensitivity == "Critical" and any(
            field["required_for_prefill"] for field in decision.allowed_data_fields
        ):
            violations.append({"id": item["id"], "rule": "critical_no_required_field"})

        rows.append(row)

    metrics = {
        name: round(dimensions[name] / totals[name], 4) if totals[name] else None
        for name in ("scenario", "assistant_role", "runtime_action", "max_runtime_action", "sensitivity", "handoff_owner")
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_version": load_registry()["version"],
        "dataset_size": len(dataset),
        "metrics": metrics,
        "counts": {name: {"correct": dimensions[name], "total": totals[name]} for name in totals},
        "invariant_violations": violations,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as file:
        dataset = json.load(file)

    report = evaluate(dataset)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(f"dataset: {args.dataset} ({report['dataset_size']} câu)")
    for name, value in report["metrics"].items():
        count = report["counts"].get(name, {})
        print(f"  {name:20s} {value}  ({count.get('correct')}/{count.get('total')})")
    print(f"invariant violations: {len(report['invariant_violations'])}")
    for row in report["rows"]:
        if not row["scenario_ok"]:
            print(f"  MISS {row['id']}: expected={row['expected_scenario_id']} predicted={row['predicted_scenario_id']}")
    print(f"report: {args.out}")
    return 1 if report["invariant_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
