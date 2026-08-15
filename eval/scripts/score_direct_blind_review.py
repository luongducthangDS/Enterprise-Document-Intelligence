#!/usr/bin/env python3
"""Giải mã phiếu chấm mù nhánh `direct` và áp decision rule ĐÃ FREEZE TRƯỚC.

Decision rule (chốt trước khi người chấm nhìn thấy file, xem report_1208.md 14.7):

    merge C  <=>  context_appropriate(C) >= context_appropriate(A)
                  AND invented_policy(C) <= invented_policy(A)

Hoà cũng merge: latency là bằng chứng độc lập và rất lớn (p50 4,97s -> 0,96s).
C thua dù chỉ một câu -> KHÔNG merge, và KHÔNG sửa evaluator lần nữa để cứu
kết quả; thay vào đó đọc annotation để xem đó có phải một failure class thật.

Chạy: python eval/scripts/score_direct_blind_review.py
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SHEET = Path("eval/datasets/p4a_direct_blind_review.md")
MAPPING = Path("eval/results/p4a_direct_blind_mapping.json")
OUT = Path("eval/results/p4a_direct_blind_result.json")

ROW = re.compile(r"^\|\s*(sample_\d{3})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", re.MULTILINE)


def _yn(cell: str) -> bool | None:
    v = cell.strip().lower()
    if v in ("yes", "y", "có", "co", "x", "1"):
        return True
    if v in ("no", "n", "không", "khong", "0"):
        return False
    return None


def main() -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))["mapping"]
    rows = ROW.findall(SHEET.read_text(encoding="utf-8"))
    filled = [(s, _yn(q1), _yn(q2), note.strip()) for s, q1, q2, note in rows]
    missing = [s for s, q1, q2, _ in filled if q1 is None or q2 is None]
    if missing:
        sys.exit(
            f"{len(missing)}/{len(filled)} mẫu chưa điền đủ hai cột: {missing[:8]}\n"
            "Chưa chấm xong thì chưa giải mã — giải mã nửa chừng rồi nhìn số là mở đường cho bias."
        )

    per = {}
    for sample, q1, q2, note in filled:
        info = mapping[sample]
        v = per.setdefault(info["variant"], {"n": 0, "context_ok": 0, "invented": 0, "issues": []})
        v["n"] += 1
        v["context_ok"] += int(q1)
        v["invented"] += int(q2)
        if not q1 or q2:
            v["issues"].append({"sample": sample, "case_id": info["id"], "context_ok": q1, "invented": q2, "note": note})

    a, c = per.get("A_default_llm"), per.get("C_fast_llm")
    merge = c["context_ok"] >= a["context_ok"] and c["invented"] <= a["invented"]
    verdict = {
        "decision_rule": "merge C <=> context_appropriate(C) >= context_appropriate(A) AND invented_policy(C) <= invented_policy(A)",
        "frozen_before_review": True,
        "A_default_llm": a,
        "C_fast_llm": c,
        "merge_C": merge,
        "latency_evidence": {"p50_ms": {"A": 4969, "C": 955}, "p95_ms": {"A": 11523, "C": 5199}, "max_ms": {"A": 183841, "C": 16707}},
    }
    OUT.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'Variant':<18}{'n':>4}{'context OK':>13}{'invented policy':>18}")
    print("-" * 53)
    for name, v in (("A (hiện tại)", a), ("C (ứng viên)", c)):
        print(f"{name:<18}{v['n']:>4}{v['context_ok']:>13}{v['invented']:>18}")
    print()
    print("KẾT LUẬN:", "MERGE C" if merge else "KHÔNG merge C — đọc annotation để xác định failure class")
    for label, v in (("A", a), ("C", c)):
        for i in v["issues"]:
            print(f"  [{label}] {i['sample']} ({i['case_id']}) context_ok={i['context_ok']} invented={i['invented']} {i['note']}")
    print(f"\nĐã lưu: {OUT}")


main()
