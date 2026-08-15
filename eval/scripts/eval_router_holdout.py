#!/usr/bin/env python3
"""Chạy router trên fresh holdout — ĐÚNG MỘT LẦN. Xem eval/ROUTER_HOLDOUT_BRIEF.md.

Khác `eval_router.py` ở ba điểm, đều nhằm bảo vệ tính held-out:

1. Tự ghi sha256 của dataset + router.py + config vào report, để sau này chứng
   minh được kết quả thuộc về đúng phiên bản nào.
2. Từ chối chạy nếu report cũ đã tồn tại — bộ holdout chỉ được tiêu một lần;
   chạy lại rồi chọn lần đẹp hơn thì nó mất sạch ý nghĩa. Muốn chạy lại thật
   sự thì phải xoá file tay, và hành động đó là có chủ đích.
3. Chấm theo GATE HƯỚNG LỖI, không phải ngưỡng accuracy — với n = 60-80 thì
   một câu đã dịch ~1,5 điểm, đòi accuracy tuyệt đối là đòi sai thống kê.

Chạy: python eval/scripts/eval_router_holdout.py [--concurrency N]
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.router import router_node  # noqa: E402
from src.config import get_settings  # noqa: E402

DATASET = Path("eval/datasets/router_holdout_v1.json")
RESULTS = Path("eval/results/router_holdout_v1_report.json")
VALID_TYPES = {"greeting", "hr_question", "ambiguous", "out_of_scope_or_personal"}


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _gates(results: list[dict]) -> dict:
    """Gate theo HƯỚNG lỗi. Không có ngưỡng accuracy — xem brief mục 7."""
    gold_hr = [r for r in results if r["expected_intent"] == "hr_question"]
    gold_amb = [r for r in results if r["expected_intent"] == "ambiguous"]
    gold_oos = [r for r in results if r["expected_intent"] == "out_of_scope_or_personal"]
    hr_rejected = [r["id"] for r in gold_hr if r["predicted_intent"] == "out_of_scope_or_personal"]
    oos_leak = [r["id"] for r in gold_oos if r["predicted_intent"] == "hr_question"]
    ucr = [r["id"] for r in gold_hr if r["predicted_intent"] == "ambiguous"]
    uar = [r["id"] for r in gold_amb if r["predicted_intent"] == "hr_question"]
    lat = sorted(r["latency_ms"] for r in results)
    p50 = lat[len(lat) // 2] if lat else 0
    return {
        "hr_false_rejection": {
            "ids": hr_rejected,
            "count": len(hr_rejected),
            "denominator": len(gold_hr),
            "gate": "0, tối đa 1 nếu review được",
            "passed": len(hr_rejected) <= 1,
            "needs_review": len(hr_rejected) == 1,
        },
        "oos_leak": {
            "ids": oos_leak,
            "count": len(oos_leak),
            "denominator": len(gold_oos),
            "gate": "0",
            "passed": len(oos_leak) == 0,
        },
        "uar": {"ids": uar, "count": len(uar), "denominator": len(gold_amb), "gate": "bot không trở nên liều"},
        "ucr": {"ids": ucr, "count": len(ucr), "denominator": len(gold_hr), "gate": "ở mức chấp nhận được"},
        "router_p50_ms": {"value": p50, "gate": "< 500 ms", "passed": p50 < 500},
    }


async def _run_one(item: dict) -> dict:
    """Chạy TUẦN TỰ có điều tiết, không song song.

    Lý do: fast router trả lời trong ~0,35s nên chạy song song đập ngay rate
    limit 429 của gateway (đã đo ở các lần A/B trước). Khi đó backoff 3-9s lọt
    vào phép đo và làm phồng latency — mà latency lại chính là một trong các
    gate của bộ holdout này. Chậm hơn vài chục giây đổi lấy con số đo đúng.
    """
    t0 = time.perf_counter()
    for attempt in range(4):
        try:
            out = await router_node({"query": item["question"]})
            break
        except Exception as e:  # noqa: BLE001 — 429/5xx thoáng qua
            if attempt == 3:
                out = {"intent": f"ERROR:{type(e).__name__}"}
                break
            await asyncio.sleep(3 * (attempt + 1))
    ms = round((time.perf_counter() - t0) * 1000)
    predicted = out.get("intent", "")
    return {
        "id": item["id"],
        "question": item["question"],
        "difficulty": item.get("difficulty"),
        "expected_intent": item["type"],
        "predicted_intent": predicted,
        "correct": predicted == item["type"],
        "latency_ms": ms,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0, help="giãn cách giữa 2 request, tránh 429 làm phồng latency")
    args = parser.parse_args()

    if not DATASET.exists():
        sys.exit(f"Chưa có {DATASET}. Xem eval/ROUTER_HOLDOUT_BRIEF.md để tạo bộ câu.")
    if RESULTS.exists():
        sys.exit(
            f"{RESULTS} đã tồn tại — bộ holdout chỉ được tiêu MỘT lần.\n"
            "Chạy lại rồi chọn lần đẹp hơn thì nó không còn là bằng chứng không thiên lệch.\n"
            "Nếu thực sự cần chạy lại, xoá file đó bằng tay (hành động có chủ đích)."
        )

    items = json.loads(DATASET.read_text(encoding="utf-8"))
    bad = [i.get("id") for i in items if i.get("type") not in VALID_TYPES]
    if bad:
        sys.exit(f"{len(bad)} câu có `type` không hợp lệ: {bad[:5]}")

    settings = get_settings()
    print(f"{len(items)} câu · {Counter(i['type'] for i in items)}", flush=True)

    results = []
    for n, item in enumerate(items, 1):
        results.append(await _run_one(item))
        if n % 20 == 0:
            print(f"  [{n}/{len(items)}]", flush=True)
        await asyncio.sleep(args.delay)
    results.sort(key=lambda r: r["id"])

    correct = sum(r["correct"] for r in results)
    gates = _gates(results)
    confusion = Counter((r["expected_intent"], r["predicted_intent"]) for r in results if not r["correct"])

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "status": "CONSUMED — bộ này không còn dùng làm bằng chứng không thiên lệch",
        "brief": "eval/ROUTER_HOLDOUT_BRIEF.md",
        "frozen_snapshot": {
            "dataset_sha256": _sha256(str(DATASET)),
            "router_py_sha256": _sha256("src/agents/nodes/router.py"),
            "thinking_router": settings.thinking_router,
            "escalation_guard_enabled": settings.escalation_guard_enabled,
            "router_model": settings.router_model,
        },
        "accuracy": round(correct / len(results), 3),
        "correct": correct,
        "total": len(results),
        "note_on_accuracy": "Tham khảo, KHÔNG phải gate. n nhỏ nên một câu dịch ~1,5 điểm — xem gates.",
        "gates": gates,
        "confusion": {f"{e}->{p}": c for (e, p), c in confusion.items()},
        "results": results,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nAccuracy (tham khảo): {correct}/{len(results)} ({correct/len(results):.1%})")
    print("\n=== GATE (đây mới là thứ quyết định) ===")
    for name in ("hr_false_rejection", "oos_leak", "ucr", "uar"):
        g = gates[name]
        mark = "" if "passed" not in g else ("  PASS" if g["passed"] else "  FAIL")
        print(f"  {name:<20} {g['count']}/{g['denominator']}  (gate: {g['gate']}){mark}  {g['ids'] or ''}")
    g = gates["router_p50_ms"]
    print(f"  {'router_p50_ms':<20} {g['value']}ms  (gate: {g['gate']})  {'PASS' if g['passed'] else 'FAIL'}")
    print(f"\nConfusion: {json.dumps(report['confusion'], ensure_ascii=False)}")
    print(f"Đã lưu: {RESULTS}")


asyncio.run(main())
