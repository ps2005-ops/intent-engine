"""Bars for scripts/render_founder_report.py (founder report, approved
2026-07-19 decision 3; bars pre-scoped in docs/report_mockup/DESIGN_NOTE.md):
golden-file from the REAL 2026-07-17 report, honesty-marker rendering
(unavailable / none-matched / data-gaps / 0-resolved), language wall on
the artifact, and parse-park on an unrecognized shape."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import render_founder_report as r  # noqa: E402

REAL_REPORT = Path(__file__).parent.parent / "reports" / "weekly_regime_report_2026-07-17.txt"


def _render_real():
    return r.render(r.parse_report(REAL_REPORT.read_text()))


# --- golden-file / no-new-claims -------------------------------------------

def test_real_report_parses_and_every_number_traces_to_source():
    parsed = r.parse_report(REAL_REPORT.read_text())
    assert parsed["snapshot_date"] == "2026-07-17"
    # the three real predictions, verbatim P-values from the .txt
    ps = sorted(p["p"] for p in parsed["predictions"])
    assert ps == ["0.58", "0.65", "0.72"]
    assert parsed["none_matched"] is True
    html = _render_real()
    for p in parsed["predictions"]:
        assert p["p"] in html and p["by"] in html  # nothing dropped, nothing added


def test_no_invented_numbers_every_html_probability_came_from_source():
    import re
    src = REAL_REPORT.read_text()
    html = _render_real()
    src_ps = set(re.findall(r"P=(0\.\d+)", src))
    html_ps = set(re.findall(r"P = (0\.\d+)", html))
    assert html_ps == src_ps  # no probability appears in HTML that wasn't in the source


# --- honesty markers as features -------------------------------------------

def test_unavailable_series_render_as_badges():
    html = _render_real()
    # 3 series are UNAVAILABLE in the real run (credit spreads, CPI, unemployment)
    assert html.count('class="badge unavail">UNAVAILABLE') == 3


def test_none_matched_is_a_featured_card():
    html = _render_real()
    assert "None matched this run — and that's the finding." in html


def test_no_gaps_run_renders_the_clean_gaps_line():
    html = _render_real()
    assert "No genuine data gaps detected in this run." in html
    assert "gaps active" not in html  # the real run had no gaps


def test_zero_resolved_track_record_card():
    html = _render_real()
    assert "0 predictions resolved so far" in html
    assert "no accuracy is claimed" in html


def test_active_gaps_render_loud_when_present():
    # Synthetic report WITH a data-gaps section -> active (amber) rendering.
    text = (
        "REGIME SNAPSHOT -- as of 2026-08-01\n"
        "----------------------------------------------------------------------\n"
        "Yield curve (T10Y2Y):        not inverted  [FRED T10Y2Y, 2026-07-31]\n"
        "\n"
        "!! DATA GAPS DETECTED (review before trusting affected indicators)\n"
        "----------------------------------------------------------------------\n"
        "- UNRATE: 1 missing observation(s) (2025-10-01) -- genuine data gap(s)\n"
        "\n"
        "Structural mechanisms possibly in play: none matched -- no forced match on an empty/weak signal.\n"
        "\n"
        "RESOLVABLE PREDICTIONS RECORDED THIS RUN (source=market)\n"
        "----------------------------------------------------------------------\n"
        "None recorded this run.\n"
        "\n"
        "CALIBRATION (read-only; no feedback into generation)\n"
        "----------------------------------------------------------------------\n"
        "market: no resolutions yet.\n"
    )
    html = r.render(r.parse_report(text))
    assert "gaps active" in html and "UNRATE: 1 missing" in html
    assert "None recorded this run." in html


def test_resolved_calibration_renders_verbatim_not_the_zero_card():
    text = (
        "REGIME SNAPSHOT -- as of 2026-09-20\n"
        "----------------------------------------------------------------------\n"
        "Yield curve (T10Y2Y):        not inverted  [FRED T10Y2Y, 2026-09-19]\n"
        "\n"
        "Structural mechanisms possibly in play: none matched -- x\n"
        "\n"
        "RESOLVABLE PREDICTIONS RECORDED THIS RUN (source=market)\n"
        "----------------------------------------------------------------------\n"
        "None recorded this run.\n"
        "\n"
        "CALIBRATION (read-only; no feedback into generation)\n"
        "----------------------------------------------------------------------\n"
        "market: 5 resolved, mean Brier 0.1800\n"
        "baseline: 5 resolved, mean Brier 0.2100\n"
    )
    html = r.render(r.parse_report(text))
    assert "5 resolved, mean Brier 0.1800" in html
    assert "0 predictions resolved so far" not in html  # data-driven, not hardcoded


# --- parse-park + language wall --------------------------------------------

def test_unrecognized_report_raises_not_guesses():
    with pytest.raises(ValueError, match="REGIME SNAPSHOT"):
        r.parse_report("just some text that isn't a report")


def test_artifact_passes_language_walls():
    # render() calls assert_language_walls internally; a clean real report
    # must not raise.
    _render_real()  # would raise on a wall violation
