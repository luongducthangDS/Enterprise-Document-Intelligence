import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "pool_nexatech_v2_candidates.py"
SPEC = importlib.util.spec_from_file_location("pool_nexatech_v2_candidates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_contextual_query_includes_parent_and_prior_turns():
    parent = {"id": "nxv2_001", "turns": [{"turn": 1, "question": "Câu đầu"}]}
    child = {
        "id": "nxv2_002",
        "continues_case_id": "nxv2_001",
        "turns": [{"turn": 2, "question": "Câu sau"}, {"turn": 3, "question": "Câu cuối"}],
    }

    query = MODULE.contextual_query(child, child["turns"][1], {"nxv2_001": parent, "nxv2_002": child})

    assert query.splitlines() == ["Ngữ cảnh hội thoại:", "- Câu đầu", "- Câu sau", "- Câu cuối"]


def test_combine_where_keeps_production_filter_and_adds_source():
    where = MODULE.combine_where({"$and": [{"authority": "tenant_official_policy"}]}, "01_policy")
    assert where == {
        "$and": [
            {"authority": "tenant_official_policy"},
            {"source_stem": "01_policy"},
        ]
    }


def test_merge_candidates_preserves_all_pool_origins():
    ids, details = MODULE.merge_candidates(
        ["a", "b"],
        [("b", 2.0), ("c", 1.0)],
        ["c", "d"],
    )

    assert set(ids) == {"a", "b", "c", "d"}
    assert set(details["b"]["origins"]) == {"dense", "bm25"}
    assert set(details["c"]["origins"]) == {"bm25", "expected_source_dense"}
