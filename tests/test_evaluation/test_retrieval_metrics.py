from src.evaluation.retrieval_metrics import (
    declared_source_stems,
    expected_source_stems,
    first_doc_hit_rank,
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
