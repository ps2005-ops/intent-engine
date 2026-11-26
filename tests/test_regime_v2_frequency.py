"""Amendment A1: the policy-rate change is a year of COMPLETED months, any input frequency."""
import datetime as dt
from intent_engine.econ import regime as RG
from intent_engine.econ.panel import Cell, Panel
from intent_engine.paper_validation import protocol as PR


def _panel(daily_from, daily_to, level_fn):
    p, d = Panel(), dt.date.fromisoformat(daily_from)
    while d <= dt.date.fromisoformat(daily_to):
        p.add(Cell(series_id="DFF", observed_at=d.isoformat(), vintage_at=d.isoformat(),
                   value=level_fn(d)))
        d += dt.timedelta(days=1)
    return p.finalise()


HIKE = lambda d: 1.0 if d < dt.date(2026, 1, 1) else 2.0     # +1.00pp at New Year


def test_v1_reads_a_daily_series_as_a_twelve_day_change_and_is_preserved():
    p = _panel("2025-01-01", "2026-11-20", HIKE)
    assert RG.classify(p, "2026-11-25", version=RG.V1).evidence.get("policy_change_pp") == 0.0


def test_v2_sees_a_years_change_on_daily_input():
    r = RG.classify(_panel("2025-01-01", "2026-11-20", HIKE), "2026-11-25", version=RG.V2)
    assert abs(r.evidence["policy_change_pp"] - 1.0) < 1e-9
    assert RG.POLICY_TIGHTENING in r.regimes


def test_v2_excludes_the_incomplete_current_month():
    # a spike in the current month must not move the reading
    p = _panel("2025-01-01", "2026-11-24",
               lambda d: 9.0 if d >= dt.date(2026, 11, 1) else HIKE(d))
    r = RG.classify(p, "2026-11-25", version=RG.V2)
    assert abs(r.evidence["policy_change_pp"] - 1.0) < 1e-9


def test_v2_on_monthly_input_gives_the_same_answer():
    p = Panel()
    for y, m in [(y, m) for y in (2025, 2026) for m in range(1, 13)]:
        if (y, m) <= (2026, 10):
            p.add(Cell(series_id="DFF", observed_at=f"{y}-{m:02d}-01",
                       vintage_at=f"{y}-{m:02d}-28", value=1.0 if y == 2025 else 2.0))
    r = RG.classify(p.finalise(), "2026-11-25", version=RG.V2)
    assert abs(r.evidence["policy_change_pp"] - 1.0) < 1e-9


def test_the_amendment_is_prospective():
    assert PR.regime_version_for("2026-11-09") == RG.V1
    assert PR.regime_version_for("2026-11-26") == RG.V2
