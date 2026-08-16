#!/usr/bin/env python3
"""P4A — A/B hai nhánh rẻ: `direct` (greeting) và `clarify` (hỏi lại).

Hai path benchmark TÁCH BIỆT vì rủi ro khác hẳn nhau:

  direct  — tác vụ đóng (chào hỏi). Gate NHẸ: đúng ý chào, không nói số liệu
            chính sách, giữ persona, đủ ngắn.
  clarify — phải xác định đúng phần thông tin còn thiếu. Gate CHẶT: không tự
            trả lời, không thêm giả định, phải nêu được lựa chọn cụ thể để lượt
            sau người dùng chọn được.

Chấm bằng tín hiệu xác định (không LLM judge) để tái lập được và tránh circular
evaluation.

Chạy: python eval/scripts/eval_p4a_cheap_paths.py [--path direct|clarify|both]
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.router import clarify_node, direct_node  # noqa: E402
from src.config import get_settings  # noqa: E402

DATASET = Path("eval/datasets/p4a_cheap_path_set.json")
RESULTS = Path("eval/results/p4a_cheap_paths_ab.json")

# Số liệu chính sách: con số kèm đơn vị. Xuất hiện trong câu chào hoặc câu hỏi
# lại nghĩa là node đã tự khẳng định chính sách — việc nó không được phép làm.
_POLICY_NUMBER = re.compile(
    r"\d+\s*(?:%|ngày|tháng|năm|giờ|tuần|lần|triệu|đồng|vnđ)", re.IGNORECASE
)
_GREETING_MARKERS = (
    "chào", "hello", "hi ", "xin chào", "rất vui", "mình là", "hân hạnh",
    # Phản hồi cho lời cảm ơn cũng là social response hợp lệ — bản gate đầu
    # thiếu nhóm này nên phạt oan câu "Dạ, không có gì ạ!" của GLM.
    "không có gì", "cảm ơn", "rất sẵn lòng", "sẵn sàng hỗ trợ",
)
_HR_HINT = ("nhân sự", "hr", "chính sách", "nghỉ phép", "lương", "bảo hiểm", "tuyển dụng", "đào tạo")
# Input dạng cảm ơn/tạm biệt: trả lời bằng lời chào MỞ ĐẦU là lệch ngữ cảnh.
# Đây là điểm yếu riêng của phương án template (một câu cố định cho mọi input)
# mà gate đầu tiên không bắt được.
# Các speech act KHÔNG phải mở đầu hội thoại: trả lời chúng bằng lời chào mở
# đầu là lệch ngữ cảnh (hội thoại đang diễn ra, không phải bắt đầu).
_NON_OPENING_ACTS = ("thanks", "acknowledgement", "goodbye", "thanks_goodbye")
_OPENING_GREETING = ("chào bạn", "xin chào", "hello", "chào anh", "chào chị", "chào em")
# Lời chào TẠM BIỆT có chứa "chào" nhưng là act khác — không tính là mở đầu.
_FAREWELL_MARKERS = ("tạm biệt", "hẹn gặp lại", "gặp lại")
# Từ nối lựa chọn — dấu hiệu cấu trúc của một câu hỏi có phương án chọn.
_OPTION_CONNECTORS = (" hay ", " hoặc ", " hay là ")


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _score_direct(text: str, item: dict) -> dict:
    """Gate cho nhánh direct — áp check theo ĐÚNG act, không áp chung.

    Lịch sử ba lần sửa gate này (ghi lại vì bản thân nó là bài học):

    v1 — `is_greeting` đòi mọi câu phải có từ chào; phạt oan "Dạ, không có gì ạ!"
         trả lời cho lời cảm ơn.
    v2 — thêm `context_appropriate`, nhưng vẫn xét chung cả nhóm là "greeting".
    v3 — xét theo `act`, nhưng còn hai lỗi nữa:
         (a) tiếng Việt dùng "chào bạn" cho CẢ mở đầu lẫn tạm biệt, nên bắt lỗi
             bằng tiền tố là sai — "Chào bạn, đi làm vui vẻ nhé!" là lời tạm
             biệt hoàn toàn đúng;
         (b) câu hỏi năng lực và câu xã giao thường cần TRẢ LỜI NỘI DUNG chứ
             không cần chào, nên đòi có từ chào là đòi sai thứ.

    Nguyên tắc v4: mỗi act chỉ bị chấm bởi tiêu chí thực sự áp dụng cho nó.
    """
    low = _norm(text)
    act = item.get("act", "opening")
    checks = {
        "no_policy_number": not bool(_POLICY_NUMBER.search(low)),
        "concise": len(text) <= 400,
        "non_empty": bool(text.strip()),
    }
    # Chỉ nhóm mở đầu và đáp-lời-cảm-ơn mới bắt buộc có dấu hiệu xã giao.
    # capability/casual_social trả lời nội dung là đúng; goodbye có thể chỉ là
    # "đi làm vui vẻ nhé".
    if act in ("opening", "thanks", "thanks_goodbye"):
        checks["is_social_response"] = any(m in low for m in _GREETING_MARKERS)
    # Chỉ nhóm mở đầu/hỏi năng lực mới cần mời hỏi tiếp về HR.
    if act in ("opening", "capability"):
        checks["offers_help"] = any(h in low for h in _HR_HINT)
    # HARD GATE — chỉ áp cho các act mà việc mở đầu lại hội thoại là SAI rõ
    # ràng. Cố ý KHÔNG áp cho `goodbye`: "chào bạn" trong tiếng Việt là lời
    # chào hai đầu, không phân biệt được bằng heuristic văn bản.
    if act in ("thanks", "acknowledgement", "thanks_goodbye"):
        reintroduces = low.startswith(_OPENING_GREETING) or "mình là trợ lý" in low
        checks["context_appropriate"] = not reintroduces
    return checks


def _score_clarify(text: str, item: dict) -> dict:
    """Gate chặt — câu hỏi lại sai hướng còn tệ hơn chậm."""
    low = _norm(text)
    q = _norm(item["query"])
    # Số ĐÃ CÓ trong câu hỏi gốc thì nhắc lại là hành vi đúng (xác nhận ngữ
    # cảnh), không phải tự khẳng định chính sách. Bản gate đầu không trừ phần
    # này nên phạt oan cả hai variant ở cl_01 ("3 ngày") và cl_10 ("60 ngày").
    invented = [m.group(0) for m in _POLICY_NUMBER.finditer(low) if _norm(m.group(0)) not in q]
    return {
        # Phải là câu HỎI, không phải câu trả lời.
        "is_question": "?" in text,
        # Không được tự bịa ra con số chính sách nào (đây là "wrong assumption").
        "no_invented_number": not invented,
        # Phải bám đúng chủ đề câu gốc, không hỏi sang chuyện khác.
        "on_topic": any(_norm(a) in low for a in item["topic_anchor"]),
        # "Clarification usefulness": câu hỏi phải cho người dùng CHỌN được.
        # Nhận diện bằng CẤU TRÚC (từ nối lựa chọn) hoặc bằng việc nêu trúng >= 2
        # phương án dự kiến — chỉ khớp từ khoá thì phạt oan mọi cách diễn đạt
        # khác, như bản gate đầu đã làm với 7/7 câu.
        "offers_options": (
            any(c in low for c in _OPTION_CONNECTORS)
            or sum(1 for o in item["expected_options"] if _norm(o) in low) >= 2
        ),
        "concise": len(text) <= 300,
        "non_empty": bool(text.strip()),
    }


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    return s[f] if f + 1 >= len(s) else s[f] + (s[f + 1] - s[f]) * (k - f)


async def _run(node, item: dict, key: str) -> tuple[str, int]:
    for attempt in range(4):
        try:
            t0 = time.perf_counter()
            out = await node({"query": item["query"]})
            return out.get(key, ""), round((time.perf_counter() - t0) * 1000)
        except Exception:  # noqa: BLE001 — 429/5xx thoáng qua
            if attempt == 3:
                raise
            await asyncio.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


async def _bench_direct(items: list[dict], delay: float) -> list[dict]:
    settings = get_settings()
    original = settings.direct_mode
    rows = []
    try:
        for variant, mode in [("A_default_llm", "default_llm"), ("C_fast_llm", "fast_llm")]:
            settings.direct_mode = mode
            for item in items:
                text, ms = await _run(direct_node, item, "response")
                rows.append({
                    "path": "direct", "variant": variant, "id": item["id"],
                    "query": item["query"], "output": text, "latency_ms": ms,
                    "checks": _score_direct(text, item),
                })
                if mode != "template":
                    await asyncio.sleep(delay)
            done = [r for r in rows if r["variant"] == variant]
            print(f"  direct/{variant}: p50={_pct([r['latency_ms'] for r in done], 50):.0f}ms", flush=True)
    finally:
        settings.direct_mode = original
    return rows


async def _bench_clarify(items: list[dict], delay: float) -> list[dict]:
    settings = get_settings()
    orig_model, orig_thinking = settings.clarify_model, settings.thinking_clarify
    rows = []
    try:
        variants = [
            ("A_glm_thinking", "", True),
            ("B_fast_no_thinking", settings.router_model, False),
        ]
        for variant, model, thinking in variants:
            settings.clarify_model, settings.thinking_clarify = model, thinking
            for item in items:
                text, ms = await _run(clarify_node, item, "clarifying_question")
                rows.append({
                    "path": "clarify", "variant": variant, "id": item["id"],
                    "query": item["query"], "output": text, "latency_ms": ms,
                    "checks": _score_clarify(text, item),
                })
                await asyncio.sleep(delay)
            done = [r for r in rows if r["variant"] == variant]
            print(f"  clarify/{variant}: p50={_pct([r['latency_ms'] for r in done], 50):.0f}ms", flush=True)
    finally:
        settings.clarify_model, settings.thinking_clarify = orig_model, orig_thinking
    return rows


def _summarize(rows: list[dict], path: str) -> list[dict]:
    out = []
    for variant in dict.fromkeys(r["variant"] for r in rows if r["path"] == path):
        sub = [r for r in rows if r["path"] == path and r["variant"] == variant]
        lat = [r["latency_ms"] for r in sub]
        check_names = list(sub[0]["checks"])
        out.append({
            "variant": variant,
            "n": len(sub),
            "all_checks_pass": sum(1 for r in sub if all(r["checks"].values())),
            "per_check": {c: sum(1 for r in sub if r["checks"][c]) for c in check_names},
            "p50_ms": round(_pct(lat, 50)),
            "p95_ms": round(_pct(lat, 95)),
            "mean_ms": round(statistics.mean(lat)),
            "max_ms": max(lat),
        })
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", choices=["direct", "clarify", "both"], default="both")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--out", default=str(RESULTS))
    args = parser.parse_args()

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    rows: list[dict] = []
    if args.path in ("direct", "both"):
        print(f"=== direct: {len(data['direct'])} câu × 3 variant ===", flush=True)
        rows += await _bench_direct(data["direct"], args.delay)
    if args.path in ("clarify", "both"):
        print(f"=== clarify: {len(data['clarify'])} câu × 2 variant ===", flush=True)
        rows += await _bench_clarify(data["clarify"], args.delay)

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "P4A — A/B nhánh direct và clarify, hai gate tách biệt.",
        "dataset": str(DATASET),
        "baseline_from_p3": {"direct_p50_ms": 5502, "clarify_p50_ms": 9236},
        "direct": _summarize(rows, "direct"),
        "clarify": _summarize(rows, "clarify"),
        "results": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for path in ("direct", "clarify"):
        summ = report[path]
        if not summ:
            continue
        print(f"\n=== {path.upper()} ===")
        checks = list(summ[0]["per_check"])
        head = f"{'Variant':<20}{'pass':>7}{'p50':>9}{'p95':>9}{'mean':>9}  " + " ".join(f"{c[:12]:>13}" for c in checks)
        print(head)
        print("-" * len(head))
        for s in summ:
            cells = " ".join(f"{s['per_check'][c]}/{s['n']:<11}".rjust(13) for c in checks)
            print(f"{s['variant']:<20}{s['all_checks_pass']}/{s['n']:<5}{s['p50_ms']:>8}ms{s['p95_ms']:>8}ms{s['mean_ms']:>8}ms  {cells}")
    print(f"\nĐã lưu: {args.out}")


asyncio.run(main())
