"""Incident regression: re-analysing a company must never return HTTP 500.

A real external tester hit this. Analysing Palantir a second time on the same
date raised

    ValueError: idempotency_key 'run:palantir.com:<as_of>' was already used
                for different content

and the Guest Demo returned 500. The run identity was `run:{domain}:{as_of}`,
but the recorded payload embeds the approved source set, which legitimately
differs between two analyses of the same company on the same day because
discovery depends on which pages respond. Sony only escaped because both its
runs produced identical near-empty content.
"""
import pytest

from intent_engine.founder_intelligence.service import (
    FounderIntelligenceService,
    analysis_fingerprint,
)
from intent_engine.founder_intelligence.intake import validate_input
from intent_engine.founder_intelligence.fixtures import demo_claims


def _run(svc, approved, as_of="2026-07-27T00:00:00+00:00"):
    return svc.run(company_name="Palantir Technologies",
                   website="https://www.palantir.com",
                   claims_by_section=demo_claims(), as_of=as_of,
                   approved_inputs=approved)


def test_reanalysis_with_different_evidence_does_not_raise(tmp_path):
    """The exact tester failure."""
    svc = FounderIntelligenceService(tmp_path / "fi.jsonl")
    _run(svc, ("src-a", "src-b"))
    # Second analysis, same company and date, different sources retrieved.
    result = _run(svc, ("src-a", "src-b", "src-c"))
    assert result["run_id"]


def test_reanalysis_yields_a_distinct_run_not_a_collision(tmp_path):
    svc = FounderIntelligenceService(tmp_path / "fi.jsonl")
    first = _run(svc, ("src-a",))["run_id"]
    second = _run(svc, ("src-a", "src-b"))["run_id"]
    assert first != second, "different evidence must be a different run"


def test_identical_inputs_still_collapse_to_one_run(tmp_path):
    """The idempotent-retry contract must survive the fix."""
    svc = FounderIntelligenceService(tmp_path / "fi.jsonl")
    a = _run(svc, ("src-a", "src-b"))["run_id"]
    b = _run(svc, ("src-a", "src-b"))["run_id"]
    assert a == b


def test_approved_input_order_does_not_change_identity(tmp_path):
    svc = FounderIntelligenceService(tmp_path / "fi.jsonl")
    a = _run(svc, ("src-a", "src-b"))["run_id"]
    b = _run(svc, ("src-b", "src-a"))["run_id"]
    assert a == b, "identity must not depend on discovery ordering"


def test_pipeline_version_participates_in_identity(monkeypatch):
    """A stale run produced by older behaviour must not be reused as current."""
    ci = validate_input(company_name="X", website="https://x.com",
                        approved_inputs=("s1",))
    before = analysis_fingerprint(ci)
    import intent_engine.founder_intelligence.service as mod
    monkeypatch.setattr(mod, "SYNTHESIS_VERSION", "9.9.9")
    assert analysis_fingerprint(ci) != before


def test_analysis_version_names_every_component():
    v = FounderIntelligenceService.analysis_version()
    for part in ("analysis=", "discovery=", "evidence=", "quality=",
                 "synthesis="):
        assert part in v
