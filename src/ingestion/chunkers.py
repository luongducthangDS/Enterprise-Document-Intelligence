import re
from dataclasses import dataclass
from typing import Optional

# Corpus rất không đồng nhất về cách đánh dấu ranh giới cấu trúc — có file dùng
# markdown heading (## N. Tên mục), có file (2 văn bản luật lớn nhất, bộ luật lao
# động và luật BHXH) hoàn toàn không có markdown heading, chỉ có dòng "Điều N."
# dạng text thường. Vì vậy boundary detection kiểm tra keyword bất kể có '#' hay
# không, chỉ dùng '#' như tín hiệu phụ cho các mục đánh số kiểu chính sách công ty.
HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.*)$")
CHAPTER_RE = re.compile(r"^CH[ƯU]ƠNG\s+[IVXLCDM0-9]")
SECTION_RE = re.compile(r"^MỤC\s+\d")
ARTICLE_RE = re.compile(r"^ĐIỀU\s+\d+[A-ZĐ]?\.")
POLICY_SECTION_RE = re.compile(r"^\d+\.\s")

# Một số quy chế công ty (vd VinFast, mẫu quy chế lương thưởng) đánh mục lớn
# bằng số La Mã đứng riêng ("I. TUYÊN NGÔN...", "II. TIÊU CHÍ...") mà không có
# markdown '#'. Không thể lỏng POLICY_SECTION_RE (bỏ điều kiện has_hash) để bắt
# kiểu này vì '\d+\. ' cũng khớp các khoản liệt kê thường ("1. Người lao động...")
# nằm NGAY TRONG thân 1 Điều — sẽ băm nát cấu trúc Chương/Điều của các văn bản
# luật đang tách đúng. Số La Mã đứng riêng đầu dòng thì an toàn hơn nhiều: đã
# grep toàn bộ data/processed/ và xác nhận pattern này CHỈ xuất hiện ở 2 file
# thật sự dùng nó làm đề mục lớn, không khớp nhầm bất kỳ đoạn thân bài nào khác
# trong 27 tài liệu còn lại.
ROMAN_NUMERAL_SECTION_RE = re.compile(r"^([IVXLCDM]{1,4})\.\s+\S")
_VALID_ROMAN_NUMERALS = {
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
}

_LEVEL = {"chapter": 0, "section": 1, "article": 2, "policy_section": 2, "heading": 3}


@dataclass
class TextChunk:
    text: str
    heading_path: str
    chapter: Optional[str]
    article: Optional[str]
    start: int
    end: int
    part_index: int = 0


@dataclass
class _Boundary:
    offset: int
    kind: str
    title: str


def classify_line(line: str) -> Optional[tuple[str, str]]:
    """Trả về (kind, title) nếu dòng là ranh giới cấu trúc, None nếu không."""
    stripped = line.strip()
    if not stripped:
        return None

    m = HEADING_LINE_RE.match(stripped)
    has_hash = m is not None
    content = m.group(2).strip() if m else stripped
    if not content:
        return None

    # Dòng bắt đầu bằng dấu ngoặc kép thường là trích dẫn nội dung sửa đổi trong
    # thân 1 Điều khác (vd luat51.md trích "Điều 7a. ..." trong Điều 1), không
    # phải ranh giới thật.
    if content[0] in "\"“":
        return None

    upper = content.upper()
    if CHAPTER_RE.match(upper):
        return ("chapter", content)
    if SECTION_RE.match(upper):
        return ("section", content)
    if ARTICLE_RE.match(upper):
        return ("article", content)
    m_roman = ROMAN_NUMERAL_SECTION_RE.match(content)
    if m_roman and m_roman.group(1) in _VALID_ROMAN_NUMERALS:
        return ("chapter", content)
    if has_hash and POLICY_SECTION_RE.match(content):
        return ("policy_section", content)
    if has_hash:
        return ("heading", content)
    return None


def _find_boundaries(text: str) -> list[_Boundary]:
    boundaries = []
    offset = 0
    for line in text.splitlines(keepends=True):
        cls = classify_line(line)
        if cls:
            boundaries.append(_Boundary(offset, cls[0], cls[1]))
        offset += len(line)
    return boundaries


def _segment_by_structure(text: str) -> list[TextChunk]:
    boundaries = _find_boundaries(text)
    if not boundaries:
        return []

    stack: list[tuple[int, str]] = []
    chapter: Optional[str] = None
    segments: list[TextChunk] = []

    for i, b in enumerate(boundaries):
        level = _LEVEL[b.kind]
        stack = [s for s in stack if s[0] < level]
        stack.append((level, b.title))
        heading_path = " > ".join(t for _, t in stack)
        if b.kind == "chapter":
            chapter = b.title
        article = b.title if b.kind in ("article", "policy_section") else None
        end = boundaries[i + 1].offset if i + 1 < len(boundaries) else len(text)
        segments.append(
            TextChunk(
                text=text[b.offset:end].strip(),
                heading_path=heading_path,
                chapter=chapter if b.kind != "chapter" else None,
                article=article,
                start=b.offset,
                end=end,
            )
        )
    return segments


def _merge_undersized(segments: list[TextChunk], min_chars: int) -> list[TextChunk]:
    """Gộp đoạn quá nhỏ (thường là dòng Chương/Mục không có nội dung riêng, chỉ có
    tiêu đề) vào đoạn liền kề — không gộp qua ranh giới Chương khác nhau."""
    if not segments:
        return segments

    def top_chapter(seg: TextChunk) -> str:
        return seg.heading_path.split(" > ")[0]

    # Đoạn đầu tiên của cả tài liệu thường chỉ là tiêu đề/letterhead (vd "# CHÍNH
    # PHỦ") đứng trước Chương/Điều đầu tiên — coi "top_chapter" của nó khác hẳn
    # đoạn kế tiếp nên không lọt qua điều kiện gộp thông thường bên dưới. Luôn gộp
    # đoạn mở đầu này vào đoạn kế nếu nó quá nhỏ, bất kể chapter có khớp hay không.
    if len(segments) >= 2 and len(segments[0].text) < min_chars:
        first, second = segments[0], segments[1]
        segments = [
            TextChunk(
                text=(first.text + "\n\n" + second.text).strip(),
                heading_path=second.heading_path,
                chapter=second.chapter,
                article=second.article,
                start=first.start,
                end=second.end,
            )
        ] + segments[2:]

    merged: list[TextChunk] = []
    pending: Optional[TextChunk] = None
    for seg in segments:
        if pending is not None:
            if top_chapter(pending) == top_chapter(seg):
                seg = TextChunk(
                    text=(pending.text + "\n\n" + seg.text).strip(),
                    heading_path=seg.heading_path,
                    chapter=seg.chapter,
                    article=seg.article,
                    start=pending.start,
                    end=seg.end,
                )
            else:
                merged.append(pending)
            pending = None
        if len(seg.text) < min_chars:
            pending = seg
        else:
            merged.append(seg)
    if pending is not None:
        if merged and top_chapter(merged[-1]) == top_chapter(pending):
            last = merged[-1]
            merged[-1] = TextChunk(
                text=(last.text + "\n\n" + pending.text).strip(),
                heading_path=last.heading_path,
                chapter=last.chapter,
                article=last.article,
                start=last.start,
                end=pending.end,
            )
        else:
            merged.append(pending)
    return merged


def _iter_paragraphs_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Tách đoạn văn theo dòng trống, giữ nguyên offset thật trong `text` gốc
    (không split-rồi-rejoin — tránh lệch offset do whitespace bị chuẩn hoá lại)."""
    gap_re = re.compile(r"\n[ \t]*\n")
    paragraphs: list[tuple[str, int, int]] = []
    cursor = 0
    for m in gap_re.finditer(text):
        if m.start() > cursor and text[cursor:m.start()].strip():
            paragraphs.append((text[cursor:m.start()], cursor, m.start()))
        cursor = m.end()
    if cursor < len(text) and text[cursor:].strip():
        paragraphs.append((text[cursor:], cursor, len(text)))
    return paragraphs


def _split_by_sentence_with_offsets(text: str, start: int, target: int) -> list[tuple[str, int, int]]:
    pieces: list[tuple[str, int, int]] = []
    cur_start = start
    cur_end = start
    for m in re.finditer(r".*?(?:[.!?;](?=\s)|$)", text, re.DOTALL):
        seg = m.group(0)
        if not seg:
            continue
        seg_start, seg_end = start + m.start(), start + m.end()
        if cur_end > cur_start and (seg_end - cur_start) > target:
            pieces.append((text[cur_start - start:cur_end - start].strip(), cur_start, cur_end))
            cur_start = seg_start
        cur_end = seg_end
    if cur_end > cur_start:
        pieces.append((text[cur_start - start:cur_end - start].strip(), cur_start, cur_end))
    return [p for p in pieces if p[0]] or [(text, start, start + len(text))]


def _split_by_paragraph_with_offsets(
    text: str, base_offset: int, target: int, max_chars: int
) -> list[tuple[str, int, int]]:
    paragraphs = _iter_paragraphs_with_offsets(text)
    if not paragraphs:
        return [(text, base_offset, base_offset + len(text))] if text.strip() else []

    pieces: list[tuple[str, int, int]] = []
    group_start: Optional[int] = None
    group_end: Optional[int] = None

    def flush() -> None:
        nonlocal group_start, group_end
        if group_start is not None:
            piece_text = text[group_start:group_end].strip()
            if piece_text:
                pieces.append((piece_text, base_offset + group_start, base_offset + group_end))
        group_start = group_end = None

    for p_text, p_start, p_end in paragraphs:
        if len(p_text) > max_chars:
            flush()
            pieces.extend(_split_by_sentence_with_offsets(p_text, base_offset + p_start, target))
            continue
        if group_start is None:
            group_start, group_end = p_start, p_end
        elif (p_end - group_start) > target:
            flush()
            group_start, group_end = p_start, p_end
        else:
            group_end = p_end
    flush()
    return pieces


def _force_split_oversized(segments: list[TextChunk], target: int, max_chars: int) -> list[TextChunk]:
    out: list[TextChunk] = []
    for seg in segments:
        if len(seg.text) <= max_chars:
            out.append(seg)
            continue
        pieces = _split_by_paragraph_with_offsets(seg.text, seg.start, target, max_chars)
        for idx, (piece_text, p_start, p_end) in enumerate(pieces):
            out.append(
                TextChunk(
                    text=piece_text,
                    heading_path=seg.heading_path,
                    chapter=seg.chapter,
                    article=seg.article,
                    start=p_start,
                    end=p_end,
                    part_index=idx,
                )
            )
    return out


_WHITESPACE_RE = re.compile(r"\s")


def _word_boundary_tail(text: str, approx_chars: int) -> str:
    """Lấy khoảng approx_chars ký tự cuối của `text`, dịch điểm bắt đầu tới
    khoảng trắng gần nhất để không cắt vỡ giữa 1 từ tiếng Việt (cắt cứng theo số
    ký tự có thể rơi giữa 1 ký tự có dấu, tạo ra overlap kiểu "ời Việt" thay vì
    "người Việt"). Nếu không tìm được ranh giới hợp lý (vd 1 "từ" dài bất
    thường), bỏ overlap còn hơn cắt vỡ từ."""
    if approx_chars <= 0 or len(text) <= approx_chars:
        return ""
    cut = len(text) - approx_chars
    m = _WHITESPACE_RE.search(text, cut)
    if not m:
        return ""
    return text[m.end():]


def _fallback_chunk(text: str, target: int, max_chars: int, min_chars: int = 200, overlap_ratio: float = 0.12) -> list[TextChunk]:
    """Dùng cho tài liệu không phát hiện được cấu trúc (vd Base.vn mẫu sơ đồ,
    talentnet) — chunk theo đoạn văn kích thước cố định (offset thật trong văn
    bản gốc, để vẫn tra được page_start/page_end), có overlap để không cắt đứt
    ngữ cảnh giữa 2 chunk liền kề."""
    pieces = _split_by_paragraph_with_offsets(text, 0, target, max_chars)

    # Đoạn đầu tiên (thường chỉ là dòng tiêu đề "# <tên file>") có thể quá nhỏ để
    # đứng thành 1 chunk riêng — gộp vào đoạn kế tiếp, cùng cách xử lý với
    # _merge_undersized() ở path có cấu trúc.
    if len(pieces) >= 2 and len(pieces[0][0]) < min_chars:
        first_text, first_start, _ = pieces[0]
        second_text, _, second_end = pieces[1]
        pieces = [(first_text + "\n\n" + second_text, first_start, second_end)] + pieces[2:]

    overlap_chars = int(target * overlap_ratio)
    chunks: list[TextChunk] = []
    prev_tail = ""
    for idx, (piece_text, start, end) in enumerate(pieces):
        merged_text = f"{prev_tail}\n\n{piece_text}".strip() if prev_tail else piece_text
        chunks.append(TextChunk(text=merged_text, heading_path="", chapter=None, article=None, start=start, end=end, part_index=idx))
        prev_tail = _word_boundary_tail(piece_text, overlap_chars)
    return chunks


def chunk_text(
    text: str,
    target_chars: int = 1200,
    max_chars: int = 2000,
    min_chars: int = 200,
) -> list[TextChunk]:
    """Chunking hybrid: ưu tiên tách theo cấu trúc văn bản (Chương/Mục/Điều hoặc
    heading đánh số kiểu chính sách công ty); nếu tài liệu không đủ cấu trúc (ít
    hơn 2 đoạn tách được), fallback sang chunking cố định theo đoạn văn có overlap."""
    segments = _segment_by_structure(text)
    if len(segments) < 2:
        return _fallback_chunk(text, target_chars, max_chars, min_chars)

    segments = _merge_undersized(segments, min_chars)
    segments = _force_split_oversized(segments, target_chars, max_chars)
    return [s for s in segments if s.text.strip()]
