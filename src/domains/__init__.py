"""Domain-specific plugin registry cho multi-tenant RAG pipeline.

Kiến trúc mở rộng:
  Mỗi phòng ban (HR, Accounting, Legal, IT...) là một DomainPlugin độc lập.
  Core code trong src/agents/nodes/ chỉ tương tác thông qua Domain Registry,
  đảm bảo hoàn toàn cách ly dữ liệu, logic nghiệp vụ và prompt giữa các phòng ban.
"""
from __future__ import annotations

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
    """Tìm domain plugin phù hợp với query và category hiện tại (ưu tiên domain chuyên biệt trước fallback)."""
    # 1. Kiểm tra các domain chuyên biệt trước (vd: accounting, procurement...)
    for name, plugin in _REGISTRY.items():
        if name != "hr" and plugin.match(query, category):
            return plugin
    # 2. Fallback về domain mặc định (hr)
    if "hr" in _REGISTRY and _REGISTRY["hr"].match(query, category):
        return _REGISTRY["hr"]
    return None


def get_domain(domain_name: str) -> DomainPlugin | None:
    """Lấy domain plugin theo tên trực tiếp."""
    return _REGISTRY.get(domain_name)


def get_conversation_domain(query: str, category: str | None = None, history: list | None = None) -> DomainPlugin | None:
    """Tìm domain plugin phù hợp với query, category và history."""
    return get_matching_domain(query, category)


# Tự động đăng ký các built-in domain plugins
import src.domains.accounting  # noqa: F401, E402
import src.domains.hr  # noqa: F401, E402
