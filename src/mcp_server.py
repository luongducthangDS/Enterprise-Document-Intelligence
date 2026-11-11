"""MCP server (stdio) cho Claude Desktop / Claude Code / Cursor.

    python -m src.mcp_server

Danh tính lấy từ biến môi trường của người cài server (MCP_TENANT_ID,
MCP_USER_ID, MCP_DEPARTMENT, MCP_ROLE), KHÔNG từ tham số tool: model gọi tool
không được tự chọn mình là ai, nên ACL phòng ban vẫn fail-closed như qua API.
"""

import contextlib
import os
import sys

from mcp.server import MCPServer

os.environ.setdefault("AGENT_MODE", "react")

from src.agents.tools import REGISTRY, QueryArgs  # noqa: E402

server = MCPServer(
    "enterprise-docs",
    instructions="Hỏi đáp có trích dẫn trên kho tài liệu nội bộ (HR, Kế toán, Sản phẩm) của NexaTech.",
)


def _identity() -> dict:
    return {
        "tenant_id": os.environ.get("MCP_TENANT_ID", "nexatech"),
        "user_id": os.environ.get("MCP_USER_ID", "mcp-user"),
        "department": os.environ.get("MCP_DEPARTMENT", "HR"),
        "user_role": os.environ.get("MCP_ROLE", "EMPLOYEE"),
    }


@server.tool()
async def ask_documents(question: str) -> dict:
    """Hỏi về chính sách/quy trình nội bộ. Trả câu trả lời kèm nguồn trích dẫn;
    state=ABSTAIN nghĩa là tài liệu không đủ hoặc cần người phụ trách (xem ticket)."""
    # Agent in log ra stdout; với stdio, stdout là kênh giao thức MCP nên phải đẩy log sang stderr.
    with contextlib.redirect_stdout(sys.stderr):
        from src.agents.service import answer

        a = await answer(question, identity=_identity())
    return {
        "answer": a.response,
        "state": a.state,
        "confidence": a.confidence_score,
        "citations": [
            {"title": c.title, "section": c.source_section, "excerpt": c.excerpt} for c in a.citations
        ],
        "ticket": a.ticket_draft.model_dump() if a.ticket_draft else None,
    }


@server.tool(description=REGISTRY["search_policies"].description)
async def search_policies(query: str) -> dict:
    """Cùng hợp đồng (schema, ACL) với tool agent dùng; client MCP tự lập luận trên đoạn trích."""
    QueryArgs(query=query)  # cùng schema agent dùng: query rỗng/quá dài bị từ chối trước khi chạm retrieval
    with contextlib.redirect_stdout(sys.stderr):
        from src.agents.nodes.react import _search

        res = await _search({**_identity(), "query": query}, query)
    if res.get("access_denied_reason"):
        return {"denied": res["access_denied_reason"], "chunks": []}
    return {
        "chunks": [
            {"title": c.get("title"), "section": c.get("heading_path"), "source_file": c.get("source_file"), "text": c.get("text")}
            for c in res.get("retrieved_chunks", [])
        ]
    }


if __name__ == "__main__":
    server.run("stdio")
