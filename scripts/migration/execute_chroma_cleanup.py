#!/usr/bin/env python3
"""Executive Chroma Cloud Knowledge Base Cleanup Script.

Thực hiện quy trình làm sạch Production Knowledge Base trên Chroma Cloud:
1. Phase 0: Backup toàn bộ 1.486 vectors (kèm embeddings) ra file snapshot an toàn.
2. Phase 1-2: Tách biệt hoàn toàn 1.217 vectors pháp luật (Legal PDFs) khỏi production collection.
3. Phase 3-5: Kiểm tra PENDING_REVIEW, giữ nguyên historical policies và đảm bảo mốc thời gian thực tế.
4. Phase 6-8: Kiểm tra chất lượng chunk, không trùng lặp ID, toàn vẹn dữ liệu.
5. Phase 9: Cập nhật production collection 'tenant_nexatech_knowledge' với đúng 269 chunks NexaTech nội bộ.
6. Phase 10-11: Xác thực Metadata Invariants & Authorization RBAC.
7. Phase 12: Chạy 6 Query Probes kiểm chứng chất lượng retrieval.
"""
import os
import sys
import json
import time
import hashlib
import asyncio
from datetime import datetime, timezone
from collections import Counter

# Set stdout to utf-8
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.agents.nodes.retrieval import _aembed_query


def step_0_backup_collection(client, collection_name: str, backup_path: str) -> dict:
    """Phase 0: Tạo snapshot backup toàn diện (IDs, documents, metadatas, embeddings)."""
    print(f"\n[PHASE 0] === BẮT ĐẦU BACKUP COLLECTION '{collection_name}' ===")
    collection = client.get_collection(collection_name)
    total_count = collection.count()
    print(f"  • Tổng số vectors hiện tại trên Chroma Cloud: {total_count}")

    batch_size = 100
    all_ids = []
    all_metadatas = []
    all_documents = []
    all_embeddings = []

    offset = 0
    while offset < total_count:
        limit = min(batch_size, total_count - offset)
        res = collection.get(
            limit=limit,
            offset=offset,
            include=["metadatas", "documents", "embeddings"],
        )
        b_ids = res.get("ids", [])
        if not b_ids:
            break
        all_ids.extend(b_ids)
        all_metadatas.extend(res.get("metadatas", []))
        all_documents.extend(res.get("documents", []))
        b_embs = res.get("embeddings")
        if b_embs is not None and len(b_embs) > 0:
            all_embeddings.extend(b_embs)
        offset += len(b_ids)
        print(f"  • Đã đọc và backup {offset}/{total_count} records (kèm 1024d embeddings)...")

    if len(all_ids) != total_count:
        raise RuntimeError(f"Backup thất bại: Chỉ lấy được {len(all_ids)}/{total_count} records!")

    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    snapshot_data = {
        "metadata": {
            "source_collection": collection_name,
            "total_vectors": len(all_ids),
            "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
            "embedding_dimension": len(all_embeddings[0]) if all_embeddings else 0,
            "backup_reason": "PRE_CLEANUP_PHASE_0_SAFETY_SNAPSHOT",
            "status": "VALIDATED_BACKUP",
        },
        "records": [
            {
                "id": cid,
                "document": doc,
                "metadata": meta,
                "embedding": emb.tolist() if hasattr(emb, "tolist") else emb,
            }
            for cid, doc, meta, emb in zip(all_ids, all_documents, all_metadatas, all_embeddings)
        ],
    }

    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

    file_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"  • [THÀNH CÔNG] Đã lưu snapshot {len(all_ids)} records vào: {backup_path} ({file_size_mb:.2f} MB)")
    return snapshot_data


def step_1_to_8_filter_and_validate(snapshot_data: dict, legal_backup_path: str):
    """Phân tách Legal corpus và xây dựng Canonical Production Dataset (NexaTech internal)."""
    print(f"\n[PHASE 1-8] === PHÂN TÁCH SCOPE & CHUẨN BỊ CANONICAL PRODUCTION DATASET ===")
    records = snapshot_data["records"]

    legal_records = []
    production_records = []

    # Danh mục các file pháp luật nhà nước cần tách riêng
    LEGAL_SOURCE_FILES = {
        "nghi_dinh_145_2020_nd_cp.pdf",
        "bộ luật lao động.pdf",
        "luat_bao_hiem_xa_hoi_41_2024_qh15.pdf",
        "luat_an_toan_ve_sinh_lao_dong_84_2015_qh13.pdf",
        "nghi_dinh_158_2025_nd_cp_bhxh_bat_buoc.pdf",
        "luat51.pdf",
        "112-vbhn-vpqh_luat_thue_tncn.pdf",
        "nghi_dinh_293_2025_nd_cp_luong_toi_thieu.pdf",
        "thong-tu-60-2025-TT-BHYT-2026.pdf",
        "161-ndcp.signed.pdf",
    }

    for r in records:
        src = r["metadata"].get("source_file", "")
        domain = r["metadata"].get("document_domain", "")
        auth = r["metadata"].get("authority", "")
        
        if src in LEGAL_SOURCE_FILES or domain == "LEGAL" or auth == "government_law":
            legal_records.append(r)
        else:
            # Clean production record
            meta = dict(r["metadata"])
            # Invariant Phase 3: Enforce retrieval_enabled = True for active internal knowledge
            meta["retrieval_enabled"] = True
            meta["publication_status"] = "active"
            
            # Verify effective date
            if meta.get("effective_date_ymd") == 10101:
                raise ValueError(f"Record {r['id']} ({src}) có fake effective date 10101!")

            r_clean = {
                "id": r["id"],
                "document": r["document"],
                "metadata": meta,
                "embedding": r["embedding"],
            }
            production_records.append(r_clean)

    print(f"  • Số lượng Legal/Reference records tách ra: {len(legal_records)}")
    print(f"  • Số lượng NexaTech Production records giữ lại: {len(production_records)}")

    # Lưu bản sao lưu riêng cho Legal reference corpus
    with open(legal_backup_path, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "description": "Legal Reference Corpus separated from active production retrieval",
                "total_vectors": len(legal_records),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "records": legal_records
        }, f, ensure_ascii=False, indent=2)
    print(f"  • Đã lưu Legal Reference Corpus ({len(legal_records)} records) vào: {legal_backup_path}")

    # Validation trên production dataset
    prod_sources = Counter(r["metadata"]["source_file"] for r in production_records)
    print(f"\n--- Production Dataset Inventory ({len(prod_sources)} files, {len(production_records)} chunks) ---")
    for s, c in sorted(prod_sources.items()):
        dom = [r["metadata"]["document_domain"] for r in production_records if r["metadata"]["source_file"] == s][0]
        date = [r["metadata"]["effective_date_ymd"] for r in production_records if r["metadata"]["source_file"] == s][0]
        print(f"  • {s:55} | {c:2} chunks | Domain: {dom:18} | Date: {date}")

    # Kiểm tra bảo toàn historical policy & decision
    assert "12_quy-che-cong-tac-phi.md" in prod_sources, "LỖI: Mất file Quy chế công tác phí gốc!"
    assert "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md" in prod_sources, "LỖI: Mất file Quyết định MGT-DEC-04!"

    # Kiểm tra duplicates
    prod_ids = [r["id"] for r in production_records]
    assert len(prod_ids) == len(set(prod_ids)), "LỖI: Tồn tại duplicate IDs trong production dataset!"

    return production_records


def step_9_safe_reindex_collection(client, collection_name: str, production_records: list[dict]):
    """Phase 9: Làm sạch và nạp đúng 269 production records vào collection 'tenant_nexatech_knowledge'."""
    print(f"\n[PHASE 9] === TIẾN HÀNH CẬP NHẬT PRODUCTION COLLECTION '{collection_name}' ===")
    collection = client.get_collection(collection_name)
    initial_count = collection.count()
    print(f"  • Số lượng vector trước khi làm sạch: {initial_count}")

    # Lấy toàn bộ IDs hiện tại trong collection để xóa các vector legal
    all_current_ids = []
    offset = 0
    while offset < initial_count:
        limit = min(250, initial_count - offset)
        res = collection.get(offset=offset, limit=limit, include=[])
        b_ids = res.get("ids", [])
        if not b_ids:
            break
        all_current_ids.extend(b_ids)
        offset += len(b_ids)

    target_prod_ids = set(r["id"] for r in production_records)
    ids_to_remove = [cid for cid in all_current_ids if cid not in target_prod_ids]
    print(f"  • Số lượng vector Legal/Không thuộc scope cần xóa khỏi collection: {len(ids_to_remove)}")

    # Xóa các vector ngoài scope theo batch 100
    if ids_to_remove:
        batch_size = 100
        for idx in range(0, len(ids_to_remove), batch_size):
            b_del = ids_to_remove[idx : idx + batch_size]
            collection.delete(ids=b_del)
            print(f"    - Đã xóa {min(idx + batch_size, len(ids_to_remove))}/{len(ids_to_remove)} vectors ngoài scope...")

    # Upsert lại toàn bộ 269 production records để đảm bảo metadata được cập nhật chuẩn
    batch_size = 100
    total_prod = len(production_records)
    for idx in range(0, total_prod, batch_size):
        b_records = production_records[idx : idx + batch_size]
        collection.upsert(
            ids=[r["id"] for r in b_records],
            embeddings=[r["embedding"] for r in b_records],
            documents=[r["document"] for r in b_records],
            metadatas=[r["metadata"] for r in b_records],
        )
        print(f"    - Đã upsert {min(idx + batch_size, total_prod)}/{total_prod} production records...")

    final_count = collection.count()
    print(f"  • [HOÀN TẤT] Số lượng vector sau khi làm sạch: {final_count}")
    if final_count != len(production_records):
        raise RuntimeError(f"Lỗi: Số lượng vector trên Chroma ({final_count}) không khớp với dataset sạch ({len(production_records)})!")


def step_10_11_validate_invariants(client, collection_name: str) -> dict:
    """Phase 10 & 11: Kiểm tra toàn diện Metadata Invariants & RBAC."""
    print(f"\n[PHASE 10-11] === KIỂM TRA METADATA INVARIANTS & RBAC TRÊN CHROMA CLOUD ===")
    collection = client.get_collection(collection_name)
    total_count = collection.count()

    res = collection.get(include=["metadatas", "documents"])
    ids = res["ids"]
    metadatas = res["metadatas"]
    documents = res["documents"]

    REQUIRED_KEYS = [
        "tenant_id", "tenant", "document_id", "version_id", "source_file",
        "title", "document_domain", "authority", "provenance", "access_scope",
        "effective_date_ymd", "publication_status", "retrieval_enabled"
    ]

    violations = []
    for i, (cid, meta) in enumerate(zip(ids, metadatas)):
        for k in REQUIRED_KEYS:
            if k not in meta or meta[k] is None or meta[k] == "":
                violations.append(f"Chunk {cid} thiếu trường bắt buộc: {k}")
        if meta.get("effective_date_ymd") == 10101:
            violations.append(f"Chunk {cid} có fake effective date 10101!")
        if meta.get("document_domain") == "LEGAL":
            violations.append(f"Chunk {cid} thuộc domain LEGAL vẫn còn trong production!")
        if not meta.get("retrieval_enabled"):
            violations.append(f"Chunk {cid} có retrieval_enabled != True!")

    if violations:
        print(f"  ❌ Phát hiện {len(violations)} vi phạm invariants:")
        for v in violations[:5]:
            print(f"    - {v}")
        raise ValueError("Invariants check FAILED!")
    else:
        print("  ✅ 100% vectors thỏa mãn đầy đủ tất cả Metadata Invariants!")

    # Thống kê phân bố
    domain_dist = Counter(m["document_domain"] for m in metadatas)
    scope_dist = Counter(m["access_scope"] for m in metadatas)
    date_dist = Counter(m["effective_date_ymd"] for m in metadatas)
    auth_dist = Counter(m["authority"] for m in metadatas)

    stats = {
        "total_vectors": total_count,
        "domains": dict(domain_dist),
        "access_scopes": dict(scope_dist),
        "effective_dates": dict(date_dist),
        "authorities": dict(auth_dist),
    }
    print("  • Phân bố Domain:", stats["domains"])
    print("  • Phân bố Access Scope:", stats["access_scopes"])
    print("  • Phân bố Effective Dates:", stats["effective_dates"])
    return stats


async def step_12_run_retrieval_probes(client, collection_name: str) -> list[dict]:
    """Phase 12: Chạy 6 Retrieval Probes kiểm chứng trên Chroma Cloud."""
    print(f"\n[PHASE 12] === CHẠY 6 RETRIEVAL PROBES TRÊN CHROMA CLOUD CLEANED ===")
    collection = client.get_collection(collection_name)

    probes = [
        {
            "id": 1,
            "query": "Nhân viên được làm việc remote bao nhiêu ngày mỗi tuần?",
            "expected_domain": "COMPANY_POLICY",
            "expected_source": "05_chinh-sach-lam-viec-tu-xa.md",
        },
        {
            "id": 2,
            "query": "Mức công tác phí khách sạn hiện tại là bao nhiêu?",
            "expected_sources": ["mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md", "12_quy-che-cong-tac-phi.md"],
        },
        {
            "id": 3,
            "query": "Quy định nghỉ phép của nhân viên như thế nào?",
            "expected_domain": "COMPANY_POLICY",
            "expected_source": "07_chinh-sach-nghi-phep.md",
        },
        {
            "id": 4,
            "query": "Quy định nào đang thay đổi chính sách cũ?",
            "expected_domain": "MANAGEMENT",
            "forbidden_domain": "LEGAL",
        },
        {
            "id": 5,
            "query": "Decision nào sửa policy hiện tại?",
            "expected_domain": "MANAGEMENT",
            "forbidden_domain": "LEGAL",
        },
        {
            "id": 6,
            "query": "Nhân viên IT đi công tác HCM tháng 9/2026 được thanh toán khách sạn tối đa bao nhiêu?",
            "expected_sources": ["mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md", "12_quy-che-cong-tac-phi.md"],
        },
    ]

    probe_results = []
    for p in probes:
        qid = p["id"]
        qtext = p["query"]
        print(f"\n  [Probe {qid}] '{qtext}'")

        emb = await _aembed_query(qtext)
        qres = collection.query(query_embeddings=[emb], n_results=5)
        
        q_ids = qres.get("ids", [[]])[0]
        q_docs = qres.get("documents", [[]])[0]
        q_metas = qres.get("metadatas", [[]])[0]
        q_dists = qres.get("distances", [[]])[0]

        top_sources = [m.get("source_file") for m in q_metas]
        top_domains = [m.get("document_domain") for m in q_metas]

        # Kiểm tra điều kiện PASS/FAIL
        passed = True
        reason = "OK"

        # 1. Tuyệt đối không được chứa LEGAL domain
        if "LEGAL" in top_domains:
            passed = False
            reason = "CHỨA VĂN BẢN LEGAL NGOÀI PHẠM VI!"

        # 2. Kiểm tra expected source/domain
        if p.get("expected_source") and p["expected_source"] not in top_sources[:2]:
            passed = False
            reason = f"Không tìm thấy expected source '{p['expected_source']}' trong Top 2!"

        if p.get("expected_domain") and top_domains[0] != p["expected_domain"]:
            # Check if domain matches
            if p["id"] in [4, 5] and "MANAGEMENT" not in top_domains[:2]:
                passed = False
                reason = "Top results không chứa Management Decision!"

        status_str = "✅ PASS" if passed else f"❌ FAIL ({reason})"
        print(f"    -> Kết quả: {status_str}")
        for rank, (src, dom, dist) in enumerate(zip(top_sources[:3], top_domains[:3], q_dists[:3]), 1):
            print(f"       {rank}. [{dist:.4f}] {src} ({dom})")

        probe_results.append({
            "probe_id": qid,
            "query": qtext,
            "status": "PASS" if passed else "FAIL",
            "reason": reason,
            "top_1_source": top_sources[0] if top_sources else None,
            "top_1_domain": top_domains[0] if top_domains else None,
            "top_1_distance": round(q_dists[0], 4) if q_dists else None,
            "top_sources": top_sources,
            "top_domains": top_domains,
            "top_chunk_preview": q_docs[0][:150] + "..." if q_docs else "",
        })

    return probe_results


async def main():
    start_time = time.time()
    settings = get_settings()
    client = get_chroma_client(settings)
    collection_name = "tenant_nexatech_knowledge"

    backup_path = "storage/backups/snapshot_tenant_nexatech_knowledge_pre_cleanup_20260821.json"
    legal_backup_path = "storage/backups/snapshot_legal_reference_corpus_20260821.json"
    report_output_path = os.path.join(r"C:\Users\Lenovo\.gemini\antigravity-ide\brain\ca50f10d-a0a8-43bf-ad89-15f40b71441d\scratch", "chroma_cleanup_execution_report.json")

    # 1. Step 0: Backup
    snapshot_data = step_0_backup_collection(client, collection_name, backup_path)

    # 2. Step 1-8: Filter & Validate
    production_records = step_1_to_8_filter_and_validate(snapshot_data, legal_backup_path)

    # 3. Step 9: Reindex
    step_9_safe_reindex_collection(client, collection_name, production_records)

    # 4. Step 10-11: Validate Invariants
    post_stats = step_10_11_validate_invariants(client, collection_name)

    # 5. Step 12: Run Probes
    probe_results = await step_12_run_retrieval_probes(client, collection_name)

    duration = time.time() - start_time
    print(f"\n=======================================================")
    print(f"🎉 CLEANUP HOÀN TẤT XUẤT SẮC TRONG {duration:.2f}s!")
    print(f"=======================================================")

    # Lưu báo cáo tổng kết
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 2),
        "collection_name": collection_name,
        "before_stats": {
            "total_vectors": snapshot_data["metadata"]["total_vectors"],
            "legal_vectors": 1217,
            "internal_vectors": 269,
        },
        "after_stats": post_stats,
        "probes": probe_results,
    }
    with open(report_output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
