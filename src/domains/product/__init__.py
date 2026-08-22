"""Product domain plugin for the dedicated Product collection."""
from __future__ import annotations

import re

from src.domains import register_domain


_PRODUCT_PATTERN = re.compile(
    r"\b(?:checkout redesign|recommendation system|notification center|dark mode"
    r"|subscription upgrade|search improvements|product roadmap|product backlog"
    r"|feature adoption|release plan|sprint planning|usability test"
    r"|product|sản phẩm|tính năng|feature|phát hành|ra mắt|roadmap"
    r"|backlog|experiment|thử nghiệm|metric|chỉ số sản phẩm|sprint)\b",
    re.IGNORECASE,
)

class ProductDomain:
    domain_name = "product"

    def match(self, query: str, category: str | None = None) -> bool:
        normalized_category = str(category or "").strip().lower()
        return normalized_category.startswith("product") or bool(_PRODUCT_PATTERN.search(query))

    def expand_query(self, query: str) -> str:
        return query

    def get_top_k_override(self, query: str, default_k: int) -> int:
        return default_k

    def should_force_hybrid(self, query: str) -> bool:
        return False

    def check_personal_data_query(self, query: str) -> tuple[bool, str]:
        return False, ""

    def get_generation_rules(self) -> str:
        return (
            "\nQUY TẮC PRODUCT:\n"
            "- Không gán owner, status, metric hoặc release date của feature này cho feature khác.\n"
            "- Chỉ khẳng định owner/status/metric khi nguồn Product được trích dẫn nói rõ.\n"
        )


register_domain(ProductDomain())




