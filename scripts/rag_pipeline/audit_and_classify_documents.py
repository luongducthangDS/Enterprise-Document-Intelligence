#!/usr/bin/env python3
"""Script kiểm tra và phân loại toàn bộ tài liệu trong document_registry.csv bằng LLM API.

Các tiêu chí phân loại nghiêm ngặt:
1. GENERAL:
   - CHÍNH DOANH NGHIỆP BAN HÀNH.
   - Chính sách, quy định, quy chế, quyết định chính thức.
   - Scope: COMPANY_WIDE (Áp dụng cho toàn bộ cán bộ công nhân viên công ty).
   - Nguồn chính thức trả lời cho nhân viên "công ty quy định như thế nào".
2. LEGAL:
   - Do Nhà nước hoặc cơ quan nhà nước ban hành (Bộ luật, Luật, Nghị định, Thông tư, VBHN).
   - Không phải company policy. Tách biệt hoàn toàn khỏi GENERAL.
3. DEPARTMENT:
   - Do doanh nghiệp hoặc một phòng ban tạo ra nhưng CHỈ phục vụ nghiệp vụ nội bộ của phòng ban cụ thể (HR SOP, Onboarding SOP, Invoice SOP...).
   - Scope: DEPARTMENT_ONLY.
4. EXTERNAL_REFERENCE:
   - Template, biểu mẫu mẫu, chính sách công ty khác (VinFast, Vingroup), bài viết từ Base.vn, Talentnet...
   - Scope: EXTERNAL.
5. NEEDS_REVIEW:
   - Tài liệu không xác định chắc chắn issuer/scope hoặc confidence < 0.85.
"""

import csv
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

import requests
from src.config import get_settings

SYSTEM_PROMPT = """Bạn là chuyên gia phân loại và thẩm định tài liệu doanh nghiệp cho hệ thống Doc Intelligence Agent.
Nhiệm vụ của bạn là đọc thông tin và trích đoạn nội dung của văn bản, sau đó trích xuất các thuộc tính thẩm định và phân loại chính xác vào đúng 1 trong các category sau:

1. "GENERAL":
   - ĐIỀU KIỆN BẮT BUỘC: Do chính doanh nghiệp (Công ty) ban hành + Là chính sách/quy định/quy chế chính thức + Phạm vi áp dụng là COMPANY_WIDE (Toàn bộ cán bộ nhân viên trong công ty, không giới hạn riêng một phòng ban).
   - Ví dụ: Chính sách WFH toàn công ty, Chính sách nghỉ phép toàn công ty, Nội quy lao động công ty, Chính sách đào tạo chung, Quy chế công tác phí, Chính sách OT toàn công ty, Chính sách BHXH nội bộ công ty, Đánh giá KPI công ty.

2. "LEGAL":
   - Văn bản quy phạm pháp luật do cơ quan Nhà nước / Quốc hội / Chính phủ / Bộ ban hành.
   - Ví dụ: Bộ luật Lao động, Luật BHXH, Luật Thuế TNCN, Nghị định 145, Nghị định 158, Nghị định 293, Thông tư 60...
   - LƯU Ý: Tuyệt đối KHÔNG phân loại vào GENERAL dù luật áp dụng cho người lao động.

3. "DEPARTMENT":
   - Tài liệu do doanh nghiệp hoặc phòng ban tạo ra nhưng CHỈ phục vụ nghiệp vụ/quy trình riêng của một phòng ban cụ thể (Scope: DEPARTMENT_ONLY).
   - Ví dụ: Quy trình tuyển dụng nội bộ của HR, Quy trình onboarding nội bộ của HR, Quy trình xử lý hóa đơn của Kế toán, SOP kỹ thuật...
   - LƯU Ý: Không phân loại vào GENERAL chỉ vì nó do công ty tạo ra.

4. "EXTERNAL_REFERENCE":
   - Tài liệu tham khảo bên ngoài: Template, biểu mẫu mẫu, chính sách của công ty khác (vd: VinFast, Vingroup), bài viết nghiệp vụ từ Base.vn, Talentnet...

5. "NEEDS_REVIEW":
   - Khi không xác định chắc chắn issuer, scope hoặc tài liệu bị rỗng/thiếu thông tin, hoặc độ tin cậy confidence < 0.85.

Hãy trả về DUY NHẤT một chuỗi JSON hợp lệ với cấu trúc sau:
{
  "category": "GENERAL" | "LEGAL" | "DEPARTMENT" | "EXTERNAL_REFERENCE" | "NEEDS_REVIEW",
  "issuer": "Tên cơ quan/đơn vị ban hành (vd: Công ty NexaTech, Quốc hội, Chính phủ, Bộ Y tế, Phòng Nhân sự, Base.vn...)",
  "document_type": "Loại văn bản (vd: Chính sách công ty, Quy trình nội bộ phòng ban, Bộ luật, Nghị định, Thông tư, Biểu mẫu tham khảo...)",
  "organization": "Tổ chức sở hữu văn bản (vd: NexaTech, Nhà nước Việt Nam, VinFast, Base.vn...)",
  "effective_date": "Ngày hiệu lực nếu có (YYYY-MM-DD) hoặc rỗng",
  "scope": "COMPANY_WIDE" | "DEPARTMENT_ONLY" | "EXTERNAL",
  "target_audience": "Đối tượng áp dụng cụ thể",
  "is_official_company_document": true | false,
  "department": "GENERAL" | "HR" | "PRODUCT" | "ACCOUNTING" | "LEGAL" | "EXTERNAL",
  "confidence": 0.95,
  "reason": "Giải thích ngắn gọn, rõ ràng căn cứ phân loại"
}
"""

USER_PROMPT_TEMPLATE = """Thông tin tài liệu cần phân loại:
- Tên file: {source_file}
- Category hiện tại: {current_category}
- Metadata trích lục:
{metadata_snippet}

- Nội dung văn bản (trích đoạn 1500 ký tự đầu tiên):
\"\"\"
{content_snippet}
\"\"\"
"""


def call_classifier_llm(prompt: str, settings) -> dict:
    url = f"{settings.fpt_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.fpt_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
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

    # Ensure required columns exist
    extended_fields = [
        "source_file",
        "access_category",
        "department",
        "scope",
        "issuer",
        "document_type",
        "confidence",
        "classification_reason",
    ]
    for ef in extended_fields:
        if ef not in fieldnames:
            fieldnames.append(ef)

    print(f"=== Bắt đầu Audit & Phân loại {len(rows)} tài liệu bằng {settings.llm_model} ===\n")

    audit_table = []

    for i, r in enumerate(rows):
        sf = r["source_file"]
        proc_path = r.get("processed_path", "")

        # Config / Eval datasets
        if r.get("category") in ("eval_dataset", "config"):
            r["access_category"] = "CONFIG"
            r["department"] = "CONFIG"
            r["scope"] = "INTERNAL_CONFIG"
            r["issuer"] = "System"
            r["document_type"] = "Config Asset"
            r["confidence"] = "1.00"
            r["classification_reason"] = "Tài liệu cấu hình/eval dataset nội bộ, không tham gia RAG"
            continue

        snippet = ""
        meta_snippet = f"Caveat: {r.get('caveat', '')}\nSourceType: {r.get('source_type', '')}"
        if os.path.exists(proc_path):
            with open(proc_path, "r", encoding="utf-8") as pf:
                snippet = pf.read(1800)

        prompt = USER_PROMPT_TEMPLATE.format(
            source_file=sf,
            current_category=r.get("category", ""),
            metadata_snippet=meta_snippet,
            content_snippet=snippet,
        )

        try:
            res = call_classifier_llm(prompt, settings)
            category = res.get("category", "NEEDS_REVIEW")
            confidence = float(res.get("confidence", 0.0))
            if confidence < 0.85 and category != "NEEDS_REVIEW":
                category = "NEEDS_REVIEW"

            issuer = res.get("issuer", "")
            scope = res.get("scope", "EXTERNAL")
            doc_type = res.get("document_type", "")
            dept = res.get("department", "GENERAL")
            reason = res.get("reason", "")

            r["access_category"] = category
            r["department"] = dept
            r["scope"] = scope
            r["issuer"] = issuer
            r["document_type"] = doc_type
            r["confidence"] = f"{confidence:.2f}"
            r["classification_reason"] = reason

            audit_table.append({
                "source_file": sf,
                "category": category,
                "issuer": issuer,
                "scope": scope,
                "confidence": f"{confidence:.2f}",
                "reason": reason,
            })

            print(f"[{i+1:02d}/{len(rows):02d}] {sf[:42]:42} | {category:18} | Conf: {confidence:.2f} | Scope: {scope:15} | {issuer[:25]}")
        except Exception as e:
            print(f"[{i+1:02d}/{len(rows):02d}] {sf[:42]:42} | ERROR: {e}")
            r["access_category"] = "NEEDS_REVIEW"
            r["confidence"] = "0.00"
            r["classification_reason"] = f"Lỗi phân loại LLM: {e}"

    with open(registry_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n✅ Hoàn thành audit & phân loại. Đã cập nhật data/metadata/document_registry.csv.")

    # Save markdown summary report
    report_path = "docs/reports/document_classification_audit.json"
    os.makedirs("docs/reports", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(audit_table, rf, ensure_ascii=False, indent=2)
    print(f"Đã lưu báo cáo JSON tại {report_path}")


if __name__ == "__main__":
    main()
