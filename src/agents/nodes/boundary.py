"""Node gắn canonical runtime decision vào state, ngay sau khi có intent.

Đặt sau `router` chứ không phải trước: decision cần cả câu hỏi đã condense lẫn
intent để chọn đúng nhánh fallback. Node này deterministic, không gọi LLM, nên
không thêm latency hay chi phí vào luồng hiện tại và không đổi cách rẽ nhánh —
`route_by_intent` vẫn đọc `intent` như cũ.
"""

from src.agents.boundary import resolve_boundary
from src.agents.state import AgentState


def boundary_node(state: AgentState) -> dict:
    query = state.get("condensed_query") or state.get("query", "")
    decision = resolve_boundary(query, state.get("intent", "hr_question"))
    return {"boundary": decision.to_dict()}
