import json
import re
import time

from src.agents.llm import acall_llm, thinking_arg
from src.agents.nodes.escalation import (
    _mentions_competitor_company,
    _requires_personal_data,
    _strip_diacritics,
)
from src.agents.state import AgentState, Intent

_INTENT_PATTERN = re.compile(r"greeting|hr_question|ambiguous|out_of_scope_or_personal")
_EXPLICIT_HYBRID_PATTERN = re.compile(r"\b(?:hybrid|wfh)\b|làm việc từ xa", re.IGNORECASE)

# Dấu hiệu người hỏi đang hỏi QUY ĐỊNH CHUNG chứ không hỏi số liệu của riêng
# mình — dùng làm circuit breaker cho nhánh escalate, KHÔNG dùng để phân loại.
# Không dấu vì so khớp qua _strip_diacritics().
_POLICY_SIGNAL_TERMS = (
    "quy dinh",
    "duoc bao nhieu",
    "toi da",
    "xu ly the nao",
    "xu ly nhu the nao",
    "co duoc",
    "duoc huong",
    "the nao",
    "nhu the nao",
    "thu tuc",
    "quy trinh",
    "cach tinh",
    "tinh sao",
    "bao lau",
    "co bat buoc",
    # Nhóm "hỏi cách làm / hỏi ai phụ trách": đo được trên bộ 140 câu, đây là
    # dạng câu hỏi quy trình bị fast router xếp nhầm sang escalate mà bộ từ khoá
    # ban đầu không bắt được (qa_013 "nộp hồ sơ qua kênh nào", qa_030 "ai phụ
    # trách phỏng vấn thôi việc").
    "kenh nao",
    "kieu gi",
    "bang cach nao",
    "ai phu trach",
    "ai se",
    "gom nhung gi",
    "can chuan bi",
)

_VERIFIER_SYSTEM = """Bạn quyết định MỘT điều duy nhất về câu hỏi của nhân viên gửi cho chatbot HR:

Câu hỏi này CÓ BẮT BUỘC phải tra dữ liệu cá nhân của chính người hỏi (số dư phép còn lại, số lương thực nhận, trạng thái đơn từ, hồ sơ/hợp đồng của họ) mới trả lời chính xác được không, hay có thể trả lời đầy đủ bằng QUY ĐỊNH CHUNG áp dụng cho mọi nhân viên?

Nguyên tắc phân định (quan trọng nhất):
- Câu hỏi CÓ nhắc tới bản thân ("tôi", "mình", kèm cả số liệu người hỏi tự cung cấp) VẪN LÀ policy_answerable nếu thứ họ cần biết là quy định xử lý, không phải số liệu trong hồ sơ của họ.
  * "Cuối năm mình còn 8 ngày phép chưa dùng thì xử lý thế nào?" -> policy_answerable (họ đã tự nói số ngày; thứ cần là quy định về phép chưa dùng).
  * "Tôi nghỉ thai sản thì được hưởng bao nhiêu?" -> policy_answerable (mức hưởng do luật quy định).
  * "Tôi ốm đột xuất sáng nay mới biết, báo nghỉ kiểu gì?" -> policy_answerable (hỏi thủ tục).
- Hỏi QUY TRÌNH, KÊNH NỘP, AI PHỤ TRÁCH một thủ tục HR luôn là policy_answerable — đây là thông tin có sẵn trong tài liệu quy trình, không nằm trong hồ sơ cá nhân.
  * "Mình giới thiệu bạn ứng tuyển thì bạn mình nộp hồ sơ qua kênh nào?" -> policy_answerable.
  * "Ai sẽ phụ trách phỏng vấn thôi việc với mình vậy?" -> policy_answerable (vai trò phụ trách do quy trình quy định).
- Chỉ là personal_data_required khi KHÔNG THỂ trả lời nếu không mở hồ sơ của riêng người đó:
  * "Tôi hiện còn chính xác bao nhiêu ngày phép?" -> personal_data_required.
  * "Đơn xin nghỉ của tôi được duyệt chưa?" -> personal_data_required.
  * "Lương tháng này của tôi là bao nhiêu?" -> personal_data_required.
- Câu hoàn toàn ngoài phạm vi HR (thời tiết, lập trình, nấu ăn) -> personal_data_required (giữ nguyên nhánh escalate).

Chỉ trả về ĐÚNG 1 từ: policy_answerable hoặc personal_data_required. Không giải thích."""

def _get_router_system() -> str:
    from src.config import get_settings
    internal_names = ", ".join(get_settings().internal_company_names)
    return f"""Bạn là bộ phân loại ý định cho chatbot HR nội bộ — chỉ phục vụ NHÂN VIÊN ĐANG LÀM VIỆC và HR Admin của công ty, KHÔNG phục vụ ứng viên/người ngoài. Phân loại câu hỏi của người dùng vào ĐÚNG 1 trong 4 nhóm:

- greeting: chào hỏi, xã giao, không phải câu hỏi HR thật (vd "chào bạn", "bạn là ai", "cảm ơn nhé").

- hr_question: chủ đề đã RÕ RÀNG, có thể trả lời ngay bằng tài liệu chính sách chung, không cần tra cứu dữ liệu riêng của người hỏi (vd "Nghỉ phép năm được mấy ngày?", "Quy trình tuyển dụng có mấy vòng?", "Nghỉ thai sản cần thủ tục gì?").

- ambiguous: câu hỏi THIẾU thông tin cần thiết để xác định người hỏi muốn biết điều gì, khiến không biết tra cứu tài liệu nào nếu không hỏi lại. Ví dụ:
  * "Bên mình có hỗ trợ chi phí y tế cho nhân viên không?" — mập mờ giữa BHYT bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Bao giờ thì thưởng về vậy?" — mập mờ giữa thưởng KPI, thưởng Tết, thưởng dự án.
  * "Chỗ mình có tham gia bảo hiểm cho người lao động không?" — mập mờ giữa BHXH bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Em đang muốn đổi chỗ làm việc." — mập mờ giữa chuyển phòng ban, chuyển địa điểm làm việc, hay xin nghỉ việc.
  * "Tôi đi làm ngày nghỉ thì được xử lý thế nào?" — mập mờ giữa trả thêm lương, nghỉ bù, hay cách chấm công.
  * "Công ty có tài trợ việc học thêm không?" — mập mờ giữa đào tạo nội bộ và hỗ trợ học/bằng cấp bên ngoài.
  * "Nghỉ việc rồi thì có được nhận khoản nào không?" — mập mờ giữa trợ cấp thôi việc, lương chưa thanh toán, hay phép năm chưa dùng.
  * "Nếu tôi nghỉ vì lý do sức khỏe thì sao?" — mập mờ giữa chế độ ốm đau BHXH, thủ tục báo nghỉ, hay phép năm còn lại.

  PHÂN ĐỊNH hr_question vs ambiguous — xét CHIỀU HỎI, không chỉ xét chủ đề HR:

  Trả về hr_question khi người hỏi ĐÃ nêu rõ họ muốn biết gì, chẳng hạn:
  mức tiền/tỷ lệ bao nhiêu · thủ tục làm thế nào, báo cho ai · điều kiện được hưởng ·
  thời điểm/thời hạn · giấy tờ cần nộp · cách tính.
  Câu vẫn có thể thiếu chi tiết cá nhân — riêng điều đó KHÔNG làm nó thành ambiguous,
  miễn là một chính sách chung trả lời được.

  Chỉ trả về ambiguous khi thông tin còn thiếu THỰC SỰ cản trở việc xác định câu hỏi
  chính sách, hoặc có thể dẫn tới nhiều câu trả lời khác nhau về bản chất.

  Cùng chủ đề nhưng khác chiều hỏi:
  * "Tôi đi làm ngày nghỉ thì được xử lý thế nào?" -> ambiguous (tiền? nghỉ bù? chấm công?)
    "Tôi đi làm ngày nghỉ thì tiền OT được tính theo tỷ lệ nào?" -> hr_question (chiều hỏi: mức tiền)
  * "Nếu tôi nghỉ vì lý do sức khỏe thì sao?" -> ambiguous (lương? thủ tục? BHXH?)
    "Nếu nghỉ ốm thì thủ tục báo nghỉ gồm những bước nào?" -> hr_question (chiều hỏi: thủ tục)
  * "Công ty có hỗ trợ bảo hiểm không?" -> ambiguous (BHYT bắt buộc? gói bổ sung?)
    "Điều kiện tham gia gói bảo hiểm sức khỏe bổ sung của công ty là gì?" -> hr_question (chiều hỏi: điều kiện)

- out_of_scope_or_personal: chủ đề đã RÕ (không cần hỏi lại để biết đang hỏi về cái gì), nhưng KHÔNG THỂ trả lời bằng tài liệu chính sách chung vì:
  (a) cần tra cứu DỮ LIỆU RIÊNG của người hỏi (lương cụ thể của tôi, số dư phép còn lại của tôi, đơn tôi đã duyệt chưa, hợp đồng của tôi khi nào hết hạn);
  (b) hỏi chính sách của MỘT CÔNG TY KHÁC CÓ TÊN CỤ THỂ (vd Viettel, FPT, Samsung, Tiki, MoMo, Grab, Shopee, Unilever...) — hễ câu hỏi nhắc tên riêng 1 công ty không phải công ty hiện tại ({internal_names}) thì LUÔN thuộc nhóm này, kể cả khi câu hỏi nghe giống hr_question bình thường; LƯU Ý: Nếu nhắc tới {internal_names} thì đó là công ty hiện tại, thuộc nhóm hr_question, KHÔNG thuộc nhóm này.
  (c) hoàn toàn ngoài phạm vi HR (thời tiết, lập trình, nấu ăn...).

QUY TẮC CHỐNG NHẦM (rất quan trọng — đây là các lỗi đã đo được, đừng lặp lại):
1. Hỏi về NỘI DUNG VĂN BẢN PHÁP LUẬT luôn là hr_question, kể cả khi nhắc tới chủ thể không phải người hỏi: "chủ hộ kinh doanh có phải đóng BHXH bắt buộc không?", "cá nhân tự kinh doanh có được thuê lao động không?", "cơ sở y tế công lập được dùng bao nhiêu % quỹ?", "Bộ Tài chính có trách nhiệm hướng dẫn gì?". Chữ "cá nhân", "cơ sở", "hộ" ở đây là ĐỐI TƯỢNG ĐIỀU CHỈNH của luật, KHÔNG phải dữ liệu riêng của người hỏi.
2. Hỏi tra cứu PHỤ LỤC/DANH MỤC của văn bản (vùng lương tối thiểu của tỉnh/phường nào, danh mục bệnh nghề nghiệp, mức lương cơ sở áp dụng cho nhóm nào) là hr_question — đây là nội dung có sẵn trong tài liệu.
3. Nhắc số hiệu văn bản (Nghị định 161/2026/NĐ-CP, Thông tư 60/2025/TT-BYT, Điều 107 Bộ luật Lao động...) là dấu hiệu MẠNH của hr_question.
4. Chỉ xếp vào nhóm (a) khi câu hỏi cần đúng HỒ SƠ CÁ NHÂN của người hỏi — tức phải mở dữ liệu của riêng họ mới trả lời được ("còn bao nhiêu ngày phép", "lương tháng này của tôi", "đơn của tôi duyệt chưa"). Câu hỏi về QUYỀN LỢI CHUNG mà nhân viên nào cũng áp dụng thì là hr_question.

Chỉ trả về ĐÚNG 1 từ trong 4 từ trên (greeting / hr_question / ambiguous / out_of_scope_or_personal). Không giải thích gì thêm."""

_DIRECT_SYSTEM = """Bạn là trợ lý HR nội bộ thân thiện. Trả lời ngắn gọn, tự nhiên cho câu xã giao của nhân viên.

Đáp đúng HÀNH VI GIAO TIẾP của người dùng — đây là điểm quan trọng nhất:
- Người dùng MỞ ĐẦU hội thoại / chào hỏi -> chào lại ngắn gọn, có thể mời họ hỏi về chính sách nhân sự.
- Người dùng CẢM ƠN hoặc xác nhận đã hiểu -> đáp lại lời cảm ơn/xác nhận đó. TUYỆT ĐỐI KHÔNG mở đầu bằng lời chào và KHÔNG tự giới thiệu lại — hội thoại đang diễn ra, không phải bắt đầu.
- Người dùng TẠM BIỆT -> chào tạm biệt ngắn gọn.
- Người dùng hỏi bạn là ai / giúp được gì -> giới thiệu ngắn về phạm vi hỗ trợ.

KHÔNG nêu số liệu, điều khoản hay quy định chính sách nào ở bước này, trừ khi chính người dùng đã nhắc tới.

Ví dụ đối chiếu:
- "Chào bạn" -> "Chào bạn! Mình có thể hỗ trợ gì về chính sách nhân sự?"
- "Ok cảm ơn nhé" -> "Không có gì, khi nào cần bạn cứ hỏi mình nhé."
- "Bye nhé" -> "Chào bạn, hẹn gặp lại!"

Chỉ trả về câu trả lời, không thêm lời dẫn."""

_CLARIFY_SYSTEM = """Câu hỏi của nhân viên về chủ đề HR nhưng còn mập mờ, có thể hiểu theo nhiều nghĩa. Hãy đặt lại ĐÚNG 1 câu hỏi làm rõ, ngắn gọn, lịch sự, giúp xác định đúng ý người hỏi (vd hỏi rõ là nghỉ phép năm, nghỉ ốm hay nghỉ việc hẳn). Chỉ trả về câu hỏi làm rõ, không thêm lời dẫn."""


async def router_node(state: AgentState) -> dict:
    from src.config import get_settings

    query = state.get("condensed_query") or state.get("query", "")
    # Deterministic brand guard for the course/demo scope: named companies that are
    # not the internal demo persona must not be treated as currently applicable HR policy.
    if _mentions_competitor_company(query):
        return {"intent": "out_of_scope_or_personal"}

    # Đây là nhóm thuật ngữ HR chuyên biệt, không mang nghĩa mập mờ và không
    # cần tốn một lượt LLM chỉ để phân loại. Guard tên công ty ở trên vẫn chạy
    # trước để câu hỏi Hybrid của doanh nghiệp khác không lọt vào RAG nội bộ.
    if _EXPLICIT_HYBRID_PATTERN.search(query):
        return {"intent": "hr_question"}

    # router_model rỗng -> None -> acall_llm dùng llm_model như cũ.
    settings = get_settings()
    model = settings.router_model or None
    raw = await acall_llm(
        _get_router_system(),
        query,
        temperature=0.0,
        model=model,
        enable_thinking=thinking_arg(settings.thinking_router),
    )
    match = _INTENT_PATTERN.search(raw.strip().lower())
    # Không parse được thì coi là hr_question — thử RAG còn hơn im lặng/escalate nhầm.
    intent: Intent = match.group(0) if match else "hr_question"  # type: ignore[assignment]

    if intent == "out_of_scope_or_personal" and settings.escalation_guard_enabled:
        return await _guard_escalation(query, model)
    return {"intent": intent}


def _has_policy_signal(query: str) -> bool:
    normalized = _strip_diacritics(query).lower()
    return any(term in normalized for term in _POLICY_SIGNAL_TERMS)


async def _guard_escalation(query: str, model: str | None) -> dict:
    """Chốt chặn cuối trước khi đẩy một câu sang nhánh escalate/HRBP.

    Vì sao chỉ đặt ở nhánh này mà không phải mọi nhánh: đây là chỗ phân loại
    sai gây hậu quả nặng nhất. `hr_question` bị đẩy nhầm sang
    `out_of_scope_or_personal` nghĩa là chatbot TỪ CHỐI một câu nó hoàn toàn trả
    lời được — tệ hơn nhiều so với chiều ngược lại (chỉ tốn thêm một lượt
    retrieval) hay so với `hr_question -> ambiguous` (chỉ tốn một lượt hỏi lại).
    Với fast router (thinking tắt), đây đúng là chỗ hỏng nhiều nhất: 7/140 câu
    hr_question rơi nhầm vào đây so với 4/140 khi bật thinking.

    Ba tầng, xếp theo giá tăng dần — cố ý KHÔNG verify mọi request:

    1. Không có dấu hiệu hỏi quy định chung -> escalate luôn, không tốn LLM.
       Câu personal thật ("Đơn của tôi duyệt chưa?") dừng ở đây.
    2. Khớp heuristic personal rõ ràng (_requires_personal_data: "của tôi" +
       lương/phép/đơn/hợp đồng...) -> escalate luôn. "Tôi còn bao nhiêu ngày
       phép?" dừng ở đây, không tốn LLM dù câu có chữ "bao nhiêu".
    3. Còn lại là ca thật sự khó (vừa nhắc bản thân vừa hỏi quy định) -> mới
       trả tiền cho 1 lần gọi LLM CÓ thinking, với prompt hẹp chỉ 2 lớp.

    Rule ở tầng 1-2 chỉ đóng vai circuit breaker (quyết định CÓ verify hay
    không), không tự đổi intent — quyết định đổi intent luôn do LLM verifier.

    Trả về dict để mang kèm telemetry (verifier_called/changed_route/latency):
    thiết kế này chỉ đúng chừng nào verifier còn SỬA được route đủ thường xuyên.
    Biết `useful_rate` tụt là điều kiện để mở task thêm pre-filter — xem
    AgentState.verifier_* để biết cách tính từ log.
    """
    if not _has_policy_signal(query) or _requires_personal_data(query):
        return {"intent": "out_of_scope_or_personal", "verifier_called": False}

    started = time.perf_counter()
    verdict = await acall_llm(
        _VERIFIER_SYSTEM,
        query,
        temperature=0.0,
        model=model,
        # Verifier CÓ thinking dù fast router tắt: đây là toàn bộ lý do nó tồn
        # tại — mua lại accuracy đã mất, và chỉ trên phần traffic nhỏ đi tới đây.
        enable_thinking=None,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    rescued = "policy_answerable" in verdict.lower()
    print(
        "[escalation_guard] "
        + json.dumps(
            {"verifier_called": True, "changed_route": rescued, "latency_ms": latency_ms},
            ensure_ascii=False,
        )
    )
    return {
        "intent": "hr_question" if rescued else "out_of_scope_or_personal",
        "verifier_called": True,
        "verifier_changed_route": rescued,
        "verifier_latency_ms": latency_ms,
    }


# Câu chào cố định cho `direct_mode="template"`. Một câu duy nhất, không chứa
# bất kỳ số liệu chính sách nào — đúng ràng buộc mà _DIRECT_SYSTEM đang dặn LLM
# ("không bịa thông tin chính sách ở bước này"), nhưng thực thi bằng hằng số nên
# không thể vi phạm.
_DIRECT_TEMPLATE = (
    "Chào bạn, mình là trợ lý HR nội bộ. Bạn cần hỏi gì về chính sách nhân sự "
    "(nghỉ phép, lương thưởng, bảo hiểm, tuyển dụng, đào tạo...) thì cứ nhắn nhé."
)


async def direct_node(state: AgentState) -> dict:
    from src.config import get_settings

    settings = get_settings()
    if settings.direct_mode == "template":
        return {"response": _DIRECT_TEMPLATE}

    query = state.get("condensed_query") or state.get("query", "")
    if settings.direct_mode == "fast_llm":
        answer = await acall_llm(
            _DIRECT_SYSTEM,
            query,
            temperature=0.5,
            model=settings.router_model or None,
            enable_thinking=False,
        )
    else:
        answer = await acall_llm(_DIRECT_SYSTEM, query, temperature=0.5)
    return {"response": answer.strip()}


async def clarify_node(state: AgentState) -> dict:
    from src.config import get_settings

    settings = get_settings()
    query = state.get("condensed_query") or state.get("query", "")
    question = (
        await acall_llm(
            _CLARIFY_SYSTEM,
            query,
            temperature=0.4,
            model=settings.clarify_model or None,
            enable_thinking=thinking_arg(settings.thinking_clarify),
        )
    ).strip()
    return {"needs_clarification": True, "clarifying_question": question, "response": question}
