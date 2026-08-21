import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "eval_retrieval.py"
SPEC = importlib.util.spec_from_file_location("eval_retrieval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


@pytest.mark.asyncio
async def test_run_one_persists_retrieval_trace(monkeypatch):
    raw = {
        "ids": ["policy::0001", "policy::0002"],
        "documents": ["answer", "context"],
        "metadatas": [{"source_file": "policy.md"}, {"source_file": "policy.md"}],
        "distances": [0.1, 0.2],
        "scores": [0.9, 0.7],
    }
    monkeypatch.setattr(MODULE, "_retrieve_raw", AsyncMock(return_value=raw))

    result = await MODULE._run_one(
        {
            "id": "q1",
            "question": "question",
            "type": "in_scope",
            "category": "policy",
            "source_file": "policy.md",
        },
        top_k=2,
        qrels={"q1": {"policy::0001": 2}},
        semaphore=None,
    )

    assert result["retrieved_chunk_ids"] == raw["ids"]
    assert result["retrieved_source_files"] == ["policy.md", "policy.md"]
    assert result["reranker_scores"] == raw["scores"]
