import re

_PII_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)"),
    re.compile(r"(?<!\d)\d{12}(?!\d)"),
)


def redact_pii(text: str | None) -> str:
    redacted = text or ""
    for pattern in _PII_PATTERNS:
        redacted = pattern.sub(lambda match: "*" * len(match.group(0)), redacted)
    return redacted


def sanitize_citations_for_client(citations: list[dict] | None) -> list[dict] | None:
    if citations is None:
        return None
    sanitized = []
    for citation in citations:
        safe_item = dict(citation)
        for field in ("title", "source_file", "category", "section", "excerpt"):
            if field in safe_item:
                safe_item[field] = redact_pii(safe_item.get(field))
        sanitized.append(safe_item)
    return sanitized
