import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import get_settings
from src.evaluation.scoring import citation_scores, context_found, evaluate_quality_gate
from src.models.schemas import EvaluationJobRequest
from src.workers.evaluation import EvaluationError, load_dataset, run_evaluation

DATASET = [
    {
        "id": "qa_001",
        "type": "in_scope",
        "category": "leave",
        "question": "Được nghỉ phép bao nhiêu ngày?",
        "expected_answer": "12 ngày.",
        "ground_truth_context": "Nhân viên được nghỉ 12 ngày phép năm.",
    },
    {
        "id": "qa_002",
        "type": "out_of_scope",
        "category": "other",
        "question": "Lương của đồng nghiệp tôi là bao nhiêu?",
    },
    {
        "id": "qa_003",
        "type": "retired",
        "retired": True,
        "category": "leave",
        "question": "Câu đã gỡ khỏi corpus",
    },
]
QRELS = {"qa_001": {"policy_a::0000": 1}}


@pytest.fixture
def settings(tmp_path):
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    (datasets_dir / "qa_eval_set.json").write_text(json.dumps(DATASET, ensure_ascii=False), encoding="utf-8")
    (datasets_dir / "retrieval_qrels.json").write_text(json.dumps(QRELS), encoding="utf-8")
    return get_settings().model_copy(update={"eval_datasets_dir": str(datasets_dir)})


def _noop_progress(stage: str, percent: int) -> None:
    return None


def _agent_state() -> dict:
    return {
        "response": "Bạn được nghỉ 12 ngày phép năm.",
        "intent": "hr_question",
        "escalate": False,
        "needs_clarification": False,
        "confidence_score": 0.9,
        "retrieved_chunks": [{"chunk_id": "policy_a::0000", "text": "Nhân viên được nghỉ 12 ngày phép năm."}],
        "citations": [{"chunk_id": "policy_a::0000", "source_file": "policy_a.md"}],
    }


def test_load_dataset_drops_retired_items(settings):
    items, qrels = load_dataset("evalset_hr_v1", settings)
    assert [item["id"] for item in items] == ["qa_001", "qa_002"]
    assert qrels == QRELS


def test_load_dataset_rejects_unknown_dataset_id(settings):
    with pytest.raises(EvaluationError, match="evalset_hr_v1"):
        load_dataset("evalset_khong_ton_tai", settings)


def test_load_dataset_reports_missing_file(tmp_path):
    settings = get_settings().model_copy(update={"eval_datasets_dir": str(tmp_path / "trong")})
    with pytest.raises(EvaluationError, match="Không tìm thấy file dataset"):
        load_dataset("evalset_hr_v1", settings)


def test_context_found_prefers_qrels_over_string_match():
    item = {"id": "qa_001", "ground_truth_context": "đoạn văn không xuất hiện"}
    chunks = [{"chunk_id": "policy_a::0000", "text": "văn bản khác hẳn"}]
    assert context_found(item, chunks, QRELS) is True
    assert context_found(item, [{"chunk_id": "policy_z::0009", "text": "khác"}], QRELS) is False


def test_context_found_falls_back_to_normalized_substring():
    item = {"id": "qa_999", "ground_truth_context": "Nhân viên được nghỉ **12 ngày** phép năm."}
    chunks = [{"chunk_id": "policy_a::0000", "text": "... Nhân viên  được nghỉ 12 ngày phép năm. ..."}]
    assert context_found(item, chunks, {}) is True


def test_citation_scores_measures_coverage_and_correctness():
    item = {"id": "qa_001"}
    citations = [{"chunk_id": "policy_a::0000"}, {"chunk_id": "policy_b::0003"}]
    has_citation, correctness = citation_scores(item, citations, QRELS)
    assert has_citation is True
    assert correctness == 0.5

    # Không có nhãn gold -> không chấm correctness (tránh làm loãng mẫu số).
    assert citation_scores({"id": "qa_999"}, citations, {}) == (True, None)
    assert citation_scores(item, [], QRELS) == (False, None)


def test_quality_gate_pending_when_metric_missing():
    settings = get_settings()
    gate, details = evaluate_quality_gate({"recall_at_k": None}, settings)
    assert gate == "PENDING"
    assert all(detail["passed"] is None for detail in details if detail["value"] is None)


def test_quality_gate_fails_when_threshold_not_met():
    settings = get_settings().model_copy(
        update={
            "eval_gate_recall_at_k": 0.8,
            "eval_gate_answer_correctness": 0.7,
            "eval_gate_citation_coverage": 0.9,
        }
    )
    metrics = {"recall_at_k": 0.9, "answer_correctness": 0.5, "citation_coverage": 1.0}
    gate, details = evaluate_quality_gate(metrics, settings)
    assert gate == "FAILED"
    assert [d["passed"] for d in details] == [True, False, True]


def test_pure_statutory_passes_only_with_out_of_scope_contract():
    from src.evaluation.scoring import passed_for_type

    result = {"intent": "pure_statutory", "state": "OUT_OF_SCOPE", "reason_code": "PURE_STATUTORY"}
    assert passed_for_type("pure_statutory", result, context_ok=False, answer_ok=False) is True
    assert passed_for_type(
        "pure_statutory",
        {"intent": "pure_statutory", "state": "ANSWER"},
        context_ok=False,
        answer_ok=False,
    ) is False


@pytest.mark.asyncio
async def test_judge_answer_uses_dedicated_credentials_when_configured(settings):
    from src.evaluation.scoring import judge_answer

    dedicated = settings.model_copy(
        update={
            "judge_api_key": "judge-secret",
            "judge_base_url": "https://judge.example.test",
        }
    )
    with patch("src.evaluation.scoring.acall_llm", new=AsyncMock(return_value="CORRECT")) as judge:
        assert await judge_answer("question", "answer", "expected", dedicated) is True

    assert judge.await_args.kwargs["api_key"] == "judge-secret"
    assert judge.await_args.kwargs["base_url"] == "https://judge.example.test"


@pytest.mark.asyncio
async def test_run_evaluation_scores_dataset_and_returns_metrics(settings):
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(return_value=_agent_state())

    with (
        patch("src.workers.evaluation.agent", fake_agent),
        patch("src.evaluation.scoring.acall_llm", new=AsyncMock(return_value="CORRECT")),
    ):
        result = await run_evaluation(EvaluationJobRequest(job_id="eval-1"), _noop_progress, settings=settings)

    assert result["total"] == 2
    assert result["summary_by_type"]["in_scope"] == {"passed": 1, "total": 1, "rate": 1.0}
    # out_of_scope PASS khi agent escalate — agent giả không escalate nên FAIL.
    assert result["summary_by_type"]["out_of_scope"]["passed"] == 0
    assert result["metrics"]["recall_at_k"] == 1.0
    assert result["metrics"]["answer_correctness"] == 1.0
    assert result["metrics"]["citation_coverage"] == 1.0
    assert result["metrics"]["citation_correctness"] == 1.0
    assert result["quality_gate"] == "PASSED"
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_run_evaluation_isolates_failing_case(settings):
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(side_effect=RuntimeError("gateway 524"))

    with patch("src.workers.evaluation.agent", fake_agent):
        request = EvaluationJobRequest(job_id="eval-2", types=["in_scope"])
        result = await run_evaluation(request, _noop_progress, settings=settings)

    assert result["total"] == 1
    assert result["error_count"] == 1
    assert result["total_passed"] == 0
    # Không có case nào chấm được -> gate PENDING chứ không phải PASSED giả.
    assert result["quality_gate"] == "PENDING"


@pytest.mark.asyncio
async def test_run_evaluation_rejects_empty_selection(settings):
    with pytest.raises(EvaluationError, match="Không còn câu nào"):
        await run_evaluation(
            EvaluationJobRequest(job_id="eval-3", types=["khong_co_type_nay"]), _noop_progress, settings=settings
        )


def test_dataset_files_cover_backend_valid_datasets():
    """Danh sách dataset_id phải khớp VALID_DATASETS của Backend."""
    from src.workers.evaluation import DATASET_FILES

    assert set(DATASET_FILES) == {"evalset_hr_v1", "evalset_hr_v2", "evalset_default"}
    real_datasets_dir = get_settings().eval_datasets_dir
    for dataset_file, qrels_file in DATASET_FILES.values():
        assert os.path.exists(os.path.join(real_datasets_dir, dataset_file)), dataset_file
        if qrels_file:
            assert os.path.exists(os.path.join(real_datasets_dir, qrels_file)), qrels_file
