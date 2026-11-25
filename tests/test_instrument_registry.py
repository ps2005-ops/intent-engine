"""Point-in-time eligibility: OLO, and the survivorship rule."""
from datetime import date, timedelta

from intent_engine.market import instrument_registry as IR
from intent_engine.market import outcome_resolver as OR


def _reg(filings):
    return IR.Registry(filings_for=lambda cik: filings, cik_for=lambda s: 1)


def _row(as_of, inst="OLO"):
    return {"as_of": as_of, "cycle_id": f"{as_of}:night", "company_id": "x",
            "instrument": inst, "signal": "baseline_momentum", "signal_version": "v1",
            "fired": False, "opportunity_state": "MISSED_OPPORTUNITY_CANDIDATE",
            "opportunity": {"horizon_days": 21}}


def _weekdays(start, end):
    d, i, out = date.fromisoformat(start), 0, {}
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out[d.isoformat()] = 100.0 + i
            i += 1
        d += timedelta(days=1)
    return out


OLO = [("2025-09-12", "25-NSE"), ("2025-09-23", "15-12G"), ("2025-07-03", "8-K")]


def test_deregistered_before_the_decision_with_no_prices_is_ineligible():
    s = _reg(OLO).status("OLO", "2026-07-31", price_absent=True)
    assert s.state == IR.INELIGIBLE and s.delisted_on == "2025-09-23"


def test_an_exchange_transfer_form_25_does_not_exclude_a_trading_company():
    """Shopify's 2025 Form 25 (NYSE -> Nasdaq) excluded it under the first rule."""
    s = _reg([("2025-03-28", "25")]).status("SHOP", "2026-08-03", price_absent=False)
    assert s.state == IR.ELIGIBLE


def test_a_deregistration_with_prices_still_present_is_not_ineligible():
    s = _reg([("2022-10-11", "15-12G")]).status("X", "2026-08-03", price_absent=False)
    assert s.state == IR.ELIGIBLE


def test_a_missing_price_alone_never_makes_an_instrument_ineligible():
    s = _reg([]).status("X", "2026-08-03", price_absent=True)
    assert s.state == IR.ELIGIBLE


def test_an_ineligible_decision_is_classified_terminal_not_unresolvable(tmp_path):
    r = OR.resolve([_row("2026-07-31")], root=tmp_path, today="2026-11-25",
                   series_fn=lambda s: {}, registry=_reg(OLO))
    assert r["counts"][OR.INELIGIBLE] == 1 and r["events"][0]["state"] == OR.INELIGIBLE
    again = OR.resolve([_row("2026-07-31")], root=tmp_path, today="2026-11-26",
                       series_fn=lambda s: {}, registry=_reg(OLO))
    assert again["appended"] == 0 and again["counts"]["already_terminal"] == 1


def test_delisted_after_a_legitimate_decision_is_still_evaluated():
    """Survivorship: the forecast stays, exited at the last tradable close."""
    reg = _reg([("2026-08-14", "25-NSE"), ("2026-08-24", "15-12G")])
    closes = _weekdays("2026-06-01", "2026-08-13")       # stops at delisting
    st = reg.status("ACQ", "2026-08-03", price_absent=False)
    assert st.state == IR.ELIGIBLE and st.delisted_on == "2026-08-24"
    ev = OR.grade(_row("2026-08-03", "ACQ"), closes, today="2026-09-30",
                  eligibility=st)
    assert ev["state"] == OR.RESOLVED
    assert ev["exit_date"] == "2026-08-13" and "delisting" in ev["exit_basis"]


def test_without_a_delisting_the_normal_rule_holds():
    st = _reg([]).status("SHOP", "2026-08-03", price_absent=False)
    assert st.state == IR.ELIGIBLE
    ev = OR.grade(_row("2026-08-03", "SHOP"), _weekdays("2026-06-01", "2026-09-30"),
                  today="2026-09-30", eligibility=st)
    assert ev["state"] == OR.RESOLVED and ev["exit_date"] == "2026-08-24"


def test_a_lookup_failure_is_unknown_never_eligible():
    def boom(cik):
        raise OSError("down")
    s = IR.Registry(filings_for=boom, cik_for=lambda s: 1).status("X", "2026-08-03")
    assert s.state == IR.UNKNOWN


def test_a_terminal_unresolvable_is_replaced_only_by_an_explicit_correction():
    prior = {"record_key": "k", "state": OR.UNRESOLVABLE, "processed_on": "2026-11-25"}
    regrade = {"record_key": "k", "state": OR.RESOLVED}
    assert OR.latest_by_key([prior, regrade])["k"]["state"] == OR.UNRESOLVABLE
    fix = OR.correction_for(prior, OR.INELIGIBLE, reason="deregistered 2025-09-23",
                            evidence=["SEC 15-12G 2025-09-23"], processed_on="2026-11-26")
    cur = OR.latest_by_key([prior, fix])["k"]
    assert cur["state"] == OR.INELIGIBLE and cur["corrects_state"] == OR.UNRESOLVABLE
    wrong = dict(fix, corrects_state=OR.RESOLVED)      # names the wrong prior
    assert OR.latest_by_key([prior, wrong])["k"]["state"] == OR.UNRESOLVABLE
