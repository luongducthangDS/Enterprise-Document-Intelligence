"""Knowledge Service & Pipeline Coordinator for Phase P1 Vertical Slice.

Tích hợp toàn diện pipeline:
Source Documents -> Ingestion/Chunks -> Structured Extraction -> Evidence -> Relations -> HITL Lifecycle -> Policy Resolver.
"""
from __future__ import annotations

import os
from typing import Any
from sqlalchemy.orm import Session

from src.knowledge.extractor import extract_document_knowledge
from src.knowledge.models import (
    AuthorityLevel,
    ReviewStatus,
)
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.resolver import (
    DeterministicPolicyResolver,
    PolicyQueryRequest,
    PolicyResolutionResult,
    verbalize_policy_resolution,
)


class KnowledgeService:
    """Service điều phối toàn bộ vòng đời tri thức và suy luận chính sách."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = KnowledgeRepository(session)
        self.resolver = DeterministicPolicyResolver(session)

    def bootstrap_target_slice(
        self,
        tenant_id: str = "nexatech",
        base_policy_path: str = "data/processed/12_quy-che-cong-tac-phi.md",
        modifying_decision_path: str = "data/processed/mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md",
        initial_review_status: str = ReviewStatus.APPROVED.value,
    ) -> dict[str, Any]:
        """Nạp 2 tài liệu mục tiêu, trích xuất cấu trúc, tạo evidence và quan hệ MODIFIES."""
        # 1. Đảm bảo Tenant tồn tại
        tenant = self.repo.get_tenant(tenant_id)
        if not tenant:
            tenant = self.repo.create_tenant(
                tenant_id=tenant_id,
                slug="nexatech",
                name="NexaTech Corporation",
            )

        # 2. Ingest Base Policy: 12_quy-che-cong-tac-phi.md
        with open(base_policy_path, "r", encoding="utf-8") as f:
            base_content = f.read()

        base_doc = self.repo.get_document_by_code(tenant_id, "12_quy-che-cong-tac-phi.md")
        if not base_doc:
            base_doc = self.repo.create_document(
                tenant_id=tenant_id,
                document_code="12_quy-che-cong-tac-phi.md",
                title="Quy chế Công tác phí và Phụ cấp Di chuyển",
                document_domain="COMPANY_POLICY",
                authority_level=AuthorityLevel.COMPANY_POLICY.value,
                access_scope="COMPANY_WIDE",
                owner_department="HR",
            )

        base_ver = self.repo.get_version_by_number(tenant_id, base_doc.document_id, "1.0")
        if not base_ver:
            base_ver = self.repo.create_version(
                tenant_id=tenant_id,
                document_id=base_doc.document_id,
                version_number="1.0",
                raw_content=base_content,
                effective_date_ymd=20250101,
            )

        # Tạo Chunk mẫu cho Base Policy
        base_chunk = self.repo.get_chunk(tenant_id, f"{tenant_id}:{base_doc.document_id}:{base_ver.version_id}:0005")
        if not base_chunk:
            base_chunk = self.repo.create_chunk(
                tenant_id=tenant_id,
                version_id=base_ver.version_id,
                chunk_index=5,
                chunk_text="## 5. Chi phí khách sạn / lưu trú\n5.1. Tối đa theo hoá đơn tài chính hợp lệ:\n- Cấp Lãnh đạo: tối đa 2.000.000 VNĐ/phòng/đêm.\n- Cấp Quản lý: tối đa 1.200.000 VNĐ/phòng/đêm.\n- Cấp Nhân viên: tối đa 800.000 VNĐ/phòng/đêm (khuyến khích 2 nhân viên cùng giới ở chung 1 phòng).",
                heading_path="## 5. Chi phí khách sạn / lưu trú",
            )

        # 3. Trích xuất Structured Knowledge từ Base Policy
        extracted_base = extract_document_knowledge("12_quy-che-cong-tac-phi.md", base_content)
        base_k_items = []
        for ext in extracted_base:
            k_item = self.repo.create_knowledge_item(
                tenant_id=tenant_id,
                version_id=base_ver.version_id,
                item_type=ext.item_type,
                statement=ext.statement,
                structured_payload=ext.structured_payload,
                confidence_score=ext.confidence,
                subject=ext.subject,
                predicate=ext.predicate,
                object_value=ext.object_value,
                value_numeric=ext.value_numeric,
                currency=ext.currency,
                scope=ext.scope,
                effective_from_ymd=ext.effective_from_ymd,
                effective_to_ymd=ext.effective_to_ymd,
                review_status=initial_review_status,
            )
            self.repo.create_evidence(
                tenant_id=tenant_id,
                knowledge_id=k_item.knowledge_id,
                chunk_id=base_chunk.chunk_id,
                source_file="12_quy-che-cong-tac-phi.md",
                section_heading=ext.evidence.section_heading,
                exact_quote_span=ext.evidence.exact_quote,
                start_char=ext.evidence.start_char,
                end_char=ext.evidence.end_char,
            )
            base_k_items.append(k_item)

        # 4. Ingest Modifying Decision: mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md
        with open(modifying_decision_path, "r", encoding="utf-8") as f:
            mod_content = f.read()

        mod_doc = self.repo.get_document_by_code(tenant_id, "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md")
        if not mod_doc:
            mod_doc = self.repo.create_document(
                tenant_id=tenant_id,
                document_code="mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md",
                title="Quyết định Ban hành Hạn mức Phê duyệt Chi tiêu Tài chính và Định mức Công tác phí Q3/2026",
                document_domain="MANAGEMENT",
                authority_level=AuthorityLevel.BOARD_DECISION.value,
                access_scope="COMPANY_WIDE",
                owner_department="EXECUTIVE",
            )

        mod_ver = self.repo.get_version_by_number(tenant_id, mod_doc.document_id, "1.0")
        if not mod_ver:
            mod_ver = self.repo.create_version(
                tenant_id=tenant_id,
                document_id=mod_doc.document_id,
                version_number="1.0",
                raw_content=mod_content,
                effective_date_ymd=20260801,
                referenced_document_codes=["12_quy-che-cong-tac-phi.md"],
            )

        # Tạo Chunk mẫu cho Modifying Decision
        mod_chunk = self.repo.get_chunk(tenant_id, f"{tenant_id}:{mod_doc.document_id}:{mod_ver.version_id}:0002")
        if not mod_chunk:
            mod_chunk = self.repo.create_chunk(
                tenant_id=tenant_id,
                version_id=mod_ver.version_id,
                chunk_index=2,
                chunk_text="### Điều 2. Điều chỉnh Định mức Khách sạn Công tác (Sửa đổi Điều 4 Quy chế 12_quy-che-cong-tac-phi.md)\n- **Đô thị loại Đặc biệt (Hà Nội, TP. Hồ Chí Minh)**:\n  - Cấp Nhân viên / Chuyên viên: Nâng từ `800.000 VNĐ/đêm` lên **1.200.000 VNĐ/đêm** (do biến động giá cả thị trường khách sạn).\n  - Cấp Quản lý (Manager): Nâng lên **1.800.000 VNĐ/đêm**.",
                heading_path="## QUYẾT ĐỊNH > ### Điều 2",
            )

        # 5. Trích xuất Structured Knowledge từ Modifying Decision
        extracted_mod = extract_document_knowledge("mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md", mod_content)
        mod_k_items = []
        for ext in extracted_mod:
            k_item = self.repo.create_knowledge_item(
                tenant_id=tenant_id,
                version_id=mod_ver.version_id,
                item_type=ext.item_type,
                statement=ext.statement,
                structured_payload=ext.structured_payload,
                confidence_score=ext.confidence,
                subject=ext.subject,
                predicate=ext.predicate,
                object_value=ext.object_value,
                value_numeric=ext.value_numeric,
                currency=ext.currency,
                scope=ext.scope,
                effective_from_ymd=ext.effective_from_ymd,
                effective_to_ymd=ext.effective_to_ymd,
                review_status=initial_review_status,
            )
            self.repo.create_evidence(
                tenant_id=tenant_id,
                knowledge_id=k_item.knowledge_id,
                chunk_id=mod_chunk.chunk_id,
                source_file="mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md",
                section_heading=ext.evidence.section_heading,
                exact_quote_span=ext.evidence.exact_quote,
                start_char=ext.evidence.start_char,
                end_char=ext.evidence.end_char,
            )
            mod_k_items.append(k_item)

            # 6. Tạo Quan hệ MODIFIES nếu chỉ định sửa đổi base document
            if ext.modifies_document_code and base_k_items:
                # Liên kết tới base hotel allowance rule
                base_target = base_k_items[0]
                self.repo.create_relation(
                    tenant_id=tenant_id,
                    source_knowledge_id=k_item.knowledge_id,
                    target_knowledge_id=base_target.knowledge_id,
                    relation_type="MODIFIES",
                    relation_payload={
                        "modified_field": ext.predicate,
                        "old_value": base_target.value_numeric,
                        "new_value": ext.value_numeric,
                        "scope": ext.scope,
                        "effective_from_ymd": ext.effective_from_ymd,
                    },
                    explanation=ext.relation_explanation,
                    effective_from_ymd=ext.effective_from_ymd,
                )

        return {
            "tenant_id": tenant_id,
            "base_document_id": base_doc.document_id,
            "modifying_document_id": mod_doc.document_id,
            "base_items_count": len(base_k_items),
            "mod_items_count": len(mod_k_items),
            "base_item_ids": [b.knowledge_id for b in base_k_items],
            "mod_item_ids": [m.knowledge_id for m in mod_k_items],
        }

    def resolve(
        self,
        query: PolicyQueryRequest,
    ) -> tuple[PolicyResolutionResult, str]:
        """Thực thi suy luận chính sách tất định và sinh câu trả lời tự nhiên."""
        result = self.resolver.resolve_hotel_allowance(query)
        verbalized = verbalize_policy_resolution(result)
        return result, verbalized
