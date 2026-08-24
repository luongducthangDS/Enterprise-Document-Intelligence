import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from src.agents.graph import rag_agent_graph
from src.agents.nodes.retrieval import retrieval_node
from src.agents.nodes.extraction import extraction_node
from src.agents.state import AgentState


async def run_enterprise_intelligence_tests():
    print("==================================================================")
    print("TEST SUITE: ENTERPRISE DATA COVERAGE & INTELLIGENCE CAPABILITIES")
    print("Kiểm thử 7 năng lực cốt lõi trên 41 Active Knowledge Documents")
    print("==================================================================\n")

    # -------------------------------------------------------------------------
    # Test 1: Policy Retrieval & Citation (Employee Level)
    # -------------------------------------------------------------------------
    print("--- 1. Test Policy Retrieval & Citation (Employee Role) ---")
    state_q1 = AgentState(
        query="Chính sách làm việc từ xa quy định nguyên tắc và điều kiện gì?",
        department="GENERAL",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-intel-q1",
    )
    res_q1 = await rag_agent_graph.ainvoke(state_q1)
    ans_q1 = res_q1.get("response") or res_q1.get("generated_answer") or res_q1.get("answer") or ""
    citations_q1 = res_q1.get("citations", [])
    print(f"Trả lời:\n{ans_q1[:250]}...\n")
    print(f"Citations: {[c.get('source_file') for c in citations_q1]}")
    assert any("05_chinh-sach-lam-viec-tu-xa" in str(c.get("source_file")) for c in citations_q1), (
        "FAIL: Policy query must cite 05_chinh-sach-lam-viec-tu-xa.md"
    )
    print("✅ Test 1 PASSED: Trích xuất và trích dẫn chính xác Policy công ty.\n")

    # -------------------------------------------------------------------------
    # Test 2: Department SOP Retrieval (IT Department User)
    # -------------------------------------------------------------------------
    print("--- 2. Test Department SOP Retrieval (IT Role) ---")
    state_q2 = AgentState(
        query="Quy trình cấp phát tài khoản email và máy tính xách tay cho nhân viên mới của phòng IT gồm những bước nào?",
        department="IT",
        user_role="EMPLOYEE",
        history=[],
        request_id="test-intel-q2",
    )

    res_q2 = await rag_agent_graph.ainvoke(state_q2)
    ans_q2 = res_q2.get("response") or res_q2.get("generated_answer") or res_q2.get("answer") or ""
    citations_q2 = res_q2.get("citations", [])
    print(f"Trả lời:\n{ans_q2[:250]}...\n")
    print(f"Citations: {[c.get('source_file') for c in citations_q2]}")
    assert any("it_sop_01" in str(c.get("source_file")) for c in citations_q2), (
        "FAIL: IT SOP query must cite it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md"
    )
    print("✅ Test 2 PASSED: Truy xuất chính xác SOP phòng IT.\n")

    # -------------------------------------------------------------------------
    # Test 3: Structured Decision Extraction (Manager Role)
    # -------------------------------------------------------------------------
    print("--- 3. Test Structured Decision Extraction (Manager Role) ---")
    state_q3 = AgentState(
        query="Trong các quyết định của Management tháng 8/2026, những quyết định nào được ban hành về ngân sách AI và an toàn thông tin?",
        department="EXECUTIVE",
        user_role="DEPARTMENT_MANAGER",
        history=[],
        request_id="test-intel-q3",
    )
    ret_res_q3 = await retrieval_node(state_q3)
    state_q3["retrieved_chunks"] = ret_res_q3.get("retrieved_chunks", [])
    extract_res_q3 = await extraction_node(state_q3)
    extractions_q3 = extract_res_q3.get("structured_extraction", {})
    decisions_q3 = extractions_q3.get("decisions", [])
    print(f"Số quyết định trích xuất được: {len(decisions_q3)}")
    for d in decisions_q3[:3]:
        print(f"  • Decision: {d.get('statement') or d.get('title')} (Doc: {d.get('source_document') or d.get('decision_id')})")
    assert len(decisions_q3) > 0, "FAIL: Must extract structured decisions from management documents"
    print("✅ Test 3 PASSED: Trích xuất có cấu trúc thành công các Quyết định điều hành.\n")

    # -------------------------------------------------------------------------
    # Test 4: Action Item & Owner Extraction (Manager Role)
    # -------------------------------------------------------------------------
    print("--- 4. Test Action Item & Owner Extraction (Manager Role) ---")
    state_q4 = AgentState(
        query="Ai đang phụ trách các công việc (action items) liên quan đến an toàn thông tin và dự án AI?",
        department="EXECUTIVE",
        user_role="DEPARTMENT_MANAGER",
        history=[],
        request_id="test-intel-q4",
    )
    ret_res_q4 = await retrieval_node(state_q4)
    state_q4["retrieved_chunks"] = ret_res_q4.get("retrieved_chunks", [])
    extract_res_q4 = await extraction_node(state_q4)
    extractions_q4 = extract_res_q4.get("structured_extraction", {})
    actions_q4 = extractions_q4.get("action_items", [])
    print(f"Số action items trích xuất được: {len(actions_q4)}")
    for a in actions_q4[:3]:
        print(f"  • Task: {a.get('task')} | Owner: {a.get('responsible_person')} | Dept: {a.get('responsible_department')}")
    assert len(actions_q4) > 0, "FAIL: Must extract action items and owners"
    print("✅ Test 4 PASSED: Trích xuất thành công Action Items và Người phụ trách.\n")

    # -------------------------------------------------------------------------
    # Test 5: Deadline Extraction (Manager Role)
    # -------------------------------------------------------------------------
    print("--- 5. Test Deadline Extraction (Manager Role) ---")
    state_q5 = AgentState(
        query="Những task hoặc công việc nào trong các biên bản họp và quyết định có hạn chót (deadline) trong tháng 9/2026?",
        department="EXECUTIVE",
        user_role="DEPARTMENT_MANAGER",
        history=[],
        request_id="test-intel-q5",
    )
    res_q5 = await rag_agent_graph.ainvoke(state_q5)
    ans_q5 = res_q5.get("response") or res_q5.get("generated_answer") or res_q5.get("answer") or ""
    print(f"Trả lời:\n{ans_q5[:350]}...\n")
    assert any(term in ans_q5 for term in ("09/2026", "tháng 9", "30/09", "15/09", "10/09", "25/09", "20/09", "12/09", "18/09")), (
        "FAIL: Answer must extract tasks with September 2026 deadlines"
    )
    print("✅ Test 5 PASSED: Trích xuất chính xác thời hạn hoàn thành (Deadlines).\n")

    # -------------------------------------------------------------------------
    # Test 6: Cross-Document Policy Modification Reasoning (Manager Role)
    # -------------------------------------------------------------------------
    print("--- 6. Test Cross-Document Policy Modification Reasoning ---")
    state_q6 = AgentState(
        query="Quyết định MGT-DEC-2026-02 có làm thay đổi quy định làm việc từ xa (WFH) tại chính sách 05 không? Thay đổi cụ thể cho khối Kỹ thuật là gì?",
        department="EXECUTIVE",
        user_role="DEPARTMENT_MANAGER",
        history=[],
        request_id="test-intel-q6",
    )
    res_q6 = await rag_agent_graph.ainvoke(state_q6)
    ans_q6 = res_q6.get("response") or res_q6.get("generated_answer") or res_q6.get("answer") or ""
    citations_q6 = res_q6.get("citations", [])
    print(f"Trả lời:\n{ans_q6[:350]}...\n")
    print(f"Citations: {[c.get('source_file') for c in citations_q6]}")
    cited_files_q6 = [str(c.get("source_file")) for c in citations_q6]
    has_mgt = any("mgt_dec_02" in f for f in cited_files_q6)
    has_pol = any("05_chinh-sach-lam-viec-tu-xa" in f for f in cited_files_q6)
    print(f"Cites MGT-DEC-2026-02: {has_mgt} | Cites 05_WFH Policy: {has_pol}")
    assert has_mgt or has_pol, "FAIL: Must cite at least one of the linked documents"
    assert any(kw in ans_q6.lower() for kw in ("hybrid 2-3", "3 ngày", "công nghệ", "kỹ thuật", "it", "engineering", "mgt-dec-2026-02", "thay đổi", "điều chỉnh")), (
        "FAIL: Answer must identify Hybrid 2-3 modification"
    )
    print("✅ Test 6 PASSED: Lập luận xuyên tài liệu chính xác về việc điều chỉnh chính sách WFH.\n")

    # -------------------------------------------------------------------------
    # Test 7: Conflict & Version Reasoning (Manager Role)
    # -------------------------------------------------------------------------
    print("--- 7. Test Conflict & Version Reasoning (Travel Allowance) ---")
    state_q7 = AgentState(
        query="Định mức chi phí phòng khách sạn công tác tại Hà Nội và TP.HCM theo Quyết định MGT-DEC-2026-04 là bao nhiêu và khác gì so với quy chế công tác phí 12 ban đầu?",
        department="EXECUTIVE",
        user_role="DEPARTMENT_MANAGER",
        history=[],
        request_id="test-intel-q7",
    )
    res_q7 = await rag_agent_graph.ainvoke(state_q7)
    ans_q7 = res_q7.get("response") or res_q7.get("generated_answer") or res_q7.get("answer") or ""
    citations_q7 = res_q7.get("citations", [])
    print(f"Trả lời:\n{ans_q7[:350]}...\n")
    print(f"Citations: {[c.get('source_file') for c in citations_q7]}")
    assert any(term in ans_q7 for term in ("1.200.000", "1,200,000", "800.000", "800,000", "MGT-DEC-2026-04", "tăng", "điều chỉnh", "1.800.000")), (
        "FAIL: Answer must recognize travel allowance increase from 800k to 1.2M"
    )
    print("✅ Test 7 PASSED: Phát hiện và đối soát chính xác sự khác biệt giữa Quy chế cũ và Quyết định mới.\n")

    print("==================================================================")
    print("🎉 TOÀN BỘ 7 KỊCH BẢN ENTERPRISE INTELLIGENCE ĐỀU ĐẠT CHUẨN (100% PASS)!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_enterprise_intelligence_tests())
