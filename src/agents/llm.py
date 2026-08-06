import asyncio

from src.config import get_settings
from src.services.fpt_client import chat_completion


async def acall_llm(system: str, user: str, temperature: float = 0.5, model: str | None = None) -> str:
    """Gọi LLM qua FPT.AI Marketplace mà không block event loop —
    fpt_client.chat_completion dùng requests đồng bộ nên chạy trong thread pool.

    `model=None` dùng `llm_model` (model của agent). Truyền model khác khi cần
    tách vai — vd eval dùng `judge_model` để không rơi vào circular evaluation.
    """
    settings = get_settings()
    return await asyncio.to_thread(
        chat_completion,
        system,
        user,
        model=model or settings.llm_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        temperature=temperature,
    )
