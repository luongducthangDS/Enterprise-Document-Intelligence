import asyncio

from src.config import get_settings
from src.services.fpt_client import chat_completion


def thinking_arg(enabled: bool) -> bool | None:
    """Đổi cờ config (bool) sang tham số `enable_thinking` của gateway.

    `enabled=True` -> None, tức KHÔNG gửi field nào cả: payload giữ nguyên
    đúng như trước khi có tính năng này, nên nhánh "bật thinking" không phải là
    một hành vi mới cần đo lại. Chỉ khi tắt mới gửi field xuống gateway.
    """
    return None if enabled else False


async def acall_llm(
    system: str,
    user: str,
    # Determinism mặc định (PR-01/TASK-004): mọi call site mới không khai báo
    # nhiệt độ sẽ chạy ở 0.0. Call site cần sampling phải ghi rõ lý do khi truyền
    # giá trị khác.
    temperature: float = 0.0,
    model: str | None = None,
    enable_thinking: bool | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int = 30,
    retries: int = 0,
) -> str:
    """Gọi LLM qua FPT.AI Marketplace mà không block event loop —
    fpt_client.chat_completion dùng requests đồng bộ nên chạy trong thread pool.

    `model=None` dùng `llm_model` (model của agent). Truyền model khác khi cần
    tách vai — vd eval dùng `judge_model` để không rơi vào circular evaluation.

    `enable_thinking=None` giữ nguyên mặc định của model; `False` tắt
    chain-of-thought (xem fpt_client._post_chat_completion để biết số đo).
    """
    settings = get_settings()
    return await asyncio.to_thread(
        chat_completion,
        system,
        user,
        model=model or settings.llm_model,
        base_url=base_url or settings.fpt_base_url,
        api_key=api_key or settings.fpt_api_key,
        temperature=temperature,
        enable_thinking=enable_thinking,
        timeout=timeout,
        retries=retries,
    )
