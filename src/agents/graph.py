from langgraph.graph import END, StateGraph

from src.agents.nodes.boundary import boundary_node
from src.agents.nodes.condense import condense_node
from src.agents.nodes.escalation import confidence_node, escalate_node, out_of_scope_node
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
    # Routing precedence priority 2 (NexaTech Type-C contract v3.1.0): pure
    # statutory/legal intent bypasses retrieval hoàn toàn — không đi qua nhánh
    # escalate/ticket, có node riêng với response cố định.
    if intent == "pure_statutory":
        return "out_of_scope"
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


def route_after_generate(state: AgentState) -> str:
    """Bỏ qua hallucination check khi model đã tự nhận không đủ thông tin
    (answerable=False): câu trả lời khi đó chỉ là lời giải thích "thiếu gì",
    không có claim nào để kiểm chứng — prompt check còn tự quy định PASS cho
    trường hợp này. confidence_node sẽ cap điểm xuống fail_cap và escalate y
    như cũ, chỉ bớt được 1 LLM call (~1-3s) trên toàn nhánh escalate.

    LƯU Ý: đây là tập con AN TOÀN của đề xuất "conditional hallucination check"
    trong report_rag_review.md — phần skip theo rerank score >= 0.8 đã bị bác
    bỏ vì đo được 7 câu reranker tự tin 0.78-1.00 nhưng đoạn SAI (xem CLAUDE.md
    [2026-08-06]); check groundedness là lớp bảo vệ đúng chỗ đó, không được bỏ.
    """
    if not state.get("answerable", True):
        return "confidence"
    return "hallucination_check"


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

    graph.add_node("condense", condense_node)
    graph.add_node("router", router_node)
    graph.add_node("boundary", boundary_node)
    graph.add_node("direct", direct_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("grade", grade_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("generate", generate_node)
    graph.add_node("hallucination_check", hallucination_check_node)
    graph.add_node("confidence", confidence_node)
    graph.add_node("escalate_ticket", escalate_node)
    graph.add_node("out_of_scope", out_of_scope_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("condense")
    graph.add_edge("condense", "router")
    # `boundary` nằm giữa router và các nhánh xử lý: nó cần `intent` do router
    # đặt, và các node phía sau (escalate, finalize) cần decision của nó.
    graph.add_edge("router", "boundary")
    graph.add_conditional_edges(
        "boundary",
        route_by_intent,
        {
            "direct": "direct",
            "clarify": "clarify",
            "escalate": "escalate_ticket",
            "out_of_scope": "out_of_scope",
            "retrieve": "retrieve",
        },
    )
    graph.add_edge("direct", END)
    graph.add_edge("clarify", END)
    graph.add_edge("out_of_scope", END)

    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route_after_grade, {"generate": "generate", "rewrite": "rewrite"})
    graph.add_edge("rewrite", "retrieve")

    graph.add_conditional_edges(
        "generate",
        route_after_generate,
        {"confidence": "confidence", "hallucination_check": "hallucination_check"},
    )
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
rag_agent_graph = agent


