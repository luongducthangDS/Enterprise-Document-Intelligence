#!/usr/bin/env python3
"""Tách core, Accounting và Product thành ba Chroma collections.

Mặc định chỉ in kế hoạch. Chỉ thay đổi Cloud khi có ``--apply`` và
snapshot hợp lệ. Script copy + verify target trước khi xóa chọn lọc
ID khỏi collection core; tuyệt đối không reset/delete collection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection


def batched(items: list, size: int = 100):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def get_all(collection, *, where: dict | None = None, include: list[str] | None = None) -> dict:
    include = include or []
    total = collection.count()
    result = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    offset = 0
    while offset < total:
        response = collection.get(
            where=where,
            limit=min(250, total - offset),
            offset=offset,
            include=include,
        )
        ids = response.get("ids") or []
        if not ids:
            break
        result["ids"].extend(ids)
        for key in ("documents", "metadatas", "embeddings"):
            values = response.get(key)
            if values is not None and len(values) > 0:
                result[key].extend(values)
        offset += len(ids)
    return result


def get_by_ids(collection, ids: list[str], include: list[str]) -> dict:
    result = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    for id_batch in batched(ids):
        response = collection.get(ids=id_batch, include=include)
        result["ids"].extend(response.get("ids") or [])
        for key in ("documents", "metadatas", "embeddings"):
            values = response.get(key)
            if values is not None and len(values) > 0:
                result[key].extend(values)
    return result


def validate_snapshot(path: Path, collection_name: str, expected_count: int) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy snapshot bắt buộc: {path}")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    metadata = snapshot.get("metadata") or {}
    if metadata.get("source_collection") != collection_name:
        raise RuntimeError("Snapshot không thuộc collection nguồn")
    if metadata.get("total_vectors") != expected_count or len(snapshot.get("records") or []) != expected_count:
        raise RuntimeError("Snapshot không đủ record so với collection hiện tại")


def upsert_records(collection, records: dict) -> None:
    positions = {chunk_id: index for index, chunk_id in enumerate(records["ids"])}
    for id_batch in batched(records["ids"], 50):
        indexes = [positions[chunk_id] for chunk_id in id_batch]
        collection.upsert(
            ids=id_batch,
            documents=[records["documents"][index] for index in indexes],
            metadatas=[records["metadatas"][index] for index in indexes],
            embeddings=[records["embeddings"][index] for index in indexes],
        )


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Thực hiện copy/verify/delete chọn lọc")
    parser.add_argument(
        "--snapshot",
        default="storage/backups/snapshot_tenant_nexatech_before_domain_split_20260822.json",
    )
    parser.add_argument("--core", default=settings.chroma_collection_name)
    parser.add_argument("--accounting", default=settings.chroma_accounting_collection_name)
    parser.add_argument("--product", default=settings.chroma_product_collection_name)
    args = parser.parse_args()

    client = get_chroma_client(settings)
    core = client.get_collection(args.core)
    accounting = client.get_collection(args.accounting)
    product = get_collection(client, args.product)
    initial_core_count = core.count()

    product_records = get_all(
        core,
        where={"department": "Product"},
        include=["documents", "metadatas", "embeddings"],
    )
    accounting_ids = get_all(accounting)["ids"]
    accounting_records = get_by_ids(
        core,
        accounting_ids,
        include=["documents", "metadatas", "embeddings"],
    )

    product_ids = set(product_records["ids"])
    accounting_id_set = set(accounting_ids)
    if product_ids & accounting_id_set:
        raise RuntimeError("Product và Accounting có ID giao nhau; dừng tách")
    if product.count() != 82 or len(accounting_id_set) != 152:
        raise RuntimeError("Target collection chưa đủ baseline Product=82 / Accounting=152")
    if len(product_ids) not in (0, 82):
        raise RuntimeError(f"Core chứa một phần Product không hợp lệ: {len(product_ids)}/82")
    if len(accounting_records["ids"]) not in (0, 152):
        raise RuntimeError(f"Core chứa một phần Accounting không hợp lệ: {len(accounting_records['ids'])}/152")

    if not product_ids and not accounting_records["ids"]:
        print(
            json.dumps(
                {
                    "status": "already_split",
                    args.core: initial_core_count,
                    args.accounting: accounting.count(),
                    args.product: product.count(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    expected_core_count = initial_core_count - len(product_ids) - len(accounting_records["ids"])
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "core_before": initial_core_count,
                "accounting_in_core": len(accounting_records["ids"]),
                "product_in_core": len(product_ids),
                "core_after_expected": expected_core_count,
                "snapshot": args.snapshot,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        return

    validate_snapshot(Path(args.snapshot), args.core, initial_core_count)

    if product_records["ids"]:
        upsert_records(product, product_records)
    product_target_ids = set(get_all(product)["ids"])
    if not product_ids <= product_target_ids or product.count() != 82:
        raise RuntimeError("Xác minh product_documents thất bại; chưa xóa source")

    delete_ids = sorted(product_ids | accounting_id_set)
    for id_batch in batched(delete_ids):
        core.delete(ids=id_batch)

    remaining = set(get_all(core)["ids"])
    if remaining & set(delete_ids):
        raise RuntimeError("Vẫn còn ID domain trong collection core")
    if core.count() != expected_core_count:
        raise RuntimeError(f"Core count sau tách sai: {core.count()} != {expected_core_count}")

    print(
        json.dumps(
            {
                "status": "success",
                args.core: core.count(),
                args.accounting: accounting.count(),
                args.product: product.count(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
