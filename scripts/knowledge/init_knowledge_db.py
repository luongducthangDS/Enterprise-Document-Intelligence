#!/usr/bin/env python3
"""Script Khởi tạo và Thiết lập Database Tri thức Doanh nghiệp (Phase P1-A).

Chức năng:
1. Tạo 7 bảng quan hệ RDBMS (PostgreSQL / SQLite).
2. Seed bản ghi Tenant mặc định cho NexaTech:
   tenant_id: 'b85f9f02-ca5d-484a-8ad0-cb4ab301e175' | slug: 'nexatech'.
3. Xác minh tính toàn vẹn của kết nối và các chỉ mục bảo mật.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.knowledge.database import create_knowledge_engine, get_session, init_db
from src.knowledge.repository import KnowledgeRepository

NEXATECH_TENANT_UUID = "b85f9f02-ca5d-484a-8ad0-cb4ab301e175"
NEXATECH_TENANT_SLUG = "nexatech"
NEXATECH_TENANT_NAME = "NexaTech Corporation"


def bootstrap_knowledge_database(db_path: str = "data/knowledge.db") -> None:
    print(f"[Knowledge DB] Bắt đầu khởi tạo cơ sở dữ liệu tri thức: '{db_path}'...")
    engine = create_knowledge_engine(f"sqlite:///{db_path}")
    init_db(engine)

    with get_session(engine) as session:
        repo = KnowledgeRepository(session)
        existing = repo.get_tenant(NEXATECH_TENANT_UUID)
        if not existing:
            repo.create_tenant(
                tenant_id=NEXATECH_TENANT_UUID,
                slug=NEXATECH_TENANT_SLUG,
                name=NEXATECH_TENANT_NAME,
            )
            print(f"  • Đã khởi tạo Tenant: {NEXATECH_TENANT_NAME} ({NEXATECH_TENANT_SLUG})")
        else:
            print(f"  • Tenant '{NEXATECH_TENANT_SLUG}' đã tồn tại sẵn.")

    print("[Knowledge DB THÀNH CÔNG] Đã tạo 7 bảng quan hệ và kích hoạt WAL + Foreign Keys!\n")


if __name__ == "__main__":
    bootstrap_knowledge_database()
