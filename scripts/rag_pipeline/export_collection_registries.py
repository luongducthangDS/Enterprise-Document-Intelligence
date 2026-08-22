#!/usr/bin/env python3
"""Export fail-closed document registries from verified live Chroma metadata.

Read-only for Chroma. DEPARTMENT documents are restricted to their own
department. Unsupported or ambiguous scopes are marked PENDING_REVIEW.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client
from src.ingestion.metadata import RegistryRow

SAFE_SCOPES = {"COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"}


def _first_by_source(collection) -> dict[str, dict]:
    result = collection.get(include=["metadatas"])
    documents: dict[str, dict] = {}
    for metadata in result.get("metadatas") or []:
        source_file = str(metadata.get("source_file") or "").strip()
        if source_file:
            documents.setdefault(source_file, metadata)
    return documents


def _row(source_file: str, metadata: dict, domain: str) -> dict:
    department = str(metadata.get("department") or "GENERAL").upper()
    raw_scope = str(metadata.get("access_scope") or metadata.get("scope") or "").upper()
    scope = raw_scope if raw_scope in SAFE_SCOPES else "PENDING_REVIEW"
    authorization_status = "ACTIVE" if scope in SAFE_SCOPES else "PENDING_REVIEW"
    authorized_departments = (
        json.dumps([department], ensure_ascii=False)
        if scope == "DEPARTMENT" and department != "GENERAL"
        else "[]"
    )
    return {
        "source_file": source_file,
        "document_domain": str(metadata.get("document_domain") or "COMPANY_POLICY"),
        "related_departments": "[]",
        "access_scope": scope,
        "authorized_departments": authorized_departments,
        "authorized_roles": "[]",
        "authorization_status": authorization_status,
        "authorization_source": "CHROMA_VERIFIED_BASELINE",
        "classification_source": "DETERMINISTIC_AUDIT",
        "is_knowledge_doc": "true",
        "department": department,
        "sensitivity": "INTERNAL",
        "scope": scope,
        "access_category": str(metadata.get("access_category") or "GENERAL"),
        "issuer": str(metadata.get("issuer") or ""),
        "document_type": str(metadata.get("document_type") or ""),
        "classification_confidence": "1.00",
        "classification_status": "APPROVED" if authorization_status == "ACTIVE" else "PENDING_REVIEW",
        "classification_reason": "Recovered from verified live Chroma baseline",
        "category": str(metadata.get("category") or domain),
        "status": "processed",
        "processed_path": f"data/processed/{Path(source_file).stem}.md",
        "chunks_path": f"data/chunks/{Path(source_file).stem}.json",
        "indexed_at": "",
        "source_type": str(metadata.get("source_type") or "synthetic"),
        "is_official_policy": str(bool(metadata.get("is_official_policy", True))).lower(),
        "caveat": str(metadata.get("caveat") or ""),
        "authority": str(metadata.get("authority") or "tenant_official_policy"),
        "provenance": str(metadata.get("provenance") or "synthetic_demo"),
        "tenant": str(metadata.get("tenant") or "nexatech"),
        "publication_status": str(metadata.get("publication_status") or "active"),
        "artifact_state": str(metadata.get("artifact_state") or "frozen"),
        "retrieval_enabled": str(bool(metadata.get("retrieval_enabled", True))).lower(),
        "expiry_date": "9999-12-31",
    }


def export(collection_name: str, output: Path, domain: str) -> dict:
    client = get_chroma_client(get_settings())
    collection = client.get_collection(collection_name)
    documents = _first_by_source(collection)
    rows = [_row(source, metadata, domain) for source, metadata in sorted(documents.items())]
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(RegistryRow.model_fields)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "documents": len(rows),
        "pending_review": sum(row["authorization_status"] != "ACTIVE" for row in rows),
    }


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-out", default="data/metadata/document_registry.csv")
    parser.add_argument("--accounting-out", default="data/metadata/accounting_document_registry.csv")
    args = parser.parse_args()
    result = {
        settings.chroma_collection_name: export(
            settings.chroma_collection_name, Path(args.core_out), "core"
        ),
        settings.chroma_accounting_collection_name: export(
            settings.chroma_accounting_collection_name,
            Path(args.accounting_out),
            "accounting",
        ),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
