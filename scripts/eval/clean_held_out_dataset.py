#!/usr/bin/env python3
"""Script Làm sạch và Chuẩn hóa Dataset Benchmark Đánh giá (Phase P2).

Chức năng:
1. Đọc bộ dataset đánh giá (qa_heldout_set.json, retrieval_eval_set.json).
2. Đối chiếu với registry chính sách (document_registry.csv).
3. Phân loại và làm sạch:
   - Loại bỏ hoặc gắn cờ các câu hỏi tham chiếu file không thuộc kho chính sách nội bộ.
   - Gắn nhãn chuẩn xác 'pure_statutory' cho câu hỏi thuần luật pháp nhà nước (hệ thống đúng khi từ chối).
   - Xuất dataset v2 đã làm sạch và báo cáo audit chi tiết.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")


def load_registry_files(registry_dir: str = "data/metadata") -> set[str]:
    """Tập hợp tất cả source_file hợp lệ từ các file registry CSV."""
    valid_files = set()
    if not os.path.exists(registry_dir):
        return valid_files

    for fname in os.listdir(registry_dir):
        if fname.endswith(".csv") and "registry" in fname:
            fpath = os.path.join(registry_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sf = row.get("source_file", "").strip()
                    if sf:
                        valid_files.add(sf)
    return valid_files


def clean_qa_dataset(
    input_path: str = "eval/datasets/qa_heldout_set.json",
    output_path: str = "eval/datasets/qa_heldout_set_cleaned.json",
    valid_files: set[str] | None = None,
) -> dict:
    """Làm sạch bộ qa_heldout_set."""
    if not os.path.exists(input_path):
        print(f"File không tồn tại: {input_path}")
        return {}

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.get("questions", data.get("data", []))
    cleaned_items = []
    dropped_items = []
    flagged_statutory = []

    for item in items:
        source_file = item.get("source_file") or item.get("expected_source_file")
        intent = item.get("intent", "hr_question")
        q_text = item.get("question") or item.get("query", "")

        # Kiểm tra file nguồn có trong registry không
        if source_file and valid_files and source_file not in valid_files:
            dropped_items.append({
                "question": q_text,
                "reason": f"source_file '{source_file}' not in document registry",
            })
            continue

        # Kiểm tra câu hỏi pháp luật thuần túy
        if intent == "pure_statutory" or "luật lao động" in q_text.lower() and "công ty" not in q_text.lower():
            item["intent"] = "pure_statutory"
            item["expected_action"] = "out_of_scope"
            flagged_statutory.append(q_text)

        cleaned_items.append(item)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_items, f, ensure_ascii=False, indent=2)

    report = {
        "input_count": len(items),
        "cleaned_count": len(cleaned_items),
        "dropped_count": len(dropped_items),
        "pure_statutory_count": len(flagged_statutory),
        "output_path": output_path,
    }
    return report


def main():
    print("=== BẮT ĐẦU CHUẨN HÓA VÀ LÀM SẠCH DATASET BENCHMARK ===")
    valid_files = load_registry_files()
    print(f"• Số lượng tài liệu hợp lệ trong registry: {len(valid_files)}")

    # 1. Làm sạch QA Held-out Set
    qa_report = clean_qa_dataset(
        input_path="eval/datasets/qa_heldout_set.json",
        output_path="eval/datasets/qa_heldout_set_cleaned.json",
        valid_files=valid_files,
    )
    if qa_report:
        print("\n[QA Held-out Set]")
        print(f"  • Tổng câu hỏi ban đầu: {qa_report['input_count']}")
        print(f"  • Câu hỏi giữ lại: {qa_report['cleaned_count']}")
        print(f"  • Câu hỏi loại bỏ (invalid source): {qa_report['dropped_count']}")
        print(f"  • Câu hỏi pure_statutory: {qa_report['pure_statutory_count']}")
        print(f"  • File xuất: {qa_report['output_path']}")

    # 2. Làm sạch Retrieval Eval Set
    retrieval_report = clean_qa_dataset(
        input_path="eval/datasets/retrieval_eval_set.json",
        output_path="eval/datasets/retrieval_eval_set_cleaned.json",
        valid_files=valid_files,
    )
    if retrieval_report:
        print("\n[Retrieval Eval Set]")
        print(f"  • Tổng mẫu ban đầu: {retrieval_report['input_count']}")
        print(f"  • Mẫu giữ lại: {retrieval_report['cleaned_count']}")
        print(f"  • Mẫu loại bỏ: {retrieval_report['dropped_count']}")
        print(f"  • File xuất: {retrieval_report['output_path']}")

    print("\n=== HOÀN TẤT CHUẨN HÓA DATASET ===")


if __name__ == "__main__":
    main()
