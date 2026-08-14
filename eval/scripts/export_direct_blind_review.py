#!/usr/bin/env python3
"""Xuất bộ chấm MÙ cho nhánh `direct` — 34 output, ẩn hoàn toàn nguồn gốc.

Vì sao cần: evaluator tự động của P4A đã phải sửa 4 lần, và bản v4 được sửa
SAU khi xem output. Nó vẫn dùng được cho phân tích khám phá, nhưng không nên là
bằng chứng quyết định. Vấn đề nằm ở người đo, không nằm ở thiếu dữ liệu — nên
lối thoát đúng là đổi người chấm, không phải chạy lại API (chạy lại chỉ thêm
nhiễu ngẫu nhiên).

Ẩn khỏi người chấm: model, variant, latency, kết quả gate v3/v4, và cả mục đích
của phép so sánh. Hai output của cùng một input được xáo để không nằm cạnh nhau.

Chạy: python eval/scripts/export_direct_blind_review.py
"""
import json
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SOURCE = Path("eval/results/p4a_direct_v2.json")
SHEET = Path("eval/datasets/p4a_direct_blind_review.md")
MAPPING = Path("eval/results/p4a_direct_blind_mapping.json")
SEED = 20260813


def main() -> None:
    if MAPPING.exists():
        sys.exit(
            f"{MAPPING} đã tồn tại — bộ chấm mù đã được xuất một lần.\n"
            "Xuất lại sẽ đổi thứ tự và làm hỏng phiếu chấm đang lưu hành.\n"
            "Nếu thực sự cần, xoá file mapping bằng tay."
        )

    rows = json.loads(SOURCE.read_text(encoding="utf-8"))["results"]
    samples = [{"variant": r["variant"], "id": r["id"], "query": r["query"], "output": r["output"]} for r in rows]

    rng = random.Random(SEED)
    rng.shuffle(samples)
    # Tách hai output của cùng một input ra xa nhau: nếu hai mục liền kề trùng
    # `id`, đẩy mục sau xuống cuối. Người chấm thấy chúng cạnh nhau sẽ vô tình
    # so sánh cặp thay vì chấm độc lập từng câu.
    for i in range(len(samples) - 1):
        if samples[i]["id"] == samples[i + 1]["id"]:
            samples.append(samples.pop(i + 1))

    lines = [
        "# Phiếu chấm — phản hồi hội thoại của trợ lý HR",
        "",
        "Nhờ bạn đọc 34 mẫu dưới đây và chấm giúp 2 câu hỏi cho mỗi mẫu.",
        "Mỗi mẫu gồm câu người dùng gõ và câu trợ lý trả lời.",
        "",
        "## Hai câu hỏi",
        "",
        "**Q1 — Phản hồi có đúng ngữ cảnh không?** (`yes` / `no`)",
        "",
        "- Có đáp đúng điều người dùng vừa nói không?",
        "- Nếu người dùng đang **cảm ơn** hoặc **tạm biệt**: trợ lý KHÔNG được mở đầu lại hội thoại"
        " bằng lời chào giới thiệu như thể vừa gặp lần đầu.",
        "- Nếu người dùng **hỏi trợ lý làm được gì** hoặc hỏi một câu xã giao: cần trả lời đúng nội dung"
        " câu hỏi đó (không bắt buộc phải chào).",
        "",
        "**Q2 — Có tự đưa ra số liệu/quy định HR không?** (`yes` / `no`)",
        "",
        "- `yes` nếu câu trả lời nêu con số hoặc quy định nhân sự cụ thể (số ngày phép, phần trăm lương,"
        " thời hạn...) mà người dùng KHÔNG hề nhắc tới trong câu của họ.",
        "- Nhắc lại con số do chính người dùng đưa ra thì trả lời `no`.",
        "",
        "## Cách điền",
        "",
        "Điền vào hai cột cuối của bảng ở cuối file. Không cần giải thích, nhưng nếu mẫu nào khiến bạn"
        " phân vân thì ghi một dòng ghi chú cũng rất hữu ích.",
        "",
        "---",
        "",
        "## 34 mẫu",
        "",
    ]
    for n, s in enumerate(samples, 1):
        lines += [
            f"### sample_{n:03d}",
            "",
            f"**Người dùng:** {s['query']}",
            "",
            f"**Trợ lý:** {s['output']}",
            "",
        ]
    lines += ["---", "", "## Bảng điền", "", "| Mẫu | Q1 đúng ngữ cảnh | Q2 tự đưa số liệu | Ghi chú |", "|---|---|---|---|"]
    lines += [f"| sample_{n:03d} | | | |" for n in range(1, len(samples) + 1)]
    lines.append("")
    SHEET.write_text("\n".join(lines), encoding="utf-8")

    MAPPING.write_text(
        json.dumps(
            {
                "note": "KHÔNG đưa file này cho người chấm. Dùng để giải mã sau khi nhận phiếu.",
                "seed": SEED,
                "source": str(SOURCE),
                "mapping": {f"sample_{n:03d}": {"variant": s["variant"], "id": s["id"]} for n, s in enumerate(samples, 1)},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    from collections import Counter
    print(f"Đã xuất {len(samples)} mẫu -> {SHEET}")
    print(f"Mapping (KHÔNG đưa người chấm) -> {MAPPING}")
    print("Phân bố variant:", dict(Counter(s["variant"] for s in samples)))
    adjacent = sum(1 for i in range(len(samples) - 1) if samples[i]["id"] == samples[i + 1]["id"])
    print(f"Cặp cùng input nằm cạnh nhau: {adjacent}")


main()
