import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from src.agents.state import AgentState
from src.config import get_settings

TICKET_ROUTING_PATH = Path(__file__).resolve().parents[1] / "resources" / "ticket_routing_rules.json"

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


def _mentions_competitor_company(query: str) -> bool:
    settings = get_settings()
    normalized_query = _strip_diacritics(query).lower()
    competitors = _COMPETITOR_COMPANY_KEYWORDS - set(settings.internal_company_names)
    return any(name in normalized_query for name in competitors)

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
    """Confidence = độ liên quan của đoạn tốt nhất, kết hợp kết quả hallucination check.

    Ưu tiên `score` của reranker: nó nằm trong khoảng 0-1 và trải rộng gần hết
    khoảng đó (đo thực tế: 0.80 cho đoạn trả lời đúng, 0.57 cho đoạn liên quan,
    0.00002 cho đoạn lạc đề), nên so với ngưỡng mới có ý nghĩa.

    Chỉ khi không có reranker mới lùi về khoảng cách cosine — nhưng khi đó
    dùng thang co giãn theo `retrieval_max_distance` thay vì `1 - distance`:
    khoảng cách cosine thực đo chỉ dao động 0.10-0.23, nên `1 - distance` luôn
    cho ra 0.77-0.90 và không bao giờ chạm được ngưỡng escalate — tức là vô
    hiệu hoá toàn bộ nhánh escalate mà không có triệu chứng nào nhìn thấy được.
    """
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
        # Neo theo phân phối distance đo thực tế trên 100 câu eval (in-scope
        # median 0.137, out-of-scope median 0.181): <= near coi như chắc chắn,
        # >= far coi như không liên quan, ở giữa nội suy tuyến tính.
        score = (far - best_distance) / (far - near) if far > near else 0.0
        score = max(0.0, min(1.0, score))
    # Cả hai tín hiệu dưới đây đều có nghĩa "câu trả lời không đáng tin, phải
    # escalate", nên cap được NEO THEO ngưỡng thay vì là hằng số rời. Cap cũ
    # (0.3) từng được chọn cho ngưỡng 0.5; khi hạ ngưỡng xuống 0.2 nó lập tức
    # nằm TRÊN ngưỡng và vô hiệu hoá escalate mà không có triệu chứng nào.
    fail_cap = settings.low_confidence_threshold / 2
    if not hallucination_passed:
        score = min(score, fail_cap)
    # Reranker có thể rất tự tin về một đoạn SAI (đo được: 10/29 câu in_scope
    # fail có score 0.78-1.00 nhưng không hề chứa câu trả lời) — không ngưỡng
    # nào trên score bắt được nhóm này. Chỉ chính model đọc context mới biết
    # đoạn trích có trả lời được câu hỏi không, nên tín hiệu đó được ưu tiên.
    if not answerable:
        score = min(score, fail_cap)

    result: dict = {"confidence_score": round(score, 3)}
    if score < settings.low_confidence_threshold:
        result["escalate"] = True
        result["escalate_reason"] = "low_confidence"
    return result


def escalate_node(state: AgentState) -> dict:
    """Escalate ở dạng NHẸ cho MVP: trả về response có cấu trúc gợi ý ticket,
    KHÔNG ghi thật vào Supabase (việc ghi ticket thật phụ thuộc backend/auth,
    ngoài phạm vi phần agent này).

    Câu hỏi nhắc công ty khác (competitor) là 1 nhánh RIÊNG, không tạo ticket:
    không có gì để HR công ty mình xử lý khi được hỏi chính sách công ty khác —
    tạo ticket ở trường hợp này là sai, chỉ nên từ chối lịch sự (khác hẳn câu
    hỏi cần tra dữ liệu cá nhân, nơi tạo ticket mới hợp lý)."""
    query = state.get("condensed_query") or state.get("query", "")
    intent = state.get("intent", "hr_question")

    if intent == "out_of_scope_or_personal" and _mentions_competitor_company(query):
        response = (
            "Knowledge base hiện tại chỉ hỗ trợ chính sách HR mẫu trong phạm vi demo, "
            "không xác nhận chính sách đang áp dụng của một công ty cụ thể. "
            "Với câu hỏi về lương/thưởng của công ty được nêu tên, bạn nên liên hệ trực tiếp HR/C&B của công ty đó."
        )
        return {
            "escalate": False,
            "escalate_reason": "competitor_question",
            "response": response,
        }

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

    response = (
        "Xin lỗi, mình chưa đủ căn cứ để trả lời chắc chắn câu hỏi này. "
        f"Mình đã tạo yêu cầu hỗ trợ gửi tới bộ phận {department} để có người xử lý trực tiếp cho bạn."
    )
    return {
        "escalate": True,
        "escalate_reason": reason,
        "ticket_category": category,
        "ticket_department": department,
        "ticket_priority": priority,
        "response": response,
    }
