"""FX4 contract: guidance (intent) vs next-quarter revenue acceleration (behaviour)."""
from intent_engine.market import intent_behaviour as IB

def _facts(values, filed_lag=40):
    """Quarter ends 2024-03-31.. with values; filed 40 days after period end."""
    import datetime as dt
    out, d = [], dt.date(2024, 3, 31)
    for v in values:
        out.append((d.isoformat(), (d + dt.timedelta(days=filed_lag)).isoformat(), float(v)))
        m = d.month + 3; y = d.year + (m > 12); m = m - 12 if m > 12 else m
        d = (dt.date(y, m % 12 + 1, 1) - dt.timedelta(days=1)) if m != 12 else dt.date(y, 12, 31)
    return out

EV = {"evidence_type": "GUIDANCE_REVISION", "evidence_id": "e1", "available_at": "2026-12-01",
      "fact": "Acme raises full-year revenue outlook, sees sales growing 12%"}

def test_a_revenue_guidance_raise_registers_one_up_forecast():
    facts = _facts([100, 102, 104, 106, 110, 113, 116, 120, 126, 133], filed_lag=40)
    out = IB.register([EV, dict(EV, evidence_id="e2")], revenue_facts=lambda s: facts,
                      company_of=lambda e: "ACME", today="2026-12-02")
    assert len(out) == 1 and out[0]["prediction"] == IB.UP
    assert out[0]["information_cutoff"] == "2026-12-01"

def test_surprises_profit_and_price_do_not_trigger():
    for text in ("Acme beats revenue estimates", "Acme raises profit forecast",
                 "Acme shares jump after outlook"):
        assert IB.trigger(dict(EV, fact=text)) is None

def test_nothing_filed_after_the_cutoff_is_used_to_register():
    facts = _facts([100, 102, 104, 106, 110, 113, 116, 120, 126, 133], filed_lag=40)
    f = IB.register([EV], revenue_facts=lambda s: facts, company_of=lambda e: "ACME",
                    today="2026-12-02")[0]
    assert all(filed < "2026-12-01" for end, filed, _ in facts if end <= f["last_known_quarter_end"])

def test_resolution_waits_for_the_next_filed_quarter_then_scores_once():
    facts = _facts([100, 102, 104, 106, 110, 113, 116, 120, 126, 133, 141])
    f = IB.register([EV], revenue_facts=lambda s: facts[:-3], company_of=lambda e: "ACME",
                    today="2026-12-02")[0]
    assert IB.resolve(f, facts[:-3], today="2026-12-03") is None
    r = IB.resolve(f, facts, today="2027-12-01")
    assert r["state"] == "RESOLVED" and r["actual"] in (IB.UP, IB.DOWN)
    assert set(r["baseline_correct"]) == {"PERSISTENCE", "DECELERATE"}


def test_a_trigger_from_before_registration_is_never_used():
    facts = _facts([100, 102, 104, 106, 110, 113, 116, 120, 126, 133])
    old = dict(EV, available_at="2026-08-09")
    assert IB.register([old], revenue_facts=lambda s: facts, company_of=lambda e: "ACME",
                       today="2026-12-02") == []

def test_reported_revenue_and_acquisitions_do_not_trigger():
    assert IB.trigger(dict(EV, fact="Linde Q3 Earnings, Revenue Rise; EPS Outlook Updated")) is None
    assert IB.trigger(dict(EV, fact="PG Raises Sales Outlook as Thorne Acquisition Adds Growth")) is None
