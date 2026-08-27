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


def resolve_llm_endpoint(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str, str]:
    """Phân giải (model, base_url, api_key) dựa trên cấu hình USE_GLM và Provider."""
    settings = get_settings()

    # Nếu caller đã chỉ định rõ cả base_url và api_key và model thì dùng nguyên
    if base_url and api_key and model:
        return model, base_url, api_key

    # 1. Nhánh USE_GLM = ON (True) -> Dùng GLM-5.2 qua FPT Cloud
    if settings.use_glm:
        target_model = model or (
            settings.llm_model
            if (settings.llm_model and not settings.llm_model.lower().startswith("gpt-"))
            else "GLM-5.2"
        )
        if target_model.lower().startswith("gpt-4o-mini"):
            target_model = (
                settings.router_model
                if (settings.router_model and not settings.router_model.lower().startswith("gpt-"))
                else "DeepSeek-V4-Flash"
            )
        elif target_model.lower().startswith("gpt-4o"):
            target_model = "GLM-5.2"

        resolved_base_url = base_url or settings.fpt_base_url
        resolved_api_key = api_key or settings.fpt_api_key
        return target_model, resolved_base_url, resolved_api_key

    # 2. Nhánh USE_GLM = OFF (False) -> Dùng OpenAI (gpt-4o / gpt-4o-mini)
    target_model = model or "gpt-4o"
    if target_model in ("GLM-5.2", "glm-5.2"):
        target_model = "gpt-4o"
    elif target_model in ("DeepSeek-V4-Flash", "deepseek-v4-flash"):
        target_model = "gpt-4o-mini"

    is_openai = True
    if settings.llm_provider == "fpt":
        is_openai = False

    resolved_base_url = base_url or (settings.openai_base_url if is_openai else settings.fpt_base_url)
    resolved_api_key = api_key or (settings.openai_api_key if is_openai else settings.fpt_api_key)

    return target_model, resolved_base_url, resolved_api_key


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
    """Gọi LLM (OpenAI hoặc FPT.AI Marketplace) mà không block event loop —
    fpt_client.chat_completion dùng requests đồng bộ nên chạy trong thread pool.

    `model=None` dùng `llm_model` (model của agent). Truyền model khác khi cần
    tách vai — vd eval dùng `judge_model` để không rơi vào circular evaluation.

    `enable_thinking=None` giữ nguyên mặc định của model; `False` tắt
    chain-of-thought (xem fpt_client._post_chat_completion để biết số đo).
    """
    effective_model, effective_base_url, effective_api_key = resolve_llm_endpoint(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    return await asyncio.to_thread(
        chat_completion,
        system,
        user,
        model=effective_model,
        base_url=effective_base_url,
        api_key=effective_api_key,
        temperature=temperature,
        enable_thinking=enable_thinking,
        timeout=timeout,
        retries=retries,
    )
