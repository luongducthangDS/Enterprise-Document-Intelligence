"""HR domain plugin — cấu hình tương thích ngược cho dữ liệu Nhân sự."""
from __future__ import annotations

from src.domains import DomainPlugin, register_domain


class HRDomain:
    domain_name = "hr"

    def match(self, query: str, category: str | None = None) -> bool:
        # Default fallback domain khi không match domain chuyên biệt nào khác
        return category == "hr" or category is None

    def expand_query(self, query: str) -> str:
        return query  # HR query expansion đã được xử lý ổn định trong retrieval.py

    def get_top_k_override(self, query: str, default_k: int) -> int:
        return default_k

    def should_force_hybrid(self, query: str) -> bool:
        return False  # Giữ nguyên cấu hình settings.use_hybrid toàn cục cho HR

    def check_personal_data_query(self, query: str) -> tuple[bool, str]:
        return False, ""  # HR personal data check do escalation guard / verifier xử lý

    def get_generation_rules(self) -> str:
        return ""


register_domain(HRDomain())
