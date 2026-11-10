"""Leakage walls that can fail, the canary, and the replay's accounting."""
import numpy as np
import pytest

from paper_validation_fixtures import universe

from intent_engine.paper_validation import features as F
from intent_engine.paper_validation import leakage as LK
from intent_engine.paper_validation import observations as OB
from intent_engine.paper_validation import policies as PL
from intent_engine.paper_validation import replay as RP


class TestEvidenceDates:
    def test_a_price_window_ending_after_the_decision_is_refused(self):
        with pytest.raises(LK.LeakDetected):
            LK.check_evidence(["px:SPY:2020-01-02..2020-03-02"], "2020-03-01")

    def test_a_panel_cell_published_after_the_decision_is_refused(self):
        # observed before the decision, but its VINTAGE is after it
        with pytest.raises(LK.LeakDetected):
            LK.check_evidence(["panel:UNRATE:2020-02-01@2020-03-06"],
                              "2020-03-01")
        LK.check_evidence(["panel:UNRATE:2020-01-01@2020-02-07"], "2020-03-01")

    def test_an_econ_state_reading_a_later_period_is_refused(self):
        with pytest.raises(LK.LeakDetected):
            LK.check_evidence(["econ_state:2020-03-01:panel:DGS10:2020-03-05"],
                              "2020-03-01")

    def test_an_undated_input_is_refused(self):
        with pytest.raises(LK.LeakDetected, match="no parseable date"):
            LK.check_evidence(["vibes:bullish"], "2020-03-01")

    def test_the_oracle_canary_is_refused(self):
        c = LK.oracle_canary("SPY", "2020-03-01", "2020-03-31", 0.02)
        assert LK.canary_refused(c)

    def test_training_labels_resolving_after_the_refit_are_refused(self):
        with pytest.raises(LK.LeakDetected, match="were not known"):
            LK.assert_purged(["2020-01-31", "2020-03-31"], "2020-03-01")


class TestTruncation:
    def test_price_features_do_not_change_when_the_future_is_deleted(self):
        _d, bars, _e, _p = universe()
        b = bars["XLE"]
        for t in (300, 450, 600):
            assert LK.truncation_invariant(F.price_features, b, t)

    def test_a_feature_that_reads_tomorrow_is_caught(self):
        _d, bars, _e, _p = universe()

        def peeks(b, t):
            f, eid = F.price_features(b, t)
            if t + 1 < len(b):
                f["r21"] = b.close_adj[t + 1] / b.close_adj[t] - 1.0
            return f, eid

        assert not LK.truncation_invariant(peeks, bars["XLE"], 400)

    def test_relative_features_are_truncation_invariant(self):
        _d, bars, _e, _p = universe()
        b, spy = bars["XLE"], bars["SPY"]
        d = b.dates[500]
        assert LK.truncation_invariant_relative(b, 500, spy, d)


def _run(policies=None):
    dates, bars, etfs, panel = universe()
    pol = policies or [p for p in PL.registry() if p.policy_id in (
        "cash", "buy_and_hold", "tsmom_12_1", "random_control",
        "ie_market_momentum")]
    res = RP.run(bars=bars, panel=panel, etfs=etfs, companies=[],
                 profiles=None, anchor=dates[300], policies=pol,
                 log=lambda s: None)
    return res


class TestReplay:
    def test_the_canary_is_refused_on_every_date(self):
        res = _run()
        c = res["canaries"]
        assert c["checked"] > 10 and c["refused"] == c["checked"]

    def test_climatology_uses_only_outcomes_known_at_the_decision(self):
        res = _run()
        obs = res["obs"]
        for o in obs[::7]:
            known = [x.y for x in obs if x.family == o.family
                     and x.universe == o.universe
                     and x.exit_date <= o.decision_date]
            expect = (sum(known) + 1) / (len(known) + 2)
            assert o.p_clim == pytest.approx(expect)

    def test_cash_earns_nothing_and_buy_and_hold_earns_the_mean_excess(self):
        res = _run()
        rows = [r for r in res["rows"]]
        obs_days = {(o.symbol, o.decision_date): 30 for o in res["obs"]}
        cash = RP.book([r for r in rows if r.policy == "cash"], obs_days, "etf")
        assert set(cash["returns"]) == {0.0}
        bh = RP.book([r for r in rows if r.policy == "buy_and_hold"],
                     obs_days, "etf")
        by_date = {}
        for r in rows:
            if r.policy == "buy_and_hold":
                by_date.setdefault(r.decision_date, []).append(r.excess)
        d1 = bh["dates"][1]
        assert bh["returns"][1] == pytest.approx(np.mean(by_date[d1]))
        assert bh["turnover"][1] == 0.0       # holding pays no cost

    def test_a_policy_that_reads_the_future_stops_the_replay(self):
        class Peeker(PL.Policy):
            def decide(self, o, history):
                return PL.Decision("LONG", 0.6,
                                   [f"outcome:{o.symbol}:{o.exit_date}"], "")

        p = Peeker("peeker", "v1", PL.CONTROL, ("etf",), "-", "", "", (), "")
        with pytest.raises(LK.LeakDetected, match="future inputs"):
            _run([p])

    def test_every_decided_window_had_closed(self):
        res = _run()
        for r in res["rows"]:
            assert r.exit_date > r.decision_date

    def test_logit_training_is_purged(self):
        dates, bars, etfs, panel = universe()
        res = OB.build(bars=bars, instruments=etfs, panel=panel,
                       dates=[s for s in OB.schedule(bars["SPY"],
                                                     anchor=dates[280])
                              if s[3]])[0]
        hist = RP.History(res)
        d = res[len(res) // 2].decision_date
        assert all(o.exit_date <= d for o in hist.resolved(d))


class TestVintageWall:
    def test_macro_features_read_the_revision_in_force_at_the_decision(self):
        """A first print, then a revision published AFTER the decision. The
        decision must read the first print ([[two-dates-per-fact]])."""
        from intent_engine.econ import panel as PN
        from intent_engine.paper_validation import macro as M
        p = PN.Panel()
        for d, v in (("2020-01-02", 2.0), ("2020-02-03", 2.0),
                     ("2020-03-02", 2.0)):
            p.add(PN.Cell(series_id="BAA10Y", observed_at=d, vintage_at=d,
                          value=v, kind="credit_spread_ig", node_class="MACRO"))
        # the March figure is revised to 9.0 on 2020-04-15
        p.add(PN.Cell(series_id="BAA10Y", observed_at="2020-03-02",
                      vintage_at="2020-04-15", value=9.0,
                      kind="credit_spread_ig", node_class="MACRO"))
        p.finalise()
        feats, ev, _missing = M.macro_features(p, "2020-03-10")
        assert feats["baa_spread"] == 2.0, "a later revision leaked into the decision"
        LK.check_evidence(ev, "2020-03-10")
