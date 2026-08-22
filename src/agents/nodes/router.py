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
from src.domains import get_conversation_domain

_INTENT_PATTERN = re.compile(r"greeting|hr_question|ambiguous|out_of_scope_or_personal|pure_statutory")
_EXPLICIT_HYBRID_PATTERN = re.compile(r"\b(?:hybrid|wfh)\b|làm việc từ xa", re.IGNORECASE)
_EXPLICIT_PRODUCT_KNOWLEDGE_PATTERN = re.compile(
    r"\b(?:checkout redesign|recommendation system|notification center|dark mode|"
    r"subscription upgrade|search improvements|product roadmap)\b",
    re.IGNORECASE,
)

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
    return f"""Bạn là bộ phân loại ý định cho trợ lý tri thức nội bộ HR và Product — chỉ phục vụ nhân viên công ty, KHÔNG phục vụ ứng viên/người ngoài. Phân loại câu hỏi của người dùng vào ĐÚNG 1 trong 5 nhóm:

- greeting: chào hỏi, xã giao, không phải câu hỏi HR thật (vd "chào bạn", "bạn là ai", "cảm ơn nhé").

- hr_question: nhãn legacy cho mọi câu hỏi tri thức nội bộ HR HOẶC Product đã RÕ RÀNG, có thể trả lời ngay bằng tài liệu chung, không cần tra cứu dữ liệu riêng của người hỏi (vd "Nghỉ phép năm theo quy định được mấy ngày?", "Checkout Redesign dự kiến release khi nào?", "Recommendation System đang ở trạng thái nào?", "Kết quả experiment Checkout Redesign là gì?").

- ambiguous: câu hỏi THIẾU thông tin cần thiết hoặc đa nghĩa, khiến không biết tra cứu chính xác tài liệu/quy định nào nếu không hỏi lại làm rõ. Ví dụ:
  * "Tôi còn bao nhiêu ngày phép?" — mập mờ giữa ngày phép tiêu chuẩn năm nay và ngày phép cộng dồn từ năm trước.
  * "Tôi khi nào được ký hợp đồng mới?" — mập mờ giữa thời điểm ký hợp đồng chính thức sau thử việc, gia hạn hợp đồng sắp hết hạn, hay phụ lục thăng cấp.
  * "Tôi muốn nghỉ thai sản thì làm thủ tục gì?" — mập mờ giữa thủ tục nghỉ thai sản trước khi sinh (khám thai/dưỡng thai) và sau khi sinh (hưởng chế độ thai sản).
  * "Lương của tôi tháng này bị thiếu." — mập mờ giữa thiếu lương cơ bản, tiền thưởng, phụ cấp hay bị khấu trừ sai.
  * "Bao giờ thì thưởng về vậy?" — mập mờ giữa thưởng KPI, thưởng Tết, thưởng dự án.
  * "Bên mình có hỗ trợ chi phí y tế cho nhân viên không?" — mập mờ giữa BHYT bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Chỗ mình có tham gia bảo hiểm cho người lao động không?" — mập mờ giữa BHXH bắt buộc và bảo hiểm sức khỏe tự nguyện.
  * "Em đang muốn đổi chỗ làm việc." — mập mờ giữa chuyển phòng ban, chuyển địa điểm làm việc, hay xin nghỉ việc.
  * "Tôi đi làm ngày nghỉ thì được xử lý thế nào?" — mập mờ giữa trả thêm lương, nghỉ bù, hay cách chấm công.
  * "Công ty có tài trợ việc học thêm không?" — mập mờ giữa đào tạo nội bộ và hỗ trợ học/bằng cấp bên ngoài.
  * "Nghỉ việc rồi thì có được nhận khoản nào không?" — mập mờ giữa trợ cấp thôi việc, lương chưa thanh toán, hay phép năm chưa dùng.
  * "Nếu tôi nghỉ vì lý do sức khỏe thì sao?" — mập mờ giữa chế độ ốm đau BHXH, thủ tục báo nghỉ, hay phép năm còn lại.
  * "Em cần xin xác nhận, làm sao ạ?" / "Em muốn xin giấy xác nhận" — mập mờ giữa xác nhận công tác, xác nhận thu nhập/lương, hay xác nhận nghỉ phép.
  * "Onboarding của em bị chậm rồi, giờ xử lý sao ạ?" — mập mờ chưa rõ chậm khâu hợp đồng, thiết bị, tài khoản hay đào tạo.
  * "Em xin nghỉ dài ngày được không ạ?" / "Làm từ xa có được không ạ?" — mập mờ giữa các chế độ nghỉ/làm việc khác nhau.

  PHÂN ĐỊNH hr_question vs ambiguous — xét CHIỀU HỎI & ĐỘ CỤ THỂ:

  Trả về hr_question khi người hỏi ĐÃ nêu rõ họ muốn biết gì, chẳng hạn:
  mức tiền/tỷ lệ bao nhiêu · thủ tục làm thế nào, báo cho ai · điều kiện được hưởng ·
  thời điểm/thời hạn · giấy tờ cần nộp · cách tính · quyền lợi mua gói bảo hiểm người thân (vợ/chồng, con cái).
  Câu vẫn có thể thiếu chi tiết cá nhân — riêng điều đó KHÔNG làm nó thành ambiguous,
  miễn là một chính sách chung trả lời được.

  Chỉ trả về ambiguous khi thông tin còn thiếu THỰC SỰ cản trở việc xác định câu hỏi
  chính sách, hoặc có thể dẫn tới nhiều câu trả lời khác nhau về bản chất cần hỏi lại để xác định.

  Cùng chủ đề nhưng khác chiều hỏi:
  * "Tôi đi làm ngày nghỉ thì được xử lý thế nào?" -> ambiguous (tiền? nghỉ bù? chấm công?)
    "Tôi đi làm ngày nghỉ thì tiền OT được tính theo tỷ lệ nào?" -> hr_question (chiều hỏi: mức tiền)
  * "Nếu tôi nghỉ vì lý do sức khỏe thì sao?" -> ambiguous (lương? thủ tục? BHXH?)
    "Nếu nghỉ ốm thì thủ tục báo nghỉ gồm những bước nào?" -> hr_question (chiều hỏi: thủ tục)
  * "Công ty có hỗ trợ bảo hiểm không?" -> ambiguous (BHYT bắt buộc? gói bổ sung?)
    "Đăng ký bảo hiểm sức khỏe cho vợ và con thì chi phí thế nào, gói hạng gì?" -> hr_question (chiều hỏi: quy định mua bảo hiểm người thân)
  * "Tôi muốn nghỉ thai sản thì làm thủ tục gì?" -> ambiguous (trước sinh hay sau sinh?)
    "Thủ tục thanh toán trợ cấp thai sản sau sinh cần nộp giấy tờ gì?" -> hr_question (chiều hỏi: thủ tục sau sinh)

- out_of_scope_or_personal: chủ đề đã RÕ, nhưng KHÔNG THỂ trả lời bằng tài liệu chính sách chung vì:
  (a) cần tra cứu DỮ LIỆU RIÊNG của người hỏi từ hệ thống CSDL (vd: "Đơn xin nghỉ ngày 15/8 của tôi đã được duyệt chưa?", "Tra cứu lịch sử chuyển khoản lương tháng 7 của tôi"); LƯU Ý: Nếu câu hỏi còn mơ hồ chưa rõ loại chính sách ("Tôi còn bao nhiêu ngày phép?", "Tôi khi nào được ký hợp đồng mới?", "Lương của tôi tháng này bị thiếu") thì phải xếp vào ambiguous để hỏi lại làm rõ, KHÔNG xếp vào out_of_scope_or_personal.
  (b) hỏi chính sách của MỘT CÔNG TY KHÁC CÓ TÊN CỤ THỂ (vd Viettel, FPT, Samsung, Tiki, MoMo, Grab, Shopee, Unilever...) — hễ câu hỏi nhắc tên riêng 1 công ty không phải công ty hiện tại ({internal_names}) thì LUÔN thuộc nhóm này, kể cả khi câu hỏi nghe giống hr_question bình thường; LƯU Ý: Nếu nhắc tới {internal_names} thì đó là công ty hiện tại, thuộc nhóm hr_question, KHÔNG thuộc nhóm này.
  (c) hoàn toàn ngoài phạm vi HR (thời tiết, lập trình, nấu ăn...).

- pure_statutory: câu hỏi hỏi THẲNG văn bản pháp luật quốc gia (luật/bộ luật/nghị định/thông tư) nói gì, KHÔNG hỏi công ty áp dụng ra sao — 4 dạng:
  a) STATUTORY_CONTENT: nội dung/phạm vi/giải thích một điều khoản luật (vd "Điều 112 Bộ luật Lao động 2019 quy định về chế độ nghỉ lễ, tết như thế nào?", "Pháp luật bảo hiểm xã hội quy định nguyên tắc chung nào về tham gia BHXH bắt buộc?").
  b) LEGAL_PROCEDURE: thủ tục/trình tự thực hiện VỚI CƠ QUAN NHÀ NƯỚC (đăng ký, xin cấp phép, nộp hồ sơ tại Sở/cơ quan quản lý lao động...) — KHÔNG phải thủ tục nội bộ công ty.
  c) LEGAL_SANCTION: trách nhiệm pháp lý, chế tài, xử phạt vi phạm hành chính do NHÀ NƯỚC áp dụng (mức phạt tiền, biện pháp khắc phục hậu quả theo quy định xử phạt).
  d) STATUTORY_THRESHOLD: mức/ngưỡng/tỷ lệ LUẬT ĐỊNH, hỏi thẳng "theo luật/pháp luật/nghị định X thì bao nhiêu" — KHÔNG hỏi công ty trả/áp dụng bao nhiêu.

  QUY TẮC ƯU TIÊN (internal override — áp dụng TRƯỚC khi xếp pure_statutory): nếu câu hỏi hỏi CHÍNH SÁCH CỦA CÔNG TY quy định/cho phép/chi trả/áp dụng gì — kể cả khi chính sách đó lấy căn cứ từ luật, hoặc trùng nội dung với một quy định luật — vẫn là hr_question. Chỉ xếp pure_statutory khi câu hỏi hỏi thẳng LUẬT/NHÀ NƯỚC quy định gì, không hỏi công ty áp dụng ra sao. So sánh:
  * "Nghỉ lễ tết được nghỉ mấy ngày?" / "Ở công ty tôi được nghỉ lễ thế nào?" -> hr_question (hỏi chính sách áp dụng).
    "Điều 112 Bộ luật Lao động quy định nghỉ lễ tết thế nào?" / "Luật lao động cho nghỉ lễ bao nhiêu ngày?" -> pure_statutory (hỏi thẳng luật).
  * "Công ty trả OT tối thiểu bao nhiêu?" -> hr_question.
    "Theo luật, công ty phải trả OT tối thiểu bao nhiêu?" -> pure_statutory (hỏi mức luật ĐỊNH, không hỏi mức công ty thực trả).
  * "Mức lương tối thiểu vùng I năm 2026 theo Nghị định 293/2025/NĐ-CP là bao nhiêu?" -> pure_statutory (hỏi thẳng số liệu nghị định, không nhắc chính sách công ty).
  * "Nghị định 145/2020/NĐ-CP nói gì về quấy rối tình dục tại nơi làm việc?" -> pure_statutory.
    "Công ty xử lý quấy rối tình dục tại nơi làm việc thế nào?" -> hr_question (hỏi quy trình nội bộ công ty).
  * "Em làm hỏng thiết bị công ty, thiệt hại dưới 10 tháng lương tối thiểu vùng thì công ty bồi thường/khấu trừ lương thế nào?" -> hr_question — "lương tối thiểu vùng" ở đây chỉ là ĐƠN VỊ QUY CHIẾU để tính ngưỡng thiệt hại, KHÔNG PHẢI chủ thể câu hỏi (câu hỏi thật sự hỏi CÔNG TY xử lý ra sao) và KHÔNG gắn số hiệu văn bản cụ thể nào -> vẫn hr_question, khác với ví dụ "Mức lương tối thiểu vùng I... là bao nhiêu?" ở trên (ở đó "lương tối thiểu vùng" MỚI LÀ chủ thể được hỏi).
  * "Trường hợp nào người lao động được quyền nghỉ việc ngay không cần báo trước cho công ty?" -> hr_question — đây là quyền lợi/thủ tục áp dụng cho NLĐ tại công ty, có thể trả lời bằng chính sách nội bộ (quy trình nghỉ việc), không phải hỏi luật trừu tượng.

QUY TẮC CHỐNG NHẦM (rất quan trọng — đây là các lỗi đã đo được, đừng lặp lại):
1. Hỏi ĐIỀU KIỆN/ĐỐI TƯỢNG cụ thể áp dụng chính sách công ty vẫn là hr_question kể cả khi chủ thể không phải người hỏi và nội dung có căn cứ luật: "chủ hộ kinh doanh có phải đóng BHXH bắt buộc không?", "người nước ngoài làm việc có phải tham gia BHXH không?", "làm part-time có được đóng BHXH không?" — đây là câu hỏi ĐIỀU KIỆN/QUYỀN LỢI cụ thể có thể trả lời bằng tài liệu chính sách nội bộ (không phải câu hỏi "luật nói gì" trừu tượng). CHỈ xếp pure_statutory khi câu hỏi minh thị hỏi "pháp luật/luật/nghị định X quy định NHƯ THẾ NÀO/NGUYÊN TẮC CHUNG" hoặc trích dẫn số hiệu văn bản để hỏi trực tiếp nội dung điều khoản đó.
2. Hỏi tra cứu PHỤ LỤC/DANH MỤC/MỨC LUẬT ĐỊNH khi câu hỏi minh thị gắn với TÊN/SỐ HIỆU văn bản pháp luật cụ thể (vd "Nghị định 293/2025/NĐ-CP quy định mức lương tối thiểu Vùng I là bao nhiêu?") là pure_statutory — đây chính là STATUTORY_THRESHOLD. Nếu câu hỏi KHÔNG gắn với văn bản cụ thể mà hỏi công ty áp dụng gì ("Lương tối thiểu ở đây là bao nhiêu?") thì vẫn là hr_question.
3. Thủ tục/chế tài với CƠ QUAN NHÀ NƯỚC (đăng ký nội quy lao động với Sở LĐTBXH, cấp giấy phép cho thuê lại lao động, xử phạt vi phạm hành chính, thẩm quyền lập biên bản xử phạt) luôn là pure_statutory — công ty không tự thực hiện các thủ tục/chế tài này cho nhân viên.
4. Chỉ xếp vào nhóm (a) out_of_scope_or_personal khi câu hỏi đã rõ ràng và bắt buộc phải tra cứu hồ sơ cá nhân thực tế. Nếu câu hỏi còn mơ hồ nhiều nghĩa chưa rõ người hỏi muốn biết khía cạnh nào thì luôn xếp vào ambiguous.
5. Câu hỏi nối tiếp / Đã chỉ định phạm vi nhánh cụ thể: Khi câu hỏi đã được làm rõ hoặc đã nêu rõ nhánh chính sách cụ thể (ví dụ: "thủ tục nghỉ thai sản sau khi sinh", "thủ tục trước khi sinh", "nghỉ thai sản sau sinh", "ngày phép năm nay", "hợp đồng chính thức sau thử việc", "thiếu tiền thưởng KPI"...) -> BẮT BUỘC xếp vào hr_question để chuyển sang RAG retrieval tìm kiếm tài liệu và trả lời kết quả kèm trích dẫn, TUYỆT ĐỐI KHÔNG lặp lại ambiguous hay hỏi lại lần nữa.

Chỉ trả về ĐÚNG 1 từ trong 5 từ trên (greeting / hr_question / ambiguous / out_of_scope_or_personal / pure_statutory). Không giải thích gì thêm."""

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

    # --- Domain-Specific Personal Data / ABSTAIN Guardrail (G5) ---
    domain = get_conversation_domain(query, state.get("category"), state.get("history"))
    if domain:
        is_personal, reason_code = domain.check_personal_data_query(query)
        if is_personal:
            return {
                "intent": "out_of_scope_or_personal",
                "escalate_reason": reason_code or "domain_personal_data_detected",
                "verifier_called": False,
            }

    # --- G10: Domain Early-Pass — câu hỏi chính sách kế toán confirmed → không qua escalate ---
    # Nếu G1 đã xác nhận query thuộc phạm vi kế toán/tài chính (accounting domain matched),
    # thì đây CHẮC CHẮN là câu hỏi chính sách nội bộ, không cần để LLM router có thể phân loại
    # nhầm thành out_of_scope_or_personal (đo được: "phòng nào vượt ngân sách" bị router nhầm).
    # Điều kiện: query phải cụ thể (≥ 6 từ) và KHÔNG chứa đại từ chỉ định mơ hồ (này/đó/kia...)
    # để tránh bypass câu hỏi ambiguous như "Hợp đồng này thanh toán thế nào?"
    _G10_AMBIGUOUS_REFS = re.compile(r"\b(n[aà]y|[đd][oó]|kia|v[uừ]a r[oồ]i|tr[eê]n|d[uư][oớ]i)\b", re.IGNORECASE)
    # HR bảo hiểm/người phụ thuộc có thể chứa từ "chi phí"; không bypass router.
    _G10_HR_EXCLUSIONS = re.compile(
        r"\b(?:bảo hiểm|sức khỏe|vợ|chồng|người phụ thuộc|con cái|thai sản|nghỉ phép|phép năm|thử việc|thôi việc|hợp đồng lao động|nghỉ ốm)\b",
        re.IGNORECASE,
    )
    if domain and getattr(domain, "domain_name", None) == "accounting":
        query_words = query.split()
        if (
            len(query_words) >= 6
            and not _G10_AMBIGUOUS_REFS.search(query)
            and not _G10_HR_EXCLUSIONS.search(query)
        ):
            return {"intent": "hr_question"}
    # Đây là nhóm thuật ngữ HR chuyên biệt, không mang nghĩa mập mờ và không
    # cần tốn một lượt LLM chỉ để phân loại. Guard tên công ty ở trên vẫn chạy
    # trước để câu hỏi Hybrid của doanh nghiệp khác không lọt vào RAG nội bộ.
    if _EXPLICIT_HYBRID_PATTERN.search(query):
        return {"intent": "hr_question"}

    # Product đã dùng chung RAG pipeline với HR. Giữ nhãn intent legacy
    # `hr_question` để không đổi graph/contract; các feature canonical rõ ràng
    # đi thẳng vào retrieval thay vì bị router HR cũ đánh nhầm là out-of-scope.
    if _EXPLICIT_PRODUCT_KNOWLEDGE_PATTERN.search(query):
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
            temperature=0.0,
            model=settings.router_model or None,
            enable_thinking=False,
        )
    else:
        answer = await acall_llm(_DIRECT_SYSTEM, query, temperature=0.0)
    return {"response": answer.strip()}


async def clarify_node(state: AgentState) -> dict:
    from src.config import get_settings

    settings = get_settings()
    query = state.get("condensed_query") or state.get("query", "")
    question = (
        await acall_llm(
            _CLARIFY_SYSTEM,
            query,
            temperature=0.0,
            model=settings.clarify_model or None,
            enable_thinking=thinking_arg(settings.thinking_clarify),
        )
    ).strip()
    return {"needs_clarification": True, "clarifying_question": question, "response": question}

