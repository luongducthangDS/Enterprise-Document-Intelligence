#!/usr/bin/env python3
"""Normalize registry/Chroma metadata for strict department isolation.

Dry-run is the default. Examples:
  python scripts/rag_pipeline/migrate_department_acl.py
  python scripts/rag_pipeline/migrate_department_acl.py --apply-registry
  python scripts/rag_pipeline/migrate_department_acl.py --apply-chroma
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import get_settings  # noqa: E402
from src.ingestion.indexer import get_chroma_client  # noqa: E402
from src.security.departments import canonical_department  # noqa: E402
from src.security.tenant_resolver import get_tenant_collection_name  # noqa: E402

COMMON_FIELDS = [
    "source_file",
    "document_domain",
    "related_departments",
    "access_scope",
    "authorized_departments",
    "authorized_roles",
    "authorization_status",
    "authorization_source",
    "classification_source",
    "is_knowledge_doc",
    "department",
    "sensitivity",
    "scope",
    "access_category",
    "issuer",
    "document_type",
    "classification_confidence",
    "classification_status",
    "classification_reason",
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
    "publication_status",
    "artifact_state",
    "retrieval_enabled",
    "expiry_date",
]
PRODUCT_EXTRA_FIELDS = ["document_id", "relative_path", "owner"]
REGISTRIES = {
    Path("data/metadata/document_registry.csv"): None,
    Path("data/metadata/accounting_document_registry.csv"): "ACCOUNTING",
    Path("data/metadata/product_document_registry.csv"): "PRODUCT",
}


def _json_list(value: str, fallback: str) -> str:
    try:
        values = json.loads(value or "[]")
    except json.JSONDecodeError:
        values = [part.strip() for part in (value or "").split(",") if part.strip()]
    normalized = [canonical_department(item) for item in values]
    if fallback not in normalized:
        normalized.append(fallback)
    return json.dumps(normalized, ensure_ascii=False)


def normalize_row(row: dict[str, str], forced_department: str | None) -> dict[str, str]:
    department = canonical_department(forced_department or row.get("department"))
    if department == "GENERAL":
        department = "HR"
    normalized = dict(row)
    normalized.update(
        {
            "department": department,
            "access_scope": (
                "DEPARTMENT"
                if (row.get("access_scope") or "COMPANY_WIDE").upper() == "COMPANY_WIDE"
                else row["access_scope"].upper()
            ),
            "authorized_departments": _json_list(row.get("authorized_departments", "[]"), department),
            "related_departments": _json_list(row.get("related_departments", "[]"), department),
            "authorized_roles": row.get("authorized_roles") or "[]",
            "authorization_status": row.get("authorization_status") or "ACTIVE",
            "authorization_source": row.get("authorization_source") or "DEPARTMENT_SOP_POLICY",
            "classification_source": row.get("classification_source") or "DETERMINISTIC_AUDIT",
            "is_knowledge_doc": row.get("is_knowledge_doc") or "true",
            "sensitivity": row.get("sensitivity") or "INTERNAL",
            "scope": "DEPARTMENT" if row.get("scope", "COMPANY_WIDE") == "COMPANY_WIDE" else row["scope"],
            "classification_confidence": row.get("classification_confidence") or "1.00",
            "classification_status": row.get("classification_status") or "APPROVED",
        }
    )
    return normalized


def migrate_registry(path: Path, forced_department: str | None, apply: bool) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        old_fields = reader.fieldnames or []
    normalized_rows = [normalize_row(row, forced_department) for row in rows]
    changed = sum(before != after for before, after in zip(rows, normalized_rows))
    if apply and changed:
        fields = COMMON_FIELDS + [field for field in PRODUCT_EXTRA_FIELDS if field in old_fields]
        with tempfile.NamedTemporaryFile(
            "w", delete=False, encoding="utf-8-sig", newline="", dir=path.parent
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(normalized_rows)
            temporary_path = handle.name
        os.replace(temporary_path, path)
    print(f"registry={path} rows={len(rows)} changed={changed} applied={apply}")
    return changed


def migrate_collection(name: str, forced_department: str | None, apply: bool) -> int:
    collection = get_chroma_client(get_settings()).get_collection(name)
    changed = 0
    offset = 0
    while True:
        batch = collection.get(limit=300, offset=offset, include=["metadatas"])
        ids = batch.get("ids") or []
        metadatas = batch.get("metadatas") or []
        if not ids:
            break
        updated_ids: list[str] = []
        updated_metadatas: list[dict] = []
        for chunk_id, metadata in zip(ids, metadatas):
            before = dict(metadata or {})
            department = canonical_department(forced_department or before.get("department"))
            if department == "GENERAL":
                department = "HR"
            updates: dict = {}
            if before.get("department") != department:
                updates["department"] = department
            current_scope = str(before.get("access_scope") or before.get("scope") or "COMPANY_WIDE").upper()
            if current_scope == "COMPANY_WIDE":
                updates["access_scope"] = "DEPARTMENT"
                # Chroma update merges metadata. Remove the obsolete alias when
                # a legacy chunk is already at the 32-key collection quota.
                if "access_scope" not in before and "scope" in before:
                    updates["scope"] = None
            if updates:
                changed += 1
                updated_ids.append(chunk_id)
                updated_metadatas.append(updates)
        if apply and updated_ids:
            collection.update(ids=updated_ids, metadatas=updated_metadatas)
        offset += len(ids)
    print(f"collection={name} changed={changed} applied={apply}")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-registry", action="store_true")
    parser.add_argument("--apply-chroma", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    for path, department in REGISTRIES.items():
        migrate_registry(path, department, args.apply_registry)
    collections = {
        get_tenant_collection_name(settings.active_tenant): None,
        settings.chroma_accounting_collection_name: "ACCOUNTING",
        settings.chroma_product_collection_name: "PRODUCT",
    }
    if args.apply_chroma:
        for name, department in collections.items():
            migrate_collection(name, department, apply=True)
    else:
        print("Chroma unchanged; pass --apply-chroma to backfill cloud/local collections.")


if __name__ == "__main__":
    main()
