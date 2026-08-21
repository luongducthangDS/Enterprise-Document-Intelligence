#!/usr/bin/env python3
"""Script kiểm định và phân loại toàn bộ kho dữ liệu doanh nghiệp NexaTech.

Phân định nghiêm ngặt:
1. KNOWLEDGE DOCUMENTS (COMPANY_POLICY, DEPARTMENT_PROCESS, LEGAL, MANAGEMENT, MEETING_MINUTES, EXTERNAL_REFERENCE)
2. NON-KNOWLEDGE / SYSTEM DATA (EVALUATION_DATA, USER_PERSONA, SYSTEM_CONFIGURATION)

Tách biệt hoàn toàn:
1. Question A — Document là gì? (document_domain, is_knowledge_doc)
2. Question B — Liên quan đến ai? (related_departments: Semantic recommendation only)
3. Question C — Ai được phép truy cập? (access_scope, authorized_departments, authorized_roles, authorization_status, authorization_source)
"""

import csv
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

# 1. Danh sách 10 COMPANY_POLICY
COMPANY_POLICIES = [
    "01_chinh-sach-lam-them-gio-OT.md",
    "05_chinh-sach-lam-viec-tu-xa.md",
    "06_chinh-sach-dao-tao-phat-trien.md",
    "07_chinh-sach-nghi-phep.md",
    "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md",
    "09_chinh-sach-bao-hiem-xa-hoi-bat-buoc.md",
    "10_chinh-sach-an-toan-ve-sinh-lao-dong.md",
    "11_chinh-sach-danh-gia-hieu-suat-kpi.md",
    "12_quy-che-cong-tac-phi.md",
    "13_noi-quy-lao-dong-va-ky-luat.md",
]

# 2. Danh sách 9 DEPARTMENT_PROCESS (3 HR cũ + 6 phòng ban mới)
DEPARTMENT_PROCESSES = {
    "02_quy-trinh-tuyen-dung.md": ("HR", ["HR_OPERATOR", "MANAGER", "ADMIN"]),
    "03_quy-trinh-onboarding.md": ("HR", ["HR_OPERATOR", "MANAGER", "ADMIN"]),
    "04_quy-trinh-offboarding.md": ("HR", ["HR_OPERATOR", "MANAGER", "ADMIN"]),
    "it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md": ("IT", ["DEPARTMENT_USER", "MANAGER", "ADMIN"]),
    "fin_sop_01_tam-ung-quyet-toan-cong-tac-phi.md": ("FINANCE", ["FINANCE_OFFICER", "MANAGER", "ADMIN"]),
    "eng_sop_01_quy-trinh-oncall-xu-ly-su-co.md": ("ENGINEERING", ["DEPARTMENT_USER", "MANAGER", "ADMIN"]),
    "prc_sop_01_quy-trinh-mua-sam-lua-chon-nha-thau.md": ("PROCUREMENT", ["DEPARTMENT_USER", "MANAGER", "ADMIN"]),
    "leg_sop_01_tham-dinh-hop-dong-va-nda.md": ("LEGAL_COMPLIANCE", ["LEGAL_COUNSEL", "MANAGER", "ADMIN"]),
    "ops_sop_01_quan-ly-van-phong-pham-co-so-vat-chat.md": ("OPERATIONS", ["DEPARTMENT_USER", "MANAGER", "ADMIN"]),
}

# 3. Danh sách 10 LEGAL (Văn bản luật nhà nước)
LEGAL_DOCS = {
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

# 4. Danh sách 6 MANAGEMENT Decisions
MANAGEMENT_DOCS = [
    "mgt_dec_01_ngan-sach-chuyen-doi-so-ai.md",
    "mgt_dec_02_dieu-chinh-hybrid-wfh-2026.md",
    "mgt_dec_03_siet-chat-an-toan-thong-tin-byod.md",
    "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md",
    "mgt_dec_05_tieu-chuan-tuyen-dung-tech-lead.md",
    "mgt_dec_06_thanh-lap-ban-ung-pho-su-co-bcp.md",
]

# 5. Danh sách 6 MEETING_MINUTES
MEETING_MINUTES_DOCS = [
    "bod_mm_01_hop-giao-ban-ban-giam-doc-082026.md",
    "ops_mm_01_hop-lien-phong-ban-chi-phi-thiet-bi.md",
    "sec_mm_01_hop-ra-soat-su-co-an-ninh-mang.md",
    "hr_mm_01_hop-hoi-dong-tuyen-dung-dai-ngo-q3.md",
    "prd_mm_01_hop-sprint-review-doc-intelligence.md",
    "fin_mm_01_hop-kiem-toan-noi-bo-cong-tac-phi.md",
]

# 6. Danh sách 10 EXTERNAL_REFERENCE
EXTERNAL_REFERENCES = [
    "1050517962-VF-I-4-1-001-V5-Quy-định-nội-bộ-Cong-ty-VinFast-08-08-2019.pdf",
    "842059170-18-Nguyễn-Đinh-Hải-Lam-Quy-Trinh-Tuyển-Dụng-Chung-Của-Vingroup.pdf",
    "[Base.vn] Mẫu sơ đồ quy trình tuyển dụng nhân sự.docx.pdf",
    "base_mau-quy-che-luong-thuong-phu-cap-xu-phat.docx",
    "leanh_mau-noi-quy-lao-dong.docx",
    "talentnet_quy-trinh-cham-dut-hop-dong-lao-dong.md",
    "base_quy-che-cong-tac-phi-va-phu-cap.md",
    "mau_quy-che-danh-gia-hieu-suat-kpi.md",
    "mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md",
    "mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai.md",
]

# 7. Danh sách 4 NON-KNOWLEDGE / SYSTEM DATA
SYSTEM_DATA = [
    ("qa_eval_set.json", "EVALUATION_DATA"),
    ("ground_truth_extractions.json", "EVALUATION_DATA"),
    ("mock_user_personas.json", "USER_PERSONA"),
    ("ticket_routing_rules.json", "SYSTEM_CONFIGURATION"),
]


def build_canonical_registry() -> list[dict]:
    rows = []

    # 1. COMPANY_POLICY
    for sf in COMPANY_POLICIES:
        rows.append({
            "source_file": sf,
            "document_domain": "COMPANY_POLICY",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps(["ALL"], ensure_ascii=False),
            "access_scope": "COMPANY_WIDE",
            "authorized_departments": json.dumps([], ensure_ascii=False),
            "authorized_roles": json.dumps([], ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "OFFICIAL_COMPANY_ISSUANCE",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": "GENERAL",
            "sensitivity": "INTERNAL",
            "category": "company_policy",
            "status": "processed",
            "processed_path": f"data/processed/{sf}",
            "chunks_path": f"data/chunks/{sf}.json",
            "source_type": "synthetic",
            "is_official_policy": "True",
            "caveat": "",
            "authority": "tenant_official_policy",
            "provenance": "synthetic_demo",
            "tenant": "NexaTech",
            "issuer": "Công ty Cổ phần Tập đoàn NexaTech",
            "document_type": "Chính sách / Quy chế nội bộ",
            "scope": "COMPANY_WIDE",
            "access_category": "COMPANY_POLICY",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Chính sách chính thức do NexaTech ban hành, phạm vi toàn công ty.",
            "retrieval_enabled": "True",
        })

    # 2. DEPARTMENT_PROCESS
    for sf, (dept, roles) in DEPARTMENT_PROCESSES.items():
        rows.append({
            "source_file": sf,
            "document_domain": "DEPARTMENT_PROCESS",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps([dept], ensure_ascii=False),
            "access_scope": "DEPARTMENT",
            "authorized_departments": json.dumps([dept], ensure_ascii=False),
            "authorized_roles": json.dumps(roles, ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "DEPARTMENT_SOP_POLICY",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": dept,
            "sensitivity": "INTERNAL",
            "category": "department_process",
            "status": "processed",
            "processed_path": f"data/processed/{sf}",
            "chunks_path": f"data/chunks/{sf}.json",
            "source_type": "synthetic",
            "is_official_policy": "True",
            "caveat": "",
            "authority": "tenant_official_policy",
            "provenance": "synthetic_demo",
            "tenant": "NexaTech",
            "issuer": f"Phòng ban {dept} - Tập đoàn NexaTech",
            "document_type": "Quy trình vận hành nội bộ (SOP)",
            "scope": "DEPARTMENT_ONLY",
            "access_category": "DEPARTMENT",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": f"SOP riêng của phòng {dept}. Yêu cầu Department={dept} AND Role in {roles}.",
            "retrieval_enabled": "True",
        })

    # 3. LEGAL
    for sf, rel_depts in LEGAL_DOCS.items():
        stem = os.path.splitext(sf)[0]
        rows.append({
            "source_file": sf,
            "document_domain": "LEGAL",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps(rel_depts, ensure_ascii=False),
            "access_scope": "PENDING_REVIEW",
            "authorized_departments": json.dumps([], ensure_ascii=False),
            "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
            "authorization_status": "PENDING_REVIEW",
            "authorization_source": "PENDING_BUSINESS_DECISION",
            "classification_source": "RULE_GOVERNMENT_ISSUER",
            "department": "EXTERNAL",
            "sensitivity": "PUBLIC",
            "category": "government_legal",
            "status": "processed",
            "processed_path": f"data/processed/{stem}.md",
            "chunks_path": f"data/chunks/{stem}.json",
            "source_type": "government_law",
            "is_official_policy": "False",
            "caveat": "Văn bản quy phạm pháp luật nhà nước",
            "authority": "government_law",
            "provenance": "government_source",
            "tenant": "",
            "issuer": "Cơ quan Nhà nước Việt Nam",
            "document_type": "Văn bản quy phạm pháp luật",
            "scope": "EXTERNAL",
            "access_category": "LEGAL",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Văn bản pháp luật nhà nước. Trạng thái phân quyền: PENDING_REVIEW.",
            "retrieval_enabled": "True",
        })

    # 4. MANAGEMENT
    for sf in MANAGEMENT_DOCS:
        rows.append({
            "source_file": sf,
            "document_domain": "MANAGEMENT",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps(["ALL"], ensure_ascii=False),
            "access_scope": "ROLE",
            "authorized_departments": json.dumps(["ALL"], ensure_ascii=False),
            "authorized_roles": json.dumps(["MANAGER", "EXECUTIVE", "ADMIN"], ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "MANAGEMENT_EXECUTIVE_ORDER",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": "EXECUTIVE",
            "sensitivity": "CONFIDENTIAL",
            "category": "management_decision",
            "status": "processed",
            "processed_path": f"data/processed/{sf}",
            "chunks_path": f"data/chunks/{sf}.json",
            "source_type": "synthetic",
            "is_official_policy": "True",
            "caveat": "",
            "authority": "tenant_official_policy",
            "provenance": "synthetic_demo",
            "tenant": "NexaTech",
            "issuer": "Tổng Giám đốc Tập đoàn NexaTech",
            "document_type": "Quyết định Ban Điều hành",
            "scope": "MANAGEMENT_ONLY",
            "access_category": "MANAGEMENT",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Quyết định điều hành của Ban Giám đốc. Quyền truy cập: Role in [MANAGER, EXECUTIVE, ADMIN].",
            "retrieval_enabled": "True",
        })

    # 5. MEETING_MINUTES
    for sf in MEETING_MINUTES_DOCS:
        rows.append({
            "source_file": sf,
            "document_domain": "MEETING_MINUTES",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps(["ALL"], ensure_ascii=False),
            "access_scope": "ROLE",
            "authorized_departments": json.dumps(["ALL"], ensure_ascii=False),
            "authorized_roles": json.dumps(["MANAGER", "EXECUTIVE", "ADMIN"], ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "EXECUTIVE_MEETING_RECORD",
            "classification_source": "DETERMINISTIC_AUDIT",
            "department": "EXECUTIVE",
            "sensitivity": "CONFIDENTIAL",
            "category": "meeting_minutes",
            "status": "processed",
            "processed_path": f"data/processed/{sf}",
            "chunks_path": f"data/chunks/{sf}.json",
            "source_type": "synthetic",
            "is_official_policy": "True",
            "caveat": "",
            "authority": "tenant_official_policy",
            "provenance": "synthetic_demo",
            "tenant": "NexaTech",
            "issuer": "Văn phòng Ban Tổng Giám đốc",
            "document_type": "Biên bản Họp Lãnh đạo",
            "scope": "MANAGEMENT_ONLY",
            "access_category": "MEETING_MINUTES",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Biên bản họp chính thức chứa quyết định, action items, người phụ trách và deadline.",
            "retrieval_enabled": "True",
        })

    # 6. EXTERNAL_REFERENCE
    for sf in EXTERNAL_REFERENCES:
        stem = os.path.splitext(sf)[0]
        rows.append({
            "source_file": sf,
            "document_domain": "EXTERNAL_REFERENCE",
            "is_knowledge_doc": "True",
            "related_departments": json.dumps([], ensure_ascii=False),
            "access_scope": "RESTRICTED",
            "authorized_departments": json.dumps([], ensure_ascii=False),
            "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "EXTERNAL_REFERENCE_DEFAULT_RESTRICTED",
            "classification_source": "EXTERNAL_ORIGIN_AUDIT",
            "department": "EXTERNAL",
            "sensitivity": "PUBLIC",
            "category": "external_reference",
            "status": "processed",
            "processed_path": f"data/processed/{stem}.md",
            "chunks_path": f"data/chunks/{stem}.json",
            "source_type": "public_template",
            "is_official_policy": "False",
            "caveat": "Tài liệu mẫu / tham khảo bên ngoài",
            "authority": "public_reference",
            "provenance": "public_web",
            "tenant": "",
            "issuer": "Nguồn bên ngoài / Mẫu tham khảo",
            "document_type": "Mẫu biểu / Tài liệu tham khảo",
            "scope": "EXTERNAL",
            "access_category": "EXTERNAL_REFERENCE",
            "classification_confidence": "0.98",
            "classification_status": "APPROVED",
            "classification_reason": "Tài liệu mẫu hoặc tài liệu từ tổ chức ngoài (VinFast, Vingroup, Base.vn, Talentnet).",
            "retrieval_enabled": "False",
        })

    # 7. NON-KNOWLEDGE / SYSTEM DATA
    for sf, dom in SYSTEM_DATA:
        rows.append({
            "source_file": sf,
            "document_domain": dom,
            "is_knowledge_doc": "False",
            "related_departments": json.dumps([], ensure_ascii=False),
            "access_scope": "RESTRICTED",
            "authorized_departments": json.dumps([], ensure_ascii=False),
            "authorized_roles": json.dumps(["ADMIN"], ensure_ascii=False),
            "authorization_status": "ACTIVE",
            "authorization_source": "SYSTEM_INTERNAL",
            "classification_source": "SYSTEM_CONFIG",
            "department": "SYSTEM",
            "sensitivity": "INTERNAL",
            "category": "system_data",
            "status": "processed",
            "processed_path": f"data/metadata/{sf}",
            "chunks_path": "",
            "source_type": "config",
            "is_official_policy": "False",
            "caveat": "Dữ liệu hệ thống / Đánh giá",
            "authority": "non_rag",
            "provenance": "internal_config",
            "tenant": "NexaTech",
            "issuer": "Engineering & QA Team",
            "document_type": "System / Evaluation Data",
            "scope": "INTERNAL",
            "access_category": "CONFIG",
            "classification_confidence": "1.00",
            "classification_status": "APPROVED",
            "classification_reason": "Dữ liệu cấu hình hoặc benchmark hệ thống. Loại khỏi RAG.",
            "retrieval_enabled": "False",
        })


    return rows


def main():
    registry_path = "data/metadata/document_registry.csv"
    rows = build_canonical_registry()

    fieldnames = [
        "source_file",
        "document_domain",
        "is_knowledge_doc",
        "related_departments",
        "access_scope",
        "authorized_departments",
        "authorized_roles",
        "authorization_status",
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
        "retrieval_enabled",
    ]

    with open(registry_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Thống kê
    stats_domain = {}
    stats_knowledge = {"Knowledge Documents": 0, "Non-Knowledge / System Data": 0}
    for r in rows:
        dom = r["document_domain"]
        stats_domain[dom] = stats_domain.get(dom, 0) + 1
        if r["is_knowledge_doc"] == "True":
            stats_knowledge["Knowledge Documents"] += 1
        else:
            stats_knowledge["Non-Knowledge / System Data"] += 1

    print(f"✅ Đã ghi nhận chính xác {len(rows)} canonical files vào {registry_path}!")
    print("\n--- BÁO CÁO PHÂN LOẠI ĐỘC QUYỀN TƯƠNG HỖ (MUTUALLY-EXCLUSIVE BREAKDOWN) ---")
    print(f"  • TOTAL FILES                   : {len(rows)}")
    print(f"  • KNOWLEDGE DOCUMENTS           : {stats_knowledge['Knowledge Documents']}")
    for k in ["COMPANY_POLICY", "DEPARTMENT_PROCESS", "LEGAL", "MANAGEMENT", "MEETING_MINUTES", "EXTERNAL_REFERENCE"]:
        print(f"      - {k:22}: {stats_domain.get(k, 0)} files")
    print(f"  • NON-KNOWLEDGE / SYSTEM DATA   : {stats_knowledge['Non-Knowledge / System Data']}")
    for k in ["EVALUATION_DATA", "USER_PERSONA", "SYSTEM_CONFIGURATION"]:
        print(f"      - {k:22}: {stats_domain.get(k, 0)} files")


if __name__ == "__main__":
    main()
