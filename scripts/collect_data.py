#!/usr/bin/env python3
"""Sinh synthetic data qua GLM-5.2 (FPT.AI Marketplace) cho các phần chưa tìm được
nguồn công khai đạt chất lượng: chính sách WFH/hybrid, chính sách đào tạo & phát
triển, và bộ câu hỏi-đáp eval.

Chạy: python scripts/collect_data.py             # sinh cả 4 policy doc + eval set
      python scripts/collect_data.py --eval-only  # chỉ sinh lại eval set (không đụng policy doc đã có)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.services.fpt_client import chat_completion

MODEL = "GLM-5.2"

STYLE_REFERENCE_PATH = "data/raw/compensation_policies/01_chinh-sach-lam-them-gio-OT.md"

# Mỗi category liệt kê >=1 file nguồn — dùng nhiều nguồn/category để câu hỏi
# eval bao phủ nhiều tài liệu thật thay vì chỉ lặp lại 1 file (như bản 45 câu
# trước). Category chỉ có 1 nguồn thật sự (leave_policies) liệt kê lặp lại
# cùng path — read_excerpt_window() sẽ tự lấy 2 cửa sổ khác nhau trong cùng
# file thay vì gửi trùng 1 đoạn trích cho GLM.
EVAL_EXCERPT_SOURCES = {
    "compensation_policies": [
        "data/raw/compensation_policies/01_chinh-sach-lam-them-gio-OT.md",
        "data/raw/compensation_policies/base_quy-che-cong-tac-phi-va-phu-cap.md",
    ],
    "recruitment_policies": [
        "data/raw/recruitment_policies/02_quy-trinh-tuyen-dung.md",
        "data/processed/842059170-18-Nguyễn-Đinh-Hải-Lam-Quy-Trinh-Tuyển-Dụng-Chung-Của-Vingroup.md",
    ],
    "onboarding_offboarding": [
        "data/raw/onboarding_offboarding/03_quy-trinh-onboarding.md",
        "data/raw/onboarding_offboarding/04_quy-trinh-offboarding.md",
    ],
    "leave_policies": [
        "data/raw/leave_policies/07_chinh-sach-nghi-phep.md",
        "data/raw/leave_policies/07_chinh-sach-nghi-phep.md",
    ],
    "government_legal": [
        "data/processed/bộ luật lao động.md",
        "data/processed/luat_bao_hiem_xa_hoi_41_2024_qh15.md",
    ],
    "company_regulations": [
        "data/processed/1050517962-VF-I-4-1-001-V5-Quy-định-nội-bộ-Cong-ty-VinFast-08-08-2019.md",
        "data/raw/company_regulations/mau_quy-che-danh-gia-hieu-suat-kpi.md",
    ],
}

QUESTIONS_PER_CATEGORY = 10
OUT_OF_SCOPE_N = 15
AMBIGUOUS_N = 15
COMPETITOR_N = 10


def call_glm(system: str, user: str, temperature: float = 0.5) -> str:
    settings = get_settings()
    return chat_completion(
        system,
        user,
        model=MODEL,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        temperature=temperature,
    )


def strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown|md|json)?\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()


def parse_json_array(text: str) -> list:
    text = strip_code_fence(text)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def generate_policy_doc(title: str, document_code: str, legal_basis: str, extra_instruction: str, out_path: str) -> None:
    with open(STYLE_REFERENCE_PATH, encoding="utf-8") as f:
        style_ref = f.read()

    system = (
        "Bạn là chuyên viên C&B/HR soạn thảo chính sách nội bộ doanh nghiệp Việt Nam. "
        "Viết đúng văn phong hành chính, có căn cứ pháp luật cụ thể (trích Điều, Khoản), "
        "và PHẢI theo đúng định dạng frontmatter + cấu trúc markdown như tài liệu mẫu."
    )
    user = f"""Đây là 1 tài liệu chính sách mẫu đã có, dùng để bạn theo đúng văn phong, cấu trúc, và LUÔN dùng công ty giả định "Công ty Cổ phần Tập đoàn V-NOVA" (KHÔNG dùng tên công ty thật nào khác, kể cả Vingroup/VinFast):

---MẪU THAM KHẢO---
{style_ref}
---HẾT MẪU---

Viết một tài liệu MỚI với thông số:
- title: {title}
- document_code: {document_code}
- legal_basis: {legal_basis}
- Yêu cầu nội dung riêng: {extra_instruction}

Trả về ĐÚNG format: frontmatter YAML (document_type, title, company, document_code, version: 1.0, effective_date: 2025-01-01, owner: Phòng Nhân sự, data_label giống mẫu, legal_basis) + nội dung markdown đầy đủ chi tiết (có số liệu cụ thể, quy trình, điều khoản rõ ràng), có banner SYNTHETIC DATA như mẫu. Chỉ trả về nội dung file markdown, không thêm giải thích ngoài lề."""

    content = strip_code_fence(call_glm(system, user, temperature=0.5))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Đã tạo: {out_path} ({len(content)} chars)")


def read_excerpt_window(path: str, window_index: int, total_windows: int, window_chars: int = 4000) -> str:
    """Đọc 1 cửa sổ window_chars ký tự của file, trải đều theo total_windows để
    câu hỏi sinh ra bao phủ nhiều phần khác nhau của tài liệu (đầu/giữa/cuối)
    thay vì luôn lấy y hệt window_chars ký tự đầu tiên mỗi lần gọi cùng 1 file."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if len(content) <= window_chars or total_windows <= 1:
        return content[:window_chars]
    step = max(1, (len(content) - window_chars) // (total_windows - 1))
    start = min(window_index * step, max(0, len(content) - window_chars))
    return content[start:start + window_chars]


def generate_qa_for_category(category: str, excerpt: str, n: int = 5) -> list:
    system = (
        "Bạn tạo bộ câu hỏi-đáp (Q&A) để eval RAG chatbot HR nội bộ. Chatbot này CHỈ phục vụ "
        "NHÂN VIÊN ĐANG LÀM VIỆC tại công ty và HR Admin — KHÔNG phục vụ ứng viên/người ngoài "
        "đang tìm việc. Câu hỏi phải là câu một nhân viên nội bộ hoặc HR Admin thực sự sẽ hỏi "
        "(tự nhiên, đời thường, tiếng Việt). TUYỆT ĐỐI KHÔNG được viết theo giọng ứng viên đang "
        "ứng tuyển/nộp hồ sơ xin việc (vd KHÔNG viết kiểu 'mình muốn ứng tuyển vào...', 'sau khi "
        "nộp CV...', 'em vừa nộp hồ sơ...') — kể cả khi đoạn trích mô tả quy trình tuyển dụng "
        "hướng tới ứng viên bên ngoài, hãy chuyển góc nhìn sang nhân viên/HR đang VẬN HÀNH hoặc "
        "TƯ VẤN quy trình đó (vd 'quy trình tuyển dụng của công ty có mấy vòng?', 'nếu mình giới "
        "thiệu bạn ứng tuyển thì họ cần nộp hồ sơ ra sao?'). Câu trả lời phải NGẮN GỌN và CHỈ dựa "
        "vào đoạn trích cho sẵn — không bịa thêm số liệu không có trong đoạn trích."
    )
    user = f"""Đoạn trích tài liệu (category: {category}):
---
{excerpt[:4000]}
---
Tạo {n} cặp câu hỏi-đáp bằng tiếng Việt, dựa HOÀN TOÀN vào đoạn trích trên, theo đúng góc nhìn nhân viên nội bộ/HR Admin đã nêu ở trên (không phải góc nhìn ứng viên). Trả về JSON array, mỗi phần tử dạng {{"question": "...", "expected_answer": "...", "ground_truth_context": "trích NGUYÊN VĂN câu/đoạn trong văn bản gốc làm căn cứ cho câu trả lời"}}. Chỉ trả JSON, không giải thích thêm."""

    items = parse_json_array(call_glm(system, user, temperature=0.6))
    for item in items:
        item["category"] = category
        item["type"] = "in_scope"
    return items


def generate_ambiguous_qa(n: int = AMBIGUOUS_N) -> list:
    system = (
        "Bạn tạo câu hỏi MẬP MỜ (ambiguous) để test xem chatbot HR có biết chủ động hỏi lại "
        "làm rõ (clarifying question) thay vì đoán bừa ý người dùng hay không."
    )
    user = f"""Tạo {n} câu hỏi tiếng Việt về chủ đề HR (nghỉ phép, lương thưởng, phúc lợi, hợp đồng...) "
mà một từ/cụm từ trong câu có THỂ hiểu theo nhiều nghĩa khác nhau, khiến chatbot không thể trả lời "
chính xác nếu không hỏi lại. Ví dụ: "Một năm tôi được nghỉ mấy ngày?" (mập mờ giữa nghỉ phép năm/nghỉ ốm/nghỉ thai sản).
Trả về JSON array, mỗi phần tử dạng {{"question": "...", "ambiguity_reason": "vì sao câu hỏi mập mờ", "expected_clarifying_question": "câu hỏi làm rõ agent nên hỏi lại"}}. Chỉ trả JSON."""

    items = parse_json_array(call_glm(system, user, temperature=0.7))
    for item in items:
        item["category"] = "ambiguous"
        item["type"] = "ambiguous"
        item["expected_answer"] = None
        item["expected_behavior"] = "ask_clarification"
    return items


def generate_competitor_qa(n: int = COMPETITOR_N) -> list:
    system = (
        "Bạn tạo câu hỏi để test chatbot HR nội bộ có từ chối đúng cách khi bị hỏi về chính sách "
        "của CÔNG TY KHÁC (đối thủ/không liên quan) — không được bịa số liệu của công ty khác."
    )
    user = f"""Tạo {n} câu hỏi tiếng Việt, mỗi câu hỏi về chính sách/đãi ngộ nhân sự của MỘT CÔNG TY "
CỤ THỂ KHÁC (không phải công ty đang dùng chatbot này) — ví dụ hỏi mức thưởng Tết, lương, phúc lợi "
của một công ty có thật/tên riêng. Trả về JSON array, mỗi phần tử dạng {{"question": "...", "reason": "vì sao chatbot không thể/không nên trả lời câu này"}}. Chỉ trả JSON."""

    items = parse_json_array(call_glm(system, user, temperature=0.7))
    for item in items:
        item["category"] = "out_of_scope"
        item["type"] = "competitor_comparison"
        item["expected_answer"] = None
        item["expected_behavior"] = "decline_politely"
    return items


def generate_out_of_scope_qa(n: int = OUT_OF_SCOPE_N) -> list:
    system = (
        "Bạn tạo câu hỏi để test một chatbot HR nội bộ (chỉ trả lời dựa trên tài liệu chính "
        "sách công ty + luật lao động Việt Nam) có biết escalate/từ chối đúng cách khi KHÔNG "
        "đủ dữ liệu để trả lời hay không."
    )
    user = f"""Tạo {n} câu hỏi tiếng Việt, mỗi câu thuộc 1 trong 2 loại:
(a) hỏi thông tin cá nhân/nội bộ cụ thể mà tài liệu chính sách chung không thể có (vd: lương cụ thể của một người, trạng thái đơn xin nghỉ phép của bản thân, số dư phép còn lại);
(b) hỏi hoàn toàn ngoài phạm vi HR (vd: hỏi về thời tiết, hỏi kỹ thuật lập trình).
Trả về JSON array, mỗi phần tử dạng {{"question": "...", "reason": "vì sao câu này ngoài phạm vi"}}. Chỉ trả JSON."""

    items = parse_json_array(call_glm(system, user, temperature=0.7))
    for item in items:
        item["category"] = "out_of_scope"
        item["type"] = "out_of_scope"
        item["expected_answer"] = None
        item["expected_behavior"] = "escalate_to_ticket"
    return items


def generate_in_scope_for_category(category: str) -> list:
    """Sinh đủ QUESTIONS_PER_CATEGORY câu in_scope cho 1 category, chia đều qua
    các nguồn khả dụng của category đó (xem EVAL_EXCERPT_SOURCES)."""
    paths = EVAL_EXCERPT_SOURCES[category]
    available = [p for p in paths if os.path.exists(p)]
    missing = [p for p in paths if p not in available]
    for p in missing:
        print(f"[skip nguồn] {category}: không tìm thấy {p}")
    if not available:
        print(f"[skip category] {category}: không còn nguồn nào")
        return []

    per_source, remainder = divmod(QUESTIONS_PER_CATEGORY, len(available))
    occurrence_seen: dict[str, int] = {}
    occurrence_total: dict[str, int] = {}
    for p in available:
        occurrence_total[p] = occurrence_total.get(p, 0) + 1

    items: list = []
    for i, path in enumerate(available):
        window_index = occurrence_seen.get(path, 0)
        occurrence_seen[path] = window_index + 1
        excerpt = read_excerpt_window(path, window_index, occurrence_total[path])
        n = per_source + (1 if i < remainder else 0)
        batch = generate_qa_for_category(category, excerpt, n=n)
        items.extend(batch)
        print(f"[{category}] +{len(batch)} câu hỏi (nguồn: {os.path.basename(path)}, window {window_index})")
    return items


def regenerate_category(out_path: str, category: str) -> None:
    """Sinh lại RIÊNG các câu in_scope của 1 category, giữ nguyên toàn bộ câu
    khác trong file (dùng khi phát hiện 1 category bị lệch chất lượng, tránh
    tốn API + tránh xáo trộn các category đã ổn)."""
    if category not in EVAL_EXCERPT_SOURCES:
        raise ValueError(f"Category không hợp lệ: {category}. Chọn 1 trong {list(EVAL_EXCERPT_SOURCES)}")

    with open(out_path, encoding="utf-8") as f:
        existing = json.load(f)

    old_count = sum(1 for it in existing if it.get("category") == category and it.get("type") == "in_scope")
    if old_count == 0:
        raise ValueError(f"Không tìm thấy câu in_scope nào của category '{category}' trong {out_path}")

    new_items = generate_in_scope_for_category(category)
    if len(new_items) != old_count:
        raise ValueError(
            f"Số câu mới ({len(new_items)}) khác số câu cũ ({old_count}) — dừng lại, không tự ghi đè "
            f"để tránh làm lệch id các câu khác."
        )

    result = []
    inserted = False
    for it in existing:
        if it.get("category") == category and it.get("type") == "in_scope":
            if not inserted:
                result.extend(new_items)
                inserted = True
            continue
        result.append(it)

    for i, item in enumerate(result, start=1):
        item["id"] = f"qa_{i:03d}"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Đã sinh lại {len(new_items)} câu cho category '{category}' — tổng file vẫn {len(result)} câu.")


def generate_eval_set(out_path: str) -> None:
    all_items = []
    for category in EVAL_EXCERPT_SOURCES:
        all_items.extend(generate_in_scope_for_category(category))

    oos_items = generate_out_of_scope_qa()
    all_items.extend(oos_items)
    print(f"[out_of_scope] +{len(oos_items)} câu hỏi")

    amb_items = generate_ambiguous_qa()
    all_items.extend(amb_items)
    print(f"[ambiguous] +{len(amb_items)} câu hỏi")

    comp_items = generate_competitor_qa()
    all_items.extend(comp_items)
    print(f"[competitor_comparison] +{len(comp_items)} câu hỏi")

    for i, item in enumerate(all_items, start=1):
        item["id"] = f"qa_{i:03d}"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"Đã tạo: {out_path} ({len(all_items)} câu hỏi)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-only", action="store_true", help="Chỉ sinh lại eval set, không đụng 4 policy doc đã có")
    parser.add_argument(
        "--category",
        choices=list(EVAL_EXCERPT_SOURCES),
        help="Chỉ sinh lại các câu in_scope của 1 category, giữ nguyên toàn bộ câu khác trong eval set",
    )
    args = parser.parse_args()

    if args.category:
        regenerate_category("eval/datasets/qa_eval_set.json", args.category)
        return

    if args.eval_only:
        generate_eval_set("eval/datasets/qa_eval_set.json")
        return

    generate_policy_doc(
        title="Chính sách Làm việc từ xa / Hybrid Working",
        document_code="HR-POL-WFH-2025",
        legal_basis="Bộ luật Lao động 2019 (Điều 90, 105 — thời giờ làm việc); Nghị định 145/2020/NĐ-CP",
        extra_instruction=(
            "Nêu rõ: đối tượng/vị trí được áp dụng, số ngày WFH tối đa/tuần (mô hình hybrid "
            "kiểu 3-2), quy trình đăng ký/phê duyệt, yêu cầu về thiết bị và bảo mật dữ liệu khi "
            "làm việc từ xa, cách chấm công/theo dõi hiệu suất, và trường hợp bị thu hồi quyền WFH."
        ),
        out_path="data/raw/company_regulations/05_chinh-sach-lam-viec-tu-xa.md",
    )

    generate_policy_doc(
        title="Chính sách Đào tạo & Phát triển nhân viên",
        document_code="HR-POL-TRAIN-2025",
        legal_basis="Bộ luật Lao động 2019 (Điều 60, 61, 62 — học nghề, đào tạo, hợp đồng đào tạo nghề)",
        extra_instruction=(
            "Nêu rõ: các loại hình đào tạo (hội nhập, chuyên môn, kỹ năng mềm, quản lý), ngân "
            "sách/số giờ đào tạo tối thiểu mỗi năm theo cấp bậc, quy trình đề xuất & phê duyệt "
            "khóa học, điều khoản cam kết làm việc sau đào tạo dài hạn/chi phí cao (đền bù chi "
            "phí nếu nghỉ việc sớm), và cách đánh giá hiệu quả đào tạo."
        ),
        out_path="data/raw/company_regulations/06_chinh-sach-dao-tao-phat-trien.md",
    )

    generate_policy_doc(
        title="Chính sách Nghỉ phép",
        document_code="HR-POL-LEAVE-2025",
        legal_basis="Bộ luật Lao động 2019 (Điều 113 — nghỉ hằng năm; Điều 115 — nghỉ việc riêng; Điều 116 — nghỉ không hưởng lương; Điều 139 — nghỉ thai sản)",
        extra_instruction=(
            "Nêu rõ: số ngày phép năm theo thâm niên (tối thiểu 12 ngày/năm, +1 ngày mỗi 5 năm "
            "thâm niên theo Điều 114), quy trình xin nghỉ phép (đăng ký trước bao lâu, ai phê "
            "duyệt), nghỉ việc riêng có hưởng lương (cưới, tang...), nghỉ không hưởng lương, nghỉ "
            "ốm (số ngày, cần giấy tờ gì), nghỉ thai sản/nghỉ chế độ theo BHXH, và quy định phép "
            "năm chưa dùng hết cuối năm (được cộng dồn tối đa bao nhiêu, có được thanh toán không)."
        ),
        out_path="data/raw/leave_policies/07_chinh-sach-nghi-phep.md",
    )

    generate_policy_doc(
        title="Chính sách Bảo hiểm Sức khỏe Tự nguyện",
        document_code="HR-POL-HEALTH-2025",
        legal_basis="Phúc lợi tự nguyện của doanh nghiệp (không phải nghĩa vụ bắt buộc theo Luật BHYT/BHXH) — bổ sung ngoài BHYT/BHXH bắt buộc theo Luật BHYT số 51/2024/QH15",
        extra_instruction=(
            "Đây là gói bảo hiểm sức khỏe tự nguyện do công ty mua thêm cho nhân viên (tham khảo "
            "cấu trúc thực tế của các gói bảo hiểm sức khỏe doanh nghiệp phổ biến tại Việt Nam như "
            "PVI Care: điều trị nội trú, ngoại trú, nha khoa, thai sản, mạng lưới bệnh viện liên "
            "kết). Nêu rõ: các hạng mức gói theo cấp bậc (vd Standard/Premium/Executive), quyền lợi "
            "nội trú/ngoại trú/nha khoa/thai sản cho từng hạng mức (có số tiền cụ thể VNĐ/năm), "
            "phạm vi áp dụng cho người thân (vợ/chồng/con), điều kiện tham gia (thời gian thử "
            "việc/chính thức), và quy trình yêu cầu bồi thường/bảo lãnh viện phí. Ghi rõ đây là "
            "phúc lợi TỰ NGUYỆN bổ sung, khác với BHYT/BHXH bắt buộc theo luật."
        ),
        out_path="data/raw/compensation_policies/08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md",
    )

    generate_eval_set("eval/datasets/qa_eval_set.json")


if __name__ == "__main__":
    main()
