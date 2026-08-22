#!/usr/bin/env python3
"""Static schema and document-reference checks for a guardrail dataset."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--registry", required=True)
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        conversations = json.load(handle)
    with open(args.registry, encoding="utf-8-sig", newline="") as handle:
        known_documents = {row["source_file"] for row in csv.DictReader(handle)}

    problems: list[str] = []
    ids = [conversation.get("conversation_id") for conversation in conversations]
    if len(ids) != len(set(ids)):
        problems.append("conversation_id bị trùng")

    for conversation in conversations:
        conversation_id = conversation.get("conversation_id", "<missing>")
        if not conversation.get("risk_type") or not conversation.get("turns"):
            problems.append(f"{conversation_id}: thiếu risk_type hoặc turns")
        unknown = set(conversation.get("required_documents", [])) - known_documents
        if unknown:
            problems.append(f"{conversation_id}: tài liệu không có trong registry: {sorted(unknown)}")
        turn_numbers = [turn.get("turn") for turn in conversation.get("turns", [])]
        if turn_numbers != list(range(1, len(turn_numbers) + 1)):
            problems.append(f"{conversation_id}: số thứ tự turn không liên tục")
        focus_turns = [turn for turn in conversation.get("turns", []) if turn.get("risk_focus")]
        if not focus_turns:
            problems.append(f"{conversation_id}: không có risk_focus turn")
        for turn in focus_turns:
            if not turn.get("expected_behavior") or not turn.get("must_not"):
                problems.append(f"{conversation_id}/turn-{turn.get('turn')}: thiếu rubric")

    if problems:
        print(f"FAIL {args.dataset}")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"PASS {args.dataset}: {len(conversations)} conversations")
    return 0


if __name__ == "__main__":
    sys.exit(main())