#!/usr/bin/env python3
"""Run the NexaTech post-MVP behavior benchmark through the real agent.

The imported document mixes three different contracts: runtime state,
scenario-boundary role, and response behavior.  This runner converts only the
unambiguous parts into deterministic signals.  It does not call an LLM judge
and does not claim semantic answer correctness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.config import get_settings  # noqa: E402

DEFAULT_DATASET = "eval/datasets/nexatech_post_mvp_v2_dev.json"
DEFAULT_OUT = "eval/results/nexatech_post_mvp_v2_agent_behavior.json"
ASSISTANT_ROLES = ("HUMAN_FIRST", "PREPARE_AND_HANDOFF", "GUIDE", "ANSWER")
UNSCORABLE_FLAGS = {
    "conditional_expectation_needs_adjudication",
    "requires_conflicting_source_fixture",
}


def expected_signals(states: list[str], contract_flags: list[str]) -> tuple[dict[str, object], str | None]:
    """Translate imported labels into non-contradictory runtime signals."""
    state_set = set(states)
    flags = set(contract_flags)
    blocked = sorted(flags & UNSCORABLE_FLAGS)
    if blocked:
        return {}, f"unresolved_contract_flag:{','.join(blocked)}"
    if "CONFLICTING_SOURCES" in state_set:
        return {}, "missing_conflicting_source_fixture"

    # The frozen Type-C contract is authoritative over the imported document's
    # stale ANSWER expectation for a pure statutory query.
    if "pure_statutory_scope_conflict" in flags:
        return {"runtime_state": "OUT_OF_SCOPE"}, None

    signals: dict[str, object] = {}
    if "AMBIGUOUS" in state_set:
        signals["needs_clarification"] = True
    if "REFUSE" in state_set:
        signals["competitor_refusal"] = True

    expected_role = next((role for role in ASSISTANT_ROLES if role in state_set), None)
    if expected_role:
        signals["assistant_role"] = expected_role

    if "INSUFFICIENT_EVIDENCE" in state_set:
        signals["runtime_state"] = "ABSTAIN"
    elif "OUT_OF_SCOPE" in state_set and not state_set.intersection({"ANSWER", "HUMAN_FIRST"}):
        signals["runtime_state"] = "OUT_OF_SCOPE"
    elif state_set.intersection({"ANSWER", "GUIDE"}) and "HUMAN_FIRST" not in state_set:
        # OUT_OF_SCOPE + ANSWER means ignore the external comparison and answer
        # the internal-policy portion, so ANSWER wins for runtime state.
        signals["runtime_state"] = "ANSWER"

    if not signals:
        return {}, "no_deterministic_signal"
    return signals, None


def evaluate_signals(signals: dict[str, object], result: dict) -> tuple[dict[str, bool], bool]:
    boundary = result.get("boundary") or {}
    checks: dict[str, bool] = {}
    if "runtime_state" in signals:
        checks["runtime_state"] = result.get("state") == signals["runtime_state"]
    if "assistant_role" in signals:
        checks["assistant_role"] = boundary.get("assistant_role") == signals["assistant_role"]
    if "needs_clarification" in signals:
        checks["needs_clarification"] = bool(result.get("needs_clarification")) is signals["needs_clarification"]
    if "competitor_refusal" in signals:
        checks["competitor_refusal"] = (
            not result.get("escalate", False) and result.get("escalate_reason") == "competitor_question"
        )
    return checks, bool(checks) and all(checks.values())


async def run_case(case: dict, semaphore: asyncio.Semaphore) -> list[dict]:
    history: list[dict[str, str]] = []
    rows: list[dict] = []
    async with semaphore:
        for turn in case.get("turns", []):
            turn_id = f"{case['id']}_l{turn['turn']}"
            signals, unscored_reason = expected_signals(
                turn.get("expected_states") or [], case.get("contract_flags") or []
            )
            started = time.perf_counter()
            try:
                result = await agent.ainvoke({"query": turn["question"], "history": history})
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                checks, passed = evaluate_signals(signals, result) if signals else ({}, False)
                boundary = result.get("boundary") or {}
                row = {
                    "id": turn_id,
                    "case_id": case["id"],
                    "turn": turn["turn"],
                    "section": case.get("section"),
                    "question": turn["question"],
                    "expected_states": turn.get("expected_states") or [],
                    "expected_signals": signals,
                    "unscored_reason": unscored_reason,
                    "scored": bool(signals),
                    "passed": passed if signals else None,
                    "checks": checks,
                    "actual": {
                        "intent": result.get("intent"),
                        "runtime_state": result.get("state"),
                        "reason_code": result.get("reason_code"),
                        "assistant_role": boundary.get("assistant_role"),
                        "runtime_action": boundary.get("runtime_action"),
                        "needs_clarification": bool(result.get("needs_clarification")),
                        "escalate": bool(result.get("escalate")),
                        "escalate_reason": result.get("escalate_reason"),
                    },
                    "retrieved_chunk_ids": [chunk.get("chunk_id") for chunk in result.get("retrieved_chunks", [])],
                    "citation_chunk_ids": [citation.get("chunk_id") for citation in result.get("citations", [])],
                    "response": result.get("response") or "",
                    "latency_ms": latency_ms,
                    "error": None,
                }
                history.extend(
                    [
                        {"role": "user", "content": turn["question"]},
                        {"role": "assistant", "content": result.get("response") or ""},
                    ]
                )
            except Exception as exc:  # noqa: BLE001 - isolate one turn and preserve prior work
                row = {
                    "id": turn_id,
                    "case_id": case["id"],
                    "turn": turn["turn"],
                    "section": case.get("section"),
                    "question": turn["question"],
                    "expected_states": turn.get("expected_states") or [],
                    "expected_signals": signals,
                    "unscored_reason": unscored_reason,
                    "scored": bool(signals),
                    "passed": False if signals else None,
                    "checks": {},
                    "actual": {},
                    "retrieved_chunk_ids": [],
                    "citation_chunk_ids": [],
                    "response": "",
                    "latency_ms": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            rows.append(row)
    return rows


def build_report(rows: list[dict], dataset_path: str) -> dict:
    scored = [row for row in rows if row["scored"]]
    passed = [row for row in scored if row["passed"]]
    signal_totals: Counter[str] = Counter()
    signal_passes: Counter[str] = Counter()
    for row in scored:
        for name, ok in row["checks"].items():
            signal_totals[name] += 1
            signal_passes[name] += int(ok)
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "status": "DEV_DIAGNOSTIC",
        "dataset": dataset_path,
        "model": get_settings().llm_model,
        "judge_used": False,
        "semantic_answer_correctness_measured": False,
        "limitations": [
            "The supplied expected behaviors are imported test intentions, not independent release labels.",
            "Only deterministic runtime-state, boundary-role, clarification, and refusal signals are scored.",
            "Response content still needs blind human review or a separately configured judge API.",
        ],
        "total_turns": len(rows),
        "scored_turns": len(scored),
        "unscored_turns": len(rows) - len(scored),
        "passed_turns": len(passed),
        "behavior_match_rate": round(len(passed) / len(scored), 4) if scored else None,
        "error_count": sum(bool(row["error"]) for row in rows),
        "signal_metrics": {
            name: {
                "passed": signal_passes[name],
                "total": total,
                "rate": round(signal_passes[name] / total, 4),
            }
            for name, total in sorted(signal_totals.items())
        },
        "unscored_reasons": dict(sorted(Counter(row["unscored_reason"] for row in rows if not row["scored"]).items())),
        "rows": sorted(rows, key=lambda row: (row["case_id"], row["turn"])),
    }


def _write_json(path: str, value: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, output)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit-cases", type=int)
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        cases = json.load(handle)
    if args.limit_cases:
        cases = cases[: args.limit_cases]

    semaphore = asyncio.Semaphore(args.concurrency)
    rows: list[dict] = []
    completed = 0
    for task in asyncio.as_completed([run_case(case, semaphore) for case in cases]):
        case_rows = await task
        rows.extend(case_rows)
        completed += 1
        report = build_report(rows, args.dataset)
        _write_json(args.out, report)
        case_id = case_rows[0]["case_id"] if case_rows else "empty"
        case_passed = sum(row["passed"] is True for row in case_rows)
        case_scored = sum(row["scored"] for row in case_rows)
        print(f"[{completed}/{len(cases)}] {case_id}: {case_passed}/{case_scored} scored turns")

    report = build_report(rows, args.dataset)
    _write_json(args.out, report)
    print(
        f"behavior={report['passed_turns']}/{report['scored_turns']} "
        f"({report['behavior_match_rate']:.1%}) unscored={report['unscored_turns']} "
        f"errors={report['error_count']}"
    )
    print(f"saved={args.out}")
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
