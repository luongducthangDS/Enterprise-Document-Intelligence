import json
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

from src.agents.state import AgentState
from src.config import get_settings

TICKET_ROUTING_PATH = Path(__file__).resolve().parents[1] / "resources" / "ticket_routing_rules.json"

# Response cố định cho intent=pure_statutory — nguyên văn `response_template`
# của NexaTech Type-C contract v3.1.0 (frozen). KHÔNG gọi LLM: đây là ranh giới
# phạm vi sản phẩm, không phải nội dung cần sinh, và một response cố định
# không thể vô tình bịa/rò rỉ nội dung luật.
OUT_OF_SCOPE_RESPONSE = (
    "[OUT_OF_SCOPE] NexaBot chỉ hỗ trợ giải đáp các quy định và chính sách nội bộ "
    "do NexaTech ban hành. Câu hỏi này yêu cầu giải thích hoặc cung cấp thông tin "
    "pháp luật quốc gia/thủ tục cơ quan nhà nước, nên nằm ngoài phạm vi của trợ lý nội bộ. "
    "Vui lòng tham khảo nguồn pháp luật chính thức hoặc liên hệ Legal/HR khi cần hỗ trợ."
)


def department_access_denied_node(state: AgentState) -> dict:
    """Return a clear refusal without revealing protected department content."""
    return {
        "response": (
            "Nội dung bạn đang hỏi thuộc tài liệu nội bộ của một phòng ban khác "
            "và không nằm trong phạm vi truy cập của bạn."
        ),
        "escalate": False,
        "escalate_reason": "department_scope_denied",
        "citations": [],
    }

def out_of_scope_node(state: AgentState) -> dict:
    """Terminal node cho intent=pure_statutory (routing_precedence priority 2).

    Bypass hoàn toàn retrieval/generation — contract cấm retrieval_allowed,
    legal_corpus_retrieval_allowed, external_web_completion_allowed,
    citation_required cho Type-C. Không tạo ticket (escalate=False): đây là
    ranh giới phạm vi sản phẩm, không phải yêu cầu cần người phụ trách xử lý.
    """
    return {"response": OUT_OF_SCOPE_RESPONSE, "escalate": False, "citations": []}

_PERSONAL_MARKERS = (
    "cua toi",
    "toi con bao nhieu",
    "don cua toi",
    "hop dong cua toi",
    "ho so cua toi",
    "tai khoan cua toi",
)
_PERSONAL_DATA_TERMS = (
    "luong",
    "thuong",
    "ngay phep",
    # "phep" đứng riêng (không ghép "ngay phep"): bắt các câu đảo trật tự như
    # "số dư PHÉP của tôi hiện còn bao nhiêu NGÀY" — "ngày" và "phép" cách xa
    # nhau nên "ngay phep" không khớp submatch. An toàn vì luôn cần marker
    # ("cua toi"...) đi kèm — câu hỏi chính sách chung như "nhân viên được bao
    # nhiêu ngày phép năm?" không có marker nên vẫn không bị xếp nhầm.
    "phep",
    "don",
    "hop dong",
    "ho so",
    "cham cong",
    "bhxh",
    "bhyt",
    "bao hiem",
    "thue",
)

# Câu hỏi nhắc tên 1 công ty khác cụ thể (router đã gom chung vào
# out_of_scope_or_personal cùng với câu hỏi dữ liệu cá nhân — xem
# _ROUTER_SYSTEM) cần hành vi khác hẳn: TỪ CHỐI LỊCH SỰ, không tạo ticket, vì
# không có gì để HR thật sự xử lý (khác với câu hỏi cần tra dữ liệu cá nhân,
# nơi tạo ticket là hợp lý). Danh sách không dấu, khớp qua _strip_diacritics().
_COMPETITOR_COMPANY_KEYWORDS = {
    "viettel", "fpt", "vingroup", "vinfast", "samsung", "tiki", "momo",
    "grab", "shopee", "unilever", "vinamilk", "vinamik",
}


# Hậu tố thường đi kèm tên công ty, bỏ qua khi tìm động từ phía sau
# ("Shopee Việt Nam có trợ cấp...", "Samsung Electronics Vietnam trả lương...").
_COMPANY_QUALIFIERS = r"(?:viet nam|vietnam|vn|software|electronics|group|corp|corporation)"
# Tên công ty đứng SAU các từ này thì nó là chủ thể của câu hỏi chính sách:
# "chính sách CỦA Vingroup", "nhân viên FPT", "làm việc TẠI Viettel".
_SUBJECT_BEFORE = r"(?:cua|tai|o|ben|nhan vien|cong ty|lam cho|lam o|lam tai|ung tuyen vao)"
# Tên công ty đứng TRƯỚC các từ này thì nó đang được hỏi về chính sách:
# "Viettel CẤP bao nhiêu ngày phép", "MoMo CÓ phụ cấp".
_SUBJECT_AFTER = (
    r"(?:co|tra|cap|cho|ho tro|ap dung|quy dinh|thuong|phu cap|yeu cau|bat buoc|la|dang|hien)"
)


# Tên công ty đứng ngay sau các từ này là PHƯƠNG TIỆN/KÊNH được dùng, không
# phải chủ thể: "đi bằng Grab", "mua trên Shopee", "đặt vé qua MoMo".
_VENDOR_BEFORE = r"(?:qua|tren|bang|dung|su dung|di|dat|mua|thanh toan|goi|hoac|va)"


@lru_cache
def _company_subject_patterns(name: str) -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    escaped = re.escape(name)
    before = re.compile(rf"\b{_SUBJECT_BEFORE}\b(?:\s+\w+){{0,2}}\s+{escaped}\b")
    after = re.compile(rf"\b{escaped}\b(?:\s+{_COMPANY_QUALIFIERS}){{0,3}}\s+{_SUBJECT_AFTER}\b")
    vendor = re.compile(rf"\b{_VENDOR_BEFORE}\s+(?:\w+\s+){{0,1}}{escaped}\b")
    return before, after, vendor


def _mentions_competitor_company(query: str) -> bool:
    """Câu hỏi có đang hỏi CHÍNH SÁCH CỦA một công ty khác hay không.

    Không dùng substring matching trần: tên công ty xuất hiện trong câu không có
    nghĩa nó là chủ thể của câu hỏi. Ca thật đã đo được (qa_006, in_scope):

        "Đi công tác nếu dùng taxi hoặc Grab di chuyển trong ngày thì được
         thanh toán tối đa bao nhiêu?"

    Ở đây Grab là PHƯƠNG TIỆN đi lại, câu hỏi vẫn là hỏi định mức công tác phí
    của công ty mình — nhưng rule cũ chặn thẳng và đẩy sang escalate, tức từ
    chối một câu hoàn toàn trả lời được. So sánh với ca competitor thật
    (qa_091-qa_100), khác biệt luôn nằm ở quan hệ ngữ pháp chứ không ở việc tên
    có mặt hay không:

        "Grab Việt Nam CÓ trả thưởng KPI..."   -> tên là chủ thể  -> chặn
        "dùng taxi hoặc Grab di chuyển"        -> tên là phương tiện -> không chặn

    Nên chỉ chặn khi tên công ty đứng ở vị trí chủ thể/sở hữu của câu hỏi.

    Ngữ cảnh phương tiện được xét TRƯỚC vị trí chủ thể vì nó thắng về ngữ nghĩa:
    trong "mua hàng trên Shopee CÓ được hoàn thuế không", chữ "có" đứng ngay sau
    tên nhưng chủ thể của câu vẫn là chính sách công ty mình.
    """
    settings = get_settings()
    normalized_query = _strip_diacritics(query).lower()
    competitors = _COMPETITOR_COMPANY_KEYWORDS - set(settings.internal_company_names)
    for name in competitors:
        if name not in normalized_query:
            continue
        before, after, vendor = _company_subject_patterns(name)
        if before.search(normalized_query):
            return True
        if vendor.search(normalized_query):
            continue
        if after.search(normalized_query):
            return True
    return False

_DIACRITIC_MAP = str.maketrans({"đ": "d", "Đ": "D"})


def _strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để khớp với trigger_keywords trong ticket_routing_rules.json
    (vốn lưu không dấu, vd "luong", "thue tncn")."""
    text = text.translate(_DIACRITIC_MAP)
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


@lru_cache
def _load_routing_rules() -> dict:
    with TICKET_ROUTING_PATH.open(encoding="utf-8") as file:
        config = json.load(file)

    rules = config.get("routing_rules") if isinstance(config, dict) else None
    if not isinstance(rules, list) or not rules:
        raise ValueError("Ticket routing config must contain a non-empty routing_rules list")

    required_fields = {"category", "target_department", "ticket_priority", "routing_priority", "trigger_keywords"}
    for rule in rules:
        if not isinstance(rule, dict) or not required_fields.issubset(rule):
            raise ValueError("Each ticket routing rule must contain all required fields")
        if rule["ticket_priority"] not in {"Low", "Medium", "High"}:
            raise ValueError("ticket_priority must be Low, Medium, or High")
        if not isinstance(rule["routing_priority"], int) or not isinstance(rule["trigger_keywords"], list):
            raise ValueError("routing_priority must be an integer and trigger_keywords must be a list")

    if not any(rule["category"] == "unmatched" for rule in rules):
        raise ValueError("Ticket routing config must contain an unmatched fallback rule")
    return config


def _match_routing_rule(query: str) -> dict:
    normalized_query = _strip_diacritics(query).lower()
    rules = _load_routing_rules()["routing_rules"]
    matches = []
    for rule in rules:
        keywords = rule.get("trigger_keywords", [])
        if any(_strip_diacritics(kw).lower() in normalized_query for kw in keywords):
            matches.append(rule)
    if matches:
        return max(matches, key=lambda rule: rule["routing_priority"])
    return next(rule for rule in rules if rule["category"] == "unmatched")


def _requires_personal_data(query: str) -> bool:
    normalized_query = _strip_diacritics(query).lower()
    return any(marker in normalized_query for marker in _PERSONAL_MARKERS) and any(
        term in normalized_query for term in _PERSONAL_DATA_TERMS
    )


def confidence_node(state: AgentState) -> dict:
    t_conf_start = time.perf_counter()
    settings = get_settings()
    chunks = state.get("retrieved_chunks", [])
    hallucination_passed = state.get("hallucination_passed", True)
    answerable = state.get("answerable", True)

    scored = [c["score"] for c in chunks if c.get("score") is not None]
    if not chunks:
        score = 0.0
    elif scored:
        score = max(scored)
    else:
        best_distance = min(c["distance"] for c in chunks)
        near, far = settings.distance_confidence_near, settings.distance_confidence_far
        score = (far - best_distance) / (far - near) if far > near else 0.0
        score = max(0.0, min(1.0, score))

    fail_cap = settings.low_confidence_threshold / 2
    if not hallucination_passed:
        score = min(score, fail_cap)
    if not answerable:
        score = min(score, fail_cap)

    from src.domains import get_matching_domain
    query = state.get("condensed_query") or state.get("query", "")
    domain = get_matching_domain(query, state.get("category"))
    if domain and hasattr(domain, "adjust_confidence"):
        score = domain.adjust_confidence(score, chunks, answerable)

    result: dict = {"confidence_score": round(score, 3)}
    if score < settings.low_confidence_threshold:
        result["escalate"] = True
        result["escalate_reason"] = "low_confidence"

    conf_ms = round((time.perf_counter() - t_conf_start) * 1000, 2)
    path_str = "FAST_PATH (Bypassing Hallucination Check)" if (answerable and score >= settings.low_confidence_threshold) else "GUARDED_PATH (Requires Verification/Escalation)"
    print(f"[TIMING] [confidence] {conf_ms}ms | score={round(score, 3)} (threshold: {settings.low_confidence_threshold}) -> {path_str}")

    return result


def _owner_phrase(boundary: dict) -> str:
    """Câu mô tả người phụ trách, lấy từ canonical registry.

    Trả chuỗi rỗng khi boundary không xác định được owner — thà không nói gì
    còn hơn chỉ người dùng tới một bộ phận do code tự suy ra.
    """
    target = boundary.get("handoff_target") or {}
    name = target.get("name")
    return f" Người phụ trách nội dung này là {name}." if name else ""


def escalate_node(state: AgentState) -> dict:
    """Escalate ở dạng NHẸ cho MVP: trả về response có cấu trúc gợi ý ticket,
    KHÔNG ghi thật vào Supabase (việc ghi ticket thật phụ thuộc backend/auth,
    ngoài phạm vi phần agent này).

    Ba nhánh KHÔNG tạo ticket, vì cùng một lý do: không có gì để một hàng ticket
    giải quyết.

    1. Câu hỏi nhắc công ty khác (competitor) — HR công ty mình không xử lý
       chính sách công ty khác, chỉ nên từ chối lịch sự.
    2. Scenario `HUMAN_FIRST` theo canonical registry — thiết kế nghiệp vụ đã
       chốt là phải trao đổi với người có thẩm quyền trước; biến nó thành một
       workflow tự động là đúng thứ registry cấm.
    3. Scenario `sensitivity=Critical` (quấy rối, kỷ luật, sức khỏe tinh thần,
       an toàn lao động) — MVP-1 chưa có ACL/audit/privacy model để giữ nội
       dung này trong một case, nên chỉ hướng tới kênh an toàn.

    Trường hợp còn lại (chủ yếu là câu cần dữ liệu cá nhân) vẫn tạo ticket như
    trước để không phá luồng hiện có. Wording user-facing KHÔNG được nói là đã
    gửi cho HR — hệ thống chưa gửi gì tới bộ phận nào.
    """
    query = state.get("condensed_query") or state.get("query", "")
    intent = state.get("intent", "hr_question")
    boundary = state.get("boundary") or {}

    if intent == "out_of_scope_or_personal" and _mentions_competitor_company(query):
        response = (
            "Kho tài liệu hiện tại chỉ chứa tài liệu nội bộ mẫu trong phạm vi demo, "
            "không xác nhận chính sách đang áp dụng của một công ty cụ thể. "
            "Với câu hỏi về lương/thưởng của công ty được nêu tên, bạn nên liên hệ trực tiếp bộ phận phụ trách của công ty đó."
        )
        return {
            "escalate": False,
            "escalate_reason": "competitor_question",
            "response": response,
        }

    if boundary.get("assistant_role") == "HUMAN_FIRST" or boundary.get("sensitivity") == "Critical":
        contact = (boundary.get("handoff_target") or {}).get("contact_label")
        channel = f" Bạn liên hệ {contact} để được hỗ trợ trực tiếp." if contact else ""
        return {
            "escalate": False,
            "escalate_reason": "human_first_required",
            "response": (
                "Nội dung này cần trao đổi trực tiếp với người có thẩm quyền, mình không xử lý thay được."
                + _owner_phrase(boundary)
                + channel
            ),
        }

    if state.get("hallucination_passed") is False:
        reason = "hallucination_detected"
    else:
        reason = state.get("escalate_reason")
    if not reason:
        if intent == "out_of_scope_or_personal" and _requires_personal_data(query):
            reason = "personal_data_required"
        else:
            reason = "out_of_scope" if intent == "out_of_scope_or_personal" else "low_confidence"

    rule = _match_routing_rule(query)
    department = rule["target_department"]
    category = rule["category"]
    priority = rule["ticket_priority"]

    # Không nói "đã gửi tới bộ phận X": sản phẩm chưa tích hợp với hệ thống HR
    # nào, nên câu đó là claim sai. Chỉ nói đúng thứ đã xảy ra — nội dung yêu
    # cầu đã được chuẩn bị — và chỉ ra người phụ trách theo registry.
    partial_answer = str(state.get("generated_answer") or "").strip()
    has_cited_evidence = bool(state.get("citations"))
    if reason == "low_confidence" and state.get("answerable") is False and partial_answer and has_cited_evidence and state.get("hallucination_passed", True):
        response = (
            partial_answer
            + "\n\nLưu ý: câu trả lời này mới dựa trên phần bằng chứng truy xuất được; "
            "chưa đủ để xác nhận toàn bộ yêu cầu."
            + _owner_phrase(boundary)
        )
    else:
        response = (
            "Xin lỗi, mình chưa đủ căn cứ để trả lời chắc chắn câu hỏi này. "
            "Mình đã chuẩn bị nội dung yêu cầu hỗ trợ để bạn chuyển tới người phụ trách."
            + _owner_phrase(boundary)
        )
    return {
        "escalate": True,
        "escalate_reason": reason,
        "ticket_category": category,
        "ticket_department": department,
        "ticket_priority": priority,
        "response": response,
    }
