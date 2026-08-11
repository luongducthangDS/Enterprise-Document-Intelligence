import re

from src.agents.nodes.escalation import _mentions_competitor_company
from src.agents.llm import acall_llm
from src.agents.state import AgentState, Intent

_INTENT_PATTERN = re.compile(r"greeting|hr_question|ambiguous|out_of_scope_or_personal")

def _get_router_system() -> str:
    from src.config import get_settings
    internal_names = ", ".join(get_settings().internal_company_names)
    return f"""Bạn là bộ phân loại ý định cho chatbot HR nội bộ — chỉ phục vụ NHÂN VIÊN ĐANG LÀM VIỆC và HR Admin của công ty, KHÔNG phục vụ ứng viên/người ngoài. Phân loại câu hỏi của người dùng vào ĐÚNG 1 trong 4 nhóm:

- greeting: chào hỏi, xã giao, không phải câu hỏi HR thật (vd "chào bạn", "bạn là ai", "cảm ơn nhé").

- hr_question: chủ đề đã RÕ RÀNG, có thể trả lời ngay bằng tài liệu chính sách chung, không cần tra cứu dữ liệu riêng của người hỏi (vd "Nghỉ phép năm được mấy ngày?", "Quy trình tuyển dụng có mấy vòng?", "Nghỉ thai sản cần thủ tục gì?").

- ambiguous: câu hỏi có từ/cụm từ có thể ứng với NHIỀU chủ đề chính sách khác nhau, khiến không biết nên tra cứu tài liệu nào nếu không hỏi lại. Dấu hiệu nhận biết: nếu phải ĐOÁN xem người hỏi đang nói tới loại nghỉ nào / loại bảo hiểm nào / loại thưởng nào / loại hỗ trợ nào thì đây là ambiguous, KHÔNG PHẢI hr_question. Ví dụ:
  * "Công ty có hỗ trợ tiền khám bệnh không?" — mập mờ giữa BHYT bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Tôi khi nào được nhận tiền thưởng?" — mập mờ giữa thưởng KPI, thưởng Tết, thưởng dự án.
  * "Công ty có đóng bảo hiểm cho mình không?" — mập mờ giữa BHXH bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Tôi muốn xin chuyển công tác." — mập mờ giữa chuyển phòng ban, chuyển địa điểm làm việc, hay xin nghỉ việc.
  * "Tôi làm cuối tuần thì được tính sao?" — mập mờ giữa OT trả thêm lương hay nghỉ bù.
  * "Công ty có hỗ trợ học tập không?" — mập mờ giữa đào tạo nội bộ và hỗ trợ học/bằng cấp bên ngoài.
  * "Nếu tôi quit thì có được nhận tiền không?" — mập mờ giữa trợ cấp thôi việc, lương ngày chưa thanh toán, hay phép năm chưa dùng.
  * "Tôi bị ốm có được trả lương không?" — mập mờ giữa chế độ ốm đau BHXH và phép năm còn lại.

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

_DIRECT_SYSTEM = """Bạn là trợ lý HR nội bộ thân thiện. Trả lời ngắn gọn, lịch sự cho lời chào/câu xã giao của nhân viên, có thể gợi ý họ hỏi về chính sách nhân sự (nghỉ phép, lương thưởng, tuyển dụng, đào tạo...). Không bịa thông tin chính sách cụ thể ở bước này."""

_CLARIFY_SYSTEM = """Câu hỏi của nhân viên về chủ đề HR nhưng còn mập mờ, có thể hiểu theo nhiều nghĩa. Hãy đặt lại ĐÚNG 1 câu hỏi làm rõ, ngắn gọn, lịch sự, giúp xác định đúng ý người hỏi (vd hỏi rõ là nghỉ phép năm, nghỉ ốm hay nghỉ việc hẳn). Chỉ trả về câu hỏi làm rõ, không thêm lời dẫn."""


async def router_node(state: AgentState) -> dict:
    from src.config import get_settings

    query = state.get("condensed_query") or state.get("query", "")
    # Deterministic brand guard for the course/demo scope: named companies that are
    # not the internal demo persona must not be treated as currently applicable HR policy.
    if _mentions_competitor_company(query):
        return {"intent": "out_of_scope_or_personal"}

    # router_model rỗng -> None -> acall_llm dùng llm_model như cũ.
    model = get_settings().router_model or None
    raw = await acall_llm(_get_router_system(), query, temperature=0.0, model=model)
    match = _INTENT_PATTERN.search(raw.strip().lower())
    # Không parse được thì coi là hr_question — thử RAG còn hơn im lặng/escalate nhầm.
    intent: Intent = match.group(0) if match else "hr_question"  # type: ignore[assignment]
    return {"intent": intent}


async def direct_node(state: AgentState) -> dict:
    query = state.get("condensed_query") or state.get("query", "")
    answer = await acall_llm(_DIRECT_SYSTEM, query, temperature=0.5)
    return {"response": answer.strip()}


async def clarify_node(state: AgentState) -> dict:
    query = state.get("condensed_query") or state.get("query", "")
    question = (await acall_llm(_CLARIFY_SYSTEM, query, temperature=0.4)).strip()
    return {"needs_clarification": True, "clarifying_question": question, "response": question}
