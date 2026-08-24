"""Canonical department identifiers shared by ingestion and authorization."""

from __future__ import annotations

import re
import unicodedata

_ALIASES = {
    "HUMAN RESOURCES": "HR",
    "HUMAN RESOURCE": "HR",
    "NHAN SU": "HR",
    "KE TOAN": "ACCOUNTING",
    "ACCOUNTANCY": "ACCOUNTING",
    "PRODUCT MANAGEMENT": "PRODUCT",
    "SAN PHAM": "PRODUCT",
    # Các nhóm xử lý ticket HR đều thuộc phòng HR ở lớp phân quyền.
    "CB": "HR",
    "ER": "HR",
    "TA": "HR",
    "LD": "HR",
    "HRBP": "HR",
}


def canonical_department(value: str | None) -> str:
    """Return one stable uppercase value for Chroma metadata and ACL checks."""
    raw = str(value or "").strip()
    if not raw:
        return "GENERAL"
    ascii_value = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Z0-9]+", " ", ascii_value.upper()).strip()
    return _ALIASES.get(normalized, normalized.replace(" ", "_")) or "GENERAL"
