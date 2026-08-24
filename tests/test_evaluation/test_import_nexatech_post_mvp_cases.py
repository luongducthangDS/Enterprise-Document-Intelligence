import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "import_nexatech_post_mvp_cases.py"
SPEC = importlib.util.spec_from_file_location("import_nexatech_post_mvp_cases", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_import_preserves_multiturn_and_flags_contract_conflict():
    markdown = '''
58 case
## I. Bảo hiểm xã hội bắt buộc (09)
| # | Persona | Câu hỏi | Loại | Vai trò kỳ vọng | Vì sao |
|---|---|---|---|---|---|
| 37 | Nhân viên | L1: "theo luật thì sao?"<br>L2: "còn hồ sơ của em?" | Follow-up / thuần luật | L1 **ANSWER** → L2 **PREPARE_AND_HANDOFF** | Test. |
'''

    cases = MODULE.parse_markdown(markdown)

    assert len(cases) == 1
    assert cases[0]["source_file"] == "09_chinh-sach-bao-hiem-xa-hoi-bat-buoc.md"
    assert [turn["question"] for turn in cases[0]["turns"]] == ["theo luật thì sao?", "còn hồ sơ của em?"]
    assert cases[0]["expected_states"] == ["PREPARE_AND_HANDOFF", "ANSWER"]
    assert cases[0]["contract_flags"] == ["pure_statutory_scope_conflict"]
    assert "retrieval" in cases[0]["evaluation_tracks"]
    assert cases[0]["turns"][0]["expected_states"] == ["ANSWER"]
    assert cases[0]["turns"][1]["expected_states"] == ["PREPARE_AND_HANDOFF"]
    assert all(turn["qrel_status"] == "pending_adjudication" for turn in cases[0]["turns"])


def test_summary_does_not_hide_stale_declared_count():
    cases = MODULE.parse_markdown(
        "## A. OT (01)\n"
        "| 1 | NV | \"OT thế nào?\" | Direct | **ANSWER** | Có trong policy. |\n"
    )
    report = MODULE.summarize(cases, declared_count=58)

    assert report["case_count"] == 1
    assert report["declared_count_matches"] is False
    assert report["document_count"] == 1


def test_import_links_followup_row_to_parent_case():
    cases = MODULE.parse_markdown(
        "## E. WFH (05)\n"
        "| 21 | (tiếp #20) | L2: \"sếp không duyệt thì sao?\" | Follow-up | **HUMAN_FIRST** | Test. |\n"
    )

    assert cases[0]["continues_case_id"] == "nxv2_020"
    assert cases[0]["turns"][0]["turn"] == 2
    assert MODULE.summarize(cases)["follow_up_cases"] == 1
