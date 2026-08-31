"""Universal Temporal Query Extraction & Expansion cho Multi-domain RAG.

Module độc lập hỗ trợ:
1. Trích xuất ngày, tháng, năm từ truy vấn người dùng (mọi định dạng tiếng Việt / chuẩn ISO).
2. Sinh các biểu diễn ngày chuẩn hoá (DD/MM/YYYY, DD/MM, DD tháng MM năm YYYY...) cho BM25 & Dense retrieval.
3. Mở rộng từ khoá tài liệu chung ("giấy tờ", "chứng từ", "hồ sơ", "tài liệu", "văn bản") khi kết hợp với mốc thời gian.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regex nhận diện các định dạng ngày tháng tiếng Việt & số
# 1. "ngày 19 tháng 08 năm 2026" / "ngày 19 tháng 8 năm 2026" / "19 tháng 8, 2026" / "19/8" / "19/08/2026"
_DATE_FULL_TEXT_RE = re.compile(
    r"(?:ngày\s+)?(?P<day>\d{1,2})\s*(?:tháng|/|-|\.)\s*(?P<month>\d{1,2})(?:\s*(?:năm|/|-|\.)\s*(?P<year>\d{4}))?",
    re.IGNORECASE,
)

# 2. "tháng 08 năm 2026" / "tháng 8/2026" / "tháng 08/2026"
_MONTH_YEAR_RE = re.compile(
    r"tháng\s+(?P<month>\d{1,2})(?:\s*(?:năm|/|-|\.)\s*(?P<year>\d{4}))",
    re.IGNORECASE,
)

# 3. Từ khoá văn bản / chứng từ chung cần mở rộng khi đi kèm thời gian
_GENERIC_DOC_TERMS_RE = re.compile(
    r"\b(?:giấy tờ|chứng từ|hồ sơ|tài liệu|văn bản|biên bản|đơn từ)\b",
    re.IGNORECASE,
)

DEFAULT_SYSTEM_YEAR = 2026


@dataclass
class ExtractedDate:
    day: int | None
    month: int
    year: int
    raw_match: str

    @property
    def ymd_int(self) -> int | None:
        if self.day is not None:
            return self.year * 10000 + self.month * 100 + self.day
        return None

    def format_variants(self) -> list[str]:
        """Sinh tất cả các biến thể định dạng ngày tháng xuất hiện trong văn bản."""
        variants: list[str] = []
        if self.day is not None:
            d2 = f"{self.day:02d}"
            d1 = f"{self.day}"
            m2 = f"{self.month:02d}"
            m1 = f"{self.month}"
            y4 = f"{self.year}"

            variants.extend([
                f"{d2}/{m2}/{y4}",
                f"{d1}/{m1}/{y4}",
                f"{d2}/{m2}",
                f"{d1}/{m1}",
                f"{d2}-{m2}-{y4}",
                f"{d1}-{m1}-{y4}",
                f"ngày {d2} tháng {m2} năm {y4}",
                f"ngày {d1} tháng {m1} năm {y4}",
                f"ngày {d2} tháng {m1} năm {y4}",
                f"ngày {d1} tháng {m2} năm {y4}",
                f"ngày {d2}/{m2}/{y4}",
                f"ngày {d1}/{m1}/{y4}",
                f"ngày {d2}/{m2}",
                f"ngày {d1}/{m1}",
            ])
        else:
            m2 = f"{self.month:02d}"
            m1 = f"{self.month}"
            y4 = f"{self.year}"
            variants.extend([
                f"tháng {m2} năm {y4}",
                f"tháng {m1} năm {y4}",
                f"{m2}/{y4}",
                f"{m1}/{y4}",
            ])
        return list(dict.fromkeys(variants))


def extract_dates_from_query(query: str, default_year: int = DEFAULT_SYSTEM_YEAR) -> list[ExtractedDate]:
    """Trích xuất tất cả các mốc thời gian xuất hiện trong câu hỏi."""
    results: list[ExtractedDate] = []
    seen = set()

    for match in _DATE_FULL_TEXT_RE.finditer(query):
        d_str = match.group("day")
        m_str = match.group("month")
        y_str = match.group("year")

        day = int(d_str) if d_str else None
        month = int(m_str) if m_str else None
        year = int(y_str) if y_str else default_year

        if month and (1 <= month <= 12) and (day is None or (1 <= day <= 31)):
            key = (day, month, year)
            if key not in seen:
                seen.add(key)
                results.append(ExtractedDate(day=day, month=month, year=year, raw_match=match.group(0)))

    return results


def expand_temporal_query(query: str, default_year: int = DEFAULT_SYSTEM_YEAR) -> str:
    """Mở rộng câu hỏi chứa mốc thời gian thành tập hợp các từ khoá ngày tháng và chứng từ.
    
    Đảm bảo cả BM25 và Dense Retriever đều tìm thấy chính xác:
    1. Các văn bản ghi "Ngày 19 tháng 08 năm 2026", "19/08/2026", "19/8".
    2. Các văn bản chứng từ cụ thể (Hóa đơn GTGT, Biên bản bàn giao/giao nhận TSCĐ, Giấy đề nghị thanh toán...).
    """
    dates = extract_dates_from_query(query, default_year=default_year)
    if not dates:
        return query

    extra_parts: list[str] = []
    for d in dates:
        variants = d.format_variants()
        extra_parts.extend(variants[:6])

    # Nếu câu hỏi dùng từ chung (giấy tờ, chứng từ, tài liệu, hồ sơ) + ngày
    if _GENERIC_DOC_TERMS_RE.search(query):
        extra_parts.extend([
            "hóa đơn GTGT",
            "hóa đơn điện tử",
            "biên bản giao nhận",
            "biên bản bàn giao TSCĐ",
            "giấy đề nghị thanh toán",
            "phiếu chi",
            "phiếu đề nghị mua hàng",
            "quyết định ban hành",
            "hợp đồng",
        ])

    unique_extras = list(dict.fromkeys(extra_parts))
    if not unique_extras:
        return query

    return f"{query}\nMốc thời gian & Chứng từ liên quan: {', '.join(unique_extras)}"
