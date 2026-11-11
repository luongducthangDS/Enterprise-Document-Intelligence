import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bench", ROOT / "eval/scripts/eval_agent_benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

TASK = {
    "id": "t", "category": "compare", "max_steps": 3,
    "expect": {"state": "ANSWER", "must_cite": ["a.md", "b.md"], "must_contain": [["05 ngày", "5 ngày"], ["07 ngày"]],
               "must_not_contain": ["tối đa 800.000"], "deliverable": "comparison_table"},
    "gold_tools": {"must_call": ["compare_documents"], "compare_files": ["a.md", "b.md"]},
}
TABLE = "| Tiêu chí | A | B |\n|---|---|---|\n| Hạn | 5 ngày [Nguồn 1] | 07 ngày [Nguồn 2] |"


def test_outcome_all_pass_and_each_failure_mode():
    ok = bench.outcome_checks(TASK, TABLE, "ANSWER", {"a.md", "b.md"})
    assert all(ok.values())
    assert not bench.outcome_checks(TASK, TABLE, "ANSWER", {"a.md"})["cite"]
    assert not bench.outcome_checks(TASK, "5 ngày và 07 ngày", "ANSWER", {"a.md", "b.md"})["deliverable"]
    assert not bench.outcome_checks(TASK, TABLE + " tối đa 800.000", "ANSWER", {"a.md", "b.md"})["not_contain"]
    assert not bench.outcome_checks(TASK, TABLE, "ABSTAIN", {"a.md", "b.md"})["state"]


def test_tool_and_argument_checks():
    steps = [{"tool": "search_policies", "args": {"query": "x"}}, {"tool": "compare_documents", "args": {"source_files": ["b.md", "a.md"], "aspect": "hạn"}}]
    assert bench.tool_checks(TASK, steps) == {"tool_selection": True, "argument": True}
    wrong = [{"tool": "compare_documents", "args": {"source_files": ["a.md", "c.md"]}}]
    assert bench.tool_checks(TASK, wrong) == {"tool_selection": True, "argument": False}
    calc = {"gold_tools": {"must_call": ["calculate_annual_leave"], "args": {"calculate_annual_leave": {"job_type": "normal", "years_of_service": 11}}}}
    good = [{"tool": "calculate_annual_leave", "args": {"job_type": "normal", "years_of_service": 11.0}}]
    errored = [{"tool": "calculate_annual_leave", "args": {"job_type": "normal", "years_of_service": 11}, "error": "x"}]
    assert bench.tool_checks(calc, good)["argument"] is True
    assert bench.tool_checks(calc, errored)["argument"] is False  # gọi lỗi không tính là đúng tham số
    assert bench.tool_checks({"gold_tools": {"must_call": ["search_policies|get_document"]}}, [{"tool": "get_document"}])["tool_selection"]


def test_trajectory_metrics_counts_redundant_and_budget():
    steps = [
        {"tool": "search_policies", "chunk_ids": ["a"]},
        {"tool": "search_policies", "chunk_ids": ["a"]},
        {"tool": "get_document", "error": "timeout"},
        {"tool": "search_policies", "chunk_ids": ["b"]},
    ]
    m = bench.trajectory_metrics(TASK, steps)
    assert m == {"steps": 4, "within_budget": False, "redundant_searches": 1, "tool_errors": 1, "trajectory_quality": 0.0}


def test_ungrounded_numbers():
    ev = "Khách sạn tối đa 1.200.000 VNĐ/đêm, nộp trong 05 ngày làm việc."
    assert bench.ungrounded_numbers("Tối đa 1.200.000 đồng [Nguồn 1], trong 05 ngày.", ev, "") == []
    assert bench.ungrounded_numbers("Tối đa 1200000 đồng", ev, "") == []  # khác cách viết dấu chấm
    assert bench.ungrounded_numbers("Tối đa 1.500.000 đồng", ev, "") == ["1.500.000"]
    assert bench.ungrounded_numbers("Bước 1, bước 2", ev, "") == []  # số 1 chữ số bỏ qua
    assert bench.ungrounded_numbers("làm 7 năm được 15 ngày", ev, "làm 7 năm") == ["15"]


def test_dataset_is_consistent():
    data = json.load(open(ROOT / "eval/datasets/agent_benchmark.json", encoding="utf-8"))
    ids = [t["id"] for t in data["tasks"]]
    assert len(ids) == len(set(ids))
    from src.agents.tools import REGISTRY

    for t in data["tasks"]:
        assert t["split"] in ("dev", "held_out") and ("question" in t) != ("turns" in t)
        assert t["expect"]["state"] in ("ANSWER", "ABSTAIN", "OUT_OF_SCOPE")
        for spec in t["gold_tools"].get("must_call", []):
            assert all(name in REGISTRY for name in spec.split("|")), spec
    assert {t["split"] for t in data["tasks"]} == {"dev", "held_out"}


def test_summarize_rates():
    rows = [
        {"id": "1", "category": "single", "success": True, "hallucinated": False, "latency_s": 1.0, "llm_calls": 2, "cost_usd": 0.001,
         "tools": {"tool_selection": True, "argument": True}, "trajectory": {"steps": 1, "within_budget": True, "trajectory_quality": 1.0}},
        {"id": "2", "category": "calc", "success": False, "hallucinated": True, "latency_s": 3.0, "llm_calls": 4, "cost_usd": 0.003,
         "tools": {"tool_selection": False}, "trajectory": {"steps": 3, "within_budget": False, "trajectory_quality": 0.333}},
        {"id": "3", "category": "calc", "arm": "react", "error": "boom"},
    ]
    s = bench.summarize(rows)
    assert s["n"] == 3 and s["errors"] == 1 and s["task_success"] == 0.5
    assert s["tool_selection_accuracy"] == 0.5 and s["argument_accuracy"] == 1.0
    assert s["hallucination_rate"] == 0.5 and s["avg_steps"] == 2 and s["by_category"] == {"calc": 0.0, "single": 1.0}
