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


def test_evidence_confidence_renders_three_separate_axes(result, tmp_path):
    """T012: the single gauge is split into Evidence Quality / Reasoning
    Coverage / Prediction Confidence — each rule-computed, never model
    self-assessment (resolves V1-roadmap finding #7)."""
    ctx_rich = BusinessContext(revenue="$45k MRR", growth_rate="8%/mo", team_size=6,
                               runway_months=5, market="B2B SaaS",
                               competitive_position="challenger",
                               founder_goals="APAC presence")
    sections = frr.build_premortem_sections(DECISION, ctx_rich, result)
    items = sections["Evidence Confidence"]
    gauges = {i["label"]: i["gauge"] for i in items
              if isinstance(i, dict) and "gauge" in i}
    assert set(gauges) == {"Evidence Quality", "Reasoning Coverage"}
    assert all(v in ("HIGH", "MEDIUM", "LOW") for v in gauges.values())
    flat = frr.flatten_sections({"Evidence Confidence": items})
    assert "NOT confidence in the future" in flat
    assert "never by model self-assessment" in flat
    assert "Prediction Confidence" in flat


def test_unrequested_leg_lowers_coverage_never_evidence_quality(result, tmp_path):
    """The finding-#7 fix, asserted directly: rich context + clean signals
    with NO mechanism/prediction legs requested -> Evidence Quality reads
    from the evidence alone; only Reasoning Coverage carries the gap."""
    ctx_rich = BusinessContext(revenue="$45k MRR", growth_rate="8%/mo", team_size=6,
                               runway_months=5, market="B2B SaaS",
                               competitive_position="challenger",
                               founder_goals="APAC presence")
    sections = frr.build_premortem_sections(DECISION, ctx_rich, result)
    items = sections["Evidence Confidence"]
    gauges = {i["label"]: i["gauge"] for i in items
              if isinstance(i, dict) and "gauge" in i}
    # this fixture requests neither leg: coverage takes BOTH crosses...
    assert gauges["Reasoning Coverage"] == "LOW"
    # ...and Evidence Quality is untouched by requested-ness. The fixture's
    # one unknown structural signal is its only evidence cross -> MEDIUM,
    # not the old LOW that unrequested legs used to force.
    assert gauges["Evidence Quality"] == "MEDIUM"
    crosses = [i["cross"] for i in items if isinstance(i, dict) and "cross" in i]
    assert any("NOT weak evidence" in c for c in crosses)


def test_missing_prediction_confidence_renders_unavailable(result, tmp_path):
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({"Evidence Confidence":
                                 sections["Evidence Confidence"]})
    assert "Prediction Confidence: UNAVAILABLE" in flat
    assert "no accuracy claimed" in flat.lower()


def test_ledgered_predictions_render_recorded_not_accuracy(result, tmp_path):
    from intent_engine.core.prediction_ledger import Prediction
    lp = [Prediction(source="premortem", entity_id="acme",
                     claim_text="Burn exceeds plan", probability=0.6,
                     resolve_by="2027-01-15")]
    wired = result._replace(ledgered_predictions=lp)
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), wired)
    flat = frr.flatten_sections({"Evidence Confidence":
                                 sections["Evidence Confidence"]})
    assert "Prediction Confidence: RECORDED — 1 ledgered claim(s)" in flat
    assert "graded by code" in flat
    frr._assert_no_accuracy_claim(flat)


def test_contradictions_affect_evidence_quality_axis(result, tmp_path):
    """Unverified/contradictory signals land on Evidence Quality (the
    evidence axis), not on coverage."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    items = sections["Evidence Confidence"]
    # find the crosses BETWEEN the two gauges: those belong to Evidence Quality
    labels = [(i.get("label") if isinstance(i, dict) else None) for i in items]
    eq_at = labels.index("Evidence Quality")
    rc_at = labels.index("Reasoning Coverage")
    eq_slice = items[eq_at:rc_at]
    assert any(isinstance(i, dict) and "cross" in i
               and "structural signals incomplete" in i["cross"]
               for i in eq_slice)


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
    # T012: the loop lives ONCE, in the Decision lifecycle section; the
    # appendix points there instead of restating a second, different loop.
    assert "nine-stage lifecycle" in flat
    assert "One loop, stated once" in flat


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


# =============================================================================
# T012: Alternatives Considered + nine-stage lifecycle presentation.
# =============================================================================

from types import SimpleNamespace


def _with_alternatives(result, alts):
    """Report-layer input shim: same attrs as PremortemResult + alternatives.
    (No engine schema is touched -- the frozen analyzer taxonomy stays
    frozen; a future slice can thread structured alternatives through.)"""
    ns = SimpleNamespace(**result._asdict())
    ns.alternatives = alts
    return ns


def test_structured_alternatives_render_with_tradeoffs(result):
    alts = [{
        "alternative": "License instead of building in-region",
        "why_considered": "lower fixed cost",
        "main_advantage": "faster market entry",
        "main_risk": "margin ceded to the licensee",
        "why_not_recommended": "conflicts with the stated control constraint",
        "preferable_if": "runway drops below 6 months",
    }]
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"),
        _with_alternatives(result, alts))
    flat = frr.flatten_sections({"Alternatives Considered":
                                 sections["Alternatives Considered"]})
    assert "1. License instead of building in-region" in flat
    for label in ("Why considered", "Main advantage", "Main risk",
                  "Why not currently recommended", "Would become preferable if"):
        assert label in flat
    assert "NONE DOCUMENTED" not in flat


def test_missing_alternatives_render_none_documented(result):
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({"Alternatives Considered":
                                 sections["Alternatives Considered"]})
    assert "NONE DOCUMENTED" in flat
    assert "never invents one" in flat


def test_no_alternative_is_invented_from_scenarios(result):
    """Scenario names must not be repackaged as 'alternatives'."""
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({"Alternatives Considered":
                                 sections["Alternatives Considered"]})
    for s in result.scenario_set.scenarios:
        assert s.name not in flat.replace("re-scope", "")


# --- lifecycle: the ten state scenarios --------------------------------------

LIFE = "Decision lifecycle"


def _life_flat(result, svc, rec):
    wired = result._replace(decision_record=rec)
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), wired,
        decision_service=svc)
    return sections[LIFE], frr.flatten_sections({LIFE: sections[LIFE]})


def _mk(tmp_path, *events):
    svc = DecisionService(str(tmp_path / "decisions.db"))
    rec = svc.create_decision("founder")
    for ev in events:
        svc.record_event(rec.decision_id, ev, actor_type="human",
                         actor_id="founder", source="cli")
    return svc, rec


def _marks(items):
    """(checked, current, future/sub, crossed) stage-number sets."""
    import re as _re
    got = {"check": set(), "h": set(), "sub": set(), "cross": set()}
    for it in items:
        if not isinstance(it, dict):
            continue
        for kind in got:
            if kind in it:
                m = _re.search(r"(\d)\.", str(it[kind]))
                if m:
                    got[kind].add(int(m.group(1)))
    return got


def test_lifecycle_draft(result, tmp_path):
    svc, rec = _mk(tmp_path)
    items, flat = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert {1, 2}.issubset(marks["check"])
    assert marks["h"] == {3}                       # current: recommendation
    assert 9 in marks["sub"] and "never shown as reached" in flat


def test_lifecycle_under_review(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted")
    items, _ = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert 3 in marks["check"]                     # recommendation issued
    assert marks["h"] == {4}                       # decision-taken is current


def test_lifecycle_approved_not_executing(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted", "DecisionApproved")
    items, _ = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert 4 in marks["check"]
    assert marks["h"] == {5}                       # execution is next, not done
    assert 6 not in marks["check"] and 7 not in marks["check"]


def test_lifecycle_executing(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted",
                   "DecisionApproved", "ExecutionStarted")
    items, _ = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert 5 in marks["check"]
    assert marks["h"] == {6}                       # monitoring is current


def test_lifecycle_paused(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted",
                   "DecisionApproved", "ExecutionStarted", "ExecutionPaused")
    items, flat = _life_flat(result, svc, rec)
    assert "currently paused" in flat
    assert 5 in _marks(items)["check"]


def test_lifecycle_resolved_not_calibrated(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted",
                   "DecisionApproved", "ExecutionStarted", "DecisionResolved")
    items, _ = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert 7 in marks["check"]
    assert marks["h"] == {8}                       # calibration current
    assert 8 not in marks["check"]                 # never shown as done


def test_lifecycle_calibrated(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted",
                   "DecisionApproved", "ExecutionStarted", "DecisionResolved", "DecisionCalibrated")
    items, _ = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert {7, 8}.issubset(marks["check"])
    assert marks["h"] == {9}                       # lessons promoted: future
    assert 9 not in marks["check"]


def test_lifecycle_declined(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted", "DecisionDeclined")
    items, flat = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert 4 in marks["check"] and "declined" in flat.lower()
    assert marks["cross"] == {5, 6, 7, 8, 9}       # honest: not applicable
    assert marks["h"] == set()                     # no fake current stage


def test_lifecycle_cancelled(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted",
                   "DecisionApproved", "ExecutionStarted", "DecisionCancelled")
    items, flat = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert "CANCELLED" in flat
    assert 5 in marks["check"]                     # it DID execute
    assert "execution abandoned" in flat
    assert {6, 7, 8, 9}.issubset(marks["cross"])


def test_lifecycle_superseded_after_approval(result, tmp_path):
    svc, rec = _mk(tmp_path, "RecommendationIssued", "DecisionSubmitted", "DecisionApproved")
    new = svc.create_decision("founder")
    svc.supersede_decision(rec.decision_id, new.decision_id)
    items, flat = _life_flat(result, svc, rec)
    marks = _marks(items)
    assert "SUPERSEDED" in flat
    assert 4 in marks["check"]                     # events remember approval
    assert "later superseded" in flat
    assert marks["h"] == set()


def test_lifecycle_without_record_is_unavailable(result):
    sections = frr.build_premortem_sections(
        DECISION, BusinessContext(revenue="$60k MRR"), result)
    flat = frr.flatten_sections({LIFE: sections[LIFE]})
    assert "UNAVAILABLE" in flat
    assert "not tracked" in flat
