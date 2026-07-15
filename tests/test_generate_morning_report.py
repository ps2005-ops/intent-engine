import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_morning_report import _parse_test_summary, _extract_needs_spec_items, render_report  # noqa: E402

REAL_SUCCESS_RESULT_JSON = Path(__file__).parent / "fixtures" / "real_nightly_agent_success_result.json"


def test_parse_test_summary_finds_the_real_pytest_summary_line():
    tail = "............                                                              [100%]\n413 passed, 1 skipped, 10 warnings in 341.51s (0:05:41)\n"
    assert _parse_test_summary(tail) == "413 passed, 1 skipped, 10 warnings in 341.51s (0:05:41)"


def test_parse_test_summary_finds_a_failure_line():
    tail = "FAILED tests/test_foo.py::test_bar\n1 failed, 412 passed in 12.3s"
    assert _parse_test_summary(tail) == "1 failed, 412 passed in 12.3s"


def test_parse_test_summary_handles_empty_output():
    assert _parse_test_summary("") == "(no output captured)"


def test_extract_needs_spec_items_reads_the_real_roadmap():
    """Real end-to-end check against this repo's actual ROADMAP.md."""
    items = _extract_needs_spec_items()
    assert len(items) >= 5
    assert any("recipient" in item.lower() for item in items)
    assert any("evaluation-stage" in item.lower() or "evaluation stage" in item.lower() for item in items)


# --- render_report's outcome classification: real bug, real regression fixture


def _args(result_json, final_tests="1 passed in 1s"):
    return SimpleNamespace(
        task_id="T001", branch="agent/T001", result_json=str(result_json),
        baseline_tests="1 passed in 1s", final_tests=final_tests,
        diff_stats="1 file changed", pr_note="test",
    )


def test_render_report_classifies_a_real_successful_run_as_done():
    """Regression test for a real bug: this repo's very first real
    nightly_agent.sh rehearsal (2026-07-15) reported "PARTIAL/BLOCKED
    (unknown)" for a run that had genuinely succeeded (5 new tests, zero
    regressions, a real commit, the agent's own final message said
    "Done"). Root cause: this function looked for a "status" field that
    does not exist in the real --output-format json shape (the real
    fields are "subtype"/"is_error") -- confirmed by inspecting the
    actual saved JSON, not guessed. Fixed, and pinned here against the
    exact real JSON that exposed it."""
    report = render_report(_args(REAL_SUCCESS_RESULT_JSON), "2026-07-15T17:26:15+00:00")
    assert "Result: **DONE**" in report


def test_render_report_classifies_is_error_true_as_partial_blocked(tmp_path):
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"subtype": "error", "is_error": True, "result": "hit an error", "total_cost_usd": 0.1}))
    report = render_report(_args(result_path), "2026-07-15T00:00:00+00:00")
    assert "Result: **PARTIAL/BLOCKED**" in report
    assert "is_error=True" in report


def test_render_report_classifies_malformed_json_as_partial_blocked_not_done(tmp_path):
    """Fails closed: an unparseable result must never be reported as DONE."""
    result_path = tmp_path / "result.json"
    result_path.write_text("not valid json{{{")
    report = render_report(_args(result_path), "2026-07-15T00:00:00+00:00")
    assert "Result: **PARTIAL/BLOCKED**" in report


def test_render_report_classifies_a_success_status_with_test_failures_as_partial_blocked():
    """Even if the model reports success, real test failures in the final
    suite run must override that -- a model's own self-report is not
    trusted over real, measured evidence."""
    report = render_report(_args(REAL_SUCCESS_RESULT_JSON, final_tests="1 failed, 4 passed"), "2026-07-15T00:00:00+00:00")
    assert "Result: **PARTIAL/BLOCKED**" in report
