"""Bộ kiểm thử nghiệm thu toàn diện cho Phase P1 Vertical Slice.

Kiểm tra:
1. Structured Knowledge Extraction từ 2 target documents.
2. Exact Evidence & Quote Hash Lineage Traceability.
3. MODIFIES Relation Detection & PostgreSQL Storage.
4. Human-In-The-Loop (HITL) Lifecycle State Transitions (CANDIDATE -> REVIEWED -> APPROVED -> ACTIVE).
5. 5 Test Cases nghiệm thu suy luận chính sách tất định (Deterministic Policy Resolution):
   - Test 1: Date 2025-06-01, Location HCM -> 800,000 VND
   - Test 2: Date 2026-09-01, Location HCM -> 1,200,000 VND
   - Test 3: Date 2026-09-01, Location Hanoi -> 1,200,000 VND
   - Test 4: Date 2026-09-01, Location Da Nang -> 800,000 VND (ngoài phạm vi sửa đổi HN/HCM)
   - Test 5: Query "Mức công tác phí khách sạn hiện tại ở HCM là bao nhiêu?" -> 1,200,000 VND kèm đầy đủ bằng chứng MGT-DEC-04, Base Policy và MODIFIES relation.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from src.knowledge.database import create_knowledge_engine, get_session, init_db
from src.knowledge.extractor import extract_document_knowledge
from src.knowledge.models import Base, ReviewStatus
from src.knowledge.repository import KnowledgeRepository, compute_sha256, normalize_canonical_text
from src.knowledge.resolver import (
    DeterministicPolicyResolver,
    PolicyQueryRequest,
    verbalize_policy_resolution,
)
from src.knowledge.service import KnowledgeService


class TestP1VerticalSlice(unittest.TestCase):
    """Test suite cho Vertical Slice Phase P1."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_knowledge_engine("sqlite:///:memory:")
        init_db(cls.engine)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        with get_session(self.engine) as session:
            self.service = KnowledgeService(session)
            self.bootstrap_info = self.service.bootstrap_target_slice(
                tenant_id="nexatech",
                base_policy_path="data/processed/12_quy-che-cong-tac-phi.md",
                modifying_decision_path="data/processed/mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md",
                initial_review_status=ReviewStatus.APPROVED.value,
            )

    def test_01_structured_extraction_and_evidence_integrity(self):
        """Kiểm tra tính toàn vẹn của dữ liệu trích xuất có cấu trúc và bằng chứng."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            
            # 1. Kiểm tra Base Policy Item
            base_items = repo.get_knowledge_items_by_subject("nexatech", "hotel_allowance")
            self.assertGreaterEqual(len(base_items), 2)
            
            base_rule = next(i for i in base_items if i.item_type == "POLICY_RULE")
            self.assertEqual(base_rule.value_numeric, 800000.0)
            self.assertEqual(base_rule.currency, "VND")
            self.assertEqual(base_rule.effective_from_ymd, 20250101)
            self.assertIn("ALL", base_rule.scope)

            # 2. Kiểm tra Modifying Decision Item
            mod_dec = next(i for i in base_items if i.item_type == "DECISION" and "HO_CHI_MINH_CITY" in (i.scope or []))
            self.assertEqual(mod_dec.value_numeric, 1200000.0)
            self.assertEqual(mod_dec.effective_from_ymd, 20260801)
            self.assertIn("HO_CHI_MINH_CITY", mod_dec.scope)
            self.assertIn("HANOI", mod_dec.scope)

            # 3. Kiểm tra Bằng chứng (Evidence Record & SHA256 Quote Hash)
            lineage = repo.trace_knowledge_lineage("nexatech", mod_dec.knowledge_id)
            self.assertGreaterEqual(len(lineage["evidences"]), 1)
            evi = lineage["evidences"][0]
            
            self.assertIn("1.200.000 VNĐ/đêm", evi["exact_quote_span"])
            self.assertEqual(evi["quote_hash"], compute_sha256(normalize_canonical_text(evi["exact_quote_span"])))
            self.assertGreaterEqual(evi["start_char"], 0)
            self.assertGreater(evi["end_char"], evi["start_char"])

    def test_02_modifies_relation_edge(self):
        """Kiểm tra quan hệ MODIFIES được thiết lập chính xác trong PostgreSQL/RDBMS."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            
            base_items = repo.get_knowledge_items_by_subject("nexatech", "hotel_allowance")
            base_rule = next(i for i in base_items if i.item_type == "POLICY_RULE")
            
            incoming_rels = repo.get_incoming_relations("nexatech", base_rule.knowledge_id, relation_type="MODIFIES")
            self.assertGreaterEqual(len(incoming_rels), 1)
            
            rel = incoming_rels[0]
            self.assertEqual(rel.relation_type, "MODIFIES")
            self.assertEqual(rel.status, "ACTIVE")
            self.assertEqual(rel.effective_from_ymd, 20260801)
            self.assertEqual(rel.relation_payload.get("new_value"), 1200000.0)

    def test_03_test1_date_2025_06_01_location_hcm_expected_800k(self):
        """TEST 1: Date 2025-06-01 (trước khi có Quyết định MGT-DEC-04), Location HCM -> 800,000 VNĐ."""
        with get_session(self.engine) as session:
            service = KnowledgeService(session)
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20250601,
                location="HCM",
                role="STAFF",
            )
            res, text = service.resolve(req)

            self.assertTrue(res.resolved)
            self.assertEqual(res.value_numeric, 800000.0)
            self.assertFalse(res.is_modified)
            self.assertEqual(res.resolved_by_document, "12_quy-che-cong-tac-phi.md")
            self.assertIn("800,000", text)

    def test_04_test2_date_2026_09_01_location_hcm_expected_1_2m(self):
        """TEST 2: Date 2026-09-01 (sau ngày hiệu lực MGT-DEC-04), Location HCM -> 1,200,000 VNĐ."""
        with get_session(self.engine) as session:
            service = KnowledgeService(session)
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20260901,
                location="HCM",
                role="STAFF",
            )
            res, text = service.resolve(req)

            self.assertTrue(res.resolved)
            self.assertEqual(res.value_numeric, 1200000.0)
            self.assertTrue(res.is_modified)
            self.assertEqual(res.resolved_by_document, "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md")
            self.assertEqual(res.base_policy_document, "12_quy-che-cong-tac-phi.md")
            self.assertEqual(res.relation_applied, "MODIFIES")
            self.assertIn("1,200,000", text)

    def test_05_test3_date_2026_09_01_location_hanoi_expected_1_2m(self):
        """TEST 3: Date 2026-09-01, Location Hanoi -> 1,200,000 VNĐ."""
        with get_session(self.engine) as session:
            service = KnowledgeService(session)
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20260901,
                location="Hanoi",
                role="STAFF",
            )
            res, text = service.resolve(req)

            self.assertTrue(res.resolved)
            self.assertEqual(res.value_numeric, 1200000.0)
            self.assertTrue(res.is_modified)
            self.assertEqual(res.resolved_by_document, "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md")
            self.assertIn("1,200,000", text)

    def test_06_test4_date_2026_09_01_location_danang_expected_800k(self):
        """TEST 4: Date 2026-09-01, Location Da Nang -> 800,000 VNĐ (ngoài phạm vi HN/HCM của Quyết định)."""
        with get_session(self.engine) as session:
            service = KnowledgeService(session)
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20260901,
                location="Da Nang",
                role="STAFF",
            )
            res, text = service.resolve(req)

            self.assertTrue(res.resolved)
            # Da Nang không nằm trong HN/HCM nên không áp mức 1.2M mà áp dụng mức cơ sở 800,000 VNĐ
            self.assertEqual(res.value_numeric, 800000.0)
            self.assertFalse(res.is_modified)
            self.assertEqual(res.resolved_by_document, "12_quy-che-cong-tac-phi.md")

    def test_07_test5_query_grounded_answer_with_evidence(self):
        """TEST 5: Tra cứu mức công tác phí khách sạn hiện tại ở HCM kèm đầy đủ Evidence & MODIFIES relation."""
        with get_session(self.engine) as session:
            service = KnowledgeService(session)
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20260915,
                location="TP. Hồ Chí Minh",
                role="STAFF",
            )
            res, text = service.resolve(req)

            self.assertTrue(res.resolved)
            self.assertEqual(res.value_numeric, 1200000.0)
            
            # Kiểm tra Bằng chứng có đủ 2 nguồn (Base Policy và Modifying Decision)
            roles = [e.role_in_reasoning for e in res.evidences]
            self.assertIn("BASE_POLICY", roles)
            self.assertIn("MODIFYING_DECISION", roles)
            
            # Kiểm tra text verbalized chứa đủ các thành phần bắt buộc
            self.assertIn("1,200,000", text)
            self.assertIn("mgt_dec_04", text.lower())
            self.assertIn("12_quy-che-cong-tac-phi", text.lower())
            self.assertIn("MODIFIES", text)

    def test_08_hitl_lifecycle_state_machine(self):
        """TEST 6: Kiểm tra cổng kiểm soát HITL - CANDIDATE không được phép tham gia reasoning cho tới khi APPROVED."""
        with get_session(self.engine) as session:
            repo = KnowledgeRepository(session)
            service = KnowledgeService(session)

            base_items = repo.get_knowledge_items_by_subject("nexatech", "hotel_allowance")
            mod_dec = next(i for i in base_items if i.item_type == "DECISION" and "HO_CHI_MINH_CITY" in (i.scope or []))

            # 1. Đưa Modifying Decision về trạng thái CANDIDATE
            repo.update_knowledge_item_status("nexatech", mod_dec.knowledge_id, review_status=ReviewStatus.CANDIDATE.value)

            # Query vào thời điểm 2026-09-01
            req = PolicyQueryRequest(
                tenant_id="nexatech",
                subject="hotel_allowance",
                target_date_ymd=20260901,
                location="HCM",
            )
            res_candidate, _ = service.resolve(req)
            # Vì item đang là CANDIDATE, resolver BẮT BUỘC bỏ qua và fallback về Base Policy (800k)
            self.assertEqual(res_candidate.value_numeric, 800000.0)
            self.assertFalse(res_candidate.is_modified)

            # 2. Phê duyệt (APPROVED)
            repo.update_knowledge_item_status("nexatech", mod_dec.knowledge_id, review_status=ReviewStatus.APPROVED.value)
            res_approved, _ = service.resolve(req)
            # Sau khi APPROVED, resolver áp dụng mức sửa đổi (1.2M)
            self.assertEqual(res_approved.value_numeric, 1200000.0)
            self.assertTrue(res_approved.is_modified)


if __name__ == "__main__":
    unittest.main()
