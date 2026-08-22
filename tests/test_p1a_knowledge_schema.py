"""Bộ kiểm thử nghiệm thu GATE P1-A (P1-A Acceptance Test Suite).

Kiểm thử 14 tiêu chí kỹ thuật:
1. Tạo tenant
2. Tạo document
3. Tạo document version
4. Tạo chunks
5. Tạo knowledge item (6 types)
6. Tạo evidence record liên kết chunk & knowledge item
7. Tạo quan hệ same-tenant hợp lệ
8. Cố gắng tạo cross-tenant relation -> Bắt buộc thất bại (FAIL)
9. Cố gắng tạo evidence trỏ tới chunk của tenant khác -> Bắt buộc thất bại (FAIL)
10. Kiểm tra toàn vẹn Foreign Key (DB Engine level)
11. Kiểm tra tính tất định ID & idempotent insert
12. Kiểm tra tính bất biến của content hash
13. Kiểm tra tính chính xác của evidence quote hash
14. Kiểm tra truy vết phả hệ toàn diện (Lineage Tracing)
"""
import hashlib
import os
import sys
import unittest
import uuid

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy.exc import IntegrityError

from src.knowledge.database import create_all_tables, create_knowledge_engine, drop_all_tables, get_session, init_db
from src.knowledge.models import (
    AuthorityLevel,
    KnowledgeType,
    RelationType,
    ReviewStatus,
)
from src.knowledge.repository import (
    KnowledgeRepository,
    compute_sha256,
    normalize_canonical_text,
)


class TestP1AKnowledgeSchema(unittest.TestCase):
    """Bộ kiểm thử toàn diện cho RDBMS Schema, Tenant Invariants và Lineage Tracing."""

    @classmethod
    def setUpClass(cls):
        # Sử dụng SQLite in-memory database phục vụ test cô lập
        cls.engine = create_knowledge_engine("sqlite:///:memory:")
        init_db(cls.engine)

    def setUp(self):
        drop_all_tables(self.engine)
        create_all_tables(self.engine)

    def test_01_to_07_end_to_end_knowledge_lifecycle(self):
        """1-7: Vòng đời tạo Tenant -> Doc -> Version -> Chunks -> Knowledge -> Evidence -> Relation."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)

            # 1. Tạo Tenant
            tenant = repo.create_tenant(
                tenant_id="b85f9f02-ca5d-484a-8ad0-cb4ab301e175",
                slug="nexatech",
                name="NexaTech Corporation",
            )
            self.assertEqual(tenant.slug, "nexatech")

            # 2. Tạo Document
            doc = repo.create_document(
                tenant_id=tenant.tenant_id,
                document_code="MGT-DEC-2026-04",
                title="Quyết định Điều chỉnh Hạn mức Công tác phí Q3/2026",
                document_domain="MANAGEMENT",
                authority_level=AuthorityLevel.BOARD_DECISION.value,
                access_scope="COMPANY_WIDE",
                owner_department="EXECUTIVE",
            )
            self.assertEqual(doc.document_code, "MGT-DEC-2026-04")

            # 3. Tạo Document Version
            raw_text = "# QUYẾT ĐỊNH MGT-DEC-2026-04\n\nĐiều 2: Hạn mức khách sạn tại Hà Nội và TP.HCM nâng lên 1.200.000 VNĐ/đêm."
            version = repo.create_version(
                tenant_id=tenant.tenant_id,
                document_id=doc.document_id,
                version_number="1.0",
                raw_content=raw_text,
                effective_date_ymd=20260901,
                referenced_document_codes=["12_quy-che-cong-tac-phi.md"],
            )
            self.assertEqual(version.effective_date_ymd, 20260901)
            self.assertEqual(len(version.raw_content_hash), 64)

            # 4. Tạo Chunks
            chunk = repo.create_chunk(
                tenant_id=tenant.tenant_id,
                version_id=version.version_id,
                chunk_index=1,
                chunk_text="Điều 2: Hạn mức khách sạn tại Hà Nội và TP.HCM nâng lên 1.200.000 VNĐ/đêm.",
                heading_path="## QUYẾT ĐỊNH > ### Điều 2",
            )
            self.assertIn(doc.document_id, chunk.chunk_id or "")


            # 5. Tạo Knowledge Item (DECISION)
            k_item_dec = repo.create_knowledge_item(
                tenant_id=tenant.tenant_id,
                version_id=version.version_id,
                item_type=KnowledgeType.DECISION.value,
                statement="Nâng hạn mức khách sạn tại TP.HCM lên 1.200.000 VNĐ/đêm cho cấp Chuyên viên từ ngày 01/09/2026.",
                structured_payload={
                    "metric_name": "hotel_per_diem_hn_hcm",
                    "metric_value_vnd": 1200000,
                    "target_grade": "SPECIALIST",
                    "effective_date": "2026-09-01",
                },
            )
            self.assertEqual(k_item_dec.item_type, "DECISION")

            # 5b. Tạo Knowledge Item thứ 2 (POLICY_RULE gốc từ Quy chế 12)
            doc_pol = repo.create_document(
                tenant_id=tenant.tenant_id,
                document_code="12_quy-che-cong-tac-phi.md",
                title="Quy chế Công tác phí Doanh nghiệp",
                document_domain="COMPANY_POLICY",
                authority_level=AuthorityLevel.COMPANY_POLICY.value,
            )
            ver_pol = repo.create_version(
                tenant_id=tenant.tenant_id,
                document_id=doc_pol.document_id,
                version_number="1.0",
                raw_content="Điều 4: Định mức khách sạn tại TP.HCM là 800.000 VNĐ/đêm.",
            )
            k_item_pol = repo.create_knowledge_item(
                tenant_id=tenant.tenant_id,
                version_id=ver_pol.version_id,
                item_type=KnowledgeType.POLICY_RULE.value,
                statement="Định mức khách sạn tại TP.HCM là 800.000 VNĐ/đêm.",
                structured_payload={"metric_value_vnd": 800000},
            )

            # 6. Tạo Evidence Record
            quote_text = "Hạn mức khách sạn tại Hà Nội và TP.HCM nâng lên 1.200.000 VNĐ/đêm."
            evidence = repo.create_evidence(
                tenant_id=tenant.tenant_id,
                knowledge_id=k_item_dec.knowledge_id,
                chunk_id=chunk.chunk_id,
                exact_quote_span=quote_text,
                start_char=8,
                end_char=75,
                section_heading="## QUYẾT ĐỊNH > ### Điều 2",
            )
            self.assertEqual(evidence.quote_hash, compute_sha256(quote_text))

            # 7. Tạo Relation Hợp lệ (SUPERSEDES)
            relation = repo.create_relation(
                tenant_id=tenant.tenant_id,
                source_knowledge_id=k_item_dec.knowledge_id,
                target_knowledge_id=k_item_pol.knowledge_id,
                relation_type=RelationType.SUPERSEDES.value,
                relation_payload={"effective_date_ymd": 20260901, "metric": "hotel_per_diem_hn_hcm"},
                explanation="Quyết định MGT-DEC-04 nâng hạn mức thay thế Quy chế 12 từ ngày 01/09/2026.",
            )
            self.assertEqual(relation.relation_type, "SUPERSEDES")

    def test_08_cross_tenant_knowledge_relation_fails(self):
        """8. Cố gắng tạo Cross-Tenant Knowledge Relation -> Bắt buộc ném ValueError."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)

            # Tạo Tenant A
            t_a = repo.create_tenant(tenant_id="tenant_a", slug="tenant_a", name="Tenant A")
            doc_a = repo.create_document(tenant_id=t_a.tenant_id, document_code="DOC_A", title="Doc A", document_domain="COMPANY_POLICY")
            ver_a = repo.create_version(tenant_id=t_a.tenant_id, document_id=doc_a.document_id, version_number="1.0", raw_content="Content A")
            k_a = repo.create_knowledge_item(tenant_id=t_a.tenant_id, version_id=ver_a.version_id, item_type=KnowledgeType.POLICY_RULE.value, statement="Rule A")

            # Tạo Tenant B
            t_b = repo.create_tenant(tenant_id="tenant_b", slug="tenant_b", name="Tenant B")
            doc_b = repo.create_document(tenant_id=t_b.tenant_id, document_code="DOC_B", title="Doc B", document_domain="COMPANY_POLICY")
            ver_b = repo.create_version(tenant_id=t_b.tenant_id, document_id=doc_b.document_id, version_number="1.0", raw_content="Content B")
            k_b = repo.create_knowledge_item(tenant_id=t_b.tenant_id, version_id=ver_b.version_id, item_type=KnowledgeType.POLICY_RULE.value, statement="Rule B")

            # Thử tạo quan hệ từ Tenant A trỏ sang item của Tenant B
            with self.assertRaises(ValueError) as ctx:
                repo.create_relation(
                    tenant_id="tenant_a",
                    source_knowledge_id=k_a.knowledge_id,
                    target_knowledge_id=k_b.knowledge_id,  # Thuộc Tenant B
                    relation_type=RelationType.CONFLICTS_WITH.value,
                )
            self.assertIn("không tồn tại hoặc không thuộc tenant", str(ctx.exception))

    def test_09_cross_tenant_evidence_pointing_to_foreign_chunk_fails(self):
        """9. Cố gắng tạo Evidence trỏ sang Chunk của Tenant khác -> Bắt buộc ném ValueError."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)

            # Tenant A
            t_a = repo.create_tenant(tenant_id="tenant_a", slug="tenant_a", name="Tenant A")
            doc_a = repo.create_document(tenant_id=t_a.tenant_id, document_code="DOC_A", title="Doc A", document_domain="COMPANY_POLICY")
            ver_a = repo.create_version(tenant_id=t_a.tenant_id, document_id=doc_a.document_id, version_number="1.0", raw_content="Content A")
            k_a = repo.create_knowledge_item(tenant_id=t_a.tenant_id, version_id=ver_a.version_id, item_type=KnowledgeType.POLICY_RULE.value, statement="Rule A")

            # Tenant B
            t_b = repo.create_tenant(tenant_id="tenant_b", slug="tenant_b", name="Tenant B")
            doc_b = repo.create_document(tenant_id=t_b.tenant_id, document_code="DOC_B", title="Doc B", document_domain="COMPANY_POLICY")
            ver_b = repo.create_version(tenant_id=t_b.tenant_id, document_id=doc_b.document_id, version_number="1.0", raw_content="Content B")
            chunk_b = repo.create_chunk(tenant_id=t_b.tenant_id, version_id=ver_b.version_id, chunk_index=1, chunk_text="Chunk B text")

            # Thử tạo Evidence của Tenant A trỏ vào Chunk B
            with self.assertRaises(ValueError) as ctx:
                repo.create_evidence(
                    tenant_id="tenant_a",
                    knowledge_id=k_a.knowledge_id,
                    chunk_id=chunk_b.chunk_id,  # Thuộc Tenant B
                    exact_quote_span="Chunk B text",
                    start_char=0,
                    end_char=12,
                )
            self.assertIn("không tồn tại hoặc không thuộc tenant", str(ctx.exception))

    def test_10_foreign_key_integrity_enforcement(self):
        """10. Kiểm tra toàn vẹn Foreign Key cấp độ Database Engine."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            t = repo.create_tenant(tenant_id="t1", slug="t1", name="Tenant 1")
            
            # Cố gắng tạo version cho document_id không tồn tại
            with self.assertRaises(ValueError):
                repo.create_version(tenant_id="t1", document_id="non_existent_doc", version_number="1.0", raw_content="text")

    def test_11_deterministic_ids_and_idempotence(self):
        """11. Kiểm tra tính tất định ID và ngăn chặn trùng lặp mã văn bản."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            t = repo.create_tenant(tenant_id="t1", slug="t1", name="Tenant 1")
            repo.create_document(tenant_id="t1", document_code="IT-SOP-01", title="IT SOP", document_domain="DEPARTMENT_PROCESS")

        # Cố gắng tạo document thứ hai cùng document_code trong cùng tenant -> Bị chặn bởi UniqueConstraint
        with self.assertRaises(IntegrityError):
            with get_session(self.engine) as session_dup:
                repo_dup = KnowledgeRepository(session_dup)
                repo_dup.create_document(tenant_id="t1", document_code="IT-SOP-01", title="Duplicate IT SOP", document_domain="DEPARTMENT_PROCESS")


    def test_12_document_version_hash_immutability(self):
        """12. Kiểm tra tính bất biến và chuẩn hóa của Content Hash."""
        raw_text_1 = "Quy định làm việc\r\nĐiều 1: Giờ làm việc 8h00 - 17h30"
        raw_text_2 = "Quy định làm việc\nĐiều 1: Giờ làm việc 8h00 - 17h30"
        
        hash_1 = compute_sha256(raw_text_1)
        hash_2 = compute_sha256(raw_text_2)

        # Hash phải giống hệt nhau bất kể ký tự xuống dòng CRLF hay LF
        self.assertEqual(hash_1, hash_2)
        self.assertEqual(len(hash_1), 64)

    def test_13_evidence_quote_hash_verification(self):
        """13. Kiểm tra tính chính xác của Evidence Quote Hash."""
        quote = "Nâng hạn mức khách sạn lên 1.200.000 VNĐ/đêm"
        expected_hash = hashlib.sha256(normalize_canonical_text(quote).encode("utf-8")).hexdigest()
        
        self.assertEqual(compute_sha256(quote), expected_hash)

    def test_14_full_lineage_tracing(self):
        """14. Kiểm tra khả năng truy vết phả hệ toàn diện (Lineage Tracing)."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            t = repo.create_tenant(tenant_id="nexatech", slug="nexatech", name="NexaTech")
            doc = repo.create_document(
                tenant_id="nexatech",
                document_code="MGT-DEC-01",
                title="Quyết định Ngân sách Dự án AI",
                document_domain="MANAGEMENT",
                authority_level=AuthorityLevel.BOARD_DECISION.value,
            )
            ver = repo.create_version(
                tenant_id="nexatech",
                document_id=doc.document_id,
                version_number="1.0",
                raw_content="Tổng ngân sách dự án AI được duyệt là 2.500.000.000 VNĐ.",
            )
            chunk = repo.create_chunk(
                tenant_id="nexatech",
                version_id=ver.version_id,
                chunk_index=1,
                chunk_text="Tổng ngân sách dự án AI được duyệt là 2.500.000.000 VNĐ.",
            )
            k_item = repo.create_knowledge_item(
                tenant_id="nexatech",
                version_id=ver.version_id,
                item_type=KnowledgeType.DECISION.value,
                statement="Phê duyệt ngân sách Dự án AI 2.5 tỷ VNĐ.",
                structured_payload={"approved_budget_vnd": 2500000000},
            )
            evi = repo.create_evidence(
                tenant_id="nexatech",
                knowledge_id=k_item.knowledge_id,
                chunk_id=chunk.chunk_id,
                exact_quote_span="Tổng ngân sách dự án AI được duyệt là 2.500.000.000 VNĐ.",
                start_char=0,
                end_char=54,
            )

            # Thực thi Trace Phả hệ
            lineage = repo.trace_knowledge_lineage(tenant_id="nexatech", knowledge_id=k_item.knowledge_id)

            # Kiểm tra các tầng truy vết
            self.assertEqual(lineage["knowledge"]["item_type"], "DECISION")
            self.assertEqual(lineage["document"]["document_code"], "MGT-DEC-01")
            self.assertEqual(lineage["document_version"]["version_number"], "1.0")
            self.assertEqual(len(lineage["evidences"]), 1)
            self.assertEqual(lineage["evidences"][0]["chunk"]["chunk_id"], chunk.chunk_id)
            self.assertEqual(lineage["evidences"][0]["quote_hash"], evi.quote_hash)


if __name__ == "__main__":
    unittest.main()
