"""The forecast-quality gate, pinned to the defects the July programme had."""
from intent_engine.core import forecast_quality as FQ


def _july(**kw):
    d = {"id": "x1", "created_at": "2026-07-20T06:00:00+00:00",
         "source": "market", "probability": 0.58, "resolve_by": "2026-08-31",
         "resolution_source": "fred",
         "claim_text": "Unemployment rate rises to at least 3.40% by end of August",
         "resolution_rule": {"type": "level", "series": "UNRATE", "op": ">=",
                             "value": 3.4, "by": "2026-08-31"}}
    d.update(kw)
    return d


def _codes(fs):
    return {f.code for f in fs}


def _complete(c):
    c.mechanism, c.baseline, c.model_version = "labour slack", "persistence", "v1"
    c.evidence_provenance, c.invalidation = ["fred:UNRATE"], "series redefined"
    return c


def test_already_true_at_creation_is_quarantined():
    c = _complete(FQ.from_july(_july()))
    fs = FQ.check(c, observe=lambda s, d: [4.3, 4.2])
    assert "ALREADY_TRUE_AT_CREATION" in _codes(fs)
    assert FQ.verdict(fs) == FQ.QUARANTINE


def test_a_basis_point_threshold_on_a_percent_series_is_rejected():
    c = _complete(FQ.from_july(_july(resolution_rule={
        "type": "level", "series": "BAMLH0A0HYM2", "op": ">=", "value": 310.0,
        "by": "2026-09-03"}, claim_text="spreads widen")))
    fs = FQ.check(c, observe=lambda s, d: [2.9, 2.7, 2.73])
    assert "IMPOSSIBLE_OR_UNIT_MISMATCH" in _codes(fs)
    assert FQ.verdict(fs) == FQ.REJECT


def test_a_persistence_claim_read_on_one_day_is_quarantined():
    c = _complete(FQ.from_july(_july(
        claim_text="the spread remains above +0.30 percentage points",
        resolution_rule={"type": "level", "series": "T10Y2Y", "op": ">=",
                         "value": 0.3, "by": "2026-10-16"})))
    fs = FQ.check(c, observe=lambda s, d: [0.2, 0.25])
    assert "CLAIM_RULE_MISMATCH" in _codes(fs)


def test_a_reachable_well_formed_forecast_is_admitted():
    c = _complete(FQ.from_july(_july(claim_text="UNRATE is at least 4.6%",
                                     resolution_rule={"type": "level",
                                                      "series": "UNRATE",
                                                      "op": ">=", "value": 4.6,
                                                      "by": "2026-08-31"})))
    fs = FQ.check(c, observe=lambda s, d: [4.3, 4.2])
    assert FQ.verdict(fs) == FQ.ADMIT, fs


def test_without_an_observer_the_data_checks_are_not_reported_as_passed():
    fs = FQ.check(_complete(FQ.from_july(_july())))
    assert "THRESHOLD_NOT_CHECKED" in _codes(fs)


def test_a_test_fixture_never_counts_as_a_real_forecast():
    c = FQ.from_july(_july(source="premortem", resolution_rule=None),
                     classification="TEST_FIXTURE")
    fs = FQ.check(c)
    assert "NOT_A_REAL_FORECAST" in _codes(fs) and FQ.verdict(fs) == FQ.REJECT


def test_no_rule_no_admission():
    fs = FQ.check(_complete(FQ.from_july(_july(resolution_rule=None))))
    assert "MISSING_RESOLUTION_RULE" in _codes(fs)
    assert FQ.verdict(fs) == FQ.REJECT


def test_evidence_after_the_cutoff_is_rejected():
    c = _complete(FQ.from_july(_july()))
    c.evidence_dates = ["2026-07-25"]
    fs = FQ.check(c, observe=lambda s, d: [4.0])
    assert "EVIDENCE_AFTER_CUTOFF" in _codes(fs)


def test_a_duplicate_contract_in_one_batch_is_caught():
    a = _complete(FQ.from_july(_july(id="a")))
    b = _complete(FQ.from_july(_july(id="b")))
    res = FQ.admit_batch([a, b], observe=lambda s, d: [3.0])
    assert len(res[FQ.ADMIT]) == 1
    assert any("DUPLICATE_CONTRACT" in _codes(fs) for _, fs in res[FQ.REJECT])


def test_two_models_on_one_target_are_not_duplicates():
    a = _complete(FQ.from_july(_july(id="a", claim_text="x (momentum baseline)")))
    b = _complete(FQ.from_july(_july(id="b", claim_text="x (base-rate baseline)")))
    res = FQ.admit_batch([a, b], observe=lambda s, d: [3.0])
    assert len(res[FQ.ADMIT]) == 2


def _paper(**kw):
    p = {"forecast_id": "pv1-fwd:logit_A:SPY:2026-12-09",
         "decision_ts": "2026-12-10T00:30:00+00:00",
         "information_cutoff": "2026-12-09", "price_cutoff": "2026-12-09",
         "target": "excess return vs cash", "probability": 0.55,
         "direction": "LONG", "horizon_sessions": 21, "entry_rule": "open",
         "exit_rule": "open +21", "instrument": "SPY",
         "data_vintage": {"prices": {"SPY": {"source": "yahoo_chart.v1"}}},
         "causal_mechanism": "none", "competing_hypotheses": ["cash"],
         "model_version": "logit_A:etf:abc", "evidence_ids": ["px:SPY"],
         "invalidation_condition": {"forecast_voided_if": "no bar"},
         "policy_id": "logit_A", "decision_date": "2026-12-09",
         "provenance": "NEW_IN_THIS_WORK"}
    p.update(kw)
    return p


def test_a_paper_registration_passes_and_a_bad_one_is_held():
    assert FQ.verdict(FQ.check(FQ.from_paper(_paper()))) == FQ.ADMIT
    bad = FQ.from_paper(_paper(price_cutoff="2026-12-11"))   # future bar
    assert FQ.verdict(FQ.check(bad)) == FQ.REJECT


def test_a_control_is_its_own_baseline():
    c = FQ.from_paper(_paper(competing_hypotheses=[], provenance="CONTROL"))
    assert "MISSING_BASELINE" not in _codes(FQ.check(c))


def test_a_derived_econ_contract_is_flagged_not_hidden():
    first = {"expectation_id": "e1", "created_at": "2026-08-27",
             "information_cutoff": "2026-08-27", "confidence": 0.5,
             "quantity": "INDPRO", "horizon_days": 180, "expires_at": "2027-02-23",
             "mechanism": "m", "model": "BASE", "belief_id": "b",
             "falsifier": "f", "source": "V3", "resolution_rule": "prose"}
    later = dict(first, resolution_contract={"series_id": "INDPRO",
                                             "vintage_policy": "LATEST_REVISION"})
    c = FQ.from_econ(first, [first, later])
    fs = FQ.check(c)
    assert "CONTRACT_DERIVED_FROM_PROSE" in _codes(fs)
    assert FQ.verdict(fs) == FQ.ADMIT


def test_the_t006_fixture_is_classified_and_excluded():
    assert FQ.classify_entity("t006-live") == "TEST_FIXTURE"
    assert FQ.classify_entity("shopify") == "GENUINE"
