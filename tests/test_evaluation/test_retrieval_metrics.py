from src.evaluation.retrieval_metrics import (
    declared_source_stems,
    expected_source_stems,
    first_doc_hit_rank,
    live_index_alignment,
    normalize_source_stem,
    qrel_source_stems,
)


def test_normalize_source_stem_handles_paths_extensions_and_unicode():
    assert normalize_source_stem(r"data\processed\Bộ luật lao động.PDF") == "bộ luật lao động"


def test_qrel_sources_are_authoritative_over_stale_dataset_source():
    item = {"source_file": "legacy-source.pdf"}
    relevant = {"canonical-policy::0001": 2, "second-policy::0003": 2}

    stems, label = expected_source_stems(item, relevant)

    assert stems == {"canonical-policy", "second-policy"}
    assert label == "qrels"


def test_declared_sources_cover_all_legacy_locations():
    item = {
        "source_file": "one.pdf",
        "source_files": ["two.docx"],
        "metadata": {"source_file": "three.md"},
    }
    assert declared_source_stems(item) == {"one", "two", "three"}


def test_document_hit_accepts_any_qrel_source():
    relevant = {"canonical-policy::0001": 2, "second-policy::0003": 2}
    expected = qrel_source_stems(relevant)
    assert first_doc_hit_rank(expected, ["unrelated.md", "SECOND-POLICY.pdf"]) == 2
    assert first_doc_hit_rank(expected, ["unrelated.md"]) == 0


def test_live_index_alignment_separates_missing_gold_from_retrieval_miss():
    dataset = [
        {"id": "q1", "type": "single_chunk"},
        {"id": "q2", "type": "multi_chunk"},
        {"id": "q3", "type": "single_chunk", "retired": True},
    ]
    qrels = {
        "q1": {"policy-a::0001": 2},
        "q2": {"policy-a::0002": 2, "removed-law::0001": 2, "support::0001": 1},
        "q3": {"retired::0001": 2},
    }

    report = live_index_alignment(dataset, qrels, {"policy-a::0001", "policy-a::0002", "other::0001"})

    assert report["benchmark_valid"] is False
    assert report["scored_queries"] == 2
    assert report["qrel_chunk_labels"] == 3
    assert report["available_qrel_chunk_labels"] == 2
    assert report["queries_with_any_available_qrel"] == 2
    assert report["fully_available_queries"] == 1
    assert report["partially_available_queries"] == ["q2"]
    assert report["missing_qrel_sources"] == ["removed-law"]


def test_live_index_alignment_reports_query_with_no_available_gold():
    report = live_index_alignment(
        [{"id": "q1", "type": "in_scope"}],
        {"q1": {"gone::0001": 2}},
        {"current::0001"},
    )

    assert report["queries_with_any_available_qrel"] == 0
    assert report["query_coverage"] == 0.0
    assert report["unavailable_queries"] == ["q1"]
