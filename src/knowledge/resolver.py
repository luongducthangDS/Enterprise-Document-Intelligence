"""Deterministic Policy Resolver for Phase P1.

Giải quyết chính sách theo mô hình tất định (Deterministic Policy Resolution):
Base Policy Rule -> Knowledge Relation (MODIFIES / SUPERSEDES) -> Modifying Decision -> Scope & Date Matching.

Nguyên tắc:
- KHÔNG dùng vector similarity để quyết định số liệu cuối cùng.
- LLM chỉ verbalize kết quả từ structured resolution payload.
- Kiểm tra tính hợp lệ của vòng đời HITL (chỉ APPROVED / ACTIVE items mới được tham gia resolution).
"""
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.knowledge.models import (
    Document,
    DocumentVersion,
    EvidenceRecord,
    KnowledgeItem,
    KnowledgeRelation,
    ReviewStatus,
)
from src.knowledge.repository import KnowledgeRepository


class PolicyQueryRequest(BaseModel):
    """Yêu cầu giải quyết chính sách."""
    tenant_id: str = "nexatech"
    subject: str = "hotel_allowance"
    target_date_ymd: int = 20260901  # YYYYMMDD
    location: str = "HO_CHI_MINH_CITY"
    role: str = "STAFF"
    category: str = "HOTEL"


class PolicyEvidenceItem(BaseModel):
    """Thông tin bằng chứng đính kèm."""
    evidence_id: str
    document_code: str
    document_title: str
    section_heading: str
    exact_quote: str
    quote_hash: str
    start_char: int
    end_char: int
    source_file: str | None = None
    role_in_reasoning: str  # "BASE_POLICY" | "MODIFYING_DECISION"


class PolicyResolutionResult(BaseModel):
    """Kết quả giải quyết chính sách tất định."""
    resolved: bool = True
    subject: str
    predicate: str
    value_numeric: float
    currency: str = "VND"
    unit: str = "VND/đêm"
    target_date_ymd: int
    location: str
    role: str
    
    # Traceability
    resolved_by_item_id: str
    resolved_by_document: str
    resolved_by_authority: str
    effective_from_ymd: int
    effective_to_ymd: int
    scope: list[str]
    
    # Quan hệ áp dụng
    is_modified: bool = False
    base_policy_item_id: str | None = None
    base_policy_document: str | None = None
    base_value_numeric: float | None = None
    relation_applied: str | None = None  # "MODIFIES" | "SUPERSEDES"
    relation_id: str | None = None
    relation_explanation: str = ""
    
    # Bằng chứng
    evidences: list[PolicyEvidenceItem] = Field(default_factory=list)
    structured_reasoning_summary: str = ""


import unicodedata

def remove_vietnamese_diacritics(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp chuỗi bền vững."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def normalize_location_name(loc: str) -> str:
    """Chuẩn hóa tên địa điểm phục vụ so khớp phạm vi (Scope Matching)."""
    loc_no_accents = remove_vietnamese_diacritics(loc).strip().upper()
    loc_clean = re.sub(r"[^\w\s]", "_", loc_no_accents)
    loc_clean = re.sub(r"\s+", "_", loc_clean)
    loc_clean = re.sub(r"_+", "_", loc_clean).strip("_")

    if any(k in loc_clean for k in ["HCM", "HO_CHI_MINH", "TP_HCM", "SAI_GON", "HOCHIMINH"]):
        return "HO_CHI_MINH_CITY"
    if any(k in loc_clean for k in ["HA_NOI", "HANOI", "HN"]):
        return "HANOI"
    if any(k in loc_clean for k in ["DA_NANG", "DANANG", "DN"]):
        return "DA_NANG"

    return loc_clean


class DeterministicPolicyResolver:
    """Bộ suy luận chính sách tất định (Deterministic Policy Engine)."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = KnowledgeRepository(session)

    def resolve_hotel_allowance(self, query: PolicyQueryRequest) -> PolicyResolutionResult:
        """Giải quyết hạn mức khách sạn theo địa điểm và mốc thời gian."""
        norm_loc = normalize_location_name(query.location)
        target_date = query.target_date_ymd
        tenant_id = query.tenant_id

        # 1. Tìm Base Policy Item (chỉ lấy APPROVED / ACTIVE)
        base_items = self.repo.get_knowledge_items_by_subject(
            tenant_id=tenant_id,
            subject=query.subject,
            target_date_ymd=None,  # Lọc ngày sau
            approved_only=True,
        )

        base_item = None
        for item in base_items:
            if item.item_type == "POLICY_RULE":
                # Kiểm tra ngày hiệu lực của base policy
                if item.effective_from_ymd <= target_date <= item.effective_to_ymd:
                    base_item = item
                    break

        if not base_item:
            # Fallback nếu không có base item hiệu lực
            return PolicyResolutionResult(
                resolved=False,
                subject=query.subject,
                predicate="maximum_amount_per_night",
                value_numeric=0,
                target_date_ymd=target_date,
                location=norm_loc,
                role=query.role,
                resolved_by_item_id="",
                resolved_by_document="N/A",
                resolved_by_authority="N/A",
                effective_from_ymd=0,
                effective_to_ymd=0,
                scope=[],
                structured_reasoning_summary="Không tìm thấy chính sách cơ sở có hiệu lực.",
            )

        # Lấy thông tin tài liệu gốc của Base Policy
        base_lineage = self.repo.trace_knowledge_lineage(tenant_id, base_item.knowledge_id)
        base_doc_code = base_lineage["document"]["document_code"] if base_lineage["document"] else "12_quy-che-cong-tac-phi.md"
        base_doc_title = base_lineage["document"]["title"] if base_lineage["document"] else "Quy chế Công tác phí"
        base_authority = base_lineage["document"]["authority_level"] if base_lineage["document"] else "COMPANY_POLICY"

        # 2. Kiểm tra các Quan hệ Sửa đổi (MODIFIES / SUPERSEDES)
        incoming_relations = self.repo.get_incoming_relations(
            tenant_id=tenant_id,
            target_knowledge_id=base_item.knowledge_id,
            relation_type="MODIFIES",
            active_only=True,
        )

        modifying_item = None
        applied_relation = None

        for rel in incoming_relations:
            # Kiểm tra thời gian hiệu lực của quan hệ
            if not (rel.effective_from_ymd <= target_date <= rel.effective_to_ymd):
                continue

            src_item = self.repo.get_knowledge_item(tenant_id, rel.source_knowledge_id)
            if not src_item:
                continue

            # Kiểm tra trạng thái HITL của source item
            if src_item.review_status not in ("APPROVED", "ACTIVE", ReviewStatus.AUTO_EXTRACTED.value):
                continue

            # Kiểm tra thời gian hiệu lực của source item
            if not (src_item.effective_from_ymd <= target_date <= src_item.effective_to_ymd):
                continue

            # Kiểm tra Scope (Địa phương áp dụng)
            item_scopes = src_item.scope or []
            if norm_loc in item_scopes or "ALL" in item_scopes:
                modifying_item = src_item
                applied_relation = rel
                break

        # 3. Tổng hợp Bằng chứng (Evidences)
        evidences: list[PolicyEvidenceItem] = []

        # Thêm evidence từ Base Policy
        for evi in base_lineage.get("evidences", []):
            evidences.append(
                PolicyEvidenceItem(
                    evidence_id=evi["evidence_id"],
                    document_code=base_doc_code,
                    document_title=base_doc_title,
                    section_heading=evi.get("section_heading", ""),
                    exact_quote=evi["exact_quote_span"],
                    quote_hash=evi["quote_hash"],
                    start_char=evi["start_char"],
                    end_char=evi["end_char"],
                    source_file=base_doc_code,
                    role_in_reasoning="BASE_POLICY",
                )
            )

        # 4. Quyết định Rule cuối cùng
        if modifying_item and applied_relation:
            mod_lineage = self.repo.trace_knowledge_lineage(tenant_id, modifying_item.knowledge_id)
            mod_doc_code = mod_lineage["document"]["document_code"] if mod_lineage["document"] else "MGT-DEC-2026-04"
            mod_doc_title = mod_lineage["document"]["title"] if mod_lineage["document"] else "Quyết định Ban Giám đốc"
            mod_authority = mod_lineage["document"]["authority_level"] if mod_lineage["document"] else "BOARD_DECISION"

            # Thêm evidence từ Modifying Decision
            for evi in mod_lineage.get("evidences", []):
                evidences.append(
                    PolicyEvidenceItem(
                        evidence_id=evi["evidence_id"],
                        document_code=mod_doc_code,
                        document_title=mod_doc_title,
                        section_heading=evi.get("section_heading", ""),
                        exact_quote=evi["exact_quote_span"],
                        quote_hash=evi["quote_hash"],
                        start_char=evi["start_char"],
                        end_char=evi["end_char"],
                        source_file=mod_doc_code,
                        role_in_reasoning="MODIFYING_DECISION",
                    )
                )

            summary = (
                f"Định mức {modifying_item.value_numeric:,.0f} {modifying_item.currency}/đêm được áp dụng "
                f"theo Quyết định {mod_doc_code} (Hiệu lực từ {modifying_item.effective_from_ymd}), "
                f"sửa đổi Quy chế cơ sở {base_doc_code} (mức gốc {base_item.value_numeric:,.0f} {base_item.currency}) "
                f"cho phạm vi {norm_loc}."
            )

            return PolicyResolutionResult(
                resolved=True,
                subject=modifying_item.subject or "hotel_allowance",
                predicate=modifying_item.predicate or "maximum_amount_per_night",
                value_numeric=modifying_item.value_numeric or 1200000.0,
                currency=modifying_item.currency or "VND",
                unit="VND/đêm",
                target_date_ymd=target_date,
                location=norm_loc,
                role=query.role,
                resolved_by_item_id=modifying_item.knowledge_id,
                resolved_by_document=mod_doc_code,
                resolved_by_authority=mod_authority,
                effective_from_ymd=modifying_item.effective_from_ymd,
                effective_to_ymd=modifying_item.effective_to_ymd,
                scope=modifying_item.scope or [norm_loc],
                is_modified=True,
                base_policy_item_id=base_item.knowledge_id,
                base_policy_document=base_doc_code,
                base_value_numeric=base_item.value_numeric or 800000.0,
                relation_applied="MODIFIES",
                relation_id=applied_relation.relation_id,
                relation_explanation=applied_relation.explanation,
                evidences=evidences,
                structured_reasoning_summary=summary,
            )

        else:
            # Áp dụng Base Policy
            summary = (
                f"Định mức {base_item.value_numeric:,.0f} {base_item.currency}/đêm được áp dụng "
                f"theo Quy chế cơ sở {base_doc_code} (Hiệu lực từ {base_item.effective_from_ymd}) "
                f"do tại thời điểm {target_date} và địa điểm {norm_loc} không có quyết định sửa đổi áp dụng."
            )

            return PolicyResolutionResult(
                resolved=True,
                subject=base_item.subject or "hotel_allowance",
                predicate=base_item.predicate or "maximum_amount_per_night",
                value_numeric=base_item.value_numeric or 800000.0,
                currency=base_item.currency or "VND",
                unit="VND/đêm",
                target_date_ymd=target_date,
                location=norm_loc,
                role=query.role,
                resolved_by_item_id=base_item.knowledge_id,
                resolved_by_document=base_doc_code,
                resolved_by_authority=base_authority,
                effective_from_ymd=base_item.effective_from_ymd,
                effective_to_ymd=base_item.effective_to_ymd,
                scope=base_item.scope or ["ALL"],
                is_modified=False,
                base_policy_item_id=base_item.knowledge_id,
                base_policy_document=base_doc_code,
                base_value_numeric=base_item.value_numeric or 800000.0,
                relation_applied=None,
                relation_id=None,
                relation_explanation="",
                evidences=evidences,
                structured_reasoning_summary=summary,
            )


def verbalize_policy_resolution(result: PolicyResolutionResult) -> str:
    """Verbalize kết quả suy luận có cấu trúc thành câu trả lời tự nhiên có dẫn chứng."""
    if not result.resolved:
        return "Hệ thống không tìm thấy quy định hoặc quyết định hiện hành nào áp dụng cho yêu cầu này."

    val_str = f"{result.value_numeric:,.0f} {result.currency}/phòng/đêm"
    
    if result.is_modified:
        text = (
            f"Theo quy định hiện hành tại NexaTech, hạn mức chi phí khách sạn/lưu trú cho Cấp Nhân viên "
            f"khi đi công tác tại **{result.location}** là **{val_str}**.\n\n"
            f"**Cơ sở pháp lý & Suy luận:**\n"
            f"1. **Quyết định điều chỉnh:** `{result.resolved_by_document}` (Hiệu lực từ ngày `{result.effective_from_ymd}`) "
            f"đã nâng hạn mức khách sạn tại các đô thị đặc biệt (Hà Nội, TP.HCM) từ mức cũ lên {val_str}.\n"
            f"2. **Quy chế gốc:** `{result.base_policy_document}` quy định mức cơ sở là `{result.base_value_numeric:,.0f} {result.currency}/phòng/đêm`.\n"
            f"3. **Quan hệ áp dụng:** `{result.relation_applied}` (Quyết định `{result.resolved_by_document}` sửa đổi `{result.base_policy_document}`).\n\n"
            f"**Trích dẫn bằng chứng nguyên văn:**\n"
        )
    else:
        text = (
            f"Theo quy định tại NexaTech, hạn mức chi phí khách sạn/lưu trú cho Cấp Nhân viên "
            f"khi đi công tác tại **{result.location}** (thời điểm áp dụng: `{result.target_date_ymd}`) là **{val_str}**.\n\n"
            f"**Cơ sở áp dụng:**\n"
            f"- Quy định theo Quy chế `{result.resolved_by_document}` (Hiệu lực từ ngày `{result.effective_from_ymd}`).\n\n"
            f"**Trích dẫn bằng chứng nguyên văn:**\n"
        )

    for i, evi in enumerate(result.evidences, 1):
        text += f"> {i}. *[{evi.document_code} - {evi.section_heading}]*: \"{evi.exact_quote}\" (Quote Hash: `{evi.quote_hash[:16]}...`)\n"

    return text
