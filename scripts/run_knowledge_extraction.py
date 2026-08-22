#!/usr/bin/env python3
"""Script trích xuất tri thức cấu trúc hàng loạt cho toàn bộ kho tài liệu doanh nghiệp (Phase P1/P2).

Sử dụng:
  python scripts/run_knowledge_extraction.py --tenant nexatech
  python scripts/run_knowledge_extraction.py --tenant nexatech --file 12_quy-che-cong-tac-phi.md
  python scripts/run_knowledge_extraction.py --tenant nexatech --dry-run
"""
import argparse
import csv
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.knowledge.database import create_knowledge_engine, get_database_url, get_session, init_db
from src.knowledge.service import KnowledgeService


def load_registry(registry_path: str = "data/metadata/document_registry.csv") -> dict[str, dict]:
    """Đọc registry CSV để lấy metadata quyền hạn và thẩm quyền của tài liệu."""
    if not os.path.exists(registry_path):
        return {}
    registry = {}
    with open(registry_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_file = row.get("source_file", "").strip()
            if source_file:
                registry[source_file] = row
    return registry


def find_processed_dirs() -> list[str]:
    """Tìm tất cả các thư mục processed tài liệu có trong dự án."""
    candidates = [
        "data/data_accounting/process",
        "data/processed",
        "data/raw",
    ]
    return [c for c in candidates if os.path.isdir(c)]


def main():
    parser = argparse.ArgumentParser(description="Extract structured knowledge from corpus")
    parser.add_argument("--tenant", default="nexatech", help="Tenant ID")
    parser.add_argument("--file", default=None, help="Chỉ trích xuất một file cụ thể")
    parser.add_argument("--processed-dir", default=None, help="Thư mục chứa file markdown processed")
    parser.add_argument("--registry", default=None, help="Đường dẫn file registry")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ quét danh sách file, không ghi DB")
    parser.add_argument("--no-llm", action="store_true", help="Chỉ dùng deterministic extraction, không gọi LLM")
    args = parser.parse_args()

    print(f"=== BẮT ĐẦU PIPELINE TRÍCH XUẤT TRI THỨC (Tenant: {args.tenant}) ===")
    
    registry = {}
    if args.registry:
        registry.update(load_registry(args.registry))
    else:
        for reg_path in glob.glob("data/metadata/*registry*.csv"):
            registry.update(load_registry(reg_path))

    print(f"• Đã nạp metadata registry: {len(registry)} tài liệu")

    # Tìm các file markdown
    if args.file:
        file_paths = [args.file] if os.path.exists(args.file) else glob.glob(f"data/**/{args.file}", recursive=True)
    elif args.processed_dir:
        file_paths = sorted(glob.glob(os.path.join(args.processed_dir, "*.md")))
    else:
        file_paths = []
        for pdir in find_processed_dirs():
            file_paths.extend(glob.glob(os.path.join(pdir, "*.md")))
        file_paths = sorted(list(set(file_paths)))

    if not file_paths:
        print("Không tìm thấy file markdown nào trong các thư mục dữ liệu.")
        return

    print(f"• Tìm thấy {len(file_paths)} tài liệu cần xử lý\n")

    if args.dry_run:
        print("[DRY-RUN] Danh sách tài liệu sẽ được trích xuất:")
        for fp in file_paths:
            fname = os.path.basename(fp)
            meta = registry.get(fname, {})
            print(f"  - {fname:40s} | Scope: {meta.get('access_scope', 'COMPANY_WIDE'):12s} | Dept: {meta.get('department', 'GENERAL')}")
        print("\nHoàn tất dry-run.")
        return

    db_url = get_database_url()
    engine = create_knowledge_engine(db_url)
    init_db(engine)

    total_items = 0
    start_time = time.time()

    with get_session(engine) as session:
        service = KnowledgeService(session)

        for idx, fp in enumerate(file_paths, 1):
            fname = os.path.basename(fp)
            meta = registry.get(fname, {})
            title = meta.get("title") or fname.replace(".md", "").replace("_", " ").title()
            access_scope = meta.get("access_scope", "COMPANY_WIDE")
            authority = meta.get("authority", "COMPANY_POLICY")
            department = meta.get("department", "GENERAL")

            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"[{idx}/{len(file_paths)}] LỖI đọc file {fname}: {e}")
                continue

            print(f"[{idx}/{len(file_paths)}] Đang xử lý: {fname} ({len(content)} ký tự)...", end=" ", flush=True)

            try:
                res = service.ingest_document_with_extraction(
                    tenant_id=args.tenant,
                    document_code=fname,
                    title=title,
                    raw_content=content,
                    authority_level=authority,
                    access_scope=access_scope,
                    owner_department=department,
                    use_llm=not args.no_llm,
                )
                items_cnt = res.get("items_extracted", 0)
                total_items += items_cnt
                print(f"-> OK ({items_cnt} items)")
            except Exception as e:
                print(f"-> LỖI: {e}")

        # Chạy Relation Detection
        print("\n--- BẮT ĐẦU PHÁT HIỆN QUAN HỆ TRI THỨC (RELATION GRAPH) ---")
        try:
            relations = service.build_relation_graph(tenant_id=args.tenant)
            print(f"• Đã phát hiện {len(relations)} quan hệ tri thức (SUPERSEDES / MODIFIES / CONFLICTS_WITH).")
            for r in relations[:5]:
                print(f"  + [{r['relation_type']}] {r['explanation']}")
        except Exception as e:
            print(f"• Lỗi khi phát hiện quan hệ: {e}")

    elapsed = time.time() - start_time
    print(f"\n=== HOÀN TẤT TRÍCH XUẤT ({elapsed:.2f}s) ===")
    print(f"• Tổng số tài liệu: {len(file_paths)}")
    print(f"• Tổng số tri thức cấu trúc: {total_items}")


if __name__ == "__main__":
    main()
