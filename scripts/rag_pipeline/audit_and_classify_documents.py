#!/usr/bin/env python3
"""Script kiểm định và phân loại tài liệu theo kiến trúc Enterprise Document Intelligence Platform.

Tách biệt hoàn toàn 3 câu hỏi độc lập:
1. Question A — Document là gì? (document_domain: COMPANY_POLICY | LEGAL | DEPARTMENT_PROCESS | EXTERNAL_REFERENCE | OTHER)
2. Question B — Liên quan đến ai? (related_departments: Semantic relevance recommendation only. KHÔNG cấp quyền)
3. Question C — Ai được phép truy cập? (access_scope, authorized_departments, authorized_roles, authorization_source)
"""

import csv
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config import get_settings


LEGAL_DOC_RELATED_DEPTS = {
    "bộ luật lao động.pdf": ["HR", "LEGAL_COMPLIANCE"],
    "nghi_dinh_293_2025_nd_cp_luong_toi_thieu.pdf": ["HR", "FINANCE", "ACCOUNTING"],
    "luat_bao_hiem_xa_hoi_41_2024_qh15.pdf": ["HR", "ACCOUNTING"],
    "nghi_dinh_158_2025_nd_cp_bhxh_bat_buoc.pdf": ["HR", "ACCOUNTING", "FINANCE"],
    "nghi_dinh_145_2020_nd_cp.pdf": ["HR", "LEGAL_COMPLIANCE"],
    "luat_an_toan_ve_sinh_lao_dong_84_2015_qh13.pdf": ["HR", "OPERATIONS", "ENGINEERING"],
    "112-vbhn-vpqh_luat_thue_tncn.pdf": ["HR", "FINANCE", "ACCOUNTING"],
    "luat51.pdf": ["HR", "ACCOUNTING"],
    "thong-tu-60-2025-TT-BHYT-2026.pdf": ["HR", "OPERATIONS", "ENGINEERING"],
    "161-ndcp.signed.pdf": ["HR", "FINANCE", "ACCOUNTING"],
}


def classify_document(row: dict) -> dict:
    """Áp dụng Deterministic Audit Rules phân định Domain, Semantic Relevance, và Authorization."""
    sf = row["source_file"]
    st = row.get("source_type", "")
    cat = row.get("category", "")

    # 1. Config Assets (Non-RAG)
    if sf.endswith(".json"):
        return {
            "document_domain": "OTHER",
            "related_departments": json.dumps([], ensure_ascii=False),
            "access_scope": "RESTRICTED",
            "authorized_departments": json.dumps([], ensure_ascii=False),
            "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
            "authorization_source": "SYSTEM_INTERNAL",
            "classification_source": "SYSTEM_CONFIG",
            "department": "CONFIG",
            "sensitivity": "INTERNAL",
            "scope": "INTERNAL",
            "access_category": "CONFIG",
            "issuer": "System",
            "document_type": "Config Asset",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Tài liệu cấu hình nội bộ hệ thống.",
        }

    # 2. LEGAL Documents (Văn bản quy phạm pháp luật nhà nước)
    if st == "government_law" or cat == "government_legal" or sf in LEGAL_DOC_RELATED_DEPTS:
        rel_depts = LEGAL_DOC_RELATED_DEPTS.get(sf, ["LEGAL_COMPLIANCE"])
        return {
            "document_domain": "LEGAL",
            "related_departments": json.dumps(rel_depts, ensure_ascii=False),
            "access_scope": "PENDING_REVIEW",
            "authorized_departments": json.dumps([], ensure_ascii=False),  # CHƯA CẤP QUYỀN - Chờ Enterprise Admin cấu hình
            "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
            "authorization_source": "PENDING_BUSINESS_DECISION",
            "classification_source": "RULE_GOVERNMENT_ISSUER",
            "department": "EXTERNAL",
            "sensitivity": "PUBLIC",
            "scope": "EXTERNAL",
            "access_category": "LEGAL",
            "issuer": row.get("issuer") or "Cơ quan Nhà nước Việt Nam",
            "document_type": row.get("document_type") or "Văn bản quy phạm pháp luật",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": f"Văn bản pháp luật nhà nước. Khuyến nghị liên quan đến {rel_depts}, nhưng chưa cấu hình consumer (authorized_departments = []).",
        }

    # 3. COMPANY_POLICY (Chính sách/Quy chế toàn công ty của NexaTech)
    company_policy_prefixes = ("01_", "05_", "06_", "07_", "08_", "09_", "10_", "11_", "12_", "13_")
    if sf.startswith(company_policy_prefixes):
        return {
            "document_domain": "COMPANY_POLICY",
            "related_departments": json.dumps(["ALL"], ensure_ascii=False),
            "access_scope": "COMPANY_WIDE",
            "authorized_departments": json.dumps(["ALL"], ensure_ascii=False),
            "authorized_roles": json.dumps(["ALL"], ensure_ascii=False),
            "authorization_source": "OFFICIAL_COMPANY_ISSUANCE",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": "GENERAL",
            "sensitivity": "INTERNAL",
            "scope": "COMPANY_WIDE",
            "access_category": "COMPANY_POLICY",
            "issuer": "Công ty Cổ phần Tập đoàn NexaTech",
            "document_type": "Chính sách / Quy chế nội bộ",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Chính sách chính thức do NexaTech ban hành, áp dụng chung cho toàn thể cán bộ nhân viên.",
        }

    # 4. DEPARTMENT_PROCESS (SOP/Quy trình nội bộ phòng ban)
    department_process_prefixes = ("02_", "03_", "04_")
    if sf.startswith(department_process_prefixes):
        dept = "HR"
        return {
            "document_domain": "DEPARTMENT_PROCESS",
            "related_departments": json.dumps([dept], ensure_ascii=False),
            "access_scope": "DEPARTMENT",
            "authorized_departments": json.dumps([dept], ensure_ascii=False),
            "authorized_roles": json.dumps(["HR_OPERATOR", "MANAGER", "ADMIN"], ensure_ascii=False),
            "authorization_source": "DEPARTMENT_SOP_POLICY",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": dept,
            "sensitivity": "INTERNAL",
            "scope": "DEPARTMENT_ONLY",
            "access_category": "DEPARTMENT",
            "issuer": f"Phòng Nhân sự - Công ty Cổ phần Tập đoàn NexaTech",
            "document_type": "Quy trình nội bộ phòng ban (SOP)",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Quy trình vận hành nội bộ riêng của phòng HR (tuyển dụng, onboarding, offboarding).",
        }

    # 5. EXTERNAL_REFERENCE (Template, bài viết hoặc chính sách công ty ngoài)
    return {
        "document_domain": "EXTERNAL_REFERENCE",
        "related_departments": json.dumps([], ensure_ascii=False),
        "access_scope": "RESTRICTED",
        "authorized_departments": json.dumps([], ensure_ascii=False),
        "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
        "authorization_source": "EXTERNAL_REFERENCE_DEFAULT_RESTRICTED",
        "classification_source": "EXTERNAL_ORIGIN_AUDIT",
        "department": "EXTERNAL",
        "sensitivity": "PUBLIC",
        "scope": "EXTERNAL",
        "access_category": "EXTERNAL_REFERENCE",
        "issuer": row.get("issuer") or "Nguồn bên ngoài / Mẫu tham khảo",
        "document_type": row.get("document_type") or "Mẫu biểu / Tài liệu tham khảo",
        "classification_confidence": "0.98",
        "classification_status": "APPROVED",
        "classification_reason": "Tài liệu mẫu hoặc tài liệu từ tổ chức ngoài (VinFast, Vingroup, Base.vn, Talentnet). Quyền truy cập mặc định là RESTRICTED.",
    }


def main():
    registry_path = "data/metadata/document_registry.csv"
    with open(registry_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"=== Đang thực hiện Audit & Chuẩn hóa 3 chiều cho {len(rows)} tài liệu... ===")

    stats = {
        "COMPANY_POLICY": 0,
        "LEGAL": 0,
        "DEPARTMENT_PROCESS": 0,
        "EXTERNAL_REFERENCE": 0,
        "OTHER": 0,
    }

    updated_rows = []
    for r in rows:
        classified = classify_document(r)
        domain = classified["document_domain"]
        stats[domain] = stats.get(domain, 0) + 1
        r.update(classified)
        updated_rows.append(r)

    fieldnames = [
        "source_file",
        "document_domain",
        "related_departments",
        "access_scope",
        "authorized_departments",
        "authorized_roles",
        "authorization_source",
        "classification_source",
        "department",
        "sensitivity",
        "category",
        "status",
        "processed_path",
        "chunks_path",
        "indexed_at",
        "source_type",
        "is_official_policy",
        "caveat",
        "authority",
        "provenance",
        "tenant",
        "issuer",
        "document_type",
        "scope",
        "access_category",
        "classification_confidence",
        "classification_status",
        "classification_reason",
    ]

    with open(registry_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in updated_rows:
            row_out = {k: r.get(k, "") for k in fieldnames}
            writer.writerow(row_out)

    print(f"✅ Đã cập nhật xong {registry_path}!")
    print("\n--- THỐNG KÊ AUDIT METADATA ---")
    for k, v in stats.items():
        print(f"  • {k:20}: {v} tài liệu")


if __name__ == "__main__":
    main()
