import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from src.agents.nodes.retrieval import retrieval_node
from src.agents.state import AgentState


async def run_tests():
    print("==================================================================")
    print("KIỂM THỬ PHÂN QUYỀN TRUY CẬP THEO PHÒNG BAN & DOMAIN LEGAL")
    print("==================================================================\n")

    # 1. Test General Employee
    print("--- 1. Test General Employee (department='GENERAL') ---")
    state_gen = AgentState(
        query="Chính sách nghỉ phép của công ty quy định bao nhiêu ngày phép năm?",
        department="GENERAL",
        history=[],
        request_id="test-gen-1",
    )
    res_gen = await retrieval_node(state_gen)
    chunks_gen = res_gen.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_gen)}")
    for i, c in enumerate(chunks_gen[:3]):
        print(f"[{i+1}] {c['source_file']} | Title: {c['title']}")
    # Assert all retrieved chunks are strictly company policies
    for c in chunks_gen:
        assert c["source_file"].startswith(("01", "05", "06", "07", "08", "09", "10", "11", "12", "13")), (
            f"FAIL: General employee retrieved non-company policy: {c['source_file']}"
        )
    print("✅ General Employee test PASSED: Chỉ truy xuất COMPANY_POLICY chung.\n")

    # 2. Test HR Employee
    print("--- 2. Test HR Employee (department='HR') ---")
    state_hr = AgentState(
        query="Quy trình tuyển dụng và phỏng vấn ứng viên của phòng nhân sự?",
        department="HR",
        history=[],
        request_id="test-hr-1",
    )
    res_hr = await retrieval_node(state_hr)
    chunks_hr = res_hr.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_hr)}")
    for i, c in enumerate(chunks_hr[:3]):
        print(f"[{i+1}] {c['source_file']} | Title: {c['title']}")
    assert any(c["source_file"] == "02_quy-trinh-tuyen-dung.md" for c in chunks_hr), (
        "FAIL: HR employee failed to retrieve HR recruitment SOP!"
    )
    print("✅ HR Employee SOP test PASSED: Truy xuất được quy trình nghiệp vụ HR.\n")

    # 3. Test Finance Employee querying PIT Tax Law
    print("--- 3. Test Finance Employee (department='FINANCE') ---")
    state_fin = AgentState(
        query="Luật Thuế thu nhập cá nhân quy định mức giảm trừ gia cảnh cho người phụ thuộc?",
        department="FINANCE",
        history=[],
        request_id="test-fin-1",
    )
    res_fin = await retrieval_node(state_fin)
    chunks_fin = res_fin.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_fin)}")
    for i, c in enumerate(chunks_fin[:3]):
        print(f"[{i+1}] {c['source_file']} | Title: {c['title']}")
    assert any("luat_thue_tncn" in c["source_file"] for c in chunks_fin), (
        "FAIL: Finance employee failed to retrieve Tax Law!"
    )
    # Check that HR SOPs are not in Finance result
    for c in chunks_fin:
        assert c["source_file"] not in ("02_quy-trinh-tuyen-dung.md", "03_quy-trinh-onboarding.md", "04_quy-trinh-offboarding.md"), (
            f"FAIL: Finance employee retrieved HR internal SOP: {c['source_file']}"
        )
    print("✅ Finance Employee test PASSED: Truy xuất được Luật Thuế và bị chặn khỏi HR SOP.\n")

    # 4. Test Engineering Employee querying Workplace Safety Law
    print("--- 4. Test Engineering Employee (department='ENGINEERING') ---")
    state_eng = AgentState(
        query="Luật An toàn vệ sinh lao động quy định trách nhiệm trang bị bảo hộ lao động?",
        department="ENGINEERING",
        history=[],
        request_id="test-eng-1",
    )
    res_eng = await retrieval_node(state_eng)
    chunks_eng = res_eng.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_eng)}")
    for i, c in enumerate(chunks_eng[:3]):
        print(f"[{i+1}] {c['source_file']} | Title: {c['title']}")
    assert any("luat_an_toan_ve_sinh_lao_dong" in c["source_file"] for c in chunks_eng), (
        "FAIL: Engineering employee failed to retrieve Workplace Safety Law!"
    )
    # Check that Tax Law is not in Engineering result
    for c in chunks_eng:
        assert "luat_thue_tncn" not in c["source_file"], (
            f"FAIL: Engineering employee retrieved Tax Law: {c['source_file']}"
        )
    print("✅ Engineering Employee test PASSED: Truy xuất được Luật ATVSLĐ và bị chặn khỏi Luật Thuế / HR SOP.\n")

    print("==================================================================")
    print("🎉 TẤT CẢ 4 KỊCH BẢN PHÂN QUYỀN PHÒNG BAN ĐỀU ĐẠT CHUẨN!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
