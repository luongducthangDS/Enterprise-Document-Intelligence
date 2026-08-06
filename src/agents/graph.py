from langgraph.graph import END, StateGraph

from src.agents.nodes.escalation import confidence_node, escalate_node
from src.agents.nodes.generation import finalize_node, generate_node, hallucination_check_node
from src.agents.nodes.retrieval import grade_node, retrieval_node, rewrite_node
from src.agents.nodes.router import clarify_node, direct_node, router_node
from src.agents.state import AgentState
from src.config import get_settings


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "hr_question")
    if intent == "greeting":
        return "direct"
    if intent == "ambiguous":
        return "clarify"
    if intent == "out_of_scope_or_personal":
        return "escalate"
    return "retrieve"


def route_after_grade(state: AgentState) -> str:
    settings = get_settings()
    if state.get("retrieved_chunks"):
        return "generate"
    if state.get("rewrite_count", 0) >= settings.max_rewrite_retries:
        # Hết lượt rewrite mà vẫn không có chunk liên quan — vẫn generate, model
        # sẽ tự nhận "chưa đủ thông tin" (xem _GENERATE_SYSTEM), confidence_node
        # phía sau sẽ escalate vì không có chunk nào.
        return "generate"
    return "rewrite"


def route_after_hallucination(state: AgentState) -> str:
    settings = get_settings()
    if state.get("hallucination_passed", True):
        return "confidence"
    if state.get("hallucination_retry_count", 0) >= settings.max_hallucination_retries:
        return "confidence"
    return "generate"


def route_after_confidence(state: AgentState) -> str:
    return "escalate" if state.get("escalate") else "finalize"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("direct", direct_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("grade", grade_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("generate", generate_node)
    graph.add_node("hallucination_check", hallucination_check_node)
    graph.add_node("confidence", confidence_node)
    graph.add_node("escalate_ticket", escalate_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {"direct": "direct", "clarify": "clarify", "escalate": "escalate_ticket", "retrieve": "retrieve"},
    )
    graph.add_edge("direct", END)
    graph.add_edge("clarify", END)

    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route_after_grade, {"generate": "generate", "rewrite": "rewrite"})
    graph.add_edge("rewrite", "retrieve")

    graph.add_edge("generate", "hallucination_check")
    graph.add_conditional_edges(
        "hallucination_check",
        route_after_hallucination,
        {"confidence": "confidence", "generate": "generate"},
    )

    graph.add_conditional_edges(
        "confidence", route_after_confidence, {"escalate": "escalate_ticket", "finalize": "finalize"}
    )
    graph.add_edge("escalate_ticket", END)
    graph.add_edge("finalize", END)

    return graph.compile()


agent = build_graph()
