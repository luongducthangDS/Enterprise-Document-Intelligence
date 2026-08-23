"""Supabase + Chroma READ-ONLY audit → CSV/JSON inventory + reconciliation.

Không mutate. Chỉ SELECT (Postgres) và .get()/list_collections (Chroma).
Không log secret. user_id bị hash trước khi ghi.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
DATA = ROOT / "qa" / "audit_20260823" / "data"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def h(value: str) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:12] if value else ""


# ---------------------------------------------------------------- Supabase
async def supabase_audit() -> dict:
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    stats: dict = {}
    async with AsyncSessionLocal() as s:
        # schema inventory
        rows = (await s.execute(text(
            "select table_name, column_name, data_type from information_schema.columns "
            "where table_schema='public' order by table_name, ordinal_position"))).fetchall()
        with (DATA / "supabase_schema.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["table", "column", "type"])
            w.writerows(rows)
        tables = sorted({r[0] for r in rows})
        stats["tables"] = tables

        # documents inventory
        docs = (await s.execute(text(
            "select document_id, title, source_file, document_code, version, effective_date,"
            " tenant_id, access_scope, department, status, created_at, updated_at, requires_reindex,"
            " ingestion_state, chunk_count, chroma_indexed_at, owner_user_id, publication_status"
            " from documents order by tenant_id, source_file"))).mappings().all()
        cols = ["document_id", "title", "source_file", "document_code", "version",
                "effective_date", "tenant_id", "access_scope", "department", "status",
                "created_at", "updated_at", "requires_reindex", "ingestion_state",
                "chunk_count", "chroma_indexed_at", "owner_hash", "publication_status"]
        with (DATA / "supabase_inventory.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for d in docs:
                w.writerow([d.get("document_id"), d.get("title"), d.get("source_file"),
                            d.get("document_code"), d.get("version"), str(d.get("effective_date") or ""),
                            d.get("tenant_id"), d.get("access_scope"), d.get("department"),
                            d.get("status"), str(d.get("created_at") or ""), str(d.get("updated_at") or ""),
                            d.get("requires_reindex"), d.get("ingestion_state"), d.get("chunk_count"),
                            str(d.get("chroma_indexed_at") or ""), h(d.get("owner_user_id")),
                            d.get("publication_status")])
        dl = [dict(d) for d in docs]
        stats["documents_total"] = len(dl)
        stats["documents_default_title"] = sum(1 for d in dl if not d.get("title") or d["title"] == "Tài liệu không tên")
        stats["documents_missing_version"] = sum(1 for d in dl if not d.get("version"))
        stats["documents_missing_effective"] = sum(1 for d in dl if not d.get("effective_date"))
        stats["documents_by_status"] = {}
        stats["documents_by_tenant"] = {}
        stats["documents_by_scope"] = {}
        for d in dl:
            stats["documents_by_status"][d.get("status") or "None"] = stats["documents_by_status"].get(d.get("status") or "None", 0) + 1
            stats["documents_by_tenant"][d.get("tenant_id") or "None"] = stats["documents_by_tenant"].get(d.get("tenant_id") or "None", 0) + 1
            stats["documents_by_scope"][d.get("access_scope") or "None"] = stats["documents_by_scope"].get(d.get("access_scope") or "None", 0) + 1
        # duplicates
        sf = {}
        for d in dl:
            sf.setdefault((d.get("tenant_id"), d.get("source_file")), []).append(d.get("document_id"))
        stats["duplicate_source_file"] = {f"{k[0]}/{k[1]}": v for k, v in sf.items() if len(v) > 1}

        # users/roles (hashed)
        users = (await s.execute(text(
            "select u.id, lower(p.role) as role, p.department, p.employment_status, u.is_active"
            " from users u left join profiles p on p.id = u.id"))).fetchall()
        with (DATA / "user_role_inventory.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["user_id_hash", "role", "department", "employment_status", "is_active"])
            for u in users:
                w.writerow([h(u[0]), u[1], u[2], u[3], u[4]])
        stats["users_total"] = len(users)
        stats["role_distribution"] = {}
        for u in users:
            stats["role_distribution"][u[1] or "None"] = stats["role_distribution"].get(u[1] or "None", 0) + 1
        stats["department_user_count"] = sum(1 for u in users if u[1] == "department_user")

        # ingestion jobs
        jobs = (await s.execute(text(
            "select state, count(*) from ingestion_jobs group by 1"))).fetchall()
        stats["ingestion_jobs_by_state"] = {j[0]: j[1] for j in jobs}
        stale = (await s.execute(text(
            "select count(*) from ingestion_jobs where state not in"
            " ('COMPLETED','SUCCEEDED','FAILED','CANCELLED') and created_at < now() - interval '1 day'"))).scalar()
        stats["ingestion_jobs_stale_gt1d"] = int(stale or 0)

        # chat requests
        cr = (await s.execute(text(
            "select state, count(*), percentile_disc(0.5) within group (order by latency_ms),"
            " percentile_disc(0.95) within group (order by latency_ms), max(latency_ms)"
            " from chat_requests group by 1"))).fetchall()
        stats["chat_requests_by_state"] = [
            {"state": r[0], "count": r[1], "p50_ms": r[2], "p95_ms": r[3], "max_ms": r[4]} for r in cr]
        total_cr = sum(r[1] for r in cr)
        refused = sum(r[1] for r in cr if r[0] == "REFUSED")
        completed = sum(r[1] for r in cr if r[0] == "COMPLETED")
        stats["chat_requests_total"] = total_cr
        stats["chat_refusal_rate_pct"] = round(100 * refused / total_cr, 1) if total_cr else None
        stats["chat_completed"] = completed
        # citations stats
        cit = (await s.execute(text(
            "select count(*) filter (where jsonb_array_length(citations) > 0), count(*)"
            " from chat_requests where state='COMPLETED'"))).fetchall()
        stats["completed_with_citation"] = {"with": cit[0][0], "total": cit[0][1]}

        # audit logs
        al = (await s.execute(text("select action, count(*) from audit_logs group by 1"))).fetchall()
        stats["audit_logs_by_action"] = {a[0]: a[1] for a in al}
    return stats


# ---------------------------------------------------------------- Chroma
def chroma_audit() -> dict:
    from src.config import get_settings
    from src.ingestion.indexer import get_chroma_client

    settings = get_settings()
    client = get_chroma_client(settings)
    stats: dict = {"chroma_tenant": settings.chroma_cloud_tenant,
                   "chroma_database": settings.chroma_cloud_database,
                   "collections": []}
    meta_rows = []
    with (DATA / "chroma_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["collection", "count", "checked_at"])
        for col in client.list_collections():
            name = col.name
            count = col.count()
            w.writerow([name, count, datetime.now(timezone.utc).isoformat()])
            got = col.get(include=["metadatas"])
            metas = got.get("metadatas") or []
            ids = got.get("ids") or []
            fields = ["source_file", "title", "document_code", "version", "effective_date",
                      "page_start", "tenant", "tenant_id", "access_scope", "department",
                      "publication_status", "document_id", "owner_user_id"]
            fill = {fn: sum(1 for m in metas if m and m.get(fn) not in (None, "", "0001-01-01")) for fn in fields}
            stats["collections"].append({
                "name": name, "count": count,
                "field_completeness_pct": {k: round(100 * v / count, 1) if count else None for k, v in fill.items()},
                "duplicate_ids": count - len(set(ids)),
            })
            for cid, m in zip(ids, metas):
                meta_rows.append({"collection": name, "chunk_id": cid,
                                  **{fn: (m or {}).get(fn) for fn in fields}})
    with (DATA / "chroma_metadata_full.json").open("w", encoding="utf-8") as f:
        json.dump(meta_rows, f, ensure_ascii=False, default=str)
    return stats


# ------------------------------------------------- Reconciliation
def reconcile(sup_stats: dict, chroma_stats: dict) -> dict:
    import csv as _csv
    docs = {}
    with (DATA / "supabase_inventory.csv").open(encoding="utf-8") as f:
        for d in _csv.DictReader(f):
            docs[(d["tenant_id"] or "", d["source_file"] or "")] = d
    chroma = {}
    for r in json.loads((DATA / "chroma_metadata_full.json").read_text(encoding="utf-8")):
        chroma[(r.get("tenant") or r.get("tenant_id") or "", r.get("source_file") or "")] = r
    classes = {}
    rows = []
    all_keys = set(docs) | set(chroma)
    for k in sorted(all_keys):
        d, c = docs.get(k), chroma.get(k)
        if d and c:
            cls = "BOTH_MATCH"
            if (d.get("title") or "") != (c.get("title") or "") and d.get("title") not in (None, "", "Tài liệu không tên"):
                cls = "TITLE_MISMATCH"
            if (d.get("version") or "") != str(c.get("version") or ""):
                cls = "VERSION_MISMATCH" if cls == "BOTH_MATCH" else cls + "+VERSION"
        elif d:
            cls = "SUPABASE_ONLY"
        else:
            cls = "CHROMA_ONLY"
        classes[cls] = classes.get(cls, 0) + 1
        rows.append({"key": f"{k[0]}/{k[1]}", "class": cls,
                     "supabase_title": (d or {}).get("title"), "chroma_title": (c or {}).get("title"),
                     "supabase_status": (d or {}).get("status"),
                     "supabase_version": (d or {}).get("version"), "chroma_version": (c or {}).get("version")})
    with (DATA / "reconciliation.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return {"classification_counts": classes, "total_keys": len(all_keys)}


def main():
    import asyncio
    sup = asyncio.run(supabase_audit())
    chroma = chroma_audit()
    rec = reconcile(sup, chroma)
    out = {"supabase": sup, "chroma": chroma, "reconciliation": rec,
           "ts": datetime.now(timezone.utc).isoformat()}
    (DATA / "cloud_audit_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"supabase_docs": sup["documents_total"],
                      "default_title": sup["documents_default_title"],
                      "collections": [(c["name"], c["count"]) for c in chroma["collections"]],
                      "reconciliation": rec["classification_counts"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
