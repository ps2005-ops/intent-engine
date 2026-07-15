import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_morning_report import _parse_test_summary, _extract_needs_spec_items  # noqa: E402


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
