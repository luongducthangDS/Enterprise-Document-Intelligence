#!/usr/bin/env python3
"""So sánh 2 lần chạy eval theo CẶP (cùng câu hỏi) và cho biết chênh lệch có thật không.

Vì sao không so 2 con số tổng: với n = 100, khoảng tin cậy của một tỉ lệ rộng
khoảng ±9 điểm. "75% → 79%" nhìn thì có vẻ cải thiện, nhưng nếu 4 câu tăng và 3
câu khác giảm thì đó là nhiễu. So theo cặp (cùng câu hỏi, so từng câu với nhau)
mạnh hơn nhiều vì loại được phương sai do độ khó khác nhau giữa các câu.

Ngoài số tổng, script liệt kê luôn **câu nào đổi chiều** — đây mới là thứ dùng
để phân tích lỗi, vì một thay đổi có thể vừa sửa được 8 câu vừa làm hỏng 5 câu
mà tổng chỉ nhích 3 điểm.

Chạy:
    python eval/scripts/compare_runs.py before.json after.json
    python eval/scripts/compare_runs.py before.json after.json --metric context_found
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _stats import bootstrap_ci, format_ci, paired_bootstrap  # noqa: E402

AGENT_METRICS = ("passed", "context_found", "answer_correct")


def load_results(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {r["id"]: r for r in data["results"]}


def compare_metric(before: dict, after: dict, ids: list[str], metric: str) -> dict | None:
    a = [1.0 if before[i].get(metric) else 0.0 for i in ids]
    b = [1.0 if after[i].get(metric) else 0.0 for i in ids]
    if not any(metric in before[i] for i in ids):
        return None
    pa, la, ha = bootstrap_ci(a)
    pb, lb, hb = bootstrap_ci(b)
    test = paired_bootstrap(a, b)
    return {
        "metric": metric,
        "before": format_ci(pa, la, ha),
        "after": format_ci(pb, lb, hb),
        **test,
        "fixed": [i for i in ids if not before[i].get(metric) and after[i].get(metric)],
        "broken": [i for i in ids if before[i].get(metric) and not after[i].get(metric)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--metrics", nargs="*", default=list(AGENT_METRICS))
    args = parser.parse_args()

    before, after = load_results(args.before), load_results(args.after)
    ids = sorted(set(before) & set(after))
    only_before, only_after = set(before) - set(after), set(after) - set(before)
    print(f"So {len(ids)} câu có ở cả 2 lần chạy")
    if only_before or only_after:
        print(f"  (bỏ qua {len(only_before)} câu chỉ có ở bản trước, {len(only_after)} câu chỉ có ở bản sau)")

    print(f"\n{'metric':<16}{'trước':<22}{'sau':<22}{'chênh lệch':<26}{'kết luận'}")
    print("-" * 100)
    details = []
    for metric in args.metrics:
        r = compare_metric(before, after, ids, metric)
        if not r:
            continue
        details.append(r)
        diff = f"{r['diff']:+.1%} [{r['ci_low']:+.1%}, {r['ci_high']:+.1%}]"
        verdict = "CÓ THẬT" if r["significant"] else "nhiễu (CI chứa 0)"
        print(f"{metric:<16}{r['before']:<22}{r['after']:<22}{diff:<26}{verdict}  p={r['p_value']:.3f}")

    for r in details:
        if r["fixed"] or r["broken"]:
            print(f"\n=== {r['metric']}: sửa được {len(r['fixed'])} câu, làm hỏng {len(r['broken'])} câu ===")
            if r["fixed"]:
                print(f"  sửa được: {', '.join(r['fixed'][:15])}")
            if r["broken"]:
                print(f"  LÀM HỎNG: {', '.join(r['broken'][:15])}")

    # Latency so theo cặp — thay đổi pipeline thường đánh đổi chất lượng lấy tốc độ
    lat_a = [before[i]["latency_ms"] for i in ids if before[i].get("latency_ms") and after[i].get("latency_ms")]
    lat_b = [after[i]["latency_ms"] for i in ids if before[i].get("latency_ms") and after[i].get("latency_ms")]
    if lat_a:
        test = paired_bootstrap(lat_a, lat_b)
        print(
            f"\nLatency trung bình: {sum(lat_a) / len(lat_a) / 1000:.1f}s → {sum(lat_b) / len(lat_b) / 1000:.1f}s "
            f"({test['diff'] / 1000:+.1f}s, {'có thật' if test['significant'] else 'nhiễu'})"
        )


if __name__ == "__main__":
    main()
