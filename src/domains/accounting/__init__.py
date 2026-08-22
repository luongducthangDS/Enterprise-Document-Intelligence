"""Accounting domain plugin — tự động đăng ký vào registry."""
from __future__ import annotations

from src.domains import DomainPlugin, register_domain
from src.domains.accounting.generation_ext import (
    ACCOUNTING_GENERATION_RULES,
    adjust_confidence_for_ocr_docs,
)
from src.domains.accounting.retrieval_ext import (
    _expand_accounting_query,
    _get_accounting_top_k,
    _is_accounting_query,
)
from src.domains.accounting.router_ext import check_accounting_personal_data


class AccountingDomain:
    domain_name = "accounting"

    def match(self, query: str, category: str | None = None) -> bool:
        return _is_accounting_query(query, category)

    def expand_query(self, query: str) -> str:
        return _expand_accounting_query(query)

    def get_top_k_override(self, query: str, default_k: int) -> int:
        return _get_accounting_top_k(query, default_k)

    def should_force_hybrid(self, query: str) -> bool:
        return True  # G1: Kế toán luôn dùng hybrid search (BM25 + Dense)

    def check_personal_data_query(self, query: str) -> tuple[bool, str]:
        return check_accounting_personal_data(query)

    def get_generation_rules(self) -> str:
        return ACCOUNTING_GENERATION_RULES

    def adjust_confidence(
        self,
        confidence: float,
        chunks: list[dict],
        answerable: bool,
    ) -> float:
        """G11: Nâng confidence floor cho OCR docs để tránh escalate nhầm."""
        return adjust_confidence_for_ocr_docs(confidence, chunks, answerable)


# Đăng ký singleton instance vào Domain Registry
register_domain(AccountingDomain())
