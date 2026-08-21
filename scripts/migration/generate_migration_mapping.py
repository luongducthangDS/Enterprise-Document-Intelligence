#!/usr/bin/env python3
"""Sinh bảng ánh xạ định danh Deterministic cho Migration (Deterministic ID Mapper).

Mục tiêu:
1. Đảm bảo tính bất biến (Idempotent): Mỗi lần chạy migration với cùng tài liệu luôn sinh ra cùng document_id, version_id.
2. Không dùng source_stem làm primary key.
3. Không giả định version='v1.0' tùy tiện (ghi rõ version_source='LEGACY_MIGRATION').
4. Lưu mapping vào 'data/metadata/migration_document_map.json'.
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.ingestion.metadata import load_registry, rag_eligible_rows

# Namespace cố định chuẩn UUIDv5 cho Enterprise Knowledge
NEXATECH_TENANT_UUID = "b85f9f02-ca5d-484a-8ad0-cb4ab301e175"
NEXATECH_TENANT_SLUG = "nexatech"
ENTERPRISE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "knowledge.nexatech.vn")


def generate_migration_mapping(
    registry_path: str = "data/metadata/document_registry.csv",
    output_path: str = "data/metadata/migration_document_map.json",
) -> dict:
    rows = rag_eligible_rows(load_registry(registry_path))
    mapping = {
        "metadata": {
            "tenant_id": NEXATECH_TENANT_UUID,
            "tenant_slug": NEXATECH_TENANT_SLUG,
            "total_documents": len(rows),
            "generated_at": "2026-08-21T22:25:00Z",
            "id_generation_method": "UUIDv5_DETERMINISTIC",
        },
        "documents": {},
    }

    for row in rows:
        source_file = row.source_file
        source_stem = os.path.splitext(source_file)[0]
        doc_uuid = str(uuid.uuid5(ENTERPRISE_NAMESPACE, f"doc:{NEXATECH_TENANT_SLUG}:{source_file}"))
        ver_uuid = str(uuid.uuid5(ENTERPRISE_NAMESPACE, f"ver:{NEXATECH_TENANT_SLUG}:{source_file}:legacy_migration"))

        mapping["documents"][source_file] = {
            "document_id": doc_uuid,
            "version_id": ver_uuid,
            "tenant_id": NEXATECH_TENANT_UUID,
            "tenant_slug": NEXATECH_TENANT_SLUG,
            "source_file": source_file,
            "source_stem": source_stem,
            "category": row.category,
            "document_domain": getattr(row, "document_domain", "COMPANY_POLICY"),
            "access_scope": getattr(row, "access_scope", "COMPANY_WIDE"),
            "department": getattr(row, "department", "GENERAL"),
            "is_official_policy": row.is_official_policy,
            "provenance": row.provenance,
            "authority": row.authority,
            "version_source": "LEGACY_MIGRATION",
            "migration_source_collection": "hr_documents",
        }



    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"[Mapper] Đã tạo deterministic mapping cho {len(rows)} tài liệu vào: {output_path}")
    return mapping


if __name__ == "__main__":
    generate_migration_mapping()
