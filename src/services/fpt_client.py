import base64
import random
import time
from collections.abc import Callable
from typing import TypeVar

import requests

from src.observability import llm_trace

# Session dùng chung cả module — giữ TCP connection + TLS session giữa các lần
# gọi (connection pooling của urllib3), bỏ được ~100-300ms handshake mỗi call.
# Một request của agent gọi gateway 3-6 lần (embed/rerank/router/generate/
# hallucination) nên phần tiết kiệm cộng dồn đáng kể.
_session = requests.Session()
# Số lần thử của lệnh gọi gần nhất — dùng để tách thời gian backoff (429/5xx)
# khỏi latency thuần của model khi profiling. Chỉ đọc ngay sau khi gọi xong.
_LAST_ATTEMPTS = [1]

T = TypeVar("T")


def _retry_with_backoff(func: Callable[[], T], retries: int) -> T:
    """Retry với exponential backoff + jitter, chỉ cho lỗi mạng/HTTP.

    Thay cho sleep 2s cố định từng ở cả 3 hàm gọi gateway — sleep cố định đã
    gây mất 9-12 câu mỗi lần chạy eval khi FPT.AI trả 5xx/DNS lỗi thoáng qua
    (2s không đủ cho gateway hồi, và mọi retry đập vào cùng thời điểm).
    Jitter tách các coroutine đang chạy song song ra để không retry đồng loạt.
    """
    last_exc: requests.exceptions.RequestException | None = None
    for attempt in range(retries + 1):
        try:
            result = func()
            _LAST_ATTEMPTS[0] = attempt + 1
            return result
        except requests.exceptions.RequestException as e:
            last_exc = e
            # 524 nghĩa là upstream model đã xử lý quá lâu và gateway đóng
            # request. Retry ngay cùng payload thường lại tốn trọn timeout,
            # vượt ngân sách HTTP giữa Backend -> Agent mà không tăng cơ hội
            # thành công. Caller nên chuyển model/fallback thay vì gọi lại.
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                if e.response.status_code == 524:
                    break
            if attempt < retries:
                delay = min(1.0 * (2**attempt) + random.uniform(0, 1), 8.0)
                time.sleep(delay)
    _LAST_ATTEMPTS[0] = retries + 1
    raise last_exc


def _post_chat_completion(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    temperature: float | None = None,
    timeout: int = 60,
    retries: int = 2,
    enable_thinking: bool | None = None,
) -> dict:
    """Gọi /chat/completions OpenAI-compatible trên FPT.AI Marketplace, trả về
    message dict {"content": ..., ...}. Dùng chung cho VLM (ảnh+text) và LLM
    text thuần — khác nhau ở nội dung `messages` truyền vào.

    `enable_thinking=False` tắt chain-of-thought của các reasoning model trên
    gateway. Đo trực tiếp trên /chat/completions (2026-08-12): GLM-5.2 mặc định
    sinh reasoning cho MỌI request, kể cả tác vụ trả về 1 từ — phân loại router
    tốn 265-467 completion token (~1.000 ký tự reasoning) để in ra đúng chữ
    "hr_question", và trả lời "OK" cho input "ping" cũng tốn 173 token / 5,5s.
    Tắt đi nhanh hơn 6-14x (router 7,4s -> 0,8s, hallucination check 6,4s ->
    1,0s, generate 10,0s -> 2,5s) NHƯNG có giá về chất lượng, khác nhau theo
    từng node — không tự ý bật cho node mới mà chưa A/B. Số đo và quyết định của
    từng node nằm ở các cờ `thinking_*` trong src/config.py.

    `None` = không gửi field, giữ nguyên hành vi mặc định của model (mọi caller
    cũ không đổi gì). Chỉ `reasoning_effort` là KHÔNG dùng được: gateway nhận
    HTTP 200 nhưng vẫn sinh đủ 265-270 token reasoning như thường.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {"model": model, "messages": messages}

    # Các model thế hệ mới của OpenAI (gpt-5*, o1*, o3*) cố định temperature=1.0 và từ chối param temperature != 1
    lower_model = model.lower()
    is_fixed_temp_model = "openai.com" in base_url.lower() and lower_model.startswith(("gpt-5", "o1", "o3", "o4"))
    if temperature is not None and not is_fixed_temp_model:
        payload["temperature"] = temperature

    if enable_thinking is not None and "openai.com" not in base_url.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

    captured_usage: dict = {}

    def _call() -> dict:
        r = _session.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        captured_usage.update(data.get("usage") or {})
        return data["choices"][0]["message"]

    if not llm_trace.is_active():
        return _retry_with_backoff(_call, retries)

    with llm_trace.Timer("chat", model, enable_thinking=enable_thinking) as timer:
        message = _retry_with_backoff(_call, retries)
        timer.usage = captured_usage
        timer.attempts = _LAST_ATTEMPTS[0]
        # Gateway KHÔNG trả `reasoning_tokens` riêng (xác thực 2026-08-13:
        # usage chỉ có prompt/completion/total). Nhưng message tách sẵn
        # `reasoning_content` khỏi `content`, nên đo được ĐỘ DÀI KÝ TỰ của
        # từng phần — đủ để biết bao nhiêu phần output là suy luận nội bộ và
        # bao nhiêu là câu trả lời thật. Token thì chỉ ước lượng được theo tỷ
        # lệ ký tự, và ước lượng đó có sai số: reasoning thường là tiếng Anh
        # còn answer là tiếng Việt, hai thứ có tỷ lệ token/ký tự khác nhau.
        timer.extra.update(
            {
                "reasoning_chars": len(message.get("reasoning_content") or ""),
                "answer_chars": len(message.get("content") or ""),
            }
        )
    return message


def extract_page_markdown(
    image_bytes: bytes,
    prompt: str,
    model: str,
    base_url: str,
    api_key: str,
    timeout: int = 120,
    retries: int = 2,
) -> str:
    """VLM trích xuất 1 trang ảnh PDF sang Markdown (dùng cho pdf_vlm.py)."""
    b64 = base64.b64encode(image_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    message = _post_chat_completion(
        messages, model=model, base_url=base_url, api_key=api_key, timeout=timeout, retries=retries
    )
    return message["content"]


def chat_completion(
    system: str,
    user: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float = 0.5,
    timeout: int = 180,
    retries: int = 2,
    enable_thinking: bool | None = None,
) -> str:
    """LLM text thuần (vd GLM-5.2 qua FPT.AI Marketplace) — dùng cho sinh synthetic data."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    message = _post_chat_completion(
        messages,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
        retries=retries,
        enable_thinking=enable_thinking,
    )
    return message.get("content") or message.get("reasoning_content") or ""


def _llm_rerank_sync(
    query: str,
    documents: list[str],
    model: str,
    base_url: str,
    api_key: str,
    top_n: int | None = None,
    timeout: int = 30,
) -> list[tuple[int, float]]:
    import json
    import re

    # Chỉ đưa top 6 ứng viên tốt nhất vào LLM Reranker để giảm latency
    max_eval = min(len(documents), 6)
    snippets = []
    for i in range(max_eval):
        doc = documents[i]
        t = doc[:140].replace("\n", " ")
        snippets.append(f"[{i}] {t}")
    prompt_context = "\n".join(snippets)

    system_prompt = (
        "Bạn là bộ thẩm định độ liên quan (Reranker). Đánh giá mức độ liên quan của từng [index] đối với câu hỏi.\n"
        "Chỉ trả về duy nhất JSON array: "
        '[{"index": 0, "score": 0.95}, ...]. Score từ 0.0 đến 1.0.'
    )
    user_prompt = f"Câu hỏi: {query}\n\nĐoạn trích:\n{prompt_context}"

    try:
        raw_msg = _post_chat_completion(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.0,
            timeout=timeout,
            retries=1,
        )
        raw = raw_msg.get("content") or ""
        match = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
        json_str = match.group(0) if match else raw.strip()
        data = json.loads(json_str)
        scored: list[tuple[int, float]] = []
        seen_indices = set()
        for item in data:
            idx = int(item["index"])
            if 0 <= idx < len(documents):
                scored.append((idx, float(item["score"])))
                seen_indices.add(idx)
        # Bổ sung các index còn lại (nếu có) với điểm thấp
        for i in range(len(documents)):
            if i not in seen_indices:
                scored.append((i, 0.05))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_n] if top_n is not None else scored
    except Exception as e:
        print(f"[llm_rerank_sync] Fallback: {e}")
        scored = [(i, max(0.1, 0.9 - i * 0.05)) for i in range(len(documents))]
        return scored[:top_n] if top_n is not None else scored


def rerank(
    query: str,
    documents: list[str],
    model: str,
    base_url: str,
    api_key: str,
    top_n: int | None = None,
    timeout: int = 60,
    retries: int = 2,
) -> list[tuple[int, float]]:
    """Gọi endpoint /rerank (cross-encoder) trên FPT.AI Marketplace hoặc OpenAI LLM Reranker khi USE_GLM=OFF.

    Trả về [(index trong `documents`, relevance_score)] đã sắp xếp giảm dần.
    `relevance_score` nằm trong khoảng 0-1.
    """
    if not documents:
        return []

    from src.config import get_settings
    settings = get_settings()

    if not settings.use_glm or "openai" in base_url.lower():
        return _llm_rerank_sync(
            query,
            documents,
            model=settings.openai_rerank_model or "gpt-4o-mini",
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            top_n=top_n,
            timeout=min(timeout, 20),
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {"model": model, "query": query, "documents": documents}
    if top_n is not None:
        payload["top_n"] = top_n

    def _call() -> list[tuple[int, float]]:
        r = _session.post(f"{base_url}/rerank", headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        results = r.json()["results"]
        return [(int(item["index"]), float(item["relevance_score"])) for item in results]

    if not llm_trace.is_active():
        return _retry_with_backoff(_call, retries)

    with llm_trace.Timer("rerank", model, n_documents=len(documents), top_n=top_n) as timer:
        ranked = _retry_with_backoff(_call, retries)
        timer.attempts = _LAST_ATTEMPTS[0]
    return ranked


def embed_batch(
    texts: list[str],
    model: str,
    base_url: str,
    api_key: str,
    timeout: int = 60,
    retries: int = 2,
) -> list[list[float]]:
    """Gọi endpoint /embeddings OpenAI-compatible trên FPT.AI Marketplace. Sắp xếp
    lại kết quả theo `index` trả về để đảm bảo khớp thứ tự với `texts` đầu vào
    (API có thể không trả đúng thứ tự khi xử lý batch)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    captured_usage: dict = {}

    def _call() -> list[list[float]]:
        payload: dict = {"model": model, "input": texts}
        if "openai.com" in base_url.lower() and model.startswith("text-embedding-3"):
            payload["dimensions"] = 1024

        r = _session.post(
            f"{base_url}/embeddings",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        payload_json = r.json()
        captured_usage.update(payload_json.get("usage") or {})
        data = payload_json["data"]
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    if not llm_trace.is_active():
        return _retry_with_backoff(_call, retries)

    with llm_trace.Timer("embedding", model, n_texts=len(texts)) as timer:
        vectors = _retry_with_backoff(_call, retries)
        timer.usage = captured_usage
        timer.attempts = _LAST_ATTEMPTS[0]
    return vectors
