import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from src.agents.nodes.retrieval import retrieval_node
from src.agents.state import AgentState
from src.security.authorization import get_authorization_engine
from src.security.models import UserContext, UserRole


async def run_semantic_acl_tests():
    print("==================================================================")
    print("KIỂM THỬ XÁC MINH SEMANTICS & PHÂN QUYỀN ENTERPRISE")
    print("Mục tiêu: Chứng minh related_departments != authorized_departments")
    print("==================================================================\n")

    auth = get_authorization_engine()
    auth.reload()

    # 1. Test 1: Employee querying Company Policy
    print("--- 1. Test Employee querying COMPANY_POLICY ---")
    state_emp = AgentState(
        query="Chính sách nghỉ phép của công ty quy định bao nhiêu ngày phép năm?",
        department="GENERAL",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-emp-1",
    )
    res_emp = await retrieval_node(state_emp)
    chunks_emp = res_emp.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_emp)}")
    for i, c in enumerate(chunks_emp[:2]):
        print(f"  [{i+1}] {c['source_file']} | Title: {c['title']}")
    assert len(chunks_emp) > 0, "FAIL: Employee should retrieve company policy"
    for c in chunks_emp:
        assert c["source_file"].startswith(("01", "05", "06", "07", "08", "09", "10", "11", "12", "13")), (
            f"FAIL: Employee retrieved non-company policy: {c['source_file']}"
        )
    print("✅ Test 1 PASSED: Employee chỉ truy xuất COMPANY_POLICY chung.\n")

    # 2. Test 2: HR Employee querying Legal Doc (Labor Code) where related_departments=['HR'] but authorized_departments=[]
    print("--- 2. Test HR Employee querying LEGAL (related_departments=['HR'], authorized_departments=[]) ---")
    state_hr_legal = AgentState(
        query="Bộ luật Lao động 2019 quy định thời gian thử việc tối đa là bao nhiêu ngày?",
        department="HR",
        user_role="HR_OPERATOR",
        history=[],
        request_id="test-hr-legal-1",
    )
    res_hr_legal = await retrieval_node(state_hr_legal)
    chunks_hr_legal = res_hr_legal.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_hr_legal)}")
    for i, c in enumerate(chunks_hr_legal[:2]):
        print(f"  [{i+1}] {c['source_file']} | Title: {c['title']}")
    # Assert that NO chunk from 'bộ luật lao động.pdf' is returned because authorized_departments=[] (PENDING_REVIEW)
    for c in chunks_hr_legal:
        assert "bộ luật lao động" not in c["source_file"].lower(), (
            f"FAIL: HR Employee accessed LEGAL doc despite authorized_departments=[]! Leakage via related_departments: {c['source_file']}"
        )
    print("✅ Test 2 PASSED: HR Employee BỊ CHẶN khỏi Bộ luật Lao động vì authorized_departments=[] (chứng minh related_departments KHÔNG cấp quyền).\n")

    # 3. Test 3: Finance Employee querying Tax Law where related_departments=['FINANCE'] but authorized_departments=[]
    print("--- 3. Test Finance Employee querying LEGAL (related_departments=['FINANCE'], authorized_departments=[]) ---")
    state_fin_legal = AgentState(
        query="Luật Thuế thu nhập cá nhân quy định mức giảm trừ gia cảnh là bao nhiêu?",
        department="FINANCE",
        user_role="FINANCE_OFFICER",
        history=[],
        request_id="test-fin-legal-1",
    )
    res_fin_legal = await retrieval_node(state_fin_legal)
    chunks_fin_legal = res_fin_legal.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_fin_legal)}")
    for i, c in enumerate(chunks_fin_legal[:2]):
        print(f"  [{i+1}] {c['source_file']} | Title: {c['title']}")
    for c in chunks_fin_legal:
        assert "luat_thue_tncn" not in c["source_file"].lower(), (
            f"FAIL: Finance Employee accessed Tax Law despite authorized_departments=[]! {c['source_file']}"
        )
    print("✅ Test 3 PASSED: Finance Employee BỊ CHẶN khỏi Luật Thuế TNCN vì chưa có quyết định cấp quyền.\n")

    # 4. Test 4: HR Employee querying HR Department SOP (02_quy-trinh-tuyen-dung) where authorized_departments=['HR']
    print("--- 4. Test HR Employee querying HR SOP (authorized_departments=['HR']) ---")
    state_hr_sop = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="HR",
        user_role="HR_OPERATOR",
        history=[],
        request_id="test-hr-sop-1",
    )
    res_hr_sop = await retrieval_node(state_hr_sop)
    chunks_hr_sop = res_hr_sop.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_hr_sop)}")
    for i, c in enumerate(chunks_hr_sop[:2]):
        print(f"  [{i+1}] {c['source_file']} | Title: {c['title']}")
    assert any(c["source_file"] == "02_quy-trinh-tuyen-dung.md" for c in chunks_hr_sop), (
        "FAIL: HR Employee should retrieve HR SOP (02_quy-trinh-tuyen-dung.md)"
    )
    print("✅ Test 4 PASSED: HR Employee truy xuất thành công SOP phòng ban của mình.\n")

    # 5. Test 5: Finance Employee querying HR SOP -> Must be BLOCKED
    print("--- 5. Test Finance Employee querying HR SOP ---")
    state_fin_sop = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="FINANCE",
        user_role="FINANCE_OFFICER",
        history=[],
        request_id="test-fin-sop-1",
    )
    res_fin_sop = await retrieval_node(state_fin_sop)
    chunks_fin_sop = res_fin_sop.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_fin_sop)}")
    for c in chunks_fin_sop:
        assert c["source_file"] not in ("02_quy-trinh-tuyen-dung.md", "03_quy-trinh-onboarding.md", "04_quy-trinh-offboarding.md"), (
            f"FAIL: Finance Employee accessed HR internal SOP: {c['source_file']}"
        )
    print("✅ Test 5 PASSED: Finance Employee BỊ CHẶN hoàn toàn khỏi SOP phòng HR.\n")

    # 6. Test 6: External Reference blocked by default for Employee
    print("--- 6. Test Employee querying EXTERNAL_REFERENCE (VinFast 2019 / Base.vn) ---")
    state_emp_ext = AgentState(
        query="Mẫu quy định nội bộ VinFast 2019 hoặc mẫu tuyển dụng Base.vn",
        department="GENERAL",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-emp-ext-1",
    )
    res_emp_ext = await retrieval_node(state_emp_ext)
    chunks_emp_ext = res_emp_ext.get("retrieved_chunks", [])
    print(f"Số chunk lấy được: {len(chunks_emp_ext)}")
    for c in chunks_emp_ext:
        assert not (c["source_file"].startswith(("1050517962-VF", "842059170-18", "[Base.vn]", "base_", "mau_"))), (
            f"FAIL: Employee accessed EXTERNAL_REFERENCE: {c['source_file']}"
        )
    print("✅ Test 6 PASSED: Employee BỊ CHẶN khỏi tài liệu tham khảo ngoại bộ.\n")

    # 7. Test 7: Admin querying EXTERNAL_REFERENCE -> Allowed
    print("--- 7. Test Admin querying full knowledge base ---")
    u_admin = UserContext(user_id="admin_user", department="IT", role=UserRole.ADMIN)
    files_admin = auth.get_authorized_source_files(u_admin)
    print(f"Số tài liệu Admin được phép truy xuất: {len(files_admin)}")
    assert len(files_admin) == 36, f"FAIL: Admin should access all 36 documents, got {len(files_admin)}"
    print("✅ Test 7 PASSED: Admin có toàn quyền truy xuất (36 tài liệu).\n")

    print("==================================================================")
    print("🎉 TOÀN BỘ 7 KỊCH BẢN KIỂM THỬ SEMANTICS & ACL ĐỀU ĐẠT CHUẨN!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_semantic_acl_tests())
