"""Domain-specific plugin registry cho multi-tenant RAG pipeline.

Kiến trúc mở rộng:
  Mỗi phòng ban (HR, Accounting, Legal, IT...) là một DomainPlugin độc lập.
  Core code trong src/agents/nodes/ chỉ tương tác thông qua Domain Registry,
  đảm bảo hoàn toàn cách ly dữ liệu, logic nghiệp vụ và prompt giữa các phòng ban.
"""
from __future__ import annotations

import re

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainPlugin(Protocol):
    domain_name: str  # VD: "accounting", "hr", "legal"

    def match(self, query: str, category: str | None = None) -> bool:
        """Trả về True nếu domain này nên xử lý query / category này."""
        ...

    def expand_query(self, query: str) -> str:
        """Mở rộng query bằng từ điển domain-specific. Trả về query gốc nếu không match."""
        ...

    def get_top_k_override(self, query: str, default_k: int) -> int:
        """Trả về top_k phù hợp. Trả về default_k nếu không cần override."""
        ...

    def should_force_hybrid(self, query: str) -> bool:
        """True nếu domain này cần bật hybrid search bất kể global settings."""
        ...

    def check_personal_data_query(self, query: str) -> tuple[bool, str]:
        """(is_personal, reason_code) — kiểm tra câu hỏi dữ liệu sống cá nhân."""
        ...

    def get_generation_rules(self) -> str:
        """Trả về đoạn prompt bổ sung inject vào generation system prompt."""
        ...


_REGISTRY: dict[str, DomainPlugin] = {}


def register_domain(plugin: DomainPlugin) -> None:
    """Đăng ký domain plugin vào registry toàn cục."""
    _REGISTRY[plugin.domain_name] = plugin


def get_matching_domain(query: str, category: str | None = None) -> DomainPlugin | None:
    """Tìm domain plugin phù hợp với query và category hiện tại."""
    for plugin in _REGISTRY.values():
        if plugin.match(query, category):
            return plugin
    return None


def get_domain(domain_name: str) -> DomainPlugin | None:
    """Lấy domain plugin theo tên trực tiếp."""
    return _REGISTRY.get(domain_name)


_FOLLOWUP_PATTERN = re.compile(
    r"^\s*(?:vậy|còn|quay lại|trong tài liệu|bỏ qua|thế còn)"
    r"|(?:đúng không|câu đầu|trường hợp đó|làm theo câu này)",
    re.IGNORECASE,
)


def get_conversation_domain(
    query: str,
    category: str | None = None,
    history: list[dict] | None = None,
) -> DomainPlugin | None:
    """Resolve domain from the current turn, inheriting only ambiguous follow-ups."""
    current = get_matching_domain(query, category)
    if current and current.domain_name != "hr":
        return current
    if not _FOLLOWUP_PATTERN.search(query):
        return current

    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        previous = get_matching_domain(str(turn.get("content") or ""), None)
        if previous and previous.domain_name != "hr":
            return previous
    return current

# Tự động đăng ký các built-in domain plugins
import src.domains.accounting  # noqa: F401, E402
import src.domains.product  # noqa: F401, E402
import src.domains.hr  # noqa: F401, E402
