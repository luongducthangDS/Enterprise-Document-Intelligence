from typing import Callable, Optional

from src.services.fpt_client import embed_batch


def embed_texts(
    texts: list[str],
    model: str,
    base_url: str,
    api_key: str,
    batch_size: int = 32,
    log: Optional[Callable[[str], None]] = None,
) -> list[list[float]]:
    """Orchestrate embedding theo batch — chỉ chia batch, gọi fpt_client, log tiến
    độ; không tự làm việc với HTTP (xem src/services/fpt_client.py)."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(embed_batch(batch, model=model, base_url=base_url, api_key=api_key))
        if log:
            log(f"embedded {min(i + batch_size, len(texts))}/{len(texts)}")
    return all_embeddings
