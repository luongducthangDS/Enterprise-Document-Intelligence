"""Phase F.1 — sửa qrel/dataset lỗi thời (bucket G1_GROUND_TRUTH_STALE), KHÔNG đụng product code.

Nguồn sự thật cho từng thay đổi trong RULES bên dưới CHỈ được lấy từ:
- tài liệu nội bộ sống hiện hành (data/processed/*.md) — đã đọc trực tiếp, không suy đoán
- chunk manifest hiện hành (data/chunks/*.json) — xác nhận chunk_id đúng bằng tìm kiếm text
- document_registry.csv — xác nhận file nào đã bị loại khỏi RAG (chunks_path/indexed_at rỗng)
- Type-C contract v3.1 đã được Ted chấp nhận (pure_statutory -> OUT_OF_SCOPE)
- việc đổi tên tenant V-NOVA -> NexaTech (đã được Ted xác nhận trước đó)

Không có case nào trong RULES đổi expected_answer để khớp với response hiện tại của
agent — mọi expected_answer mới đều được viết lại từ nội dung THẬT trong tài liệu
sống, đọc độc lập (xem phase_f_regression_triage_2026-08-15.md mục "G1" và session
log để biết trích dẫn gốc).

Idempotent: so sánh giá trị hiện tại với giá trị đích trước khi ghi; chạy lần 2 phải
ra 0 thay đổi. Không sửa eval/results/*.json (lịch sử đóng băng).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QA_EVAL_SET = REPO_ROOT / "eval" / "datasets" / "qa_eval_set.json"
HOLDOUT_PATH = REPO_ROOT / "eval" / "datasets" / "type_c_pure_statutory_holdout.json"
QRELS_PATH = REPO_ROOT / "eval" / "datasets" / "retrieval_qrels.json"
ANCHORS_PATH = REPO_ROOT / "eval" / "datasets" / "retrieval_anchors.json"
CHUNKS_DIR = REPO_ROOT / "data" / "chunks"
AUDIT_DIR = REPO_ROOT / "eval" / "results"
ANCHOR_LEN = 300


def load_chunk_texts() -> dict[str, str]:
    """data/ bị gitignore — chỉ có ở máy có sẵn dữ liệu (local/pre-push hook).
    Nếu không có, sync qrels/anchors tự bỏ qua (không phải lỗi toàn vẹn)."""
    texts: dict[str, str] = {}
    if not CHUNKS_DIR.exists():
        return texts
    for path in sorted(CHUNKS_DIR.glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8")):
            texts[c["metadata"]["chunk_id"]] = c["text"]
    return texts


@dataclass
class RemapRule:
    eval_id: str
    source_of_truth: str
    reason: str
    # Bằng chứng ở mức assertion — bắt buộc cho mọi remap (yêu cầu Ted 2026-08-15
    # "G1 migration phải có assertion-level proof"): old_chunk_ids để biết đã
    # đổi từ đâu, supported_assertion là claim cụ thể được evidence_excerpt xác
    # nhận (không phải "chủ đề liên quan"), validation phân biệt EXACT (trích
    # nguyên văn, không đổi nghĩa) vs SEMANTIC (diễn giải lại nhưng cùng
    # assertion, hoặc cắt bớt phần không có nguồn).
    old_relevant_chunk_ids: list[str] = field(default_factory=list)
    supported_assertion: str = ""
    evidence_excerpt: str = ""
    validation: str = "EXACT"  # "EXACT" | "SEMANTIC"
    new_source_file: str | None = None
    new_relevant_chunk_ids: list[str] | None = None
    new_evidence_chunk_id: str | None = None
    new_expected_answer: str | None = None
    new_ground_truth_context: str | None = None
    new_ground_truth_context_long: str | None = None


@dataclass
class RetireRule:
    eval_id: str
    retired_reason: str
    source_of_truth: str


# ---------------------------------------------------------------------------
# G1 REMAP — internal frozen evidence xác nhận tồn tại, đọc trực tiếp từ
# data/processed/*.md + data/chunks/*.json (2026-08-15).
# ---------------------------------------------------------------------------
REMAP_RULES: list[RemapRule] = [
    # --- Rename-drift (V-NOVA -> NexaTech re-chunk dịch chuyển chunk_id) ---
    RemapRule(
        eval_id="qa_102",
        source_of_truth="current chunk manifest (data/chunks/05_chinh-sach-lam-viec-tu-xa.json) "
        "+ tenant rename V-NOVA->NexaTech",
        reason="Nội dung '08 ngày/tháng, 96 ngày/năm' vẫn đúng và agent trả lời đúng 100%; "
        "chunk_id trong qrel (::0010) đã lệch khỏi vị trí thật sau re-chunk hậu đổi tên. "
        "Xác nhận vị trí đúng hiện tại bằng tìm kiếm text trực tiếp trong chunk manifest.",
        old_relevant_chunk_ids=["05_chinh-sach-lam-viec-tu-xa::0010"],
        supported_assertion="NLĐ được WFH tối đa 08 ngày/tháng và 96 ngày/năm; vượt giới hạn vì lý do "
        "sức khỏe/bất khả kháng phải được Giám đốc bộ phận + Trưởng phòng NS phê duyệt bằng văn bản.",
        evidence_excerpt="Không quá 08 ngày WFH/tháng. Không quá 96 ngày WFH/năm (dựa trên 02 ngày/tuần "
        "× 48 tuần làm việc thực tế). Trường hợp NLĐ cần WFH vượt giới hạn trên vì lý do sức khỏe hoặc "
        "bất khả kháng, phải được Giám đốc bộ phận và Trưởng phòng Nhân sự phê duyệt bằng văn bản.",
        validation="EXACT",
        new_relevant_chunk_ids=["05_chinh-sach-lam-viec-tu-xa::0009"],
        new_evidence_chunk_id="05_chinh-sach-lam-viec-tu-xa::0009",
        new_ground_truth_context="Không quá **96 ngày WFH/năm** (dựa trên 02 ngày/tuần × 48 tuần làm việc thực tế).",
        new_ground_truth_context_long=(
            "### 5.3. Số ngày WFH tối đa trong tháng và năm\n"
            "- Không quá **08 ngày WFH/tháng**.\n"
            "- Không quá **96 ngày WFH/năm** (dựa trên 02 ngày/tuần × 48 tuần làm việc thực tế).\n"
            "- Trường hợp NLĐ cần WFH vượt giới hạn trên vì lý do sức khỏe hoặc bất khả kháng, "
            "phải được Giám đốc bộ phận và Trưởng phòng Nhân sự phê duyệt bằng văn bản."
        ),
    ),
    RemapRule(
        eval_id="qa_110",
        source_of_truth="current chunk manifest (data/chunks/08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.json) "
        "+ tenant rename V-NOVA->NexaTech",
        reason="Nội dung 'chấm dứt vào ngày cuối cùng của tháng nghỉ việc' vẫn đúng và agent trả lời "
        "đúng 100%; chunk_id trong qrel (::0007) hiện trỏ sang nội dung khác (§7.1 bảng điều trị nội "
        "trú) sau re-chunk. Vị trí đúng hiện tại xác nhận bằng tìm kiếm text trực tiếp.",
        old_relevant_chunk_ids=["08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0007"],
        supported_assertion="Gói BHSTN chấm dứt vào ngày cuối cùng của tháng NLĐ nghỉ việc; có thể tiếp "
        "tục duy trì cá nhân bằng tự đóng phí cho Đối tác BH.",
        evidence_excerpt="Gói BHSTN chấm dứt vào ngày cuối cùng của tháng mà NLĐ nghỉ việc theo quyết "
        "định chấm dứt HĐLĐ. NLĐ có thể tiếp tục duy trì cá nhân bằng cách tự đóng phí cho Đối tác BH.",
        validation="EXACT",
        new_relevant_chunk_ids=["08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0019"],
        new_evidence_chunk_id="08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0019",
        new_ground_truth_context=(
            "Gói BHSTN chấm dứt vào ngày cuối cùng của tháng mà NLĐ nghỉ việc theo quyết định chấm "
            "dứt HĐLĐ. NLĐ có thể tiếp tục duy trì cá nhân bằng cách tự đóng phí cho Đối tác BH."
        ),
        new_ground_truth_context_long=(
            "**H: Tôi nghỉ việc giữa kỳ thì gói BHSTN còn hiệu lực đến khi nào?**\n"
            "Đ: Gói BHSTN chấm dứt vào ngày cuối cùng của tháng mà NLĐ nghỉ việc theo quyết định "
            "chấm dứt HĐLĐ. NLĐ có thể tiếp tục duy trì cá nhân bằng cách tự đóng phí cho Đối tác BH."
        ),
    ),
    # --- Template/reference đã bị loại khỏi RAG index -> remap sang tài liệu sống ---
    RemapRule(
        eval_id="qa_120",
        source_of_truth="data/processed/07_chinh-sach-nghi-phep.md (§8.3, chunk ::0014) "
        "+ data/processed/08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md (§7.4, chunk ::0010) "
        "— cả hai là tenant_official_policy, artifact_state=frozen",
        reason="Qrel cũ trỏ base_mau-quy-che-luong-thuong-phu-cap-xu-phat.md (public_template, đã bị "
        "loại khỏi RAG index — chunks_path/indexed_at rỗng trong document_registry.csv). Nội dung "
        "'chế độ đãi ngộ thai sản' KHÔNG có trong bất kỳ tài liệu sống nào ở dạng chung chung như cũ, "
        "nhưng có 2 nguồn sống cụ thể hơn: (1) 07§8.3 — hỗ trợ thêm 2 tháng lương nếu HĐLĐ>=12 tháng "
        "và đóng BHXH liên tục; (2) 08§7.4 — quyền lợi thai sản BHSTN chỉ áp dụng nếu đã tham gia gói "
        "ít nhất 10 tháng tính đến ngày dự sinh. Không có nguồn nào nêu THỜI ĐIỂM chi trả cụ thể — "
        "bỏ chi tiết đó khỏi expected_answer, không invent.",
        old_relevant_chunk_ids=["base_mau-quy-che-luong-thuong-phu-cap-xu-phat::0000"],
        supported_assertion="(1) Hỗ trợ thêm 2 tháng lương nếu HĐLĐ>=12 tháng + đóng BHXH liên tục; "
        "(2) quyền lợi thai sản BHSTN chỉ áp dụng nếu tham gia gói >=10 tháng tính đến ngày dự sinh.",
        evidence_excerpt="NLĐ nữ sinh con được công ty hỗ trợ thêm 2 tháng lương (trợ cấp riêng từ công "
        "ty) ngoài chế độ BHXH, nếu có HĐLĐ xác định thời hạn từ 12 tháng trở lên và đóng BHXH liên tục. "
        "| Lưu ý thai sản: Quyền lợi thai sản chỉ áp dụng khi NLĐ nữ đã tham gia gói BHSTN ít nhất 10 "
        "tháng tính đến ngày dự sinh.",
        validation="SEMANTIC",  # gộp 2 nguồn sống, bỏ claim "thời điểm chi trả" không có evidence
        new_source_file="data/processed/07_chinh-sach-nghi-phep.md",
        new_relevant_chunk_ids=[
            "07_chinh-sach-nghi-phep::0014",
            "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0010",
        ],
        new_evidence_chunk_id="07_chinh-sach-nghi-phep::0014",
        new_expected_answer=(
            "Có hai chế độ liên quan: (1) Nếu có HĐLĐ xác định thời hạn từ 12 tháng trở lên và đóng "
            "BHXH liên tục, bạn được công ty hỗ trợ thêm 2 tháng lương ngoài chế độ BHXH. (2) Nếu đã "
            "tham gia gói Bảo hiểm Sức khỏe Tự nguyện (BHSTN) ít nhất 10 tháng tính đến ngày dự sinh, "
            "bạn còn được hưởng thêm quyền lợi thai sản của gói BHSTN. Tài liệu nội bộ hiện có không "
            "nêu rõ thời điểm chi trả cụ thể của khoản hỗ trợ 2 tháng lương."
        ),
        new_ground_truth_context=(
            "NLĐ nữ sinh con được công ty hỗ trợ thêm **2 tháng lương** (trợ cấp riêng từ công ty) "
            "ngoài chế độ BHXH, nếu có HĐLĐ xác định thời hạn từ 12 tháng trở lên và đóng BHXH liên tục."
        ),
    ),
    RemapRule(
        eval_id="qa_122",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§7, chunk ::0007) — tenant_official_policy, frozen",
        reason="Qrel cũ trỏ base_mau-quy-che-luong-thuong-phu-cap-xu-phat.md (public_template, đã loại "
        "khỏi RAG index). Tài liệu sống 13_noi-quy-lao-dong-va-ky-luat.md §7 CHỈ xác nhận ngưỡng "
        "'05 ngày cộng dồn trong 30 ngày' dẫn tới sa thải — KHÔNG có ngưỡng '15 ngày cộng dồn trong 1 "
        "năm' mà expected_answer cũ khẳng định. Bỏ vế không có nguồn hỗ trợ, không invent.",
        old_relevant_chunk_ids=["base_mau-quy-che-luong-thuong-phu-cap-xu-phat::0001"],
        supported_assertion="Tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày không lý do chính đáng dẫn tới "
        "sa thải (KHÔNG có ngưỡng theo năm — claim đó bị loại vì không có nguồn).",
        evidence_excerpt="Sa thải | Trộm cắp, tham ô, tiết lộ bí mật kinh doanh/công nghệ, quấy rối tình "
        "dục, tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày mà không có lý do chính đáng",
        validation="SEMANTIC",  # cắt bớt claim "15 ngày/năm" không có evidence
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0007"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0007",
        new_expected_answer=(
            "Theo Nội quy Lao động NexaTech, nếu bạn tự ý bỏ việc 05 ngày cộng dồn trong thời hạn 30 "
            "ngày mà không có lý do chính đáng, bạn sẽ bị sa thải."
        ),
        new_ground_truth_context=(
            "Sa thải | Trộm cắp, tham ô, tiết lộ bí mật kinh doanh/công nghệ, quấy rối tình dục, tự ý "
            "bỏ việc 05 ngày cộng dồn trong 30 ngày mà không có lý do chính đáng"
        ),
    ),
    RemapRule(
        eval_id="qa_123",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§2, chunk ::0002) — tenant_official_policy, frozen",
        reason="Sửa qrel phụ (case này primary root-cause là G6 confidence-collapse, không phải G1 — "
        "xem phase_f_regression_triage). Nhưng qrel vẫn trỏ leanh_mau-noi-quy-lao-dong.md (public_"
        "template, đã loại khỏi RAG index) nên vẫn cần sửa để không gây context_found=False giả khi "
        "P1 (F.2) sửa xong confidence bug. Nội dung '40 giờ/tuần, 05 ngày, T2-T6' khớp nguyên văn tài "
        "liệu sống thay thế.",
        old_relevant_chunk_ids=["leanh_mau-noi-quy-lao-dong::0000"],
        supported_assertion="Thời gian làm việc chuẩn: 40 giờ/tuần, 08 giờ/ngày, từ thứ Hai đến thứ Sáu.",
        evidence_excerpt="Thời gian làm việc: 40 giờ/tuần, 08 giờ/ngày, từ thứ Hai đến thứ Sáu.",
        validation="EXACT",
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0002"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0002",
        new_ground_truth_context="Thời gian làm việc: 40 giờ/tuần, 08 giờ/ngày, từ thứ Hai đến thứ Sáu.",
    ),
    RemapRule(
        eval_id="qa_124",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§5.1, chunk ::0005) — tenant_official_policy, frozen",
        reason="Sửa qrel phụ (primary root-cause là G4 human_first-over-trigger). Qrel cũ trỏ leanh_"
        "mau-noi-quy-lao-dong.md (public_template, đã loại khỏi RAG index). Tài liệu sống 13_noi-quy-"
        "lao-dong-va-ky-luat.md §5.1 nêu đúng 3 nhóm hành vi quấy rối tình dục, khớp gần như nguyên "
        "văn expected_answer cũ.",
        old_relevant_chunk_ids=["leanh_mau-noi-quy-lao-dong::0022"],
        supported_assertion="Hành vi quấy rối tình dục gồm 3 nhóm: hành động/cử chỉ tính chất tình dục; "
        "ngôn ngữ/tài liệu liên quan hoạt động tình dục; đề nghị đổi quan hệ tình dục lấy đánh giá ưu "
        "ái/lương thưởng/công việc.",
        evidence_excerpt="5.1. Hành vi quấy rối tình dục bao gồm: hành động/cử chỉ có tính chất tình "
        "dục; ngôn ngữ, tài liệu liên quan đến hoạt động tình dục; đề nghị đổi quan hệ tình dục lấy sự "
        "đánh giá ưu ái/lương thưởng/công việc.",
        validation="SEMANTIC",  # paraphrase khớp đúng 3 nhóm, không thêm/bớt nội dung
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0005"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0005",
        new_expected_answer=(
            "Các hành vi được xem là quấy rối tình dục tại nơi làm việc bao gồm: hành động/cử chỉ có "
            "tính chất tình dục; ngôn ngữ, tài liệu liên quan đến hoạt động tình dục; và đề nghị đổi "
            "quan hệ tình dục lấy sự đánh giá ưu ái/lương thưởng/công việc."
        ),
        new_ground_truth_context=(
            "Hành vi quấy rối tình dục bao gồm: hành động/cử chỉ có tính chất tình dục; ngôn ngữ, tài "
            "liệu liên quan đến hoạt động tình dục; đề nghị đổi quan hệ tình dục lấy sự đánh giá ưu "
            "ái/lương thưởng/công việc."
        ),
    ),
    RemapRule(
        eval_id="qa_126",
        source_of_truth="data/processed/06_chinh-sach-dao-tao-phat-trien.md (§6.1, chunk ::0006) — tenant_official_policy, frozen",
        reason="Qrel cũ trỏ mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md (public_template, đã loại khỏi "
        "RAG index) với bảng SỐ KHÁC (20tr -> 12 tháng). Tài liệu sống 06_chinh-sach-dao-tao-phat-"
        "trien.md §6.1 có bảng cam kết riêng, mốc 20tr rơi vào khoảng '20.000.000-50.000.000 VNĐ' "
        "-> 02 năm, KHÔNG phải 12 tháng. Dùng đúng số của tài liệu sống, không giữ số của template đã "
        "loại.",
        old_relevant_chunk_ids=["mau_quy-che-dao-tao-va-cam-ket-boi-hoan::0002"],
        supported_assertion="Chi phí đào tạo 20 triệu (thuộc mức 20.000.000-50.000.000 VNĐ) -> cam kết "
        "làm việc tối thiểu 02 năm sau khi hoàn thành khóa học.",
        evidence_excerpt="Từ 20.000.000 VNĐ - 50.000.000 VNĐ hoặc thời gian đào tạo từ 06 - 12 tháng | "
        "02 năm",
        validation="SEMANTIC",  # số liệu đổi 12 tháng->02 năm theo đúng bảng nguồn sống, không phải giữ nguyên
        new_source_file="data/processed/06_chinh-sach-dao-tao-phat-trien.md",
        new_relevant_chunk_ids=["06_chinh-sach-dao-tao-phat-trien::0006"],
        new_evidence_chunk_id="06_chinh-sach-dao-tao-phat-trien::0006",
        new_expected_answer=(
            "Với chi phí đào tạo 20 triệu đồng (thuộc mức từ 20.000.000 đến dưới 50.000.000 VNĐ), bạn "
            "phải cam kết làm việc tối thiểu 02 năm sau khi hoàn thành khóa học."
        ),
        new_ground_truth_context=(
            "Từ 20.000.000 VNĐ - 50.000.000 VNĐ hoặc thời gian đào tạo từ 06 - 12 tháng | 02 năm"
        ),
    ),
    RemapRule(
        eval_id="qa_127",
        source_of_truth="data/processed/06_chinh-sach-dao-tao-phat-trien.md (§6, chunk ::0006) — tenant_official_policy, frozen",
        reason="Cùng lý do qa_126: qrel cũ trỏ template đã loại (12 tháng); tài liệu sống ghi 02 năm "
        "cho mốc 20tr. Công thức đền bù §6.2 khớp nguyên văn (viết lại tương đương toán học, dùng "
        "đúng cách diễn đạt của tài liệu sống thay vì template).",
        old_relevant_chunk_ids=["mau_quy-che-dao-tao-va-cam-ket-boi-hoan::0004"],
        supported_assertion="Chi phí đào tạo 20 triệu -> cam kết 02 năm; công thức đền bù = Tổng chi phí "
        "đào tạo × (Số tháng chưa làm đủ cam kết / Tổng số tháng cam kết).",
        evidence_excerpt="Từ 20.000.000 VNĐ - 50.000.000 VNĐ | 02 năm ... Chi phí đền bù = Tổng chi phí "
        "đào tạo × (Số tháng chưa làm đủ cam kết / Tổng số tháng cam kết)",
        validation="SEMANTIC",
        new_source_file="data/processed/06_chinh-sach-dao-tao-phat-trien.md",
        new_relevant_chunk_ids=["06_chinh-sach-dao-tao-phat-trien::0006"],
        new_evidence_chunk_id="06_chinh-sach-dao-tao-phat-trien::0006",
        new_expected_answer=(
            "Với chi phí đào tạo 20 triệu đồng (thuộc mức 20.000.000 - 50.000.000 VNĐ), bạn phải cam "
            "kết làm việc tối thiểu 02 năm. Nếu nghỉ việc trước thời hạn, chi phí đền bù = Tổng chi "
            "phí đào tạo × (Số tháng chưa làm đủ cam kết / Tổng số tháng cam kết)."
        ),
        new_ground_truth_context="Chi phí đền bù = Tổng chi phí đào tạo × (Số tháng chưa làm đủ cam kết / Tổng số tháng cam kết)",
    ),
    RemapRule(
        eval_id="qa_129",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§9.1, chunk ::0009) — tenant_official_policy, frozen",
        reason="Qrel cũ trỏ mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai.md (public_template, đã loại "
        "khỏi RAG index). Agent đã trả lời ĐÚNG 100% từ tài liệu sống thay thế (03 tháng lương, "
        "khấu trừ <=30%) — chỉ chunk_id trong qrel sai, nội dung không đổi.",
        old_relevant_chunk_ids=["mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai::0003"],
        supported_assertion="Thiệt hại không nghiêm trọng (dưới 10 tháng lương tối thiểu vùng): bồi "
        "thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng tháng không quá 30%/tháng.",
        evidence_excerpt="9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới "
        "10 tháng lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
        "tháng (không quá 30% lương thực nhận/tháng).",
        validation="EXACT",
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0009"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0009",
        new_ground_truth_context=(
            "9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới 10 tháng "
            "lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
            "tháng (không quá 30% lương thực nhận/tháng)."
        ),
    ),
    RemapRule(
        eval_id="qa_130",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§9.1, chunk ::0009) — tenant_official_policy, frozen",
        reason="Giống qa_129 — cùng qrel gốc, cùng fix.",
        old_relevant_chunk_ids=["mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai::0003"],
        supported_assertion="Thiệt hại không nghiêm trọng (dưới 10 tháng lương tối thiểu vùng): bồi "
        "thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng tháng không quá 30%/tháng.",
        evidence_excerpt="9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới "
        "10 tháng lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
        "tháng (không quá 30% lương thực nhận/tháng).",
        validation="EXACT",
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0009"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0009",
        new_ground_truth_context=(
            "9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới 10 tháng "
            "lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
            "tháng (không quá 30% lương thực nhận/tháng)."
        ),
    ),
    RemapRule(
        eval_id="qa_131",
        source_of_truth="data/processed/13_noi-quy-lao-dong-va-ky-luat.md (§9.1, chunk ::0009) — tenant_official_policy, frozen",
        reason="Giống qa_129/130 — cùng qrel gốc, cùng fix.",
        old_relevant_chunk_ids=["mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai::0006"],
        supported_assertion="Thiệt hại không nghiêm trọng (dưới 10 tháng lương tối thiểu vùng): bồi "
        "thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng tháng không quá 30%/tháng.",
        evidence_excerpt="9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới "
        "10 tháng lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
        "tháng (không quá 30% lương thực nhận/tháng).",
        validation="EXACT",
        new_source_file="data/processed/13_noi-quy-lao-dong-va-ky-luat.md",
        new_relevant_chunk_ids=["13_noi-quy-lao-dong-va-ky-luat::0009"],
        new_evidence_chunk_id="13_noi-quy-lao-dong-va-ky-luat::0009",
        new_ground_truth_context=(
            "9.1. NLĐ làm hư hỏng dụng cụ, thiết bị do sơ suất với giá trị thiệt hại dưới 10 tháng "
            "lương tối thiểu vùng: bồi thường tối đa 03 tháng lương, khấu trừ dần vào lương hằng "
            "tháng (không quá 30% lương thực nhận/tháng)."
        ),
    ),
    RemapRule(
        eval_id="qa_138",
        source_of_truth="data/processed/04_quy-trinh-offboarding.md (§4, chunk ::0004) — tenant_official_policy, frozen",
        reason="Sửa qrel phụ (primary root-cause là G4). Qrel cũ trỏ bài viết public_article của "
        "Talentnet (đã loại khỏi RAG index). Tài liệu sống 04_quy-trinh-offboarding.md §4 chỉ liệt kê "
        "4 ví dụ (không được bố trí đúng công việc; không trả đủ lương/đúng hạn; bị ngược đãi; bị "
        "quấy rối tình dục) theo khoản 2 Điều 35 — KHÔNG có 'đánh đập' và 'lao động nữ mang thai' như "
        "expected_answer cũ (những vế đó chỉ có trong bài viết Talentnet, không có trong tài liệu nội "
        "bộ sống). Dùng đúng 4 ví dụ tài liệu sống nêu, không invent.",
        old_relevant_chunk_ids=["talentnet_quy-trinh-cham-dut-hop-dong-lao-dong::0001"],
        supported_assertion="NLĐ có quyền chấm dứt HĐLĐ không cần báo trước trong một số trường hợp cụ "
        "thể theo khoản 2 Điều 35, gồm (theo đúng 4 ví dụ tài liệu sống nêu): không được bố trí đúng "
        "công việc; không được trả đủ lương/đúng hạn; bị ngược đãi; bị quấy rối tình dục.",
        evidence_excerpt="Các trường hợp NLĐ được quyền nghỉ không cần báo trước: theo khoản 2 Điều 35 "
        "(ví dụ không được bố trí đúng công việc, không được trả đủ lương/đúng hạn, bị ngược đãi, bị "
        "quấy rối tình dục...).",
        validation="SEMANTIC",  # cắt "đánh đập" + "lao động nữ mang thai" — không có trong nguồn sống
        new_source_file="data/processed/04_quy-trinh-offboarding.md",
        new_relevant_chunk_ids=["04_quy-trinh-offboarding::0004"],
        new_evidence_chunk_id="04_quy-trinh-offboarding::0004",
        new_expected_answer=(
            "Theo Điều 35 khoản 2 (được Quy trình Offboarding NexaTech dẫn chiếu), người lao động có "
            "quyền chấm dứt hợp đồng mà không cần báo trước trong một số trường hợp, ví dụ: không "
            "được bố trí đúng công việc, không được trả đủ lương hoặc trả lương không đúng hạn, bị "
            "ngược đãi, hoặc bị quấy rối tình dục."
        ),
        new_ground_truth_context=(
            "Các trường hợp NLĐ được quyền nghỉ không cần báo trước: theo khoản 2 Điều 35 (ví dụ "
            "không được bố trí đúng công việc, không được trả đủ lương/đúng hạn, bị ngược đãi, bị "
            "quấy rối tình dục...)."
        ),
    ),
    RemapRule(
        eval_id="qa_140",
        source_of_truth="data/processed/04_quy-trinh-offboarding.md (Bước 5+6, chunk ::0007 + ::0008) — tenant_official_policy, frozen",
        reason="Qrel cũ trỏ bài viết public_article của Talentnet (đã loại khỏi RAG index). Agent đã "
        "trả lời ĐÚNG từ tài liệu sống thay thế. Trim chi tiết 'xác nhận bảo hiểm thất nghiệp' (chỉ "
        "có ở bài Talentnet, tài liệu sống chỉ nói 'trả lại sổ bảo hiểm xã hội, giấy tờ đã giữ') để "
        "khớp đúng nguồn sống, không invent.",
        old_relevant_chunk_ids=["talentnet_quy-trinh-cham-dut-hop-dong-lao-dong::0006"],
        supported_assertion="Trong 14 ngày làm việc kể từ ngày chấm dứt HĐLĐ (có thể tới 30 ngày trong "
        "một số trường hợp theo Điều 48), công ty thanh toán đầy đủ quyền lợi, trả lại sổ BHXH + giấy "
        "tờ đã giữ, cấp giấy xác nhận thời gian làm việc nếu NLĐ yêu cầu.",
        evidence_excerpt="Trong thời hạn 14 ngày làm việc kể từ ngày chấm dứt, hai bên thanh toán đầy đủ "
        "các khoản liên quan đến quyền lợi mỗi bên (có thể kéo dài nhưng không quá 30 ngày trong một số "
        "trường hợp theo Điều 48). ... Công ty hoàn thành thủ tục xác nhận và trả lại sổ bảo hiểm xã "
        "hội, giấy tờ đã giữ của NLĐ (Điều 48). Cấp giấy xác nhận thời gian làm việc nếu NLĐ yêu cầu.",
        validation="SEMANTIC",  # cắt claim "xác nhận bảo hiểm thất nghiệp" — chỉ có ở nguồn Talentnet cũ
        new_source_file="data/processed/04_quy-trinh-offboarding.md",
        new_relevant_chunk_ids=[
            "04_quy-trinh-offboarding::0007",
            "04_quy-trinh-offboarding::0008",
        ],
        new_evidence_chunk_id="04_quy-trinh-offboarding::0007",
        new_expected_answer=(
            "Công ty phải thanh toán đầy đủ các khoản quyền lợi cho người lao động trong vòng 14 ngày "
            "làm việc kể từ ngày chấm dứt hợp đồng (có thể kéo dài nhưng không quá 30 ngày trong một "
            "số trường hợp theo Điều 48). Ngoài ra, công ty hoàn thành thủ tục xác nhận và trả lại sổ "
            "bảo hiểm xã hội, giấy tờ đã giữ của người lao động, đồng thời cấp giấy xác nhận thời "
            "gian làm việc nếu người lao động yêu cầu."
        ),
        new_ground_truth_context=(
            "Trong thời hạn 14 ngày làm việc kể từ ngày chấm dứt, hai bên thanh toán đầy đủ các khoản "
            "liên quan đến quyền lợi mỗi bên (có thể kéo dài nhưng không quá 30 ngày trong một số "
            "trường hợp theo Điều 48)."
        ),
    ),
]

# ---------------------------------------------------------------------------
# G1 RETIRE — không có bằng chứng nội bộ sống nào hỗ trợ CÙNG assertion; nguồn
# duy nhất là tài liệu public_template/public_reference đã bị loại khỏi RAG
# index (xác nhận qua document_registry.csv: chunks_path/indexed_at rỗng).
# Không invent qrel — reclassify khỏi current benchmark.
# ---------------------------------------------------------------------------
RETIRE_RULES: list[RetireRule] = [
    RetireRule(
        eval_id="qa_121",
        source_of_truth="document_registry.csv (base_mau-quy-che-luong-thuong-phu-cap-xu-phat.md: "
        "chunks_path/indexed_at rỗng) + rà soát data/processed/07,08,11,12,13 (không tìm thấy)",
        retired_reason="Nguồn duy nhất hỗ trợ khoản 'mừng cưới hỏi' bằng tiền là "
        "base_mau-quy-che-luong-thuong-phu-cap-xu-phat.md (public_template, đã loại khỏi RAG index). "
        "Không tài liệu nội bộ sống nào (07/08/11/12/13) đề cập chế độ này bằng tiền — 07 chỉ có "
        "'nghỉ phép cưới 3 ngày có lương' (khác chủ đề: ngày nghỉ, không phải tiền mừng). Không "
        "invent qrel — loại khỏi current benchmark theo Phase F.1.",
    ),
    RetireRule(
        eval_id="qa_125",
        source_of_truth="document_registry.csv (leanh_mau-noi-quy-lao-dong.md: chunks_path/indexed_at "
        "rỗng) + đọc toàn văn data/processed/13_noi-quy-lao-dong-va-ky-luat.md (không có điều khoản "
        "tương ứng)",
        retired_reason="Nguồn duy nhất hỗ trợ 'chi nhánh/đơn vị thành viên được tự cụ thể hóa nội quy "
        "riêng' là leanh_mau-noi-quy-lao-dong.md (public_template, đã loại khỏi RAG index). Tài liệu "
        "13_noi-quy-lao-dong-va-ky-luat.md (thay thế sống) không có điều khoản phân quyền cho đơn vị "
        "thành viên. Không invent qrel — loại khỏi current benchmark theo Phase F.1.",
    ),
    RetireRule(
        eval_id="qa_139",
        source_of_truth="data/processed/04_quy-trinh-offboarding.md — legal_basis frontmatter chỉ dẫn "
        "chiếu Điều 35 (thời hạn báo trước của NLĐ xin nghỉ); §4 tiêu đề đúng là 'Thời hạn báo trước "
        "khi NLĐ xin nghỉ (theo Điều 35)' — không đề cập Điều 36 (chấm dứt do công ty đơn phương)",
        retired_reason="TỰ SỬA SAI SÓT của lần remap F.1 đầu tiên: em từng giả định các mốc 45/30/3 "
        "ngày (Điều 35, áp dụng khi NLĐ xin nghỉ) cũng áp dụng đối xứng cho trường hợp CÔNG TY đơn "
        "phương chấm dứt vì NLĐ không hoàn thành công việc (Điều 36) — giả định này KHÔNG có căn cứ "
        "trong tài liệu sống. Phát hiện qua chính response thật của agent (chạy live sau khi remap): "
        "agent trả lời trung thực rằng 'các đoạn trích chỉ nêu thời hạn áp dụng khi NLĐ tự xin nghỉ, "
        "không nêu thời hạn khi công ty đơn phương chấm dứt' — đúng, vì doc 04 không có câu đó. Không "
        "invent qrel — loại khỏi current benchmark. Đây không phải product bug, là lỗi authoring của "
        "chính migration F.1, đã tự phát hiện và sửa qua live regression run.",
    ),
    RetireRule(
        eval_id="qa_128",
        source_of_truth="document_registry.csv (mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md: "
        "chunks_path/indexed_at rỗng) + đọc toàn văn data/processed/06_chinh-sach-dao-tao-phat-trien.md "
        "§6.2 (chỉ có công thức tổng quát)",
        retired_reason="Câu hỏi yêu cầu breakdown cụ thể của 'tổng chi phí đào tạo' (học phí/tài "
        "liệu/lệ phí thi/di chuyển) và thứ tự ưu tiên khấu trừ (lương/phụ cấp/trợ cấp) — chi tiết này "
        "chỉ có trong mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md Điều 5-6 (public_template, đã loại "
        "khỏi RAG index). Tài liệu sống 06_chinh-sach-dao-tao-phat-trien.md §6.2 chỉ có công thức "
        "'Chi phí đền bù = Tổng chi phí đào tạo × (...)', không itemize, không nêu thứ tự khấu trừ. "
        "Không invent qrel — loại khỏi current benchmark theo Phase F.1.",
    ),
]

# ---------------------------------------------------------------------------
# 10 case pure_statutory — dataset chưa cập nhật theo Type-C contract v3.1 đã
# được Ted chấp nhận (pure_statutory -> OUT_OF_SCOPE). Router đang hành xử
# ĐÚNG theo contract đóng băng; đây KHÔNG phải router bug, chỉ là dataset
# `type=in_scope` cũ chưa retype. Theo yêu cầu Phase F.1: chuyển sang holdout
# riêng, KHÔNG đưa vào canonical 20 Type-C, KHÔNG để production router đọc.
# ---------------------------------------------------------------------------
PURE_STATUTORY_HOLDOUT_IDS = [
    "qa_113",
    "qa_114",
    "qa_115",
    "qa_116",
    "qa_132",
    "qa_133",
    "qa_134",
    "qa_135",
    "qa_136",
    "qa_137",
]

# Archetype theo ĐÚNG 4 nhóm đã dùng trong eval/datasets/type_c_contract_set.json
# (ARC_1=STATUTORY_CONTENT, ARC_2=LEGAL_PROCEDURE, ARC_3=LEGAL_SANCTION/trách
# nhiệm cơ quan nhà nước, ARC_4=STATUTORY_THRESHOLD) — không invent nhóm mới.
PURE_STATUTORY_ARCHETYPE = {
    "qa_113": "ARC_1",  # phạm vi áp dụng của nghị định cho CBCC/viên chức
    "qa_114": "ARC_1",  # diễn giải nội dung quy định bảo lưu chênh lệch lương
    "qa_115": "ARC_4",  # ngưỡng % cụ thể (35%) cơ sở y tế công lập được sử dụng
    "qa_116": "ARC_3",  # trách nhiệm hướng dẫn của Bộ Tài chính
    "qa_132": "ARC_1",  # diễn giải điều khoản luật BHXH (Điều 13)
    "qa_133": "ARC_1",  # diễn giải quyền lợi phụ cấp khu vực khi hưu trí
    "qa_134": "ARC_1",  # diễn giải điều kiện tính thời gian hưu trí
    "qa_135": "ARC_4",  # ngưỡng số cụ thể (mức lương tối thiểu vùng I)
    "qa_136": "ARC_4",  # tra cứu địa giới hành chính theo vùng lương tối thiểu
    "qa_137": "ARC_4",  # tra cứu địa giới hành chính theo vùng lương tối thiểu
}
PURE_STATUTORY_RETIRE_REASON = (
    "Câu hỏi thuộc nhóm PURE STATUTORY (đã xác nhận qua Phase F triage: hỏi phạm vi/nội dung nghị "
    "định/luật áp dụng cho khu vực công/CBCC/viên chức hoặc tra cứu vùng lương tối thiểu theo địa "
    "giới hành chính — không liên quan chính sách nội bộ NexaTech). Router phân loại pure_statutory -> "
    "OUT_OF_SCOPE đúng theo Type-C contract v3.1 đã được chấp nhận (KHÔNG phải router bug). Dataset "
    "'type=in_scope' cũ có trước khi contract này tồn tại — chuyển sang "
    "eval/datasets/type_c_pure_statutory_holdout.json làm additional/holdout statutory case, KHÔNG "
    "đưa vào canonical 20 Type-C, KHÔNG tính vào regression 125-case chính."
)


def _get(item: dict, path: list[str]):
    cur = item
    for key in path[:-1]:
        cur = cur.get(key, {})
        if not isinstance(cur, dict):
            return None
    return cur.get(path[-1]) if isinstance(cur, dict) else None


def _set(item: dict, path: list[str], value) -> None:
    cur = item
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


@dataclass
class AuditRecord:
    eval_id: str
    old_value: object
    new_value: object
    field_changed: str
    reason: str
    source_of_truth: str
    product_code_changed: bool = False

    def as_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "field_changed": self.field_changed,
            "reason": self.reason,
            "source_of_truth": self.source_of_truth,
            "product_code_changed": self.product_code_changed,
        }


@dataclass
class AssertionAuditRecord:
    """Bằng chứng ở mức assertion cho mỗi case remap — yêu cầu Ted 2026-08-15:
    'không được coi retrieved document có vẻ đúng là đủ để remap qrel'. Mỗi
    record chứng minh new_chunk_ids THỰC SỰ support đúng supported_assertion,
    không chỉ liên quan chủ đề."""

    eval_id: str
    old_chunk_ids: list[str]
    new_chunk_ids: list[str]
    supported_assertion: str
    evidence_excerpt_or_hash: str
    evidence_sha256: str
    validation: str  # "EXACT" | "SEMANTIC"

    def as_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "old_chunk_ids": self.old_chunk_ids,
            "new_chunk_ids": self.new_chunk_ids,
            "supported_assertion": self.supported_assertion,
            "evidence_excerpt_or_hash": self.evidence_excerpt_or_hash,
            "evidence_sha256": self.evidence_sha256,
            "validation": self.validation,
        }


def build_assertion_audit(rule: RemapRule) -> AssertionAuditRecord:
    assert rule.validation in ("EXACT", "SEMANTIC"), f"{rule.eval_id}: validation phải EXACT|SEMANTIC"
    assert rule.supported_assertion, f"{rule.eval_id}: thiếu supported_assertion"
    assert rule.evidence_excerpt, f"{rule.eval_id}: thiếu evidence_excerpt"
    digest = hashlib.sha256(rule.evidence_excerpt.encode("utf-8")).hexdigest()
    return AssertionAuditRecord(
        eval_id=rule.eval_id,
        old_chunk_ids=rule.old_relevant_chunk_ids,
        new_chunk_ids=rule.new_relevant_chunk_ids or [],
        supported_assertion=rule.supported_assertion,
        evidence_excerpt_or_hash=rule.evidence_excerpt,
        evidence_sha256=digest,
        validation=rule.validation,
    )


def _apply_field(item: dict, path: list[str], new_value, rule_eval_id: str, reason: str, source: str,
                  audit: list[AuditRecord]) -> bool:
    old_value = _get(item, path)
    if old_value == new_value:
        return False
    audit.append(
        AuditRecord(
            eval_id=rule_eval_id,
            old_value=old_value,
            new_value=new_value,
            field_changed=".".join(path),
            reason=reason,
            source_of_truth=source,
        )
    )
    _set(item, path, new_value)
    return True


def apply_remap(item: dict, rule: RemapRule, audit: list[AuditRecord]) -> bool:
    changed = False
    field_map = [
        (["metadata", "source_file"], rule.new_source_file),
        (["relevant_chunk_ids"], rule.new_relevant_chunk_ids),
        (["evidence_chunk_id"], rule.new_evidence_chunk_id),
        (["expected_answer"], rule.new_expected_answer),
        (["ground_truth_context"], rule.new_ground_truth_context),
        (["ground_truth_context_long"], rule.new_ground_truth_context_long),
    ]
    for path, new_value in field_map:
        if new_value is None:
            continue
        if _apply_field(item, path, new_value, rule.eval_id, rule.reason, rule.source_of_truth, audit):
            changed = True
    return changed


def apply_retire(item: dict, rule: RetireRule, audit: list[AuditRecord]) -> bool:
    changed = False
    if _apply_field(item, ["retired"], True, rule.eval_id, rule.retired_reason, rule.source_of_truth, audit):
        changed = True
    if _apply_field(
        item, ["retired_reason"], rule.retired_reason, rule.eval_id, rule.retired_reason, rule.source_of_truth, audit
    ):
        changed = True
    return changed


def apply_pure_statutory_retire(item: dict, audit: list[AuditRecord]) -> bool:
    changed = False
    source = "Type-C contract v3.1 (đã được Ted chấp nhận) + phase_f_regression_triage_2026-08-15.md " "mục pure_statutory disambiguation"
    if _apply_field(item, ["retired"], True, item["id"], PURE_STATUTORY_RETIRE_REASON, source, audit):
        changed = True
    if _apply_field(
        item, ["retired_reason"], PURE_STATUTORY_RETIRE_REASON, item["id"], PURE_STATUTORY_RETIRE_REASON, source, audit
    ):
        changed = True
    return changed


def build_holdout_entry(item: dict) -> dict:
    """Dùng ĐÚNG schema đã có sẵn trong eval/datasets/type_c_contract_set.json
    (id/category/archetype/query/expected_state) — KHÔNG invent field mới
    (target_state/reason_code/fact_evidence/citation_required). "no internal
    evidence expected" và "no citation expected" đã là hệ quả tất định của
    expected_state=OUT_OF_SCOPE trong chính out_of_scope_node() (escalation.py),
    không cần field riêng để mã hoá lại. Field ngoài schema chuẩn (origin_eval_id,
    note) chỉ thêm vào file MỚI này để truy vết, không đụng schema của
    type_c_contract_set.json hay qa_eval_set.json."""
    return {
        "id": item["id"],
        "category": "Type C",
        "archetype": PURE_STATUTORY_ARCHETYPE[item["id"]],
        "query": item["question"],
        "expected_state": "OUT_OF_SCOPE",
        "origin_eval_id": item["id"],
        "note": "Additional/holdout pure_statutory case — KHÔNG thuộc canonical 20 Type-C matrix "
        "(xem eval/datasets/type_c_contract_set.json cho 20 case đóng băng). Production router "
        "KHÔNG đọc file này.",
        "migrated_at": None,  # điền tại runtime
    }


def sync_qrels_and_anchors(chunk_texts: dict[str, str], audit: list[AuditRecord]) -> bool:
    """retrieval_qrels.json / retrieval_anchors.json là 2 file TÁCH BIỆT khỏi
    relevant_chunk_ids nhúng trong qa_eval_set.json — check_dataset_integrity.py
    dùng 2 file này làm nguồn kiểm tra chunk-level, nên phải đồng bộ theo cùng
    RULES ở trên, không thì để lại qrel mồ côi/anchor lệch."""
    qrels: dict = json.loads(QRELS_PATH.read_text(encoding="utf-8")) if QRELS_PATH.exists() else {}
    anchors: dict = json.loads(ANCHORS_PATH.read_text(encoding="utf-8")) if ANCHORS_PATH.exists() else {}
    changed = False

    remap_ids = {r.eval_id: r for r in REMAP_RULES if r.new_relevant_chunk_ids}
    retire_ids = {r.eval_id for r in RETIRE_RULES} | set(PURE_STATUTORY_HOLDOUT_IDS)

    for eval_id, rule in remap_ids.items():
        new_qrel = {cid: 2 for cid in rule.new_relevant_chunk_ids}
        if qrels.get(eval_id) != new_qrel:
            audit.append(
                AuditRecord(
                    eval_id=eval_id,
                    old_value=qrels.get(eval_id),
                    new_value=new_qrel,
                    field_changed="retrieval_qrels.json",
                    reason=rule.reason,
                    source_of_truth=rule.source_of_truth,
                )
            )
            qrels[eval_id] = new_qrel
            changed = True

        new_anchor = {}
        for cid in rule.new_relevant_chunk_ids:
            text = chunk_texts.get(cid)
            if text is None:
                continue  # data/chunks không có sẵn (CI clean checkout) — bỏ qua, không phải lỗi
            new_anchor[cid] = {"score": 2, "anchor": text[:ANCHOR_LEN]}
        if new_anchor and anchors.get(eval_id) != new_anchor:
            audit.append(
                AuditRecord(
                    eval_id=eval_id,
                    old_value=anchors.get(eval_id),
                    new_value=new_anchor,
                    field_changed="retrieval_anchors.json",
                    reason=rule.reason,
                    source_of_truth=rule.source_of_truth,
                )
            )
            anchors[eval_id] = new_anchor
            changed = True

    for eval_id in retire_ids:
        if eval_id in qrels:
            audit.append(
                AuditRecord(
                    eval_id=eval_id,
                    old_value=qrels[eval_id],
                    new_value=None,
                    field_changed="retrieval_qrels.json (removed)",
                    reason="Câu đã retired/chuyển holdout — không còn trong current benchmark nên "
                    "không được có qrel (tránh orphan qrel).",
                    source_of_truth="Phase F.1 retire/holdout rules",
                )
            )
            del qrels[eval_id]
            changed = True
        if eval_id in anchors:
            audit.append(
                AuditRecord(
                    eval_id=eval_id,
                    old_value=anchors[eval_id],
                    new_value=None,
                    field_changed="retrieval_anchors.json (removed)",
                    reason="Câu đã retired/chuyển holdout — không còn trong current benchmark.",
                    source_of_truth="Phase F.1 retire/holdout rules",
                )
            )
            del anchors[eval_id]
            changed = True

    if changed:
        QRELS_PATH.write_text(json.dumps(qrels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ANCHORS_PATH.write_text(json.dumps(anchors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    qa_items = json.loads(QA_EVAL_SET.read_text(encoding="utf-8"))
    by_id = {it["id"]: it for it in qa_items}

    audit: list[AuditRecord] = []
    changed_ids: set[str] = set()

    for rule in REMAP_RULES:
        item = by_id.get(rule.eval_id)
        if item is None:
            raise KeyError(f"eval_id không tồn tại trong qa_eval_set.json: {rule.eval_id}")
        if apply_remap(item, rule, audit):
            changed_ids.add(rule.eval_id)

    for rule in RETIRE_RULES:
        item = by_id.get(rule.eval_id)
        if item is None:
            raise KeyError(f"eval_id không tồn tại trong qa_eval_set.json: {rule.eval_id}")
        if apply_retire(item, rule, audit):
            changed_ids.add(rule.eval_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    holdout_entries = []
    for eid in PURE_STATUTORY_HOLDOUT_IDS:
        item = by_id.get(eid)
        if item is None:
            raise KeyError(f"eval_id không tồn tại trong qa_eval_set.json: {eid}")
        if apply_pure_statutory_retire(item, audit):
            changed_ids.add(eid)
        entry = build_holdout_entry(item)
        entry["migrated_at"] = now_iso
        holdout_entries.append(entry)

    # Idempotent write cho holdout file: chỉ ghi nếu nội dung THỰC SỰ khác (bỏ
    # qua migrated_at khi so sánh để tránh false-positive "changed" mỗi lần chạy).
    holdout_changed = True
    if HOLDOUT_PATH.exists():
        existing = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
        existing_no_ts = [{k: v for k, v in e.items() if k != "migrated_at"} for e in existing]
        new_no_ts = [{k: v for k, v in e.items() if k != "migrated_at"} for e in holdout_entries]
        if existing_no_ts == new_no_ts:
            holdout_changed = False
            holdout_entries = existing  # giữ nguyên migrated_at cũ, không đổi file
    if holdout_changed:
        HOLDOUT_PATH.write_text(
            json.dumps(holdout_entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if changed_ids:
        QA_EVAL_SET.write_text(json.dumps(qa_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    chunk_texts = load_chunk_texts()
    qrels_anchors_changed = sync_qrels_and_anchors(chunk_texts, audit)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / "phase_f1_migration_audit.json"
    audit_path.write_text(
        json.dumps([a.as_dict() for a in audit], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Assertion-level proof — 1 record/eval_id remap, độc lập với audit theo field
    # ở trên. Ghi LUÔN mỗi lần chạy (không chỉ khi có thay đổi) vì đây là bằng
    # chứng cho trạng thái ĐÍCH hiện tại, không phải log incremental.
    assertion_audit = [build_assertion_audit(r) for r in REMAP_RULES if r.new_relevant_chunk_ids]
    assertion_audit_path = AUDIT_DIR / "phase_f1_assertion_audit.json"
    assertion_audit_path.write_text(
        json.dumps([a.as_dict() for a in assertion_audit], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"eval_ids changed this run: {len(changed_ids)} ({sorted(changed_ids)})")
    print(f"audit records this run:    {len(audit)}")
    print(f"holdout file changed:      {holdout_changed}")
    print(f"qrels/anchors changed:     {qrels_anchors_changed}")
    print(f"audit log written to:      {audit_path.relative_to(REPO_ROOT)}")
    print(f"assertion audit ({len(assertion_audit)} records): {assertion_audit_path.relative_to(REPO_ROOT)}")
    if not changed_ids and not holdout_changed and not qrels_anchors_changed:
        print("IDEMPOTENT: 0 changes (script already applied, dataset already at target state).")


if __name__ == "__main__":
    main()
