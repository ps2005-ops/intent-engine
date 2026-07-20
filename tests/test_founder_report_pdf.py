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


ORIGINAL_NINE = ["Executive Summary", "Decision", "Mechanisms", "Evidence",
                 "Contradictions", "Scenario tree", "Metrics to watch",
                 "90-day checklist", "Prediction"]


def test_pdf_has_all_sections_including_original_nine(result, tmp_path):
    out = tmp_path / "premortem.pdf"
    sections = frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"),
                                        result, out)
    assert list(sections) == frr.PREMORTEM_SECTION_ORDER
    # the original C2 DoD set survives as a subset, in order
    assert [s for s in sections if s in ORIGINAL_NINE] == ORIGINAL_NINE
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    for title in frr.PREMORTEM_SECTION_ORDER:
        assert title.encode() in raw, title


def test_recommendation_is_a_decision_framework_not_a_prediction(result, tmp_path):
    """Founder feedback #1: conditions drawn from stated constraints/risks,
    with an explicit delay path — and no forecast language."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = "\n".join(frr.flatten_sections({"Recommendation": sections["Recommendation"]})
                     .splitlines())
    assert "Proceed only if ALL of the following hold" in flat
    assert "delay or re-scope" in flat
    assert "does not forecast an outcome" in flat
    # every condition traces to a stated constraint, the key sensitivity, or a risk
    for c in result.intent.constraints:
        assert c in flat
    assert result.risk_audit.key_sensitivity in flat


def test_evidence_confidence_is_rule_computed_about_the_analysis(result, tmp_path):
    """Founder feedback #2: confidence in the ANALYSIS, never the future,
    and derived by rule from the checks — not model self-assessment."""
    ctx_rich = BusinessContext(revenue="$45k MRR", growth_rate="8%/mo", team_size=6,
                               runway_months=5, market="B2B SaaS",
                               competitive_position="challenger",
                               founder_goals="APAC presence")
    sections = frr.build_premortem_sections(DECISION, ctx_rich, result)
    items = sections["Evidence Confidence"]
    gauge = next(i for i in items if isinstance(i, dict) and "gauge" in i)
    assert gauge["gauge"] in ("HIGH", "MEDIUM", "LOW")
    flat = frr.flatten_sections({"Evidence Confidence": items})
    assert "NOT confidence in the future" in flat
    assert "never by model self-assessment" in flat
    # rule check: this fixture has an unknown signal + no mechanisms + no
    # ledger entry -> 3 crosses -> LOW. Deterministic, not a judgment call.
    assert gauge["gauge"] == "LOW"
    assert sum(1 for i in items if isinstance(i, dict) and "cross" in i) == 3


def test_evidence_separates_facts_from_inference_and_grades_risk(result, tmp_path):
    """Founder feedback #3 + #10."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    ev = sections["Evidence"]
    headers = [i["h"] for i in ev if isinstance(i, dict) and "h" in i]
    assert any("Observed inputs" in h for h in headers)
    assert any("Inference and possible consequence" in h for h in headers)
    bars = [i for i in ev if isinstance(i, dict) and "bar" in i]
    assert len(bars) == len(result.risk_audit.failure_modes)
    assert bars[0]["bar"] == "HIGH"           # 'likely' sorts first
    assert all(b["bar"] in frr._RISK_ORDER for b in bars)
    # inference is a separate, subordinate item — never fused into the fact
    subs = [i["sub"] for i in ev if isinstance(i, dict) and "sub" in i]
    assert len(subs) == len(bars)
    assert all(s.startswith("Inference: ") for s in subs)


def test_assumptions_are_numbered_and_trigger_rerun(result, tmp_path):
    """Founder feedback #4."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR", team_size=6), result)
    flat = frr.flatten_sections({"Assumptions": sections["Assumptions"]})
    assert "1. 18-month timeline (stated constraint)" in flat
    assert "2. $2M budget (stated constraint)" in flat
    assert "re-run because assumption #N changed" in flat


def test_what_would_change_this_section(result, tmp_path):
    """Founder feedback #5: the report is dynamic, with explicit triggers."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({"x": sections["What would change this"]})
    assert result.risk_audit.key_sensitivity in flat
    assert "any numbered assumption above breaks" in flat
    assert "upside scenario band" in flat and "downside scenario band" in flat


def test_company_snapshot_grounds_the_report(result, tmp_path):
    """Founder feedback #8: written for one company. Missing fields are
    labeled 'not provided' rather than silently dropped."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({"Company Snapshot": sections["Company Snapshot"]})
    assert "Revenue: $60k MRR" in flat
    assert "Team size: not provided" in flat


def test_appendix_makes_the_report_auditable(result, tmp_path):
    """Founder feedback #9 + #12."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result,
        generated_at="2026-07-20T12:00:00+00:00")
    flat = frr.flatten_sections({"Appendix": sections["Appendix"]})
    for expected in ("Methodology", "Evidence sources", "Mechanisms consulted",
                     "Prediction ledger", "Version & audit trail",
                     "The decision loop"):
        assert expected in flat, expected
    assert "Engine version:" in flat
    assert "2026-07-20T12:00:00+00:00" in flat
    assert "Decision journal" in flat and "Calibration" in flat


def test_visual_elements_are_wall_checked_not_a_loophole(result, tmp_path):
    """A claim hidden inside a box/gauge/bar/tree must still hit the walls."""
    poisoned = {"Recommendation": [{"box": [{"check": "our proven 90% hit rate"}]}]}
    flat = frr.flatten_sections(poisoned)
    assert "proven" in flat and "hit rate" in flat
    with pytest.raises(ValueError):
        frr._assert_no_accuracy_claim(flat)


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


# =============================================================================
# T011 Slice 2A bars (ROADMAP.md): Decision Record -> report wiring.
# Reads only; absent record -> unchanged output; walls still run.
# =============================================================================

from intent_engine.core.decision_record import DecisionService  # noqa: E402


def _result_with_record(base_result, svc, entity="acme"):
    rec = svc.create_decision("founder", idempotency_key="report-test")
    svc.add_entity(rec.decision_id, entity, "subject")
    return base_result._replace(decision_record=rec), rec


def test_report_renders_decision_id_key_status_and_owner(result, tmp_path):
    """Bars (a)-(c): identity header, folded three-axis status badge, owner."""
    svc = DecisionService(str(tmp_path / "decisions.db"))
    wired, rec = _result_with_record(result, svc)
    svc.record_event(rec.decision_id, "OwnerAssigned", actor_type="human",
                     actor_id="founder", source="cli",
                     payload={"owner": "Pratham"})
    out = tmp_path / "premortem.pdf"
    sections = frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"),
                                        wired, out, decision_service=svc)
    flat = frr.flatten_sections(sections)
    assert rec.decision_key in flat and rec.decision_id in flat
    assert "decision=draft" in flat            # folded, not inferred
    assert "execution=not_started" in flat
    assert "evaluation=unresolved" in flat
    assert "Owner: Pratham" in flat
    # the badge is read from the fold; the record's schema version is in the
    # audit trail (bar e)
    assert f"record schema v{rec.record_schema_version}" in flat
    # and it made it into the actual PDF bytes (uncompressed streams)
    assert rec.decision_key.encode() in out.read_bytes()


def test_report_renders_supersession_links(result, tmp_path):
    """Bar (d): supersedes / superseded-by cross-links by decision_key."""
    svc = DecisionService(str(tmp_path / "decisions.db"))
    wired_old, old_rec = _result_with_record(result, svc)
    new_rec = svc.create_decision("founder", idempotency_key="successor")
    svc.supersede_decision(old_rec.decision_id, new_rec.decision_id)

    flat_old = frr.flatten_sections(frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), wired_old,
        decision_service=svc))
    assert f"Superseded by: {new_rec.decision_key}" in flat_old
    assert "decision=superseded" in flat_old

    wired_new = result._replace(decision_record=new_rec)
    flat_new = frr.flatten_sections(frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), wired_new,
        decision_service=svc))
    assert f"Supersedes: {old_rec.decision_key}" in flat_new


def test_report_without_record_is_unchanged(result, tmp_path):
    """Bar (f): additive default -- no record, no new lines, same sections."""
    baseline = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result,
        generated_at="2026-07-20T00:00:00+00:00")
    with_kwarg = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result,
        generated_at="2026-07-20T00:00:00+00:00", decision_service=None)
    assert baseline == with_kwarg
    flat = frr.flatten_sections(baseline)
    assert "Decision record" not in flat


def test_record_wiring_passes_walls_and_never_writes_events(result, tmp_path):
    """Bar (g) + the read-only wall: rendering appends ZERO decision events."""
    svc = DecisionService(str(tmp_path / "decisions.db"))
    wired, rec = _result_with_record(result, svc)
    events_before = len(svc.get_events(rec.decision_id))
    out = tmp_path / "premortem.pdf"
    sections = frr.render_premortem_pdf(DECISION, BusinessContext(revenue="$60k MRR"),
                                        wired, out, decision_service=svc)
    flat = frr.flatten_sections(sections)
    frr.assert_language_walls(flat)            # would raise on violation
    frr._assert_no_accuracy_claim(flat)
    assert len(svc.get_events(rec.decision_id)) == events_before   # reads only
