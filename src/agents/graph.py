from langgraph.graph import END, StateGraph

from src.agents.nodes.boundary import boundary_node
from src.agents.nodes.condense import condense_node
from src.agents.nodes.escalation import confidence_node, department_access_denied_node, escalate_node, out_of_scope_node
from src.agents.nodes.generation import finalize_node, generate_node, hallucination_check_node
from src.agents.nodes.knowledge_lookup import knowledge_lookup_node
from src.agents.nodes.retrieval import grade_node, retrieval_node, rewrite_node
from src.agents.nodes.router import clarify_node, condense_and_route_node, direct_node, router_node
from src.agents.state import AgentState
from src.config import get_settings


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "hr_question")
    if intent == "greeting":
        return "direct"
    if intent == "ambiguous":
        return "clarify"
    # Routing precedence priority 2 (NexaTech Type-C contract v3.1.0): pure
    # statutory/legal intent bypasses retrieval hoàn toàn — không đi qua nhánh
    # escalate/ticket, có node riêng với response cố định.
    if intent == "pure_statutory":
        return "out_of_scope"
    if intent == "out_of_scope_or_personal":
        return "escalate"
    return "retrieve"


def route_after_knowledge_lookup(state: AgentState) -> str:
    return "finalize" if state.get("skip_retrieval") else "retrieve"


def route_after_grade(state: AgentState) -> str:
    settings = get_settings()
    if state.get("access_denied_reason") == "DEPARTMENT_SCOPE_DENIED":
        return "access_denied"
    if state.get("retrieved_chunks"):
        return "generate"
    if state.get("rewrite_count", 0) >= settings.max_rewrite_retries:
        # Hết lượt rewrite mà vẫn không có chunk liên quan — vẫn generate, model
        # sẽ tự nhận "chưa đủ thông tin" (xem _GENERATE_SYSTEM), confidence_node
        # phía sau sẽ escalate vì không có chunk nào.
        return "generate"
    return "rewrite"


def route_after_confidence(state: AgentState) -> str:
    """Tối ưu Conditional Hallucination Check:
    - UNANSWERABLE: Model tự nhận không đủ thông tin (answerable=False) -> đi thẳng escalate (tiết kiệm 1 LLM call).
    - FAST PATH (~85-90%): Điểm tin cậy cao (confidence >= threshold) -> Chuyển thẳng sang finalize (che PII và trả về ngay ~2-3s).
    - GUARDED PATH (~10-15%): Điểm tin cậy thấp (< threshold) -> Chuyển sang hallucination_check để kiểm chứng claim/số liệu hoặc retry/escalate.
    """
    settings = get_settings()
    if not state.get("answerable", True):
        return "escalate"

    score = state.get("confidence_score", 0.0)
    if score >= settings.low_confidence_threshold:
        return "finalize"

    return "hallucination_check"


def route_after_hallucination(state: AgentState) -> str:
    """Điều hướng an toàn sau khi kiểm tra ảo giác:
    - PASS: Nếu confidence cao -> finalize; nếu confidence thấp -> escalate (low_confidence).
    - FAIL & còn lượt retry (< max_retries): Cho phép sinh lại (generate).
    - FAIL & Hết lượt retry: Escalate sang Ticket HR (hallucination_detected, tuyệt đối không trả câu ảo giác).
    """
    settings = get_settings()
    passed = state.get("hallucination_passed", True)
    retry_count = state.get("hallucination_retry_count", 0)

    if passed:
        score = state.get("confidence_score", 0.0)
        if score >= settings.low_confidence_threshold and state.get("answerable", True):
            return "finalize"
        return "escalate"

    if retry_count < settings.max_hallucination_retries:
        return "generate"
    return "escalate"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Core Nodes
    graph.add_node("condense_and_route", condense_and_route_node)
    graph.add_node("condense", condense_and_route_node)
    graph.add_node("router", router_node)
    graph.add_node("boundary", boundary_node)
    graph.add_node("direct", direct_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("knowledge_lookup", knowledge_lookup_node)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("grade", grade_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("generate", generate_node)
    graph.add_node("hallucination_check", hallucination_check_node)
    graph.add_node("confidence", confidence_node)
    graph.add_node("escalate_ticket", escalate_node)
    graph.add_node("access_denied", department_access_denied_node)
    graph.add_node("out_of_scope", out_of_scope_node)
    graph.add_node("finalize", finalize_node)

    # Unified Entry Point
    graph.set_entry_point("condense_and_route")
    graph.add_edge("condense_and_route", "boundary")

    graph.add_conditional_edges(
        "boundary",
        route_by_intent,
        {
            "direct": "direct",
            "clarify": "clarify",
            "escalate": "escalate_ticket",
            "out_of_scope": "out_of_scope",
            "retrieve": "knowledge_lookup",
        },
    )
    graph.add_edge("direct", END)
    graph.add_edge("clarify", END)
    graph.add_edge("out_of_scope", END)

    graph.add_conditional_edges(
        "knowledge_lookup",
        route_after_knowledge_lookup,
        {"finalize": "finalize", "retrieve": "retrieve"},
    )
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", route_after_grade,
        {"generate": "generate", "rewrite": "rewrite", "access_denied": "access_denied"},
    )
    graph.add_edge("access_denied", END)
    graph.add_edge("rewrite", "retrieve")

    # Pipeline sau Generate: Generate -> Confidence -> (Fast: Finalize | Guarded: Hallucination)
    graph.add_edge("generate", "confidence")
    graph.add_conditional_edges(
        "confidence",
        route_after_confidence,
        {
            "finalize": "finalize",
            "hallucination_check": "hallucination_check",
            "escalate": "escalate_ticket",
        },
    )

    graph.add_conditional_edges(
        "hallucination_check",
        route_after_hallucination,
        {
            "finalize": "finalize",
            "generate": "generate",
            "escalate": "escalate_ticket",
        },
    )

    graph.add_edge("escalate_ticket", END)
    graph.add_edge("finalize", END)

    return graph.compile()


agent = build_graph()
rag_agent_graph = agent

