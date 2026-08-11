from src.agents.llm import acall_llm
from src.agents.state import AgentState

_CONDENSE_SYSTEM = """Bạn giúp viết lại câu hỏi HIỆN TẠI của người dùng dựa trên lịch sử hội thoại phía trên, để câu hỏi trở nên ĐỘC LẬP — hiểu được đầy đủ mà không cần đọc lại lịch sử.

Quy tắc:
- Thay thế đại từ/tham chiếu mơ hồ ("cái đó", "khoản này", "4 giờ đó", "E", "tôi"...) bằng đúng thực thể/dữ kiện cụ thể đã xuất hiện trong lịch sử.
- Giữ nguyên MỌI dữ kiện định lượng liên quan (số tháng, số ngày, số tiền, loại hợp đồng...) đã được nêu ở các lượt trước nếu câu hỏi hiện tại phụ thuộc vào chúng.
- KHÔNG trả lời câu hỏi, KHÔNG thêm thông tin/giả định mới ngoài những gì lịch sử đã cung cấp, KHÔNG thêm chủ đề nào khác.
- Nếu câu hỏi hiện tại đã tự đủ ngữ cảnh (không phụ thuộc lịch sử), giữ nguyên gần như không đổi.

Chỉ trả về câu hỏi đã viết lại, không giải thích, không thêm lời dẫn."""


def _format_history(history: list[dict], max_turns: int) -> str:
    recent = history[-max_turns:] if max_turns > 0 else history
    lines = []
    for turn in recent:
        role = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        lines.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(lines)


async def condense_node(state: AgentState) -> dict:
    query = state.get("query", "")
    history = state.get("history") or []
    if not history:
        return {"condensed_query": query}

    from src.config import get_settings

    settings = get_settings()
    history_text = _format_history(history, settings.max_history_turns)
    user_prompt = f"Lịch sử hội thoại:\n{history_text}\n\nCâu hỏi hiện tại: {query}"

    model = settings.condense_model or None
    # temperature=0.0: đây là node QUYẾT ĐỊNH (câu hỏi độc lập sinh ra ở đây quyết
    # định router/retrieval/generation phía sau) — không phải node sinh văn phong tự
    # nhiên. Từng để 0.2, đo được cùng 1 input (câu hỏi + history) cho ra
    # condensed_query khác nhau đủ để retrieval lệch, confidence rơi dưới ngưỡng
    # escalate ở một số lần chạy mà lần khác không (xem guardrail pilot,
    # context_drift_001 turn 8: cùng history, có lần trả lời đúng có lần escalate
    # "chưa đủ căn cứ").
    rewritten = (await acall_llm(_CONDENSE_SYSTEM, user_prompt, temperature=0.0, model=model)).strip()
    return {"condensed_query": rewritten or query}
