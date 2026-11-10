"""The forward resolver, the shadow learning loop, and the econ arm's liveness."""
import datetime as dt
import pathlib

import pytest

from paper_validation_fixtures import universe

from intent_engine.paper_validation import forward as FW
from intent_engine.paper_validation import learning_loop as LL
from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import observations as OB
from intent_engine.paper_validation import policies as PL

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _registered(tmp_path, kind=LG.REHEARSAL):
    dates, bars, etfs, panel = universe()
    d = dates[400]
    rows, _ = OB.build(bars=bars, instruments=etfs, panel=panel,
                       dates=[(0, d, "", "")])
    pol = FW.rehearsal_policy()
    stamp = dt.datetime.fromisoformat(d + "T21:30:00+00:00")
    recs = FW.decide_records(kind=kind, policies=[pol], rows=rows,
                             history=None, bars=bars,
                             decision_ts=stamp.isoformat(), decision_date=d,
                             data_vintage={"label": "test"}, cash_rate=0.02)
    led = LG.Ledger(tmp_path / "r.jsonl", kind, clock=lambda: stamp)
    led.register(recs)
    return dates, bars, led, d, stamp


class TestResolver:
    def test_nothing_resolves_before_the_exit_session_is_over(self, tmp_path):
        dates, bars, led, d, stamp = _registered(tmp_path)
        i = dates.index(d)
        # clock on the exit day itself
        exit_day = dt.datetime.fromisoformat(dates[i + 22] + "T15:00:00+00:00")
        out = FW.resolve_open(LG.Ledger(led.path, LG.REHEARSAL,
                                        clock=lambda: exit_day), bars,
                              now=exit_day)
        assert out["resolved"] == 0 and out["still_open"] == len(led.states())

    def test_it_resolves_once_the_window_has_closed(self, tmp_path):
        dates, bars, led, d, stamp = _registered(tmp_path)
        i = dates.index(d)
        later = dt.datetime.fromisoformat(dates[i + 30] + "T22:00:00+00:00")
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: later)
        out = FW.resolve_open(l2, bars, now=later)
        assert out["resolved"] == len(l2.states())
        st = next(iter(l2.states().values()))
        assert st.resolution["entry_date"] == dates[i + 1]
        assert st.resolution["exit_date"] == dates[i + 22]
        b = bars[st.registration["instrument"]]
        ret = b.open_adj[i + 22] / b.open_adj[i + 1] - 1
        days = (dt.date.fromisoformat(dates[i + 22])
                - dt.date.fromisoformat(dates[i + 1])).days
        assert st.resolution["excess_return"] == pytest.approx(
            ret - 0.02 * days / 360, abs=1e-6)

    def test_a_missing_bar_voids_rather_than_inventing_a_price(self, tmp_path):
        dates, bars, led, d, stamp = _registered(tmp_path)
        i = dates.index(d)
        tlt = bars["TLT"]
        keep = [k for k in range(len(tlt)) if k != i + 22]
        from intent_engine.paper_validation.bars import Bars
        bars = dict(bars)
        bars["TLT"] = Bars("TLT", tuple(tlt.dates[k] for k in keep),
                           tuple(tlt.open_adj[k] for k in keep),
                           tuple(tlt.close_adj[k] for k in keep))
        later = dt.datetime.fromisoformat(dates[i + 30] + "T22:00:00+00:00")
        out = FW.resolve_open(LG.Ledger(led.path, LG.REHEARSAL,
                                        clock=lambda: later), bars, now=later)
        assert out["voided"] >= 1


class TestShadowLearning:
    def _resolved(self, tmp_path):
        dates, bars, led, d, stamp = _registered(tmp_path)
        i = dates.index(d)
        later = dt.datetime.fromisoformat(dates[i + 30] + "T22:00:00+00:00")
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: later)
        FW.resolve_open(l2, bars, now=later)
        return l2

    def test_beliefs_update_only_within_their_own_ledger_kind(self, tmp_path):
        l2 = self._resolved(tmp_path)
        rows = LL.resolved_rows(l2)
        fwd = LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW)
        with pytest.raises(LL.LearningRefused, match="may not learn"):
            LL.update_beliefs(fwd, rows, path=tmp_path / "b.jsonl")
        out = LL.update_beliefs(l2, rows, path=tmp_path / "b.jsonl")
        assert out["events"] >= 1
        # the same resolutions are never counted twice
        assert LL.update_beliefs(l2, rows, path=tmp_path / "b.jsonl")[
            "events"] == 0

    def test_the_loop_proposes_but_only_a_human_may_promote(self, tmp_path):
        from intent_engine.learning.records import LearningError
        from intent_engine.learning.service import LearningLedger
        l2 = self._resolved(tmp_path)
        rows = LL.resolved_rows(l2)
        drift = {"rehearsal_constant": {"status": "DRIFT",
                                        "brier_first": 0.20,
                                        "brier_last": 0.30}}
        db = tmp_path / "shadow.db"
        ids = LL.propose_candidates(l2, rows, drift, db_path=db)
        assert ids
        with pytest.raises(LearningError, match="HUMAN"):
            LearningLedger(db).promote(ids[0], actor_type="agent",
                                       actor_id="learning_loop",
                                       rationale="looked good")

    def test_attribution_separates_near_misses_from_misses(self):
        reg = {"direction": "LONG", "expected_cost_bps": 10.0}
        assert LL.attribute(reg, {"excess_return": -0.001,
                                  "net_position_return": -0.002}) == "NEAR_MISS"
        assert LL.attribute(reg, {"excess_return": -0.05,
                                  "net_position_return": -0.05}) == "MISS"
        assert LL.attribute(reg, {"excess_return": 0.0005,
                                  "net_position_return": -0.0005}) == \
            "COST_LOSS"


class TestEconArmIsLive:
    """The economic engine is called, vintage-walled, and its output moves
    WHEN THE STATE MOVES ([[decision-delta-needs-a-real-comparator]])."""

    @pytest.fixture(scope="class")
    def panel(self):
        from intent_engine.paper_validation import macro as M
        return M.load_panel(ROOT / "reports/panel/historical_panel.jsonl")[0]

    def test_a_bank_reads_the_curve_and_the_flags_move_with_the_state(self,
                                                                       panel):
        from intent_engine.executive import company_profile as CP
        from intent_engine.paper_validation import leakage as LK
        from intent_engine.paper_validation import macro as M
        from intent_engine.validation import load
        prof = CP.profile_for(
            company_id="jpmorgan-chase",
            manifest=load(ROOT / "docs/execution/v5/"
                                 "COMPANY_VALIDATION_MANIFEST.yaml"))
        assert prof.known and prof.business_model_class == \
            "BALANCE_SHEET_OR_NETWORK"
        reads = {}
        for d in ("2009-03-31", "2019-06-28", "2022-06-30"):
            e = M.EconReader(panel, d).company(prof)
            LK.check_evidence(e["evidence_ids"], d)
            reads[d] = sorted(r["quantity"] for r in e["adverse"])
        assert "curve_slope" in reads["2022-06-30"]
        assert len({tuple(v) for v in reads.values()}) == 3


class TestCommittedLedgers:
    """Invariants of the ledgers in the repository. Counts are never pinned:
    the forward ledger grows ([[tests-must-not-pin-a-live-artifact]])."""

    def test_the_forward_ledger_is_intact_and_never_saw_its_outcomes(self):
        path = ROOT / "reports/paper_validation/forward_shadow_ledger.jsonl"
        if not path.exists():
            pytest.skip("no forward ledger committed")
        led = LG.Ledger(path, LG.FORWARD_SHADOW)
        led.verify()
        for e in led.entries():
            if e["event"] == LG.REGISTER:
                p = e["payload"]
                assert p["ledger_kind"] == LG.FORWARD_SHADOW
                assert p["decision_ts"] <= e["recorded_at"]
                assert p["information_cutoff"] <= p["decision_date"]
            elif e["event"] == LG.RESOLVE:
                assert e["payload"]["exit_date"] < LG.ny_date(
                    dt.datetime.fromisoformat(e["recorded_at"]))

    def test_every_rehearsal_record_says_rehearsal(self):
        path = ROOT / "reports/paper_validation/rehearsal_ledger.jsonl"
        if not path.exists():
            pytest.skip("no rehearsal ledger committed")
        led = LG.Ledger(path, LG.REHEARSAL)
        led.verify()
        for st in led.states().values():
            assert st.registration["ledger_kind"] == LG.REHEARSAL
            assert st.registration["policy_id"] == "rehearsal_constant"
            assert st.registration["probability"] in (None, 0.55)


class TestCadence:
    def test_the_daily_job_registers_only_on_the_21_session_cadence(self,
                                                                     tmp_path):
        dates, bars, led, d, stamp = _registered(tmp_path,
                                                 kind=LG.FORWARD_SHADOW)
        spy = bars["SPY"]
        cut = spy.truncated(dates[dates.index(d) + 5])
        assert FW.sessions_since_last_registration(cut, led.path) == 5
        assert FW.sessions_since_last_registration(
            spy, tmp_path / "none.jsonl") is None
