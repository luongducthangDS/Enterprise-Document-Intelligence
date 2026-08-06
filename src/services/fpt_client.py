import base64
import time

import requests


def _post_chat_completion(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    temperature: float | None = None,
    timeout: int = 60,
    retries: int = 2,
) -> dict:
    """Gọi /chat/completions OpenAI-compatible trên FPT.AI Marketplace, trả về
    message dict {"content": ..., ...}. Dùng chung cho VLM (ảnh+text) và LLM
    text thuần — khác nhau ở nội dung `messages` truyền vào."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature

    last_exc: requests.exceptions.RequestException | None = None
    for _ in range(retries + 1):
        try:
            r = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(2)
    raise last_exc


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
) -> str:
    """LLM text thuần (vd GLM-5.2 qua FPT.AI Marketplace) — dùng cho sinh synthetic data."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    message = _post_chat_completion(
        messages, model=model, base_url=base_url, api_key=api_key, temperature=temperature, timeout=timeout, retries=retries
    )
    return message.get("content") or message.get("reasoning_content") or ""


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
    """Gọi endpoint /rerank (cross-encoder) trên FPT.AI Marketplace.

    Trả về [(index trong `documents`, relevance_score)] đã sắp xếp giảm dần.
    `relevance_score` nằm trong khoảng 0-1 (server đã áp sigmoid), nên dùng
    trực tiếp được làm ngưỡng lọc và làm điểm confidence — khác với logit thô
    của cross-encoder chạy local.

    Chạy qua gateway thay vì tải model 560M về máy: không thêm dependency nặng
    (sentence-transformers/torch), không phụ thuộc cache HuggingFace của từng
    máy, và deploy được lên môi trường không có GPU/disk lớn.
    """
    if not documents:
        return []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {"model": model, "query": query, "documents": documents}
    if top_n is not None:
        payload["top_n"] = top_n

    last_exc: requests.exceptions.RequestException | None = None
    for _ in range(retries + 1):
        try:
            r = requests.post(f"{base_url}/rerank", headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()
            results = r.json()["results"]
            return [(int(item["index"]), float(item["relevance_score"])) for item in results]
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(2)
    raise last_exc


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
    last_exc: requests.exceptions.RequestException | None = None
    for _ in range(retries + 1):
        try:
            r = requests.post(
                f"{base_url}/embeddings",
                headers=headers,
                json={"model": model, "input": texts},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()["data"]
            data.sort(key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(2)
    raise last_exc
