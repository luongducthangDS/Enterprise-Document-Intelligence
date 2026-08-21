import asyncio
import os
import sys
import unittest

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.security.models import UserContext, UserRole
from src.security.authorization import get_authorization_engine
from src.security.tenant_resolver import resolve_tenant_collection, validate_tenant_id
from src.agents.nodes.retrieval import _aembed_query, _provenance_filter
from scripts.migration.migrate_to_tenant_collection import run_tenant_migration


class TestMigrationParityAndSecurity(unittest.IsolatedAsyncioTestCase):
    """Bộ kiểm thử nghiệm thu Migration Parity, Idempotency và Security Boundaries."""

    def setUp(self):
        self.settings = get_settings()
        self.client = get_chroma_client(self.settings)
        self.legacy_coll = get_collection(self.client, "hr_documents")
        self.target_coll = get_collection(self.client, "tenant_nexatech_knowledge")

    def test_01_structural_parity(self):
        """1. Structural Parity: Số lượng vector và trường metadata mới."""
        legacy_count = self.legacy_coll.count()
        target_count = self.target_coll.count()

        self.assertEqual(legacy_count, 1486, "Legacy collection phải đủ 1486 vectors")
        self.assertEqual(target_count, 1486, "Target collection phải đủ 1486 vectors")

        sample = self.target_coll.get(limit=5, include=["metadatas"])
        for meta in sample["metadatas"]:
            self.assertIn("tenant_id", meta)
            self.assertIn("document_id", meta)
            self.assertIn("version_id", meta)
            self.assertIn("chunk_index", meta)
            self.assertEqual(meta.get("migration_source"), "hr_documents_legacy")
            self.assertEqual(meta.get("tenant"), "nexatech")

    def test_02_idempotency(self):
        """2. Idempotency Test: Chạy migration lần 2 không sinh duplicate vector."""
        res = run_tenant_migration()
        post_count = self.target_coll.count()
        self.assertEqual(post_count, 1486, "Sau khi chạy lại migration, số vector vẫn phải chính xác bằng 1486")

    async def test_03_retrieval_parity(self):
        """3. Retrieval Parity: So sánh kết quả truy vấn giữa legacy và target collection."""
        test_queries = [
            ("Chính sách làm việc từ xa quy định mô hình gì?", "05_chinh-sach-lam-viec-tu-xa.md"),
            ("Quy trình cấp phát tài khoản email cho nhân viên mới phòng IT", "it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md"),
            ("Định mức phòng khách sạn khi đi công tác Hà Nội", "12_quy-che-cong-tac-phi.md"),
            ("Ngân sách dự án AI chuyển đổi số được duyệt", "mgt_dec_01_ngan-sach-chuyen-doi-so-ai.md"),
            ("Chính sách làm thêm giờ OT và ngày nghỉ bù", "01_chinh-sach-lam-them-gio-OT.md"),
        ]

        auth_engine = get_authorization_engine()
        admin_user = UserContext(user_id="audit_admin", department="EXECUTIVE", role=UserRole.ADMIN, tenant_id="nexatech")
        where_clause = _provenance_filter(self.settings, user_context=admin_user)

        for query_text, expected_doc in test_queries:
            query_emb = await _aembed_query(query_text)
            
            res_legacy = self.legacy_coll.query(query_embeddings=[query_emb], where=where_clause, n_results=5)
            res_target = self.target_coll.query(query_embeddings=[query_emb], where=where_clause, n_results=5)

            legacy_docs = [m.get("source_file") for m in res_legacy["metadatas"][0]]
            target_docs = [m.get("source_file") for m in res_target["metadatas"][0]]

            # Top-1 doc phải trùng khớp 100%
            self.assertEqual(legacy_docs[0], target_docs[0], f"Top-1 document phải trùng khớp cho query: {query_text}")
            self.assertIn(expected_doc, target_docs[:3], f"Tài liệu kỳ vọng {expected_doc} phải nằm trong top 3")

    def test_04_tenant_routing_and_cross_tenant_denial(self):
        """4. Security: Phân giải tenant collection cô lập và từ chối truy cập chéo."""
        user_nexatech = UserContext(user_id="emp_1", department="IT", role=UserRole.EMPLOYEE, tenant_id="nexatech")
        user_external = UserContext(user_id="emp_2", department="IT", role=UserRole.EMPLOYEE, tenant_id="tenant_b")

        # NexaTech user phân giải vào đúng tenant_nexatech_knowledge
        self.assertEqual(resolve_tenant_collection(user_nexatech), "tenant_nexatech_knowledge")

        # External user phân giải vào tenant_tenant_b_knowledge (không thể chạm tới NexaTech)
        self.assertEqual(resolve_tenant_collection(user_external), "tenant_tenant_b_knowledge")

        # Chặn tenant_id chứa ký tự đặc biệt / injection
        with self.assertRaises(ValueError):
            validate_tenant_id("tenant_b; DROP COLLECTION;")

    def test_05_role_and_department_acl_on_target_collection(self):
        """5. Security: Phân quyền Department & Role trên Target Collection."""
        auth_engine = get_authorization_engine()

        # Employee bình thường
        emp = UserContext(user_id="emp_user", department="GENERAL", role=UserRole.EMPLOYEE, tenant_id="nexatech")
        where_emp = _provenance_filter(self.settings, user_context=emp)
        allowed_emp = auth_engine.get_authorized_source_files(emp)

        # HR SOP không nằm trong quyền của Employee
        self.assertNotIn("02_quy-trinh-tuyen-dung.md", allowed_emp)
        self.assertNotIn("it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md", allowed_emp)
        self.assertIn("07_chinh-sach-nghi-phep.md", allowed_emp)

        # IT User có quyền đọc IT SOP
        it_user = UserContext(user_id="it_user", department="IT", role=UserRole.DEPARTMENT_USER, tenant_id="nexatech")
        allowed_it = auth_engine.get_authorized_source_files(it_user)
        self.assertIn("it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md", allowed_it)
        self.assertNotIn("02_quy-trinh-tuyen-dung.md", allowed_it)

    def test_06_rollback_safety(self):
        """6. Rollback Safety: Collection legacy 'hr_documents' vẫn nguyên vẹn 1486 vectors."""
        self.assertEqual(self.legacy_coll.count(), 1486)
        sample_legacy = self.legacy_coll.get(limit=1)
        self.assertTrue(len(sample_legacy["ids"]) > 0)


if __name__ == "__main__":
    unittest.main()
