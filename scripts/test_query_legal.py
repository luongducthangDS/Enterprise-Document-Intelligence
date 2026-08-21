import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from src.agents.nodes.retrieval import retrieval_node
from src.agents.state import AgentState


async def main():
    state = AgentState(
        query="Thời gian thử việc tối đa theo Bộ luật lao động là bao lâu?",
        department="HR",
        history=[],
        request_id="test-legal-retrieval",
    )
    res = await retrieval_node(state)
    chunks = res.get("retrieved_chunks", [])
    print(f"Tổng số chunks truy xuất được: {len(chunks)}")
    for i, c in enumerate(chunks[:3]):
        print(f"\n[{i+1}] Nguồn: {c['source_file']} | Authority: {c['authority']} | Score: {c.get('score', 0):.4f}")
        print(f"    Nội dung: {c['text'][:150]}...")


if __name__ == "__main__":
    asyncio.run(main())
