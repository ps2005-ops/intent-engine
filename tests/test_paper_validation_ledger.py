"""The pre-registration ledger: append-only, hash-chained, and it refuses the past."""
import datetime as dt
import json

import pytest

from intent_engine.paper_validation import ledger as LG

T0 = dt.datetime(2026, 11, 10, 1, 0, tzinfo=dt.timezone.utc)   # 20:00 NY 11-09


def rec(fid="pv1-fwd:p:SPY:2026-11-09", kind=LG.FORWARD_SHADOW,
        decision_ts="2026-11-10T00:30:00+00:00", **kw):
    r = {f: "x" for f in LG.REQUIRED}
    r.update({"forecast_id": fid, "ledger_kind": kind,
              "decision_ts": decision_ts, "decision_date": "2026-11-09",
              "information_cutoff": "2026-11-09", "direction": "LONG",
              "probability": 0.55, "evidence_ids": [],
              "competing_hypotheses": [], "abstention_reason": ""})
    r.update(kw)
    return r


def led(tmp_path, kind=LG.FORWARD_SHADOW, clock=T0):
    return LG.Ledger(tmp_path / "l.jsonl", kind, clock=lambda: clock)


def resolution(fid="pv1-fwd:p:SPY:2026-11-09", exit_date="2026-12-10", **kw):
    r = {"forecast_id": fid, "entry_date": "2026-11-10",
         "exit_date": exit_date, "excess_return": 0.01, "outcome": 1}
    r.update(kw)
    return r


class TestTheChain:
    def test_register_then_resolve_round_trips_and_verifies(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        b = led(tmp_path, clock=dt.datetime(2026, 12, 12, tzinfo=dt.timezone.utc))
        b.resolve([resolution()])
        assert b.verify() == 2
        st = b.states()["pv1-fwd:p:SPY:2026-11-09"]
        assert st.status == LG.RESOLVED and st.resolution["outcome"] == 1
        assert st.registration["probability"] == 0.55

    def test_an_edited_line_breaks_the_chain(self, tmp_path):
        a = led(tmp_path)
        a.register([rec(), rec(fid="pv1-fwd:p:TLT:2026-11-09")])
        lines = a.path.read_text().splitlines()
        e = json.loads(lines[0])
        e["payload"]["probability"] = 0.75          # the edit a cheat makes
        lines[0] = json.dumps(e)
        a.path.write_text("\n".join(lines) + "\n")
        with pytest.raises(LG.LedgerViolation, match="line 1"):
            a.verify()

    def test_a_deleted_line_breaks_the_chain(self, tmp_path):
        a = led(tmp_path)
        a.register([rec(), rec(fid="b"), rec(fid="c")])
        lines = a.path.read_text().splitlines()
        a.path.write_text("\n".join([lines[0], lines[2]]) + "\n")
        with pytest.raises(LG.LedgerViolation):
            a.verify()

    def test_appending_to_a_tampered_file_is_refused(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        e = json.loads(a.path.read_text())
        e["payload"]["direction"] = "SHORT"
        a.path.write_text(json.dumps(e) + "\n")
        with pytest.raises(LG.LedgerViolation):
            a.register([rec(fid="later")])


class TestNoEditsAfterRegistration:
    def test_reregistering_an_id_is_refused(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        with pytest.raises(LG.LedgerViolation, match="already registered"):
            a.register([rec(probability=0.9)])

    def test_a_second_resolution_is_refused(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        b = led(tmp_path, clock=dt.datetime(2026, 12, 12, tzinfo=dt.timezone.utc))
        b.resolve([resolution()])
        with pytest.raises(LG.LedgerViolation, match="already closed"):
            b.resolve([resolution(outcome=0)])

    def test_resolving_an_unregistered_forecast_is_refused(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="never registered"):
            led(tmp_path).resolve([resolution()])


class TestOutcomesMustHaveHappened:
    def test_an_exit_session_that_has_not_completed_is_refused(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        # Clock on the exit day itself: the session is not over.
        b = led(tmp_path, clock=dt.datetime(2026, 12, 10, 18, tzinfo=dt.timezone.utc))
        with pytest.raises(LG.LedgerViolation, match="has not completed"):
            b.resolve([resolution()])

    def test_an_entry_on_or_before_the_decision_is_refused(self, tmp_path):
        a = led(tmp_path)
        a.register([rec()])
        b = led(tmp_path, clock=dt.datetime(2026, 12, 12, tzinfo=dt.timezone.utc))
        with pytest.raises(LG.LedgerViolation, match="not after the decision"):
            b.resolve([resolution(entry_date="2026-11-09")])


class TestTheForwardLedgerRefusesThePast:
    def test_a_backdated_registration_is_refused(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="may not be backdated"):
            led(tmp_path).register([rec(decision_ts="2026-11-01T20:00:00+00:00")])

    def test_the_same_record_is_accepted_by_a_rehearsal_ledger(self, tmp_path):
        a = led(tmp_path, kind=LG.REHEARSAL)
        a.register([rec(kind=LG.REHEARSAL,
                        decision_ts="2026-11-01T20:00:00+00:00")])
        assert a.verify() == 1

    def test_a_rehearsal_record_cannot_enter_the_forward_ledger(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="may not enter"):
            led(tmp_path).register([rec(kind=LG.REHEARSAL)])

    def test_a_future_decision_timestamp_is_refused(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="future"):
            led(tmp_path).register([rec(decision_ts="2026-11-11T00:00:00+00:00")])


class TestRecordShape:
    def test_a_missing_required_field_is_refused(self, tmp_path):
        r = rec()
        del r["invalidation_condition"]
        with pytest.raises(LG.LedgerViolation, match="missing"):
            led(tmp_path).register([r])

    def test_an_abstention_must_say_why(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="must say why"):
            led(tmp_path).register([rec(direction="ABSTAIN", probability=None)])

    def test_a_long_whose_probability_says_down_is_incoherent(self, tmp_path):
        with pytest.raises(LG.LedgerViolation, match="LONG with"):
            led(tmp_path).register([rec(probability=0.4)])
