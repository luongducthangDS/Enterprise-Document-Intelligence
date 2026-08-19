import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "eval_nexatech_post_mvp.py"
SPEC = importlib.util.spec_from_file_location("eval_nexatech_post_mvp", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_expected_signals_resolves_mixed_and_contract_states():
    assert MODULE.expected_signals(["OUT_OF_SCOPE", "ANSWER"], []) == (
        {"assistant_role": "ANSWER", "runtime_state": "ANSWER"},
        None,
    )
    assert MODULE.expected_signals(["INSUFFICIENT_EVIDENCE", "GUIDE"], []) == (
        {"assistant_role": "GUIDE", "runtime_state": "ABSTAIN"},
        None,
    )
    assert MODULE.expected_signals(["ANSWER"], ["pure_statutory_scope_conflict"]) == (
        {"runtime_state": "OUT_OF_SCOPE"},
        None,
    )


def test_expected_signals_excludes_unresolved_fixture():
    signals, reason = MODULE.expected_signals(
        ["CONFLICTING_SOURCES"], ["requires_conflicting_source_fixture"]
    )
    assert signals == {}
    assert reason == "unresolved_contract_flag:requires_conflicting_source_fixture"


def test_evaluate_signals_checks_independent_contract_dimensions():
    checks, passed = MODULE.evaluate_signals(
        {"runtime_state": "ABSTAIN", "assistant_role": "GUIDE"},
        {
            "state": "ABSTAIN",
            "boundary": {"assistant_role": "GUIDE"},
            "needs_clarification": False,
        },
    )
    assert checks == {"runtime_state": True, "assistant_role": True}
    assert passed is True

    checks, passed = MODULE.evaluate_signals(
        {"runtime_state": "ANSWER", "assistant_role": "GUIDE"},
        {"state": "ANSWER", "boundary": {"assistant_role": "ANSWER"}},
    )
    assert checks == {"runtime_state": True, "assistant_role": False}
    assert passed is False
