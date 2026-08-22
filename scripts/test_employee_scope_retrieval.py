
__test__ = False

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from src.agents.nodes.retrieval import retrieval_node
from src.agents.state import AgentState


async def test_employee_scope():
    # Test 1: Employee queries company WFH policy
    state_employee = AgentState(
        query="Chính sách làm việc từ xa WFH của công ty quy định thế nào?",
        department="Engineering",
        history=[],
        request_id="test-employee-general",
    )
    res = await retrieval_node(state_employee)
    chunks = res.get("retrieved_chunks", [])
    print(f"=== Test 1: Employee Query (WFH Policy) ===")
    print(f"Số chunk lấy được: {len(chunks)}")
    for i, c in enumerate(chunks[:3]):
        print(f"[{i+1}] {c['source_file']} | Category: {c.get('category')} | Score: {c.get('score', 0):.4f}")
    
    # Assert all retrieved chunks are strictly GENERAL
    general_files = [
        "01_chinh-sach-lam-them-gio-OT.md",
        "05_chinh-sach-lam-viec-tu-xa.md",
        "06_chinh-sach-dao-tao-phat-trien.md",
        "07_chinh-sach-nghi-phep.md",
        "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md",
        "09_chinh-sach-bao-hiem-xa-hoi-bat-buoc.md",
        "10_chinh-sach-an-toan-ve-sinh-lao-dong.md",
        "11_chinh-sach-danh-gia-hieu-suat-kpi.md",
        "12_quy-che-cong-tac-phi.md",
        "13_noi-quy-lao-dong-va-ky-luat.md",
    ]
    for c in chunks:
        assert c["source_file"] in general_files, f"FAIL: {c['source_file']} không thuộc GENERAL!"
    print("✅ Test 1 PASSED: Chỉ có tài liệu GENERAL được retrieve!\n")

    # Test 2: Employee queries legal question without permission
    state_legal = AgentState(
        query="Điều 25 Bộ luật Lao động quy định thời gian thử việc tối đa là bao lâu?",
        department="Engineering",
        history=[],
        request_id="test-employee-legal",
    )
    res_legal = await retrieval_node(state_legal)
    chunks_legal = res_legal.get("retrieved_chunks", [])
    print(f"=== Test 2: Employee Query on Legal Question (Without Permission) ===")
    print(f"Số chunk lấy được: {len(chunks_legal)}")
    for i, c in enumerate(chunks_legal[:3]):
        print(f"[{i+1}] {c['source_file']} | Title: {c.get('title')}")
    # Verify no legal files retrieved
    for c in chunks_legal:
        assert not c["source_file"].endswith(".pdf") or "bộ luật" not in c["source_file"], "FAIL: Legal document leaked into employee scope!"
    print("✅ Test 2 PASSED: Tài liệu LEGAL không bị rò rỉ vào Employee Scope!\n")


if __name__ == "__main__":
    asyncio.run(test_employee_scope())
