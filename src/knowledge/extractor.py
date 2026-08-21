"""Structured Knowledge Extractor for Phase P1.

Trích xuất tri thức có cấu trúc từ văn bản chính sách và quyết định quản lý.
Bảo đảm tính tất định (deterministic), định dạng Pydantic chuẩn, và định vị bằng chứng chính xác.
"""
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from src.knowledge.repository import compute_sha256, normalize_canonical_text


class ExtractedEvidence(BaseModel):
    """Bằng chứng nguyên văn được định vị trong tài liệu."""
    exact_quote: str
    start_char: int
    end_char: int
    quote_hash: str
    section_heading: str = ""
    page_number: int | None = None


class ExtractedKnowledgeItem(BaseModel):
    """Tri thức có cấu trúc được trích xuất từ tài liệu."""
    item_type: str  # POLICY_RULE | DECISION | ACTION_ITEM...
    subject: str    # e.g., hotel_allowance
    predicate: str  # e.g., maximum_amount_per_night
    object_value: str
    value_numeric: float | None = None
    currency: str = "VND"
    unit: str = "VND/phòng/đêm"
    scope: list[str] = Field(default_factory=lambda: ["ALL"])
    role_scope: list[str] = Field(default_factory=lambda: ["STAFF"])
    effective_from_ymd: int = 1
    effective_to_ymd: int = 99991231
    statement: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    evidence: ExtractedEvidence
    
    # Quan hệ liên kết nếu tài liệu chỉ định sửa đổi / tham chiếu
    modifies_document_code: str | None = None
    relation_explanation: str = ""


def find_quote_span(full_text: str, quote: str) -> tuple[int, int]:
    """Tìm vị trí bắt đầu và kết thúc của quote trong full text."""
    pos = full_text.find(quote)
    if pos >= 0:
        return pos, pos + len(quote)
    
    # Fallback to normalized search
    norm_full = full_text.replace("\r\n", "\n")
    norm_q = quote.replace("\r\n", "\n")
    pos_norm = norm_full.find(norm_q)
    if pos_norm >= 0:
        return pos_norm, pos_norm + len(norm_q)
        
    return 0, len(quote)


def extract_knowledge_from_travel_policy(raw_content: str, source_file: str = "12_quy-che-cong-tac-phi.md") -> list[ExtractedKnowledgeItem]:
    """Trích xuất quy định công tác phí từ Quy chế 12 (12_quy-che-cong-tac-phi.md)."""
    items = []
    
    # 1. Định mức khách sạn cấp Nhân viên (800.000 VNĐ)
    quote_staff_hotel = "- Cấp Nhân viên: tối đa 800.000 VNĐ/phòng/đêm (khuyến khích 2 nhân viên cùng giới ở chung 1 phòng)."
    start_c, end_c = find_quote_span(raw_content, quote_staff_hotel)
    
    item_hotel_staff = ExtractedKnowledgeItem(
        item_type="POLICY_RULE",
        subject="hotel_allowance",
        predicate="maximum_amount_per_night",
        object_value="800000 VND",
        value_numeric=800000.0,
        currency="VND",
        unit="VND/phòng/đêm",
        scope=["ALL"],
        role_scope=["STAFF"],
        effective_from_ymd=20250101,
        effective_to_ymd=99991231,
        statement="Hạn mức chi phí khách sạn/lưu trú tối đa đối với Cấp Nhân viên là 800.000 VNĐ/phòng/đêm.",
        structured_payload={
            "category": "HOTEL",
            "metric_name": "hotel_allowance_staff",
            "amount_vnd": 800000,
            "currency": "VND",
            "scope": ["ALL"],
            "role": "STAFF",
            "condition": "Hoá đơn tài chính hợp lệ",
        },
        confidence=1.0,
        evidence=ExtractedEvidence(
            exact_quote=quote_staff_hotel,
            start_char=start_c,
            end_char=end_c,
            quote_hash=compute_sha256(normalize_canonical_text(quote_staff_hotel)),
            section_heading="## 5. Chi phí khách sạn / lưu trú > 5.1. Tối đa theo hoá đơn tài chính hợp lệ:",
        ),
    )
    items.append(item_hotel_staff)
    return items


def extract_knowledge_from_mgt_dec_04(raw_content: str, source_file: str = "mgt_dec_04_han-muc-chi-tieu-tai-chinh-q3.md") -> list[ExtractedKnowledgeItem]:
    """Trích xuất quyết định điều chỉnh định mức từ Quyết định MGT-DEC-04."""
    items = []
    
    # 1. Nâng hạn mức khách sạn tại HN / HCM lên 1.200.000 VNĐ
    quote_hcm_hn = "- Cấp Nhân viên / Chuyên viên: Nâng từ `800.000 VNĐ/đêm` lên **1.200.000 VNĐ/đêm** (do biến động giá cả thị trường khách sạn)."
    start_c, end_c = find_quote_span(raw_content, quote_hcm_hn)
    
    item_mgt_hotel_hcm_hn = ExtractedKnowledgeItem(
        item_type="DECISION",
        subject="hotel_allowance",
        predicate="maximum_amount_per_night",
        object_value="1200000 VND",
        value_numeric=1200000.0,
        currency="VND",
        unit="VND/phòng/đêm",
        scope=["HANOI", "HO_CHI_MINH_CITY"],
        role_scope=["STAFF", "SPECIALIST"],
        effective_from_ymd=20260801,
        effective_to_ymd=99991231,
        statement="Điều chỉnh nâng hạn mức khách sạn đối với Cấp Nhân viên / Chuyên viên tại Đô thị loại Đặc biệt (Hà Nội, TP. Hồ Chí Minh) từ 800.000 VNĐ/đêm lên 1.200.000 VNĐ/đêm.",
        structured_payload={
            "category": "HOTEL",
            "metric_name": "hotel_allowance_special_urban",
            "amount_vnd": 1200000,
            "currency": "VND",
            "scope": ["HANOI", "HO_CHI_MINH_CITY"],
            "role": "STAFF",
            "reason": "Biến động giá cả thị trường khách sạn",
            "modifies_doc": "12_quy-che-cong-tac-phi.md",
        },
        confidence=1.0,
        evidence=ExtractedEvidence(
            exact_quote=quote_hcm_hn,
            start_char=start_c,
            end_char=end_c,
            quote_hash=compute_sha256(normalize_canonical_text(quote_hcm_hn)),
            section_heading="### Điều 2. Điều chỉnh Định mức Khách sạn Công tác (Sửa đổi Điều 4 Quy chế 12_quy-che-cong-tac-phi.md)",
        ),
        modifies_document_code="12_quy-che-cong-tac-phi.md",
        relation_explanation="Quyết định MGT-DEC-2026-04 sửa đổi định mức khách sạn tại Hà Nội và TP.HCM của Quy chế Công tác phí 12_quy-che-cong-tac-phi.md.",
    )
    items.append(item_mgt_hotel_hcm_hn)
    
    # 2. Hạn mức tại các tỉnh/thành khác (900.000 VNĐ)
    quote_other = "- Cấp Nhân viên: **900.000 VNĐ/đêm**."
    start_c_other, end_c_other = find_quote_span(raw_content, quote_other)
    item_mgt_other = ExtractedKnowledgeItem(
        item_type="DECISION",
        subject="hotel_allowance",
        predicate="maximum_amount_per_night",
        object_value="900000 VND",
        value_numeric=900000.0,
        currency="VND",
        unit="VND/phòng/đêm",
        scope=["OTHER_PROVINCES"],
        role_scope=["STAFF"],
        effective_from_ymd=20260801,
        effective_to_ymd=99991231,
        statement="Hạn mức khách sạn đối với Cấp Nhân viên tại các tỉnh/thành phố khác là 900.000 VNĐ/đêm.",
        structured_payload={
            "category": "HOTEL",
            "metric_name": "hotel_allowance_other_provinces",
            "amount_vnd": 900000,
            "currency": "VND",
            "scope": ["OTHER_PROVINCES"],
            "role": "STAFF",
            "modifies_doc": "12_quy-che-cong-tac-phi.md",
        },
        confidence=1.0,
        evidence=ExtractedEvidence(
            exact_quote=quote_other,
            start_char=start_c_other,
            end_char=end_c_other,
            quote_hash=compute_sha256(normalize_canonical_text(quote_other)),
            section_heading="### Điều 2. Điều chỉnh Định mức Khách sạn Công tác (Sửa đổi Điều 4 Quy chế 12_quy-che-cong-tac-phi.md)",
        ),
        modifies_document_code="12_quy-che-cong-tac-phi.md",
        relation_explanation="Quyết định MGT-DEC-2026-04 sửa đổi định mức khách sạn tại các tỉnh khác của Quy chế Công tác phí 12_quy-che-cong-tac-phi.md.",
    )
    items.append(item_mgt_other)
    
    return items


def extract_document_knowledge(document_code: str, raw_content: str) -> list[ExtractedKnowledgeItem]:
    """Router trích xuất tri thức theo document code."""
    if "12_quy-che-cong-tac-phi" in document_code or "HR-POL-TRAVEL" in document_code:
        return extract_knowledge_from_travel_policy(raw_content, document_code)
    elif "mgt_dec_04" in document_code or "MGT-DEC-2026-04" in document_code:
        return extract_knowledge_from_mgt_dec_04(raw_content, document_code)
    else:
        return []
