import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval" / "datasets" / "product_retrieval_eval_set.json"
QRELS = ROOT / "eval" / "datasets" / "product_retrieval_qrels.json"


def test_hard_demo_cases_cover_multi_source_tables_charts_and_scans():
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    qrels = json.loads(QRELS.read_text(encoding="utf-8"))
    demo_cases = [case for case in cases if case.get("demo_priority")]

    assert len(demo_cases) >= 3
    assert all(case.get("difficulty") == "hard" for case in demo_cases)
    assert all(case.get("reasoning") == "multi_document_synthesis" for case in demo_cases)
    assert all(len(case.get("source_files", [])) >= 3 for case in demo_cases)
    assert all(qrels.get(case["id"]) for case in demo_cases)

    modalities = {modality for case in demo_cases for modality in case.get("modalities", [])}
    assert any("table" in modality for modality in modalities)
    assert "xlsx_chart" in modalities
    assert "scanned_image" in modalities
