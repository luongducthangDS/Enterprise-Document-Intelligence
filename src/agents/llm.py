import asyncio

from src.config import get_settings
from src.services.fpt_client import chat_completion


async def acall_llm(system: str, user: str, temperature: float = 0.5) -> str:
    """Gọi LLM (GLM-5.2 qua FPT.AI Marketplace) mà không block event loop —
    fpt_client.chat_completion dùng requests đồng bộ nên chạy trong thread pool."""
    settings = get_settings()
    return await asyncio.to_thread(
        chat_completion,
        system,
        user,
        model=settings.llm_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        temperature=temperature,
    )
