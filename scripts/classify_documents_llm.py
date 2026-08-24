import csv
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

import requests
from src.config import get_settings

PROMPT_TEMPLATE = """Bạn là chuyên gia phân loại tài liệu doanh nghiệp. Hãy phân loại tài liệu dưới đây vào đúng 1 trong các nhóm sau:

1. "GENERAL": Chính sách, quy chế, nội quy CHÍNH THỨC DO DOANH NGHIỆP BAN HÀNH áp dụng chung cho TẤT CẢ cán bộ nhân viên trong công ty (ví dụ: Chính sách nghỉ phép của công ty, Nội quy lao động công ty, Chính sách WFH công ty, Công tác phí công ty, Đánh giá KPI công ty, Chế độ OT công ty, BHXH công ty).
2. "LEGAL": Văn bản quy phạm pháp luật DO NHÀ NƯỚC / CHÍNH PHỦ / BỘ BAN HÀNH (ví dụ: Bộ luật Lao động, Luật BHXH, Luật Thuế TNCN, Nghị định, Thông tư của cơ quan nhà nước).
3. "HR": Tài liệu, quy trình, biểu mẫu NGHIỆP VỤ NỘI BỘ RIÊNG của phòng Nhân sự (ví dụ: Quy trình tuyển dụng nội bộ HR, Hướng dẫn nghiệp vụ HR, Mẫu biểu tham khảo HR).
4. "PRODUCT": Tài liệu chuyên môn, PRD, nghiên cứu người dùng của phòng Sản phẩm / Công nghệ.
5. "ACCOUNTING": Tài liệu, chứng từ, hạch toán riêng của phòng Kế toán / Tài chính.
6. "EXTERNAL_REFERENCE": Tài liệu tham khảo từ tổ chức bên ngoài (ví dụ quy chế của công ty khác, bài viết trên mạng).

Thông tin tài liệu:
- Tên file: {source_file}
- Category: {category}
- Đoạn trích nội dung:
\"\"\"
{content_snippet}
\"\"\"

Trả về DUY NHẤT một chuỗi JSON theo định dạng:
{{"classification": "GENERAL"|"LEGAL"|"HR"|"PRODUCT"|"ACCOUNTING"|"EXTERNAL_REFERENCE", "reason": "Lý do ngắn gọn"}}
"""


def call_llm(prompt: str, settings) -> dict:
    url = f"{settings.fpt_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.fpt_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "You are a professional document taxonomy classifier. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown code block if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def main():
    settings = get_settings()
    registry_path = "data/metadata/document_registry.csv"
    with open(registry_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    print(f"Bắt đầu phân loại {len(rows)} tài liệu bằng LLM ({settings.llm_model})...\n")


    results = []
    for i, r in enumerate(rows):
        sf = r["source_file"]
        proc_path = r.get("processed_path", "")

        # Skip eval/config assets
        if r.get("category") in ("eval_dataset", "config"):
            r["department"] = "CONFIG"
            continue

        snippet = ""
        if os.path.exists(proc_path):
            with open(proc_path, "r", encoding="utf-8") as pf:
                snippet = pf.read(1200)

        prompt = PROMPT_TEMPLATE.format(
            source_file=sf,
            category=r.get("category", ""),
            content_snippet=snippet,
        )

        try:
            res = call_llm(prompt, settings)
            classification = res.get("classification", "GENERAL")
            reason = res.get("reason", "")
            r["department"] = classification
            results.append((sf, classification, reason))
            print(f"[{i+1}/{len(rows)}] {sf[:40]:40} -> {classification:15} ({reason})")
        except Exception as e:
            print(f"[{i+1}/{len(rows)}] {sf[:40]:40} -> LỖI: {e}")

    with open(registry_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n✅ Phân loại bằng LLM hoàn tất và đã lưu vào data/metadata/document_registry.csv!")


if __name__ == "__main__":
    main()
