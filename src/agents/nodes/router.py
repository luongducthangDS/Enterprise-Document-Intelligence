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

# Fast-path câu chào hỏi thuần túy (≤ 5 từ): trả về greeting ngay mà không tốn LLM call.
_SIMPLE_GREETING_RE = re.compile(
    r"^\s*(?:ok\s+)?(?:xin\s+)?(?:chao|hello|h[ie]+y?|ok|cam\s*on|thanks?|bye|tam\s*biet)"
    r"(?:\s+(?:ban|nhe|anh|chi|em|oi|cac\s*ban|minh|nha|ad|bot|nhieu|roi|a|nhen))*\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# Fast-path câu xã giao hỏi về bot: anchor ^...$ bắt buộc — câu phải TOÀN BỘ là xã giao.
# Bỏ "the nao" đứng độc lập: trong multi-turn có thể là follow-up nghiệp vụ ("Thế nào rồi?").
# Chỉ cho phép "the nao" khi có chủ ngữ rõ ràng về bot ("ban the nao", "bot the nao").
_CHIT_CHAT_RE = re.compile(
    r"^\s*(?:"
    r"(?:(?:ban|anh|chi|em|may|bot)\s+)?"
    r"(?:la ai|ten gi|tu dau|thong minh(?: qu[ae])?|hay day|gioi that|dep qua|co ten khong|(?:co\s+)?khoe(?:\s+khong)?|nghi sao|nghi gi|biet gi khong|co hieu khong|hieu khong)"
    r"|"
    r"(?:ban|anh|chi|em|may|bot)\s+(?:the nao|sao roi|dang lam gi|o dau)"
    r"|"
    r"(?:ban|bot)\s*oi|ok\s+ban"
    r")\s*[?!.]?\s*$",
    re.IGNORECASE,
)

# Fast-path câu hỏi về khả năng của bot.
# Chỉ chứa cụm tường minh hỏi về BOT — KHÔNG có "mau don", "huong dan", "vi du",
# "ho tro gi" vì các cụm này trùng với cách diễn đạt của câu hỏi nghiệp vụ thật.
# Lớp bảo vệ thứ 2: điều kiện AND NOT _has_any_business_signal() được áp dụng
# trực tiếp trong condense_and_route_node (Priority Gate trước Tier 3).
_CAPABILITY_DISCOVERY_RE = re.compile(
    r"(?:"
    r"(?:ban\s+)?(?:co\s+the\s+)?(?:lam|giup|ho\s+tro|xu\s+ly|tra\s+loi)\s+(?:duoc\s+)?(?:nhung\s+)?(?:gi|cai\s+gi)"
    r"|"
    r"(?:ban\s+)?(?:co\s+the\s+)?(?:biet|co\s+kha\s+nang)\s+(?:duoc\s+)?(?:nhung\s+)?(?:gi|cai\s+gi)"
    r"|"
    r"(?:toi|minh|em|nguoi\s+dung)?\s*(?:co\s+the\s+)?(?:hoi|tra\s+cuu)\s+(?:duoc\s+)?(?:nhung\s+)?(?:gi|cai\s+gi)"
    r"|"
    r"cac\s+chu\s+de\s+(?:ban\s+)?(?:ho\s+tro|xu\s+ly|tra\s+loi)"
    r"|"
    r"co\s+the\s+hoi\s+gi"
    r")",
    re.IGNORECASE,
)

# Acronym ngắn (2-4 ký tự) case-sensitive trên query gốc.
# Khôi phục các thuật ngữ viết tắt quan trọng (VAT, API, OT, UI, UX, PIT, KPI...)
# tránh va chạm ngẫu nhiên với âm tiết tiếng Việt sau khi bỏ dấu (vd: VAT vs vất vả, OT vs tốt/một, UI vs vui, DAU vs đâu).
_CASE_SENSITIVE_ACRONYMS_PATTERN = re.compile(
    r"\b(?:VAT|PIT|OT|UI|UX|API|CI/CD|OKR|DAU|MAU|SLA|SDK|DB|SQL|QA|QC)\b"
)

# Whitelist tín hiệu nghiệp vụ (HR / Accounting / Product) đã chuẩn hoá không dấu.
# Sử dụng word-boundary (\b) để khớp chính xác theo ranh giới từ.
#
# Nguyên tắc thêm từ:
#   - Chỉ thêm từ/cụm ĐỦ ĐẶC HIỆU trong ngữ cảnh HR/Accounting/Product.
#   - Tránh từ mang nghĩa kép phổ biến trong tiếng Việt thường ngày:
#       "thue" (thuê/thuế), "chi phi" (chi phí chung), "release/sprint/feature" độc lập.
#   - Ưu tiên CỤM TỪ (>= 2 từ) hoặc từ viết tắt kỹ thuật qua _CASE_SENSITIVE_ACRONYMS_PATTERN.
_BUSINESS_SIGNAL_TERMS: frozenset[str] = frozenset({
    # HR & Company Policies — chính sách, quy chế, thời gian, làm việc
    "chinh sach", "quy dinh", "quy che", "quy trinh", "che do", "quyen loi",
    "nghia vu", "trach nhiem", "huong dan", "bieu mau", "mau don", "noi quy",
    "luong", "thuong", "phep", "nghi phep", "xin nghi", "muon nghi", "don xin nghi",
    "nghi bu", "nghi le", "nghi khong luong", "nghi viec rieng", "nghi thai san", "nghi om",
    "nghi duong suc", "tai nan lao dong", "che do nghi", "thoi gian lam viec", "gio lam viec",
    "ca lam viec", "di muon", "ve som", "cham cong", "lam viec tu xa", "tu xa", "lam tu xa",
    "lam them gio", "lam them", "them gio", "tang ca", "overtime", "wfh", "hybrid",
    "hop dong", "hop dong lao dong", "hdld", "thu viec", "gia han hop dong",
    "bao hiem", "bhxh", "bhyt", "bhtn", "bao hiem suc khoe", "nghi viec", "thoi viec",
    "sa thai", "kpi", "okr", "phong ban", "nhan su", "nhan vien", "quy trinh nhan su",
    "cong tac phi", "tam ung", "hoan ung", "dao tao nhan vien", "tuyen dung",
    "onboarding", "offboarding", "phu cap", "chuc danh", "canh cao ky luat", "ky luat",
    "boi thuong", "xac nhan cong tac", "xac nhan thu nhap", "dong phuc", "the nhan vien",
    "kham suc khoe dinh ky", "kham suc khoe", "phuc loi", "tro cap", "danh gia hieu suat",
    "xep loai nhan su", "nang luc",
    # Accounting & Finance — chi tiêu, hạn mức, mua sắm, duyệt chi, hóa đơn, chứng từ
    "hoa don", "chung tu", "quyet toan", "ke khai thue", "khau tru thue",
    "thu nhap tinh thue", "thu nhap mien thue", "bao cao tai chinh", "cong no",
    "ngan sach", "chi phi cong tac", "khau hao", "tai san co dinh",
    "nhap kho", "xuat kho", "kiem ke", "ton kho", "chiet khau",
    "thanh toan", "thue thu nhap", "thue gtgt", "gia tri gia tang",
    "tai khoan ngan hang", "so quy", "bang ke chi phi", "phieu chi", "phieu thu",
    "han muc", "han muc chi", "han muc chi tieu", "han muc duyet", "han muc duyet chi",
    "chi tieu", "duyet chi", "phe duyet chi", "duyet", "phe duyet", "mua sam", "bao gia", "de nghi thanh toan",
    "de nghi mua hang", "de nghi", "tam ung", "hoan ung", "quyet toan chi phi", "bien ban ban giao",
    "bien ban giao nhan", "bien ban", "tai san", "so tien", "khoan chi", "khoan", "chi phi", "dinh khoan",
    "giay to", "tai lieu", "ho so",
    "so quy", "bang luong", "chuyen khoan", "tien mat", "hop dong kinh te",
    # Product & Engineering — roadmap, sprint, release, UI/UX, features
    "product roadmap", "roadmap", "san pham", "tinh nang", "feature", "sprint planning",
    "sprint review", "sprint", "release schedule", "release", "phat hanh", "ra mat",
    "product backlog", "backlog", "checkout redesign", "checkout flow", "checkout",
    "recommendation system", "notification center", "dark mode", "ui", "ux",
    "subscription plan", "subscription upgrade", "experiment tracking", "technical",
    "ab test", "design system", "deployment pipeline", "staging environment", "trien khai",
    "weekly retention", "monthly retention", "conversion rate", "churn rate", "metric",
    "kien truc", "he thong", "backend", "frontend", "api", "database",
    # Statutory / Legal — các câu hỏi pháp luật quốc gia / điều khoản luật
    "bo luat lao dong", "luat lao dong", "bo luat", "nghi dinh", "thong tu",
    "phap luat", "van ban phap luat", "lao dong", "luat",
})


def _build_business_signal_re(terms: frozenset[str]) -> re.Pattern:
    sorted_terms = sorted(terms, key=len, reverse=True)
    escaped = [re.escape(t) for t in sorted_terms]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


_BUSINESS_SIGNAL_RE: re.Pattern = _build_business_signal_re(_BUSINESS_SIGNAL_TERMS)


def _has_any_business_signal(query: str) -> bool:
    """True nếu query chứa ít nhất 1 tín hiệu nghiệp vụ từ HR / Accounting / Product.

    Kiểm tra 2 tầng:
    1. Case-sensitive acronyms (VAT, PIT, OT, UI, UX, API, CI/CD, OKR, DAU, MAU, SLA...)
       trên query gốc để bảo vệ acronyms ngắn không bị va chạm từ tiếng Việt sau khi bỏ dấu.
    2. Word-boundary regex trên chuỗi đã chuẩn hoá không dấu cho các từ/cụm từ nghiệp vụ.
    """
    if _CASE_SENSITIVE_ACRONYMS_PATTERN.search(query):
        return True
    try:
        from src.domains.accounting.retrieval_ext import _ACCOUNTING_KEYWORD_PATTERN
        if _ACCOUNTING_KEYWORD_PATTERN.search(query):
            return True
    except Exception:
        pass
    normalized = _strip_diacritics(query).lower()
    return bool(_BUSINESS_SIGNAL_RE.search(normalized))


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

- hr_question: nhãn legacy cho mọi câu hỏi tri thức nội bộ HR, Kế toán HOẶC Product đã RÕ RÀNG, có thể trả lời ngay bằng tài liệu chung, không cần tra cứu dữ liệu riêng của người hỏi (vd "Nhân viên có bao nhiêu ngày phép năm?", "Nghỉ phép năm theo quy định được mấy ngày?", "Hạn mức duyệt chi trong quy chế nội bộ thế nào?", "Quy trình tạm ứng công tác phí ra sao?", "Checkout Redesign dự kiến release khi nào?", "Recommendation System đang ở trạng thái nào?").

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

_DIRECT_SYSTEM = """Bạn là trợ lý tri thức nội bộ thân thiện. Trả lời ngắn gọn, tự nhiên cho câu xã giao của nhân viên.

Đáp đúng HÀNH VI GIAO TIẾP của người dùng — đây là điểm quan trọng nhất:
- Người dùng MỞ ĐẦU hội thoại / chào hỏi -> chào lại ngắn gọn, có thể mời họ hỏi về quy trình, quy định và chính sách nội bộ.
- Người dùng CẢM ƠN hoặc xác nhận đã hiểu -> đáp lại lời cảm ơn/xác nhận đó. TUYỆT ĐỐI KHÔNG mở đầu bằng lời chào và KHÔNG tự giới thiệu lại — hội thoại đang diễn ra, không phải bắt đầu.
- Người dùng TẠM BIỆT -> chào tạm biệt ngắn gọn.
- Người dùng hỏi bạn là ai / giúp được gì -> giới thiệu ngắn về phạm vi hỗ trợ.

KHÔNG nêu số liệu, điều khoản hay quy định chính sách nào ở bước này, trừ khi chính người dùng đã nhắc tới.

Ví dụ đối chiếu:
- "Chào bạn" -> "Chào bạn! Mình có thể hỗ trợ gì về tài liệu nội bộ?"
- "Ok cảm ơn nhé" -> "Không có gì, khi nào cần bạn cứ hỏi mình nhé."
- "Bye nhé" -> "Chào bạn, hẹn gặp lại!"

Chỉ trả về câu trả lời, không thêm lời dẫn."""

_CLARIFY_SYSTEM = """Câu hỏi của nhân viên về tài liệu nội bộ nhưng còn mập mờ, có thể hiểu theo nhiều nghĩa. Hãy đặt lại ĐÚNG 1 câu hỏi làm rõ, ngắn gọn, lịch sự, giúp xác định đúng ý người hỏi (vd hỏi rõ là nghỉ phép năm, nghỉ ốm hay nghỉ việc hẳn). Chỉ trả về câu hỏi làm rõ, không thêm lời dẫn."""


def _format_history_text(
    history: list[dict],
    max_turns: int,
    max_content_chars: int = 2000,
    injection_hits: list[str] | None = None,
) -> str:
    from src.agents.guardrails import strip_injection

    recent = history[-max_turns:] if max_turns > 0 else history
    lines = []
    for turn in recent:
        role = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        content = str(turn.get("content", ""))[:max_content_chars]
        content, hits = strip_injection(content)
        if hits and injection_hits is not None:
            injection_hits.extend(hits)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _get_unified_condense_router_system() -> str:
    from src.config import get_settings
    internal_names = ", ".join(get_settings().internal_company_names)
    return f"""Bạn là bộ điều hướng ý định và tổng hợp ngữ cảnh hội thoại cho trợ lý tri thức nội bộ ({internal_names}).

Nhiệm vụ:
1. Xử lý ngữ cảnh (Condense & Coreference Resolution):
   - Đọc lịch sử hội thoại (nếu có trong <HISTORY>) và câu hỏi hiện tại trong <CURRENT_QUERY>, viết lại thành `condensed_query` độc lập mang đầy đủ ngữ cảnh (thay thế đại từ mơ hồ, giữ nguyên dữ kiện định lượng). Nếu không có lịch sử hoặc câu hỏi đã độc lập, giữ nguyên câu hỏi.
   - QUY TẮC GIẢI MÃ ĐẠI TỪ (COREF - BẮT BUỘC): Nếu câu hỏi hiện tại chứa các đại từ hoặc cụm chỉ định như: "này", "đó", "kia", "vừa rồi", "trên", "dưới", "giấy tờ này", "hóa đơn đó", "khoản này", "chứng từ vừa rồi", "tài liệu này", "hợp đồng đó", "quy định này", "quy chế trên", "người này", "chi phí đó"...
     → Tìm thực thể cụ thể gần nhất trong <HISTORY> (mã chứng từ, tên tài liệu, số hóa đơn, số biên bản, tên chính sách, khoản tiền, số ngày, tên người/chức danh...) và THAY THẾ đại từ bằng thực thể đó trong `condensed_query`.
     → Khi đã xác định được thực thể từ <HISTORY>, câu hỏi này KHÔNG PHẢI là câu hỏi thiếu thông tin (vì đã có ngữ cảnh nối tiếp), intent PHẢI là "hr_question" (hoặc "pure_statutory" / "out_of_scope_or_personal" nếu bản thân câu hỏi yêu cầu điều đó), TUYỆT ĐỐI KHÔNG phân loại "ambiguous" hay hỏi lại làm rõ.
     → CHỈ phân loại "ambiguous" khi câu hỏi mơ hồ, thiếu thông tin VÀ trong <HISTORY> hoàn toàn không có thực thể/ngữ cảnh nào để suy luận.

2. Phân loại ý định (Intent): Phân loại câu hỏi vào ĐÚNG 1 trong 5 nhóm sau:
   - "greeting": Chào hỏi, cảm ơn, tạm biệt, xã giao (vd "chào bạn", "cảm ơn nhé").
   - "hr_question": Câu hỏi chính sách, quy chế, quy trình nội bộ ({internal_names}), hoặc câu hỏi tra cứu tài liệu/chứng từ/hóa đơn/quyết định cụ thể của công ty đã rõ ràng hoặc đã được bổ sung ngữ cảnh từ lịch sử, có thể trả lời bằng tài liệu chung (vd "Thời gian thử việc tối đa là bao lâu?", "Checkout Redesign release khi nào?", "Giấy tờ BBGN-01/2026 có đúng quy trình không?").
   - "ambiguous": Câu hỏi thiếu thông tin cụ thể hoặc đa nghĩa mà <HISTORY> không giải quyết được, cần hỏi lại để làm rõ (vd "Tôi còn bao nhiêu ngày phép?", "Bao giờ thì thưởng về?"). Kèm theo `clarifying_question` là 1 câu hỏi làm rõ ngắn gọn, lịch sự.
   - "pure_statutory": Câu hỏi hỏi thẳng văn bản pháp luật/nghị định quốc gia hoặc thủ tục với cơ quan nhà nước, không hỏi chính sách công ty áp dụng ra sao (vd "Điều 112 Bộ luật Lao động quy định nghỉ lễ thế nào?").
   - "out_of_scope_or_personal": Tra cứu dữ liệu cá nhân thực tế (đơn của tôi đã duyệt chưa, số dư lương tháng này...) hoặc hỏi về công ty khác không phải {internal_names}, hoặc ngoài phạm vi công việc.

TRẢ VỀ DUY NHẤT 1 ĐỐI TƯỢNG JSON (KHÔNG KÈM TEXT NÀO KHÁC):
{{
  "condensed_query": "câu hỏi độc lập mang đủ ngữ cảnh",
  "intent": "greeting" | "hr_question" | "ambiguous" | "pure_statutory" | "out_of_scope_or_personal",
  "clarifying_question": "câu hỏi làm rõ ngắn gọn nếu intent=ambiguous, ngược lại để null"
}}"""


async def condense_and_route_node(state: AgentState) -> dict:
    """Unified node: gộp xử lý ngữ cảnh lịch sử (Condense) và phân loại ý định (Router)
    vào 1 lượt gọi LLM duy nhất (gpt-4o-mini) với đầu ra JSON định dạng có cấu trúc.
    """
    from src.agents.guardrails import detect_injection
    from src.config import get_settings

    node_start_t = time.perf_counter()
    query = state.get("query") or state.get("condensed_query") or ""
    history = state.get("history") or []
    settings = get_settings()

    injection_hits: list[str] = []
    if settings.guardrail_injection_enabled:
        injection_hits.extend(detect_injection(query))

    # --- PRIORITY GATE: Kiểm tra business signal 1 lần duy nhất, tái dùng ở bước whitelist ---
    # Nếu query có tín hiệu nghiệp vụ hoặc đang trong hội thoại có lịch sử → bỏ qua toàn bộ Tier 1/2 (chit-chat/capability),
    # tránh "Cho tôi mẫu đơn nghỉ phép" bị Capability tier nuốt mất hoặc câu follow-up bị chặn oan.
    _has_signal = _has_any_business_signal(query) or bool(history)

    if not _has_signal:
        # Tier 1 — Fast-path câu chào hỏi thuần túy (≤ 5 từ)
        if _SIMPLE_GREETING_RE.match(_strip_diacritics(query).lower()):
            total_router_ms = round((time.perf_counter() - node_start_t) * 1000)
            print(f"[TIMING] [condense_and_route] {total_router_ms}ms (fast_greeting) | intent=greeting")
            return {
                "condensed_query": query,
                "intent": "greeting",
                "guardrail_injection_detected": bool(injection_hits),
            }

        # Tier 2 — Chit-chat xã giao hỏi về bot (anchor ^...$, câu phải TOÀN BỘ là xã giao)
        if _CHIT_CHAT_RE.match(_strip_diacritics(query).lower()):
            total_router_ms = round((time.perf_counter() - node_start_t) * 1000)
            print(f"[TIMING] [condense_and_route] {total_router_ms}ms (fast_chit_chat) | intent=greeting")
            return {
                "condensed_query": query,
                "intent": "greeting",
                "guardrail_injection_detected": bool(injection_hits),
            }

        # Tier 3 — Capability Discovery (≤ 8 từ + không có business signal đã kiểm tra ở trên)
        _normalized = _strip_diacritics(query).lower()
        if len(query.split()) <= 8 and _CAPABILITY_DISCOVERY_RE.search(_normalized):
            total_router_ms = round((time.perf_counter() - node_start_t) * 1000)
            print(f"[TIMING] [condense_and_route] {total_router_ms}ms (capability_discovery) | intent=capability_discovery")
            return {
                "condensed_query": query,
                "intent": "capability_discovery",
                "guardrail_injection_detected": bool(injection_hits),
            }

    # Guard công ty đối thủ
    if _mentions_competitor_company(query):
        return {
            "condensed_query": query,
            "intent": "out_of_scope_or_personal",
            "guardrail_injection_detected": bool(injection_hits),
        }

    # Guard dữ liệu cá nhân theo Domain (G5)
    domain = get_conversation_domain(query, state.get("category"), state.get("history"))
    if domain:
        is_personal, reason_code = domain.check_personal_data_query(query)
        if is_personal:
            return {
                "condensed_query": query,
                "intent": "out_of_scope_or_personal",
                "escalate_reason": reason_code or "domain_personal_data_detected",
                "verifier_called": False,
                "guardrail_injection_detected": bool(injection_hits),
            }

    # Whitelist Guard: kiểm tra tín hiệu nghiệp vụ (HR / Accounting / Product)
    # _has_signal đã được tính ở Priority Gate trên, tái dùng không tính lại.
    if not _has_signal:
        _shadow = settings.whitelist_guard_shadow
        print(
            "[whitelist_guard] "
            + json.dumps(
                {"shadow": _shadow, "would_block": True, "query_prefix": query[:80]},
                ensure_ascii=False,
            )
        )
        if not _shadow:
            total_router_ms = round((time.perf_counter() - node_start_t) * 1000)
            print(f"[TIMING] [condense_and_route] {total_router_ms}ms (whitelist_blocked) | intent=out_of_scope_or_personal")
            return {
                "condensed_query": query,
                "intent": "out_of_scope_or_personal",
                "verifier_called": False,
                "guardrail_injection_detected": bool(injection_hits),
                "whitelist_blocked": True,
            }

    # G10: Domain Early-Pass kế toán
    _g10_ambiguous_refs = re.compile(r"\b(n[aà]y|[đd][oó]|kia|v[uừ]a r[oồ]i|tr[eê]n|d[uư][oớ]i)\b", re.IGNORECASE)
    _g10_hr_exclusions = re.compile(
        r"\b(?:bảo hiểm|sức khỏe|vợ|chồng|người phụ thuộc|con cái|thai sản|nghỉ phép|phép năm|thử việc|thôi việc|hợp đồng lao động|nghỉ ốm)\b",
        re.IGNORECASE,
    )
    if domain and getattr(domain, "domain_name", None) == "accounting" and not history:
        query_words = query.split()
        if len(query_words) >= 6 and not _g10_ambiguous_refs.search(query) and not _g10_hr_exclusions.search(query):
            return {
                "condensed_query": query,
                "intent": "hr_question",
                "guardrail_injection_detected": bool(injection_hits),
            }

    # Heuristics: Hybrid policy / Product knowledge
    if not history and (_EXPLICIT_HYBRID_PATTERN.search(query) or _EXPLICIT_PRODUCT_KNOWLEDGE_PATTERN.search(query)):
        return {
            "condensed_query": query,
            "intent": "hr_question",
            "guardrail_injection_detected": bool(injection_hits),
        }

    # Chuẩn bị Prompt
    history_text = _format_history_text(
        history,
        settings.max_history_turns,
        settings.max_history_content_chars,
        injection_hits,
    ) if history else ""

    if history_text:
        user_prompt = f"<HISTORY>\n{history_text}\n</HISTORY>\n\n<CURRENT_QUERY>{query}</CURRENT_QUERY>"
    else:
        user_prompt = f"<CURRENT_QUERY>{query}</CURRENT_QUERY>"

    model = settings.router_model or None
    t_start = time.perf_counter()
    raw = await acall_llm(
        _get_unified_condense_router_system(),
        user_prompt,
        temperature=0.0,
        model=model,
        enable_thinking=thinking_arg(settings.thinking_router),
    )
    llm_ms = round((time.perf_counter() - t_start) * 1000)

    # Parse JSON output có fallback an toàn
    condensed_query = query
    intent_str = "hr_question"
    clarifying_q = None

    clean_raw = raw.strip()
    if clean_raw.startswith("```json"):
        clean_raw = clean_raw[7:]
    if clean_raw.startswith("```"):
        clean_raw = clean_raw[3:]
    if clean_raw.endswith("```"):
        clean_raw = clean_raw[:-3]

    try:
        data = json.loads(clean_raw.strip())
        if isinstance(data, dict):
            condensed_query = str(data.get("condensed_query") or query).strip()
            intent_str = str(data.get("intent") or "").strip().lower()
            clarifying_q = data.get("clarifying_question")
    except Exception:
        match = _INTENT_PATTERN.search(raw.strip().lower())
        intent_str = match.group(0) if match else "hr_question"

    valid_intents = {"greeting", "capability_discovery", "hr_question", "ambiguous", "out_of_scope_or_personal", "pure_statutory"}
    if intent_str not in valid_intents:
        match = _INTENT_PATTERN.search(intent_str)
        intent: Intent = match.group(0) if match else "hr_question"  # type: ignore[assignment]
    else:
        intent: Intent = intent_str  # type: ignore[assignment]

    result: dict = {
        "condensed_query": condensed_query or query,
        "intent": intent,
        "guardrail_injection_detected": bool(injection_hits) or state.get("guardrail_injection_detected", False),
    }
    if not _has_signal:
        result["whitelist_shadow_would_block"] = True

    if intent == "ambiguous" and clarifying_q:
        result["needs_clarification"] = True
        result["clarifying_question"] = clarifying_q
        result["response"] = clarifying_q

    if intent == "out_of_scope_or_personal" and settings.escalation_guard_enabled:
        guard_res = await _guard_escalation(condensed_query, model)
        result.update(guard_res)

    total_router_ms = round((time.perf_counter() - node_start_t) * 1000)
    print(f"[TIMING] [condense_and_route] {total_router_ms}ms (LLM: {llm_ms}ms, model: {model or 'default'}) | intent={intent}")

    return result


async def router_node(state: AgentState) -> dict:
    """Tương thích ngược: router_node ủy thác sang condense_and_route_node."""
    return await condense_and_route_node(state)


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

    0. Tier-0 (Pre-filter): Không có bất kỳ tín hiệu nghiệp vụ nào (HR/Accounting/Product) -> escalate luôn.
       NOTE lifecycle: Chỉ có tác dụng thực sự trong giai đoạn whitelist_guard_shadow=True.
       Sau khi whitelist_guard_shadow=False, mọi câu đến đây chắc chắn đã có business signal
       (nếu không đã bị chặn từ trước). Giữ lại làm safety-net phòng ngừa edge-case;
       có thể dọn dẹp sau khi Phase 3 go-live ổn định >= 2 tuần (TODO: cleanup post-whitelist-live).
    1. Không có dấu hiệu hỏi quy định chung -> escalate luôn, không tốn LLM.
       Câu personal thật ("Đơn của tôi duyệt chưa?") dừng ở đây.
    2. Khớp heuristic personal rõ ràng (_requires_personal_data: "của tôi" +
       lương/phép/đơn/hợp đồng...) -> escalate luôn. "Tôi còn bao nhiêu ngày
       phép?" dừng ở đây, không tốn LLM dù câu có chữ "bao nhiêu".
    3. Còn lại là ca thật sự khó (vừa nhắc bản thân vừa hỏi quy định) -> mới
       trả tiền cho 1 lần gọi LLM CÓ thinking, với prompt hẹp chỉ 2 lớp.

    Rule ở tầng 0-2 chỉ đóng vai circuit breaker (quyết định CÓ verify hay
    không), không tự đổi intent — quyết định đổi intent luôn do LLM verifier.

    Trả về dict để mang kèm telemetry (verifier_called/changed_route/latency):
    thiết kế này chỉ đúng chừng nào verifier còn SỬA được route đủ thường xuyên.
    Biết `useful_rate` tụt là điều kiện để mở task thêm pre-filter — xem
    AgentState.verifier_* để biết cách tính từ log.
    """
    # Tier-0 (Pre-filter): thiếu tín hiệu nghiệp vụ -> dừng ngay không gọi verifier
    if not _has_any_business_signal(query):
        return {"intent": "out_of_scope_or_personal", "verifier_called": False}

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
    "Chào bạn, mình là trợ lý tri thức nội bộ. Bạn cần tra cứu quy trình, quy định hay "
    "chính sách nội bộ (nghỉ phép, lương thưởng, bảo hiểm, tuyển dụng, quy trình vận hành...) "
    "thì cứ nhắn nhé."
)


async def direct_node(state: AgentState) -> dict:
    from src.config import get_settings

    settings = get_settings()
    if settings.direct_mode == "template":
        return {"response": _DIRECT_TEMPLATE}

    query = state.get("condensed_query") or state.get("query", "")
    try:
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
    except Exception as e:
        print(f"[direct_node] LLM call failed ({e}), falling back to default template")
        return {"response": _DIRECT_TEMPLATE}


async def clarify_node(state: AgentState) -> dict:
    existing_q = state.get("clarifying_question")
    if existing_q:
        return {"needs_clarification": True, "clarifying_question": existing_q, "response": existing_q}

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


# Template cố định cho intent=capability_discovery — KHÔNG gọi LLM, không có rủi ro
# bịa số liệu chính sách. Mô tả 3 nhóm tài liệu đã được nạp vào hệ thống.
_CAPABILITY_TEMPLATE = (
    "Mình là trợ lý tri thức nội bộ, có thể hỗ trợ bạn tra cứu:\n\n"
    "🏢 **HR & Nhân sự** — Nghỉ phép, lương thưởng, bảo hiểm, tuyển dụng, onboarding/offboarding\n"
    "📊 **Kế toán & Tài chính** — Hóa đơn, chứng từ, quyết toán, khai thuế, chi phí công tác\n"
    "🚀 **Product & Tech** — Roadmap, sprint planning, deployment, release schedule\n\n"
    "Bạn có thể hỏi thẳng hoặc chọn một gợi ý bên dưới nhé."
)

_QUICK_PROMPTS = [
    "Nhân viên có bao nhiêu ngày phép năm?",
    "Quy định làm việc hybrid như thế nào?",
    "Quy định tạm ứng công tác phí?",
]


async def capability_node(state: AgentState) -> dict:
    """Terminal node cho intent=capability_discovery.

    Trả về template cố định mô tả phạm vi hỗ trợ + danh sách quick_prompts để
    frontend render thành chip/button. Không gọi LLM, không truy vấn RAG —
    latency ~0ms.
    """
    return {
        "response": _CAPABILITY_TEMPLATE,
        "quick_prompts": _QUICK_PROMPTS,
    }
