"""C2 (PLAN_2026-07-21) definition-of-done tests for the premortem PDF.

Given a real analysis fixture (the canned extraction the analyzer tests use,
run through the REAL PremortemAnalyzer with a fake LLM client — zero model
calls), a PDF is produced with all nine approved sections; the "what we
could not verify" block renders even when empty-labelled; honesty markers
are present; no accuracy claim anywhere. Streams are uncompressed, so
section presence is asserted directly on the PDF bytes.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.simulator.analysis import PremortemAnalyzer  # noqa: E402
from intent_engine.simulator.context_schema import BusinessContext  # noqa: E402
from intent_engine.simulator.pipeline import PremortemResult  # noqa: E402


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


frr = _load("_frr_pdf_test", "scripts/render_founder_report.py")
ta = _load("_test_analysis_fixture", "tests/test_analysis.py")

DECISION = "Expand into Asia with $2M."


@pytest.fixture()
def result():
    analyzer = PremortemAnalyzer(client=ta.FakeLLMClient(ta.CANNED_FLAT_RESPONSE))
    ar = analyzer.run(DECISION, BusinessContext(revenue="$60k MRR"))
    return PremortemResult(
        intent=ar.intent, risk_audit=ar.risk_audit, scenario_set=ar.scenario_set,
        elapsed_seconds=0.0, ranked_mechanisms=None, ledgered_predictions=None)


def test_pdf_has_all_nine_sections(result, tmp_path):
    out = tmp_path / "premortem.pdf"
    sections = frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"),
                                        result, out)
    assert list(sections) == frr.PREMORTEM_SECTION_ORDER
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    for title in frr.PREMORTEM_SECTION_ORDER:
        assert title.encode() in raw, title


def test_honesty_markers_and_no_accuracy_claim(result, tmp_path):
    out = tmp_path / "premortem.pdf"
    frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"), result, out)
    raw = out.read_bytes()
    # honesty markers: unrequested legs say UNAVAILABLE; weak signals say UNKNOWN
    assert b"UNAVAILABLE" in raw
    assert b"UNKNOWN" in raw
    # mandatory could-not-verify block present (uncertain market timing flags it)
    assert b"WHAT WE COULD NOT VERIFY" in raw
    # only permitted performance statement is the disclaimer
    assert b"no accuracy is claimed" in raw
    flat = raw.decode("cp1252", errors="ignore").lower()
    for forbidden in ("track record", "hit rate", "win rate", "correctly predicted"):
        assert forbidden not in flat


def test_could_not_verify_block_renders_even_when_empty():
    lines = frr._could_not_verify_lines([])
    assert lines[0].startswith("WHAT WE COULD NOT VERIFY")
    assert "NONE FLAGGED" in lines[1]          # empty-labelled, not omitted
    lines = frr._could_not_verify_lines(["Market timing signal: uncertain"])
    assert lines[1] == "- Market timing signal: uncertain"


def test_accuracy_claim_wall_blocks_render(result, tmp_path, monkeypatch):
    poisoned = result.risk_audit.model_copy(
        update={"narrative_summary": "Our proven engine has a 90% hit rate."})
    bad = PremortemResult(intent=result.intent, risk_audit=poisoned,
                          scenario_set=result.scenario_set, elapsed_seconds=0.0)
    out = tmp_path / "bad.pdf"
    with pytest.raises(ValueError, match="Accuracy-claim wall"):
        frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"), bad, out)
    assert not out.exists()  # walls run before any byte is written
