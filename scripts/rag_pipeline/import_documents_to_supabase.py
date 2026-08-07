#!/usr/bin/env python3
"""Import data/metadata/document_registry.csv -> bảng public.documents trên
Supabase, dùng upsert theo source_file nên chạy lại bao nhiêu lần cũng an toàn.
Bỏ qua dòng config/eval_asset (không phải tài liệu HR thật) — giữ lại cả dòng
rejected để HR Admin dashboard nhìn thấy lịch sử tài liệu bị loại và lý do.

Chạy sau khi đã apply migration (supabase/migrations/0001_initial_schema.sql)
và .env đã có SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY.

Chạy: python scripts/rag_pipeline/import_documents_to_supabase.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.ingestion.metadata import load_registry
from src.services.supabase_client import get_supabase_client


def main() -> None:
    client = get_supabase_client()  # service role — bypass RLS, chỉ dùng cho job hệ thống
    rows = load_registry()
    # Bỏ config/eval_asset (vd ticket_routing_rules.json, qa_eval_set.json) — không
    # phải tài liệu HR thật, không thuộc phạm vi bảng documents (dashboard quản lý
    # tài liệu chính sách/luật). Vẫn giữ 'rejected' vì đó là lịch sử tài liệu thật.
    rows = [r for r in rows if r.source_type not in ("config", "eval_asset")]

    payload = [
        {
            "source_file": row.source_file,
            "category": row.category,
            "status": row.status,
            "source_type": row.source_type,
            "is_official_policy": row.is_official_policy,
            "caveat": row.caveat or None,
            "processed_path": row.processed_path or None,
            "chunks_path": row.chunks_path or None,
            "chroma_indexed_at": row.indexed_at or None,
        }
        for row in rows
    ]

    if not payload:
        print("Registry rỗng, không có gì để import.")
        return

    result = client.table("documents").upsert(payload, on_conflict="source_file").execute()
    print(f"Đã import {len(result.data)} document vào bảng public.documents.")


if __name__ == "__main__":
    main()
