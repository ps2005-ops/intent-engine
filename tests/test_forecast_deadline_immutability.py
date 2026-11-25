"""A forecast's due date is fixed when it is made. Nothing afterwards moves it.

Audit of 2026-11-10 (docs/engineering/forecast_audit/AUDIT_2026-11-10.md).
Every property here exists because its absence was a real defect, or because
one code path away from it was:

* the July prediction ledger closed six FRED forecasts "unresolvable" at 06:00
  on their due dates, before the values were published, and cached the empty
  answers so no retry could ever succeed;
* that ledger folded every read to the LATEST row whole, so any later row --
  a migration, a regenerated store -- could move `resolve_by`;
* the paper-validation resolver found a forecast's exit by counting 21 bars in
  today's price feed, so one missing bar silently made every open forecast
  one session later, with no stored date to compare against.

"Restart", "redeploy", "regenerate" and "migrate" are exercised literally:
a new process is a new reader over the same file; a redeploy is the same
resolver run again on a later clock; a regenerate is the registration path
run again; a migration is the file copied to a new location, or rewritten.
"""
import datetime as dt
import functools
import gzip
import json
import pathlib
import shutil
import sqlite3
import sys

import pytest

from paper_validation_fixtures import universe

from intent_engine.core import macro_data as MD
from intent_engine.core import market_resolution as MR
from intent_engine.core import prediction_ledger as PLG
from intent_engine.core.macro_data import FredSeries
from intent_engine.paper_validation import forward as FW
from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import observations as OB
from intent_engine.paper_validation import schedule as SCH
from intent_engine.paper_validation.bars import Bars

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import resolve_market_predictions as RMP  # noqa: E402

DUE = "2026-09-18"
LEVEL = {"type": "level", "series": "T10Y2Y", "op": "<", "value": 0.3, "by": DUE}


# =============================================================================
# The July prediction ledger (scripts/resolve_market_predictions.py, cron)
# =============================================================================

def _level_prediction(path, due=DUE, rule=LEVEL):
    return PLG.record_prediction(
        "market", "macro-watch", "10Y-2Y below +0.30 by the due date", 0.62,
        due, path=path, resolution_rule=dict(rule, by=due),
        resolution_source="fred")


def _fred(observations):
    """A FRED fetcher that, like the real one, raises on an empty answer."""
    def fetch(series_id, start, end):
        obs = [o for o in observations if start <= o[0] <= end]
        if not obs:
            raise ValueError(f"FRED series {series_id!r} returned no "
                             "observations for the requested range")
        return FredSeries(series_id=series_id, realtime_date=end,
                          observations=obs)
    return fetch


def _run(monkeypatch, path, as_of, fetch):
    monkeypatch.setattr(RMP, "resolve_market_prediction", functools.partial(
        MR.resolve_market_prediction, fred_fetcher=fetch))
    return RMP.resolve_due_predictions(as_of, path=path)


class TestJulyLedgerCannotCloseOrPostponeOnMissingData:
    def test_the_september_defect_a_rule_due_today_stays_open(
            self, tmp_path, monkeypatch):
        path = tmp_path / "l.db"
        p = _level_prediction(path)
        # 06:00 on the due date: the day's value does not exist yet.
        out = _run(monkeypatch, path, DUE, _fred([]))
        assert out["pending"] == 1 and out["total"] == 0
        (cur,) = PLG.list_predictions(path=path)
        assert cur.outcome is None and cur.resolve_by == DUE
        (att,) = PLG.list_resolution_attempts(p.id, path=path)
        assert att["status"] == "PENDING"
        assert att["original_resolve_by"] == DUE
        assert att["next_attempt_on"] == "2026-09-19"
        # The next morning the value is published, and it resolves.
        out = _run(monkeypatch, path, "2026-09-19",
                   _fred([("2026-09-18", 0.25)]))
        assert out["counts"]["happened"] == 1
        (cur,) = PLG.list_predictions(path=path)
        assert cur.outcome == "happened" and cur.resolve_by == DUE
        assert cur.brier_component == pytest.approx((0.62 - 1) ** 2)

    def test_restarts_and_retries_record_attempts_and_never_move_the_due_date(
            self, tmp_path, monkeypatch):
        path = tmp_path / "l.db"
        p = _level_prediction(path)
        for day in ("2026-09-18", "2026-09-19", "2026-09-22", "2026-10-30"):
            _run(monkeypatch, path, day, _fred([]))       # a fresh process each
        (cur,) = PLG.list_predictions(path=path)
        assert cur.outcome is None and cur.resolve_by == DUE
        atts = PLG.list_resolution_attempts(p.id, path=path)
        assert [a["status"] for a in atts] == ["PENDING"] * 4
        assert {a["original_resolve_by"] for a in atts} == {DUE}
        assert [a["as_of"] for a in atts] == [
            "2026-09-18", "2026-09-19", "2026-09-22", "2026-10-30"]

    def test_it_gives_up_only_after_the_final_date_and_says_when_it_was_due(
            self, tmp_path, monkeypatch):
        path = tmp_path / "l.db"
        p = _level_prediction(path)
        final = MR.final_resolution_date(DUE, MR._FRED_FORWARD_SEARCH_DAYS,
                                         MR._FRED_PUBLICATION_GRACE_DAYS)
        assert _run(monkeypatch, path, final, _fred([]))["pending"] == 1
        nxt = (dt.date.fromisoformat(final) + dt.timedelta(days=1)).isoformat()
        out = _run(monkeypatch, path, nxt, _fred([]))
        assert out["counts"]["unresolvable"] == 1
        (cur,) = PLG.list_predictions(path=path)
        assert cur.outcome == "unresolvable" and cur.resolve_by == DUE
        assert DUE in cur.resolution_note and final in cur.resolution_note
        assert PLG.list_resolution_attempts(p.id, path=path)[-1][
            "status"] == "GAVE_UP"

    def test_a_tiingo_outage_is_pending_not_final(self):
        rule = PLG.PctChangeRule(type="pct_change", symbol="SPY", op=">=",
                                 value=0.02, window_days=60)

        def down(*_a, **_k):
            raise RuntimeError("Tiingo API returned 503")
        r = MR.resolve_pct_change_rule(rule, "2026-07-20", "2026-09-18",
                                       price_fetcher=down, as_of="2026-09-20")
        assert r.outcome == MR.PENDING


class TestJulyLedgerFieldsAreImmutable:
    def test_a_migrated_row_cannot_postpone_a_prediction(self, tmp_path):
        """A row written past the API (a migration, a regenerated store)
        with a later resolve_by is ignored by every reader, and named."""
        path = tmp_path / "l.db"
        p = _level_prediction(path)
        moved = p.model_copy(update={"resolve_by": "2026-12-31",
                                     "probability": 0.9})
        con = sqlite3.connect(path)
        con.execute("INSERT INTO predictions (id, created_at, source, "
                    "entity_id, resolved_at, outcome, data) VALUES "
                    "(?,?,?,?,?,?,?)", (p.id, p.created_at, p.source,
                                        p.entity_id, None, None,
                                        moved.model_dump_json()))
        con.commit()
        con.close()
        (cur,) = PLG.list_predictions(path=path)
        assert cur.resolve_by == DUE and cur.probability == 0.62
        assert [x.id for x in PLG.list_predictions(
            unresolved_only=True, due_by=DUE, path=path)] == [p.id]
        (drift,) = PLG.immutable_drift(path)
        assert drift["fields"] == ["probability", "resolve_by"]
        assert drift["registered"]["resolve_by"] == DUE

    def test_the_api_refuses_a_row_that_changes_the_forecast(self, tmp_path):
        path = tmp_path / "l.db"
        p = _level_prediction(path)
        for change in ({"resolve_by": "2026-12-31"},
                       {"created_at": "2026-08-01T00:00:00+00:00"},
                       {"horizon_days": 120},
                       {"resolution_rule": PLG.LevelRule(
                           **dict(LEVEL, by="2026-12-31"))}):
            with pytest.raises(PLG.LedgerIntegrityError, match="may not change"):
                PLG._persist(p.model_copy(update=change), path)
        # recording the outcome is still allowed
        PLG.resolve_prediction(p.id, "happened", path=path)
        assert PLG.immutable_drift(path) == []

    def test_an_empty_fred_answer_is_never_cached(self, tmp_path, monkeypatch):
        calls = []

        def fetch(series_id, start, end, key, retries, timeout):
            calls.append(start)
            return {"observations": [] if len(calls) == 1 else
                    [{"date": "2026-09-18", "value": "0.25",
                      "realtime_start": "2026-09-19"}]}
        monkeypatch.setattr(MD, "_fetch_with_retry", fetch)
        with pytest.raises(ValueError, match="no observations"):
            MD.get_series("T10Y2Y", DUE, "2026-10-28", api_key="k",
                          cache_dir=tmp_path)
        assert list(tmp_path.iterdir()) == []
        s = MD.get_series("T10Y2Y", DUE, "2026-10-28", api_key="k",
                          cache_dir=tmp_path)
        assert len(calls) == 2 and s.observations[0][1] == 0.25


# =============================================================================
# The paper-validation forward ledger (977 forecasts registered 2026-11-09)
# =============================================================================

FWD = ROOT / "reports/paper_validation/forward_shadow_ledger.jsonl"
SPY_HISTORY = ROOT / "reports/paper_validation/prices/SPY.json.gz"


class TestTheCalendarDecidesTheDueDate:
    def test_the_2026_11_09_cohort_is_due_2026_12_10(self):
        assert SCH.scheduled_window("2026-11-09", 21) == ("2026-11-10",
                                                          "2026-12-10")
        assert SCH.resolvable_from("2026-12-10") == "2026-12-11"

    @pytest.mark.skipif(not FWD.exists(), reason="forward ledger not here")
    def test_the_registered_977_keep_the_date_they_were_registered_with(self):
        """Those records predate stored schedules; theirs is recomputed. Pin
        it, so a calendar change can never quietly re-date them. Later
        cohorts appended to the file do not touch this row."""
        due = LG.due_schedule(LG.Ledger(FWD, LG.FORWARD_SHADOW))["2026-11-09"]
        assert due["forecasts"] == 977
        assert (due["scheduled_entry_session"], due["scheduled_exit_session"],
                due["resolvable_from"]) == ("2026-11-10", "2026-12-10",
                                            "2026-12-11")
        assert due["schedule_stored"] is False

    @pytest.mark.skipif(not SPY_HISTORY.exists(), reason="no SPY history")
    def test_the_rules_reproduce_every_spy_session_since_2001(self):
        rows = json.loads(gzip.open(SPY_HISTORY).read())["rows"]
        bars = {r[0] for r in rows}
        d, end, cal = dt.date.fromisoformat(min(bars)), max(bars), set()
        while d.isoformat() <= end:
            if SCH.NYSE.is_session(d.isoformat()):
                cal.add(d.isoformat())
            d += dt.timedelta(days=1)
        assert cal == bars

    def test_years_without_rules_are_refused_not_guessed(self):
        with pytest.raises(SCH.CalendarOutOfRange):
            SCH.scheduled_window("2100-12-20", 21)


def _registered(tmp_path):
    dates, bars, etfs, panel = universe()
    d = dates[400]
    rows, _ = OB.build(bars=bars, instruments=etfs, panel=panel,
                       dates=[(0, d, "", "")])
    stamp = dt.datetime.fromisoformat(d + "T21:30:00+00:00")
    recs = FW.decide_records(kind=LG.REHEARSAL,
                             policies=[FW.rehearsal_policy()], rows=rows,
                             history=None, bars=bars,
                             decision_ts=stamp.isoformat(), decision_date=d,
                             data_vintage={"label": "test"}, cash_rate=0.02)
    led = LG.Ledger(tmp_path / "r.jsonl", LG.REHEARSAL, clock=lambda: stamp)
    led.register(recs)
    return dates, bars, led, d, recs


def _without(b, *days):
    keep = [k for k, x in enumerate(b.dates) if x not in days]
    return Bars(b.symbol, tuple(b.dates[k] for k in keep),
                tuple(b.open_adj[k] for k in keep),
                tuple(b.close_adj[k] for k in keep), b.retrieved_at,
                b.sha256, b.source)


def _clock(day, hour=22):
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


class TestMissingDataCannotPostponeAForecast:
    def test_new_registrations_store_their_schedule(self, tmp_path):
        dates, bars, led, d, recs = _registered(tmp_path)
        i = dates.index(d)
        for r in recs:
            assert (r["scheduled_entry_session"], r["scheduled_exit_session"]
                    ) == (dates[i + 1], dates[i + 22])
            assert r["schedule_calendar"] == SCH.NYSE.calendar_id

    def test_a_missing_benchmark_bar_inside_the_window_does_not_shift_exit(
            self, tmp_path):
        """The old resolver took spy.dates[entry + 21]: with one bar missing
        that is a session LATER than scheduled, for every open forecast."""
        dates, bars, led, d, _ = _registered(tmp_path)
        i = dates.index(d)
        bars = dict(bars, SPY=_without(bars["SPY"], dates[i + 10]))
        now = _clock(dates[i + 40])
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: now)
        out = FW.resolve_open(l2, bars, now=now)
        assert out["resolved"] == len(l2.states())
        for st in l2.states().values():
            assert st.resolution["exit_date"] == dates[i + 22]
            assert st.resolution["benchmark_sessions_elapsed"] == 20

    def test_a_missing_bar_on_the_exit_session_voids_and_names_it(
            self, tmp_path):
        dates, bars, led, d, _ = _registered(tmp_path)
        i = dates.index(d)
        bars = dict(bars, SPY=_without(bars["SPY"], dates[i + 22]))
        now = _clock(dates[i + 40])
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: now)
        out = FW.resolve_open(l2, bars, now=now)
        assert out["resolved"] == 0 and out["voided"] == len(l2.states())
        for st in l2.states().values():
            assert dates[i + 22] in st.void_reason
            assert "never moved" in st.void_reason

    def test_a_stale_feed_waits_forever_and_never_voids(self, tmp_path):
        """A fetch that has not caught up is a fetch failure. It must not
        close a forecast, however late the resolver runs."""
        dates, bars, led, d, _ = _registered(tmp_path)
        i = dates.index(d)
        stale = {s: _without(b, *b.dates[i + 15:]) for s, b in bars.items()}
        now = _clock(dates[i + 200])
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: now)
        out = FW.resolve_open(l2, stale, now=now)
        assert out == {"resolved": 0, "voided": 0,
                       "still_open": len(l2.states()),
                       "clock_ny_date": LG.ny_date(now)}
        # and when the feed catches up it resolves on the ORIGINAL dates
        out = FW.resolve_open(l2, bars, now=now)
        assert out["resolved"] == len(l2.states())
        assert {s.resolution["exit_date"] for s in l2.states().values()} == {
            dates[i + 22]}

    def test_a_delisted_instrument_voids_only_after_the_grace(self, tmp_path):
        dates, bars, led, d, _ = _registered(tmp_path)
        i = dates.index(d)
        b = bars["TLT"]
        bars = dict(bars, TLT=_without(b, *b.dates[i + 15:]))
        exit_ = dt.date.fromisoformat(dates[i + 22])
        early = _clock((exit_ + dt.timedelta(days=3)).isoformat())
        l2 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: early)
        assert FW.resolve_open(l2, bars, now=early)["voided"] == 0
        late = _clock((exit_ + dt.timedelta(
            days=FW.DATA_GRACE_DAYS + 1)).isoformat())
        l3 = LG.Ledger(led.path, LG.REHEARSAL, clock=lambda: late)
        assert FW.resolve_open(l3, bars, now=late)["voided"] >= 1
        voided = [s for s in l3.states().values() if s.status == LG.VOIDED]
        assert all("delisted" in s.void_reason for s in voided)


T0 = dt.datetime(2026, 11, 10, 1, 0, tzinfo=dt.timezone.utc)   # 20:00 NY 11-09


def _rec(fid="pv1-fwd:p:SPY:2026-11-09", **kw):
    r = {f: "x" for f in LG.REQUIRED}
    r.update({"forecast_id": fid, "ledger_kind": LG.FORWARD_SHADOW,
              "decision_ts": "2026-11-10T00:30:00+00:00",
              "decision_date": "2026-11-09", "information_cutoff": "2026-11-09",
              "direction": "LONG", "probability": 0.55, "evidence_ids": [],
              "competing_hypotheses": [], "abstention_reason": "",
              "horizon_sessions": 21, "scheduled_entry_session": "2026-11-10",
              "scheduled_exit_session": "2026-12-10",
              "schedule_calendar": SCH.NYSE.calendar_id})
    r.update(kw)
    return r


def _res(exit_date="2026-12-10", **kw):
    r = {"forecast_id": "pv1-fwd:p:SPY:2026-11-09", "entry_date": "2026-11-10",
         "exit_date": exit_date, "excess_return": 0.01, "outcome": 1}
    r.update(kw)
    return r


class TestTheLedgerRefusesAMovedDueDate:
    def test_a_resolution_on_a_later_session_is_refused(self, tmp_path):
        LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                  clock=lambda: T0).register([_rec()])
        later = LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                          clock=lambda: _clock("2026-12-20"))
        with pytest.raises(LG.LedgerViolation, match="may not move"):
            later.resolve([_res(exit_date="2026-12-11")])
        later.resolve([_res()])
        assert later.states()[_rec()["forecast_id"]].status == LG.RESOLVED

    def test_a_registration_cannot_be_written_already_postponed(self, tmp_path):
        led = LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                        clock=lambda: T0)
        with pytest.raises(LG.LedgerViolation, match="calendar gives"):
            led.register([_rec(scheduled_exit_session="2026-12-11")])
        with pytest.raises(LG.LedgerViolation, match="unknown schedule"):
            led.register([_rec(schedule_calendar="made-up")])

    def test_a_forecast_cannot_be_voided_before_its_window_closes(
            self, tmp_path):
        LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                  clock=lambda: T0).register([_rec()])
        early = LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                          clock=lambda: _clock("2026-12-01"))
        with pytest.raises(LG.LedgerViolation, match="not voided before"):
            early.void([{"forecast_id": _rec()["forecast_id"],
                         "reason": "no bar yet"}])


class TestRestartRegenerateMigrate:
    def test_restart_reads_the_same_schedule(self, tmp_path):
        LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                  clock=lambda: T0).register([_rec()])
        a = LG.due_schedule(LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW))
        b = LG.due_schedule(LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW))
        assert a == b and a["2026-11-09"]["scheduled_exit_session"] == \
            "2026-12-10"

    def test_regenerating_cannot_re_register_or_re_date(self, tmp_path):
        led = LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                        clock=lambda: T0)
        led.register([_rec()])
        with pytest.raises(LG.LedgerViolation, match="already registered"):
            led.register([_rec(decision_date="2026-11-10",
                               scheduled_entry_session="2026-11-11",
                               scheduled_exit_session="2026-12-11")])
        # a LATER cohort is a new forecast with its own date; the first keeps
        # its own
        nxt = SCH.scheduled_window("2026-12-10", 21)
        t1 = dt.datetime(2026, 12, 11, 1, 0, tzinfo=dt.timezone.utc)
        LG.Ledger(tmp_path / "f.jsonl", LG.FORWARD_SHADOW,
                  clock=lambda: t1).register([_rec(
                      fid="pv1-fwd:p:SPY:2026-12-10",
                      decision_ts="2026-12-11T00:30:00+00:00",
                      decision_date="2026-12-10",
                      information_cutoff="2026-12-10",
                      scheduled_entry_session=nxt[0],
                      scheduled_exit_session=nxt[1])])
        due = LG.due_schedule(LG.Ledger(tmp_path / "f.jsonl",
                                        LG.FORWARD_SHADOW))
        assert due["2026-11-09"]["scheduled_exit_session"] == "2026-12-10"
        assert due["2026-12-10"]["scheduled_exit_session"] == nxt[1]

    def test_a_migrated_copy_keeps_its_schedule_and_an_edit_is_caught(
            self, tmp_path):
        src = tmp_path / "f.jsonl"
        LG.Ledger(src, LG.FORWARD_SHADOW, clock=lambda: T0).register([_rec()])
        dst = tmp_path / "moved" / "f.jsonl"
        dst.parent.mkdir()
        shutil.copy(src, dst)
        moved = LG.Ledger(dst, LG.FORWARD_SHADOW)
        assert moved.verify() == 1
        assert LG.due_schedule(moved) == LG.due_schedule(
            LG.Ledger(src, LG.FORWARD_SHADOW))
        for field, value in (("scheduled_exit_session", "2026-12-11"),
                             ("horizon_sessions", 22),
                             ("decision_date", "2026-11-10"),
                             ("information_cutoff", "2026-11-10")):
            e = json.loads(src.read_text())
            e["payload"][field] = value
            dst.write_text(json.dumps(e) + "\n")
            with pytest.raises(LG.LedgerViolation, match="line 1"):
                LG.Ledger(dst, LG.FORWARD_SHADOW).verify()


# =============================================================================
# The market runtime's expectations (launchd, production)
# =============================================================================

class TestMarketExpectationWindowsAreFixed:
    def _store(self, tmp_path):
        from intent_engine.market import learning_store as LS
        return LS.LearningStore(tmp_path / "learning.jsonl")

    def _exp(self, prereg="2026-08-05", ends="2026-12-03"):
        from intent_engine.market import expectation as EXP
        return EXP.preregister(
            hypothesis_id="bel_x", subject="acme", expected_event="capacity",
            expected_direction="UP", preregistered_at=prereg,
            evaluation_window_ends=ends, falsifier="the programme is cut")

    def test_a_second_row_cannot_extend_an_open_window(self, tmp_path):
        store = self._store(tmp_path)
        assert store.record_expectation(self._exp()) is True
        # same proposition, same registration date, later window: same id
        later = self._exp(ends="2027-08-05")
        assert later.expectation_id == self._exp().expectation_id
        assert store.record_expectation(later) is False
        (e,) = store.open_expectations(as_of="2026-11-10")
        assert e.evaluation_window_ends == "2026-12-03"

    def test_re_forecasting_later_is_a_new_expectation_not_a_postponement(
            self, tmp_path):
        store = self._store(tmp_path)
        store.record_expectation(self._exp())
        store.record_expectation(self._exp(prereg="2026-08-08",
                                           ends="2026-12-06"))
        windows = sorted((e.preregistered_at, e.evaluation_window_ends)
                         for e in store.open_expectations(as_of="2026-11-10"))
        assert windows == [("2026-08-05", "2026-12-03"),
                           ("2026-08-08", "2026-12-06")]


class TestSupersedingAWronglyClosedPrediction:
    """The six July FRED forecasts were closed 'unresolvable' before their data
    existed. The repair appends an outcome; it never edits or re-scores."""

    def _closed(self, path, p=0.62):
        pred = PLG.record_prediction("market", "macro-watch", "spread < 0.30",
                                     p, "2026-09-18", path=path)
        PLG.resolve_prediction(pred.id, "unresolvable",
                               "FRED returned no observations", path=path)
        return pred

    def test_an_unresolvable_is_superseded_by_an_appended_row(self, tmp_path):
        path = tmp_path / "l.db"
        pred = self._closed(path)
        new = PLG.supersede_unresolvable(
            pred.id, "happened", evidence_note="T10Y2Y 0.25 on 09-18",
            data_first_published="2026-09-19", path=path)
        assert new.brier_component == pytest.approx((0.62 - 1) ** 2)
        assert new.resolve_by == "2026-09-18" and new.probability == 0.62
        assert PLG.SUPERSEDE_MARKER in new.resolution_note
        assert "FRED returned no observations" in new.resolution_note
        import sqlite3
        rows = sqlite3.connect(path).execute(
            "SELECT outcome FROM predictions WHERE id=? ORDER BY rowid",
            (pred.id,)).fetchall()
        assert [r[0] for r in rows] == [None, "unresolvable", "happened"]

    def test_it_counts_once_in_the_brier_summary(self, tmp_path):
        path = tmp_path / "l.db"
        pred = self._closed(path)
        PLG.supersede_unresolvable(pred.id, "happened", evidence_note="x",
                                   data_first_published="d", path=path)
        s = PLG.brier_summary(path=path)
        assert s.count == 1

    def test_a_scored_prediction_can_never_be_superseded(self, tmp_path):
        path = tmp_path / "l.db"
        pred = PLG.record_prediction("market", "m", "c", 0.6, "2026-09-18",
                                     path=path)
        PLG.resolve_prediction(pred.id, "did_not_happen", path=path)
        with pytest.raises(ValueError, match="only an 'unresolvable'"):
            PLG.supersede_unresolvable(pred.id, "happened", evidence_note="x",
                                       data_first_published="d", path=path)

    def test_a_second_supersession_is_refused(self, tmp_path):
        path = tmp_path / "l.db"
        pred = self._closed(path)
        PLG.supersede_unresolvable(pred.id, "happened", evidence_note="x",
                                   data_first_published="d", path=path)
        with pytest.raises(ValueError):
            PLG.supersede_unresolvable(pred.id, "did_not_happen",
                                       evidence_note="x",
                                       data_first_published="d", path=path)

    def test_unresolvable_cannot_supersede_unresolvable(self, tmp_path):
        path = tmp_path / "l.db"
        pred = self._closed(path)
        with pytest.raises(ValueError, match="must be happened"):
            PLG.supersede_unresolvable(pred.id, "unresolvable",
                                       evidence_note="x",
                                       data_first_published="d", path=path)
