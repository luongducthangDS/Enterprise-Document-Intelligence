import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "audit_benchmark_corpus.py"
SPEC = importlib.util.spec_from_file_location("audit_benchmark_corpus", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_audit_separates_document_coverage_from_behavior_only_cases():
    cases = [
        {"id": "a", "source_file": "01_policy.md"},
        {"id": "b", "source_file": "02_policy.md"},
        {"id": "c", "source_file": None},
    ]

    report = MODULE.audit(cases, {"01_policy.md", "unrelated.md"})

    assert report["covered_source_count"] == 1
    assert report["missing_sources"] == ["02_policy"]
    assert report["extra_index_sources"] == ["unrelated"]
    assert report["behavior_only_cases"] == 1
