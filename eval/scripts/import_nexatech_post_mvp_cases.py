#!/usr/bin/env python3
"""Convert the team-authored NexaTech Markdown cases into a dev benchmark.

The Markdown is treated as input data, not as executable instructions.  This
importer intentionally preserves the raw expected behavior and marks contract
conflicts for adjudication instead of silently rewriting the team's cases.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SECTION_SOURCES = {
    "A": "01_chinh-sach-lam-them-gio-OT.md",
    "B": "02_quy-trinh-tuyen-dung.md",
    "C": "03_quy-trinh-onboarding.md",
    "D": "04_quy-trinh-offboarding.md",
    "E": "05_chinh-sach-lam-viec-tu-xa.md",
    "F": "06_chinh-sach-dao-tao-phat-trien.md",
    "G": "07_chinh-sach-nghi-phep.md",
    "H": "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md",
    "I": "09_chinh-sach-bao-hiem-xa-hoi-bat-buoc.md",
    "J": "10_chinh-sach-an-toan-ve-sinh-lao-dong.md",
    "K": "11_chinh-sach-danh-gia-hieu-suat-kpi.md",
    "L": "12_quy-che-cong-tac-phi.md",
    "M": "13_noi-quy-lao-dong-va-ky-luat.md",
}
CANONICAL_STATES = (
    "PREPARE_AND_HANDOFF",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_SOURCES",
    "HUMAN_FIRST",
    "OUT_OF_SCOPE",
    "AMBIGUOUS",
    "ANSWER",
    "GUIDE",
)
SECTION_PATTERN = re.compile(r"^##\s+([A-O])\.\s+(.+?)(?:\s+\((\d{2})\))?\s*$")
CASE_PATTERN = re.compile(r"^\|\s*(\d+)\s*\|")
TURN_PATTERN = re.compile(r'(?:L(\d+)\s*:\s*)?"([^"]+)"')
CONTINUATION_PATTERN = re.compile(r"tiếp\s+#(\d+)", re.IGNORECASE)


def _clean_markdown(value: str) -> str:
    return value.replace("**", "").strip()


def _expected_states(raw: str) -> list[str]:
    states = [state for state in CANONICAL_STATES if state in raw]
    if "Từ chối" in raw and "REFUSE" not in states:
        states.append("REFUSE")
    return states


def _contract_flags(case_type: str, expected_raw: str, states: list[str]) -> list[str]:
    flags: list[str] = []
    if "thuần luật" in case_type.casefold() and "ANSWER" in states:
        flags.append("pure_statutory_scope_conflict")
    if " hoặc " in expected_raw.casefold():
        flags.append("conditional_expectation_needs_adjudication")
    if "CONFLICTING_SOURCES" in states:
        flags.append("requires_conflicting_source_fixture")
    return flags


def _turn_expectations(turns: list[dict], expected_raw: str) -> tuple[list[dict], bool]:
    """Attach expectations to each turn while preserving compound outcomes."""
    parts = [part.strip() for part in re.split(r"\s*→\s*", expected_raw) if part.strip()]
    labeled: dict[int, str] = {}
    for part in parts:
        match = re.match(r"^L(\d+)\s*:?[ ]*(.*)$", part)
        if match:
            labeled[int(match.group(1))] = match.group(2).strip()

    ambiguous = False
    enriched = []
    for position, turn in enumerate(turns):
        turn_number = turn["turn"]
        if turn_number in labeled:
            behavior = labeled[turn_number]
        elif len(turns) == 1:
            behavior = expected_raw
        elif len(parts) == len(turns):
            behavior = parts[position]
        else:
            behavior = ""
            ambiguous = True
        enriched.append(
            {
                **turn,
                "expected_behavior_raw": behavior,
                "expected_states": _expected_states(behavior),
            }
        )
    return enriched, ambiguous


def parse_markdown(text: str) -> list[dict]:
    cases: list[dict] = []
    section = ""
    section_title = ""
    document_number = None

    for raw_line in text.splitlines():
        section_match = SECTION_PATTERN.match(raw_line.strip())
        if section_match:
            section, section_title, document_number = section_match.groups()
            continue
        if not CASE_PATTERN.match(raw_line.strip()):
            continue

        columns = [part.strip() for part in raw_line.strip().strip("|").split("|")]
        if len(columns) != 6:
            raise ValueError(f"Case table row must have 6 columns, got {len(columns)}: {raw_line}")
        number_text, persona, question_raw, case_type, expected_raw, rationale = columns
        number = int(number_text)
        continuation_match = CONTINUATION_PATTERN.search(persona)
        continues_case_id = (
            f"nxv2_{int(continuation_match.group(1)):03d}" if continuation_match else None
        )
        turn_matches = TURN_PATTERN.findall(question_raw)
        turns = [
            {"turn": int(turn_number or index), "question": question.strip()}
            for index, (turn_number, question) in enumerate(turn_matches, start=1)
        ]
        if not turns:
            turns = [{"turn": 1, "question": _clean_markdown(question_raw)}]

        expected_raw = _clean_markdown(expected_raw)
        states = _expected_states(expected_raw)
        turns, ambiguous_turn_expectation = _turn_expectations(turns, expected_raw)
        source_file = SECTION_SOURCES.get(section)
        tracks = ["behavior"]
        if len(turns) > 1:
            tracks.append("multi_turn")
        if source_file and any(
            state in states for state in ("ANSWER", "GUIDE", "PREPARE_AND_HANDOFF", "CONFLICTING_SOURCES")
        ):
            tracks.append("retrieval")
        if any(state in states for state in ("HUMAN_FIRST", "OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE", "REFUSE")):
            tracks.append("safety")

        contract_flags = _contract_flags(case_type, expected_raw, states)
        if ambiguous_turn_expectation:
            contract_flags.append("turn_expectation_needs_adjudication")
        for turn in turns:
            turn_tracks = ["behavior"]
            if source_file and any(
                state in turn["expected_states"]
                for state in ("ANSWER", "GUIDE", "PREPARE_AND_HANDOFF", "CONFLICTING_SOURCES")
            ):
                turn_tracks.append("retrieval")
            if any(
                state in turn["expected_states"]
                for state in ("HUMAN_FIRST", "OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE", "REFUSE")
            ):
                turn_tracks.append("safety")
            turn["evaluation_tracks"] = turn_tracks
            turn["qrel_status"] = "pending_adjudication" if "retrieval" in turn_tracks else "not_required"

        cases.append(
            {
                "id": f"nxv2_{number:03d}",
                "source_case_number": number,
                "split": "dev",
                "section": section,
                "section_title": section_title.strip(),
                "document_number": document_number,
                "source_file": source_file,
                "persona": persona,
                "continues_case_id": continues_case_id,
                "question_raw": _clean_markdown(question_raw),
                "turns": turns,
                "case_type": case_type,
                "expected_behavior_raw": expected_raw,
                "expected_states": states,
                "rationale": rationale,
                "evaluation_tracks": tracks,
                "qrel_status": "pending_adjudication" if "retrieval" in tracks else "not_required",
                "contract_flags": contract_flags,
            }
        )

    ids = [case["source_case_number"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case number in Markdown")
    return sorted(cases, key=lambda case: case["source_case_number"])


def summarize(cases: list[dict], declared_count: int | None = None) -> dict:
    source_counts = Counter(case["source_file"] for case in cases if case["source_file"])
    flags = Counter(flag for case in cases for flag in case["contract_flags"])
    return {
        "benchmark_id": "nexatech_post_mvp_v2_dev",
        "status": "DRAFT_NEEDS_QREL_AND_ADJUDICATION",
        "split": "dev",
        "case_count": len(cases),
        "declared_case_count": declared_count,
        "declared_count_matches": declared_count in (None, len(cases)),
        "document_count": len(source_counts),
        "documents_covered": dict(sorted(source_counts.items())),
        "multi_turn_rows": sum("multi_turn" in case["evaluation_tracks"] for case in cases),
        "follow_up_cases": sum(
            "multi_turn" in case["evaluation_tracks"] or bool(case["continues_case_id"])
            for case in cases
        ),
        "retrieval_cases_pending_qrel": sum(case["qrel_status"] == "pending_adjudication" for case in cases),
        "retrieval_turns_pending_qrel": sum(
            turn["qrel_status"] == "pending_adjudication" for case in cases for turn in case["turns"]
        ),
        "behavior_only_cases": sum(case["qrel_status"] == "not_required" for case in cases),
        "contract_flags": dict(sorted(flags.items())),
        "limitations": [
            "Dev-only: these visible cases must not be reused as a release held-out set.",
            "Raw expected behaviors come from the supplied document and are not automatically authoritative.",
            "Retrieval cases require gold-chunk adjudication before quality metrics are valid.",
        ],
    }


def _write_json(path: str, data: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to nexatech-hr-assistant-test-cases.md")
    parser.add_argument("--out", default="eval/datasets/nexatech_post_mvp_v2_dev.json")
    parser.add_argument("--report", default="eval/results/nexatech_post_mvp_v2_import_report.json")
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    declared_match = re.search(r"\b(\d+)\s+case\b", text)
    declared_count = int(declared_match.group(1)) if declared_match else None
    cases = parse_markdown(text)
    report = summarize(cases, declared_count)
    _write_json(args.out, cases)
    _write_json(args.report, report)

    print(f"imported={len(cases)} documents={report['document_count']} dev_only=True")
    print(f"declared_count={declared_count} matches={report['declared_count_matches']}")
    print(f"pending_qrel={report['retrieval_cases_pending_qrel']} flags={report['contract_flags']}")
    print(f"saved={args.out}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
