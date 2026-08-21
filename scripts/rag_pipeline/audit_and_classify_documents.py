#!/usr/bin/env python3
"""Script kiểm định và phân loại tài liệu với logic domain LEGAL theo phòng ban (related_departments).

Quy tắc phân loại & phân quyền nghiêm ngặt:
1. Doanh nghiệp chủ quản hệ thống: Công ty Cổ phần Tập đoàn NexaTech.
2. COMPANY_POLICY:
   - CHỈ khi do chính NexaTech ban hành.
   - Chính sách/quy chế/quy định chính thức áp dụng chung toàn công ty (Scope: COMPANY_WIDE).
   - related_departments: ["ALL"]
3. DEPARTMENT:
   - Do NexaTech hoặc phòng ban của NexaTech ban hành nhưng CHỈ phục vụ nghiệp vụ nội bộ của phòng ban cụ thể (Scope: DEPARTMENT_ONLY, vd: Quy trình tuyển dụng, Onboarding, Offboarding của phòng HR).
   - related_departments: [Phòng ban đó, vd: "HR"]
4. LEGAL:
   - Văn bản quy phạm pháp luật do Nhà nước / Quốc hội / Chính phủ / Bộ ban hành (Domain: LEGAL).
   - LLM phân tích để xác định related_departments: list[str] (vd ["HR", "FINANCE", "ACCOUNTING", "LEGAL_COMPLIANCE", "OPERATIONS", "ENGINEERING"]).
5. EXTERNAL_REFERENCE:
   - Mẫu biểu, template, chính sách của công ty KHÁC (như VinFast 2019, Vingroup), bài viết từ Base.vn, Talentnet...
   - related_departments: []
6. NEEDS_REVIEW:
   - Nếu confidence < 0.85 hoặc không xác định chắc chắn.
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

SYSTEM_PROMPT = """Bạn là chuyên gia thẩm định và phân loại tài liệu cho hệ thống Doc Intelligence Agent của doanh nghiệp NexaTech (Công ty Cổ phần Tập đoàn NexaTech).
Nhiệm vụ của bạn là đọc thông tin và trích đoạn nội dung văn bản, sau đó trích xuất các thuộc tính:

1. "category":
   - "COMPANY_POLICY": CHỈ khi do chính NexaTech ban hành VÀ là chính sách/quy chế chính thức áp dụng chung toàn thể cán bộ nhân viên công ty (Scope: COMPANY_WIDE).
   - "DEPARTMENT": Do NexaTech hoặc phòng ban nội bộ của NexaTech tạo ra nhưng CHỈ phục vụ quy trình/nghiệp vụ nội bộ riêng của phòng ban cụ thể (Scope: DEPARTMENT_ONLY, ví dụ: Quy trình tuyển dụng HR, Quy trình Onboarding HR...).
   - "LEGAL": Văn bản quy phạm pháp luật do Nhà nước / Quốc hội / Chính phủ / Bộ ban hành (Bộ luật Lao động, Luật BHXH, Luật Thuế TNCN, Nghị định...).
   - "EXTERNAL_REFERENCE": Biểu mẫu, template tham khảo, chính sách của CÔNG TY KHÁC (như VinFast 2019, Vingroup), bài viết từ Base.vn, Talentnet... (LƯU Ý: Văn bản của VinFast hay công ty khác KHÔNG PHẢI là COMPANY_POLICY của NexaTech, bắt buộc phải là EXTERNAL_REFERENCE).

2. "related_departments":
   - Với tài liệu "LEGAL": Phân tích nội dung để chỉ định TẤT CẢ các phòng ban trong doanh nghiệp có nghiệp vụ liên quan trực tiếp. Một văn bản có thể liên quan nhiều phòng ban (vd: Luật Thuế TNCN -> ["FINANCE", "ACCOUNTING", "HR"]; Bộ luật Lao động -> ["HR", "LEGAL_COMPLIANCE"]; Luật ATVSLĐ -> ["HR", "OPERATIONS", "ENGINEERING"]; Luật BHYT/BHXH -> ["HR", "ACCOUNTING"]).
   - Với tài liệu "DEPARTMENT": Chứa đúng 1 phòng ban sở hữu quy trình (vd: ["HR"]).
   - Với tài liệu "COMPANY_POLICY": Để ["ALL"].
   - Với tài liệu "EXTERNAL_REFERENCE": Để [].

3. "classification_confidence": Float từ 0.0 đến 1.0. Nếu không chắc chắn hoặc confidence < 0.85 -> classification_status là "NEEDS_REVIEW".

Trả về DUY NHẤT một chuỗi JSON hợp lệ:
{
  "category": "COMPANY_POLICY" | "DEPARTMENT" | "LEGAL" | "EXTERNAL_REFERENCE",
  "document_domain": "LEGAL" | "INTERNAL_POLICY" | "INTERNAL_SOP" | "EXTERNAL_REFERENCE",
  "issuer": "Tên cơ quan/đơn vị ban hành",
  "document_type": "Loại văn bản",
  "organization": "Tổ chức sở hữu văn bản (NexaTech / Nhà nước Việt Nam / VinFast / Base.vn...)",
  "scope": "COMPANY_WIDE" | "DEPARTMENT_ONLY" | "EXTERNAL",
  "department": "GENERAL" | "HR" | "FINANCE" | "ACCOUNTING" | "IT" | "LEGAL" | "EXTERNAL",
  "related_departments": ["HR", "FINANCE", ...],
  "classification_confidence": 0.95,
  "classification_status": "APPROVED" | "NEEDS_REVIEW",
  "reason": "Căn cứ phân loại chi tiết và lý do chỉ định related_departments"
}
"""

USER_PROMPT_TEMPLATE = """Thông tin tài liệu:
- Tên file: {source_file}
- Category hiện tại: {current_category}
- Metadata: {metadata_snippet}
- Trích đoạn nội dung:
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
    resp = requests.post(url, headers=headers, json=payload, timeout=40)
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
        fieldnames = list(reader.fieldnames)

    extended_fields = [
        "source_file",
        "access_category",
        "document_domain",
        "department",
        "related_departments",
        "scope",
        "issuer",
        "document_type",
        "classification_confidence",
        "classification_status",
        "classification_reason",
    ]
    for ef in extended_fields:
        if ef not in fieldnames:
            fieldnames.append(ef)

    print(f"=== Bắt đầu Thẩm định & Phân tích related_departments cho {len(rows)} tài liệu ===", flush=True)

    audit_table = []

    for i, r in enumerate(rows):
        sf = r["source_file"]
        proc_path = r.get("processed_path", "")

        if r.get("category") in ("eval_dataset", "config"):
            r["access_category"] = "CONFIG"
            r["document_domain"] = "CONFIG"
            r["department"] = "CONFIG"
            r["related_departments"] = "[]"
            r["scope"] = "INTERNAL_CONFIG"
            r["issuer"] = "System"
            r["document_type"] = "Config Asset"
            r["classification_confidence"] = "1.00"
            r["classification_status"] = "APPROVED"
            r["classification_reason"] = "Tài liệu cấu hình nội bộ"
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
            confidence = float(res.get("classification_confidence", res.get("confidence", 0.0)))
            status = res.get("classification_status", "APPROVED")
            if confidence < 0.85:
                status = "NEEDS_REVIEW"

            issuer = res.get("issuer", "")
            scope = res.get("scope", "EXTERNAL")
            doc_type = res.get("document_type", "")
            doc_domain = res.get("document_domain", "INTERNAL_POLICY")
            dept = res.get("department", "GENERAL")
            related_depts = res.get("related_departments", [])
            reason = res.get("reason", "")

            # If company policy, alias to COMPANY_POLICY
            if category in ("GENERAL", "COMPANY_POLICY"):
                category = "COMPANY_POLICY"
                related_depts = ["ALL"]
                dept = "GENERAL"
                scope = "COMPANY_WIDE"

            r["access_category"] = category
            r["document_domain"] = doc_domain
            r["department"] = dept
            r["related_departments"] = json.dumps(related_depts, ensure_ascii=False)
            r["scope"] = scope
            r["issuer"] = issuer
            r["document_type"] = doc_type
            r["classification_confidence"] = f"{confidence:.2f}"
            r["classification_status"] = status
            r["classification_reason"] = reason

            audit_table.append({
                "source_file": sf,
                "access_category": category,
                "document_domain": doc_domain,
                "issuer": issuer,
                "scope": scope,
                "department": dept,
                "related_departments": related_depts,
                "confidence": f"{confidence:.2f}",
                "status": status,
                "reason": reason,
            })

            print(f"[{i+1:02d}/{len(rows):02d}] {sf[:35]:35} | {category:14} | Related: {str(related_depts):30} | Conf: {confidence:.2f}", flush=True)
        except Exception as e:
            print(f"[{i+1:02d}/{len(rows):02d}] {sf[:35]:35} | ERROR: {e}", flush=True)
            r["access_category"] = "NEEDS_REVIEW"
            r["classification_status"] = "NEEDS_REVIEW"
            r["classification_confidence"] = "0.00"
            r["classification_reason"] = f"Lỗi gọi LLM: {e}"

    with open(registry_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n✅ Hoàn thành phân loại related_departments. Đã cập nhật document_registry.csv.", flush=True)

    with open("docs/reports/document_classification_audit.json", "w", encoding="utf-8") as rf:
        json.dump(audit_table, rf, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
