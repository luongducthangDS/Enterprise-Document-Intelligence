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
    print("KIỂM THỬ XÁC MINH SEMANTICS & PHÂN QUYỀN ENTERPRISE (VÒNG AUDIT 2)")
    print("Kiểm tra: AND/OR semantics, Manager cross-dept denial, System data exclusion")
    print("==================================================================\n")

    auth = get_authorization_engine()
    auth.reload()

    # -------------------------------------------------------------------------
    # 1. Test 1: Employee querying Company Policy (COMPANY_WIDE)
    # -------------------------------------------------------------------------
    print("--- 1. Test Company-wide Policy Access ---")
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
    assert len(chunks_emp) > 0, "FAIL: Employee should retrieve company policy"
    for c in chunks_emp:
        assert c["source_file"].startswith(("01", "05", "06", "07", "08", "09", "10", "11", "12", "13")), (
            f"FAIL: Employee retrieved non-company policy: {c['source_file']}"
        )
    print("✅ Test 1 PASSED: Employee truy xuất thành công COMPANY_POLICY chung (07_chinh-sach-nghi-phep.md).\n")

    # -------------------------------------------------------------------------
    # 2. Test 2: HR + HR_OPERATOR querying HR SOP (Department AND Role Match)
    # -------------------------------------------------------------------------
    print("--- 2. Test Department SOP: HR + HR_OPERATOR (AND Match) ---")
    state_hr_op = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="HR",
        user_role="HR_OPERATOR",
        history=[],
        request_id="test-hr-op-1",
    )
    res_hr_op = await retrieval_node(state_hr_op)
    chunks_hr_op = res_hr_op.get("retrieved_chunks", [])
    assert any(c["source_file"] == "02_quy-trinh-tuyen-dung.md" for c in chunks_hr_op), (
        "FAIL: HR_OPERATOR in HR department should retrieve HR SOP (02_quy-trinh-tuyen-dung.md)"
    )
    print("✅ Test 2 PASSED: HR + HR_OPERATOR truy xuất thành công SOP phòng HR.\n")

    # -------------------------------------------------------------------------
    # 3. Test 3: HR + MANAGER querying HR SOP (Department AND Role Match)
    # -------------------------------------------------------------------------
    print("--- 3. Test Department SOP: HR + MANAGER (AND Match) ---")
    state_hr_mgr = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="HR",
        user_role="MANAGER",
        history=[],
        request_id="test-hr-mgr-1",
    )
    res_hr_mgr = await retrieval_node(state_hr_mgr)
    chunks_hr_mgr = res_hr_mgr.get("retrieved_chunks", [])
    assert any(c["source_file"] == "02_quy-trinh-tuyen-dung.md" for c in chunks_hr_mgr), (
        "FAIL: MANAGER in HR department should retrieve HR SOP (02_quy-trinh-tuyen-dung.md)"
    )
    print("✅ Test 3 PASSED: HR + MANAGER truy xuất thành công SOP phòng HR.\n")

    # -------------------------------------------------------------------------
    # 4. Test 4: FINANCE + MANAGER querying HR SOP (Cross-Department DENIAL)
    # -------------------------------------------------------------------------
    print("--- 4. Test Manager Cross-Department Denial: FINANCE + MANAGER ---")
    state_fin_mgr = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="FINANCE",
        user_role="MANAGER",
        history=[],
        request_id="test-fin-mgr-1",
    )
    res_fin_mgr = await retrieval_node(state_fin_mgr)
    chunks_fin_mgr = res_fin_mgr.get("retrieved_chunks", [])
    for c in chunks_fin_mgr:
        assert c["source_file"] not in ("02_quy-trinh-tuyen-dung.md", "03_quy-trinh-onboarding.md", "04_quy-trinh-offboarding.md"), (
            f"FAIL: Finance Manager accessed HR internal SOP: {c['source_file']}"
        )
    print("✅ Test 4 PASSED: FINANCE + MANAGER BỊ CHẶN hoàn toàn khỏi SOP phòng HR (Chứng minh MANAGER không được cấp quyền xuyên phòng ban).\n")

    # -------------------------------------------------------------------------
    # 5. Test 5: FINANCE + HR_OPERATOR querying HR SOP (Department mismatch DENIAL)
    # -------------------------------------------------------------------------
    print("--- 5. Test Role Cross-Department Denial: FINANCE + HR_OPERATOR ---")
    state_fin_hrop = AgentState(
        query="Quy trình tuyển dụng và các vòng phỏng vấn ứng viên của phòng nhân sự?",
        department="FINANCE",
        user_role="HR_OPERATOR",
        history=[],
        request_id="test-fin-hrop-1",
    )
    res_fin_hrop = await retrieval_node(state_fin_hrop)
    chunks_fin_hrop = res_fin_hrop.get("retrieved_chunks", [])
    for c in chunks_fin_hrop:
        assert c["source_file"] not in ("02_quy-trinh-tuyen-dung.md", "03_quy-trinh-onboarding.md", "04_quy-trinh-offboarding.md"), (
            f"FAIL: User with department=FINANCE accessed HR internal SOP: {c['source_file']}"
        )
    print("✅ Test 5 PASSED: FINANCE + HR_OPERATOR BỊ CHẶN khỏi SOP phòng HR (Yêu cầu cả Department AND Role).\n")

    # -------------------------------------------------------------------------
    # 6. Test 6: LEGAL Domain Pending Review (Fail-closed)
    # -------------------------------------------------------------------------
    print("--- 6. Test LEGAL Pending Review (related_depts=['HR'], authorized_depts=[]) ---")
    state_hr_legal = AgentState(
        query="Bộ luật Lao động 2019 quy định thời gian thử việc tối đa là bao nhiêu ngày?",
        department="HR",
        user_role="HR_OPERATOR",
        history=[],
        request_id="test-hr-legal-1",
    )
    res_hr_legal = await retrieval_node(state_hr_legal)
    chunks_hr_legal = res_hr_legal.get("retrieved_chunks", [])
    for c in chunks_hr_legal:
        assert "bộ luật lao động" not in c["source_file"].lower(), (
            f"FAIL: HR Employee accessed LEGAL doc despite authorized_departments=[]! {c['source_file']}"
        )
    print("✅ Test 6 PASSED: LEGAL doc ở trạng thái PENDING_REVIEW bị chặn 100% (Fail-closed).\n")

    # -------------------------------------------------------------------------
    # 7. Test 7: EXTERNAL_REFERENCE Domain Restricted
    # -------------------------------------------------------------------------
    print("--- 7. Test EXTERNAL_REFERENCE Domain Restricted ---")
    state_emp_ext = AgentState(
        query="Mẫu quy định nội bộ VinFast 2019 hoặc mẫu tuyển dụng Base.vn",
        department="GENERAL",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-emp-ext-1",
    )
    res_emp_ext = await retrieval_node(state_emp_ext)
    chunks_emp_ext = res_emp_ext.get("retrieved_chunks", [])
    for c in chunks_emp_ext:
        assert not (c["source_file"].startswith(("1050517962-VF", "842059170-18", "[Base.vn]", "base_", "mau_"))), (
            f"FAIL: Employee accessed EXTERNAL_REFERENCE: {c['source_file']}"
        )
    print("✅ Test 7 PASSED: Employee BỊ CHẶN khỏi tài liệu tham khảo ngoại bộ.\n")

    # -------------------------------------------------------------------------
    # 8. Test 8: SYSTEM / INTERNAL DATA Exclusion
    # -------------------------------------------------------------------------
    print("--- 8. Test System & Evaluation Data Exclusion ---")
    state_sys_query = AgentState(
        query="qa_eval_set ground truth personas ticket routing rules",
        department="GENERAL",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-sys-query-1",
    )
    res_sys_query = await retrieval_node(state_sys_query)
    chunks_sys_query = res_sys_query.get("retrieved_chunks", [])
    for c in chunks_sys_query:
        assert c["source_file"] not in ("qa_eval_set.json", "mock_user_personas.json", "ticket_routing_rules.json"), (
            f"FAIL: System / Evaluation data leaked into retrieval: {c['source_file']}"
        )
    print("✅ Test 8 PASSED: System / Evaluation data bị loại trừ hoàn toàn khỏi retrieval.\n")

    # -------------------------------------------------------------------------
    # 9. Test 9: ADMIN Global Override
    # -------------------------------------------------------------------------
    print("--- 9. Test Admin Global Override ---")
    u_admin = UserContext(user_id="admin_user", department="IT", role=UserRole.ADMIN)
    files_admin_active = auth.get_authorized_source_files(u_admin, include_disabled=False)
    files_admin_all = auth.get_authorized_source_files(u_admin, include_disabled=True)
    print(f"Số tài liệu Active Knowledge Admin được truy xuất trong RAG: {len(files_admin_active)} (Kỳ vọng: 41)")
    # Admin được phép truy cập 41 active knowledge documents trong RAG
    # và quản trị toàn bộ 55 tài liệu (bao gồm 10 EXTERNAL + 4 SYSTEM)
    assert len(files_admin_active) == 41, f"FAIL: Admin should access 41 active knowledge documents, got {len(files_admin_active)}"
    assert len(files_admin_all) == 55, f"FAIL: Admin should administer 55 total inventory documents, got {len(files_admin_all)}"
    print("✅ Test 9 PASSED: Admin có toàn quyền truy xuất đúng phạm vi 41 active docs.\n")

    print("==================================================================")
    print("🎉 TOÀN BỘ 9 BÀI TEST SEMANTICS & PHÂN QUYỀN ĐỀU ĐẠT CHUẨN (100% PASS)!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_semantic_acl_tests())
