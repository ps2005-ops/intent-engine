"""The price-outcome resolver: what it refuses matters more than what it grades."""
import hashlib
import json
import pathlib
import types
from datetime import date, timedelta

import pytest

from intent_engine.market import outcome_resolver as OR
from intent_engine.market import signal_opportunity as SO
from intent_engine.market import steps as ST


def _row(as_of="2026-08-03", inst="SHOP", cycle="night", state=None, **kw):
    r = {"as_of": as_of, "cycle_id": f"{as_of}:{cycle}:America/Toronto",
         "company_id": inst.lower(), "instrument": inst,
         "signal": "baseline_momentum", "signal_version": "v1",
         "fired": False,
         "opportunity_state": state or SO.MISSED_OPPORTUNITY_CANDIDATE,
         "opportunity": {"horizon_days": 21}, "outcome_state": SO.UNRESOLVED}
    r.update(kw)
    return r


def _weekdays(start, end, px=lambda i: 100.0 + i):
    d, i, out = date.fromisoformat(start), 0, {}
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out[d.isoformat()] = px(i)
            i += 1
        d += timedelta(days=1)
    return out


# --- maturity ---------------------------------------------------------------
def test_an_unelapsed_horizon_is_not_mature_and_never_graded():
    ev = OR.grade(_row(), _weekdays("2026-07-01", "2026-08-20"),
                  today="2026-08-20")
    assert ev["state"] == OR.NOT_MATURE
    assert "realized_return" not in ev


def test_on_the_horizon_end_day_itself_the_record_is_not_yet_mature(tmp_path):
    """Found in the production dry run on 2026-11-25: three records whose
    horizon ended that day were graded on the live intraday quote, and a
    04:47 run the same day graded them on the PRIOR close. Either one would
    have been written as terminal. The end-day close is final only once that
    day has passed."""
    end = SO.horizon_end("2026-08-03")                       # 2026-08-24
    closes = _weekdays("2026-07-01", end)                    # includes 'today'
    ev = OR.grade(_row(), closes, today=end)
    assert ev["state"] == OR.NOT_MATURE
    r = OR.resolve([_row()], root=tmp_path, today=end,
                   series_fn=lambda s: closes, write=True)
    assert r["counts"][OR.NOT_MATURE] == 1 and r["appended"] == 0
    nxt = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    ev2 = OR.grade(_row(), closes, today=nxt)
    assert ev2["state"] == OR.RESOLVED and ev2["exit_date"] == end


def test_a_mature_record_is_graded_by_the_preregistered_rule():
    closes = _weekdays("2026-07-01", "2026-09-30")
    ev = OR.grade(_row(), closes, today="2026-09-30")
    assert ev["state"] == OR.RESOLVED
    assert ev["horizon_end"] == "2026-08-24" == SO.horizon_end("2026-08-03")
    assert ev["entry_date"] == "2026-08-03" and ev["exit_date"] == "2026-08-24"
    assert ev["realized_return"] == pytest.approx(
        (closes["2026-08-24"] - closes["2026-08-03"]) / closes["2026-08-03"],
        abs=1e-6)
    assert ev["confirmed_miss"] is True
    assert ev["rule"] == SO.DEFINITION


def test_horizon_end_on_a_weekend_uses_the_last_prior_session():
    # 2026-08-08 + 21 = 2026-08-29, a Saturday.
    ev = OR.grade(_row(as_of="2026-08-07"),
                  _weekdays("2026-07-01", "2026-09-30"), today="2026-09-30")
    assert ev["state"] == OR.RESOLVED and ev["exit_date"] == "2026-08-28"


# --- the fabricated-zero defect --------------------------------------------
def test_no_bar_after_as_of_is_never_a_zero_return():
    """The old grader used the entry bar as the exit: a delisting graded 0.0%."""
    closes = _weekdays("2026-07-01", "2026-08-03")         # series dies at as_of
    old = SO.resolve_outcome(SO.AuditRecord(**{
        **{k: v for k, v in _row().items() if k in
           {f for f in SO.AuditRecord.__dataclass_fields__}},
        "strategic_view": "present", "evidence_ids": (), "inputs": {},
        "threshold": 0.02, "raw_value": None, "fire_reason": ""}),
        closes, today="2026-09-01")
    assert old.realized_return == 0.0                       # the defect, pinned
    ev = OR.grade(_row(), closes, today="2026-09-01")
    assert ev["state"] == OR.PENDING and "realized_return" not in ev


def test_on_a_short_horizon_the_entry_bar_can_never_double_as_the_exit():
    """At 21 days the staleness check hides this; at 3 days it does not."""
    row = _row(opportunity={"horizon_days": 3})
    closes = _weekdays("2026-07-01", "2026-08-03")
    closes.update({"2026-08-10": 120.0})                    # series continues later
    ev = OR.grade(row, closes, today="2026-09-30")
    assert ev["state"] == OR.UNRESOLVABLE and "realized_return" not in ev


def test_a_dead_series_turns_terminal_only_after_the_final_date():
    closes = _weekdays("2026-07-01", "2026-08-03")
    final = OR.grade(_row(), closes, today="2026-09-01")["final_date"]
    assert final == "2026-09-08"
    assert OR.grade(_row(), closes, today="2026-09-08")["state"] == OR.PENDING
    ev = OR.grade(_row(), closes, today="2026-09-09")
    assert ev["state"] == OR.UNRESOLVABLE and "before horizon end" in ev["reason"]


def test_a_stale_exit_inside_a_continuing_series_is_unresolvable():
    closes = {d: v for d, v in _weekdays("2026-07-01", "2026-09-30").items()
              if not ("2026-08-10" <= d <= "2026-08-31")}
    ev = OR.grade(_row(), closes, today="2026-09-30")
    assert ev["state"] == OR.UNRESOLVABLE and "although the series continues" in ev["reason"]


def test_a_stale_entry_is_unresolvable():
    closes = {d: v for d, v in _weekdays("2026-07-01", "2026-09-30").items()
              if not ("2026-07-20" <= d <= "2026-08-03")}
    ev = OR.grade(_row(), closes, today="2026-09-30")
    assert ev["state"] == OR.UNRESOLVABLE and "entry bar" in ev["reason"]


def test_a_provider_failure_is_pending_not_a_crash(tmp_path):
    def boom(_):
        raise RuntimeError("HTTP 429")
    res = OR.resolve([_row()], root=tmp_path, today="2026-09-01", series_fn=boom)
    assert res["counts"][OR.PENDING] == 1
    assert "HTTP 429" in res["events"][0]["reason"]


# --- append-only and idempotent --------------------------------------------
def test_rerun_appends_nothing_and_terminal_is_never_regraded(tmp_path):
    rows = [_row()]
    good = _weekdays("2026-07-01", "2026-09-30")
    r1 = OR.resolve(rows, root=tmp_path, today="2026-09-30",
                    series_fn=lambda s: good)
    assert r1["appended"] == 1
    path = tmp_path / OR.OUTCOMES_FILE
    before = path.read_bytes()
    revised = {d: v * 2 for d, v in good.items()}          # a later, different feed
    r2 = OR.resolve(rows, root=tmp_path, today="2026-10-30",
                    series_fn=lambda s: revised)
    assert r2["appended"] == 0 and r2["counts"]["already_terminal"] == 1
    assert path.read_bytes() == before


def test_an_unchanged_pending_is_not_reappended(tmp_path):
    dead = _weekdays("2026-07-01", "2026-08-03")
    OR.resolve([_row()], root=tmp_path, today="2026-09-01", series_fn=lambda s: dead)
    r = OR.resolve([_row()], root=tmp_path, today="2026-09-02", series_fn=lambda s: dead)
    assert r["appended"] == 0 and r["counts"]["unchanged_pending"] == 1


def test_a_terminal_event_wins_over_any_later_line():
    k = OR.record_key(_row())
    evs = [{"record_key": k, "state": OR.RESOLVED, "realized_return": 0.1},
           {"record_key": k, "state": OR.PENDING}]
    assert OR.latest_by_key(evs)[k]["state"] == OR.RESOLVED


def test_dry_run_writes_nothing(tmp_path):
    OR.resolve([_row()], root=tmp_path, today="2026-09-30",
               series_fn=lambda s: _weekdays("2026-07-01", "2026-09-30"),
               write=False)
    assert not (tmp_path / OR.OUTCOMES_FILE).exists()


# --- duplicates and statistics ---------------------------------------------
def test_day_and_night_records_of_one_decision_count_once():
    good = _weekdays("2026-07-01", "2026-09-30")
    evs = [OR.grade(_row(cycle=c), good, today="2026-09-30") for c in ("day", "night")]
    assert evs[0]["record_key"] != evs[1]["record_key"]
    s = OR.summarise(evs)
    assert s["distinct_decisions_resolved"] == 1
    assert s["duplicate_records_collapsed"] == 1


def test_a_row_written_twice_by_one_cycle_is_graded_once(tmp_path):
    good = _weekdays("2026-07-01", "2026-09-30")
    res = OR.resolve([_row(), _row()], root=tmp_path, today="2026-09-30",
                     series_fn=lambda s: good)
    assert res["appended"] == 1 and res["counts"]["duplicate_rows"] == 1


def test_no_brier_or_trade_return_without_a_probability_or_a_fire():
    s = OR.summarise([OR.grade(_row(), _weekdays("2026-07-01", "2026-09-30"),
                               today="2026-09-30")])
    assert s["brier"] is None and s["trade_return"] is None


def test_unmeasurable_records_are_graded_but_never_confirmable():
    ev = OR.grade(_row(state=SO.UNMEASURABLE), _weekdays("2026-07-01", "2026-09-30"),
                  today="2026-09-30")
    assert ev["state"] == OR.RESOLVED and "confirmed_miss" not in ev
    assert ev["opportunity_state"] == SO.UNMEASURABLE


# --- the cycle step ---------------------------------------------------------
def _ctx(root, as_of, dry=False):
    return types.SimpleNamespace(root=pathlib.Path(root), as_of=as_of,
                                 dry_run=dry, results={})


def test_the_step_resolves_and_never_touches_the_audit_file(tmp_path):
    audit = tmp_path / ST.AUDIT_FILE
    audit.parent.mkdir(parents=True)
    audit.write_text("".join(json.dumps(r) + "\n" for r in
                             [_row(), _row(cycle="day"), _row(as_of="2026-09-25")]))
    digest = hashlib.sha256(audit.read_bytes()).hexdigest()
    step = ST.resolve_outcomes_step(lambda s: _weekdays("2026-07-01", "2026-09-30"))
    out = step(_ctx(tmp_path, "2026-09-30T23:00:00"))
    assert out["resolved"] == 2 and out["not_mature"] == 1 and out["appended"] == 2
    assert out["summary"]["distinct_decisions_resolved"] == 1
    assert hashlib.sha256(audit.read_bytes()).hexdigest() == digest
    again = step(_ctx(tmp_path, "2026-09-30T23:30:00"))
    assert again["appended"] == 0 and again["already_terminal"] == 2


def test_the_step_in_dry_run_reports_but_does_not_write(tmp_path):
    audit = tmp_path / ST.AUDIT_FILE
    audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps(_row()) + "\n")
    out = ST.resolve_outcomes_step(
        lambda s: _weekdays("2026-07-01", "2026-09-30"))(
        _ctx(tmp_path, "2026-09-30", dry=True))
    assert out["would_append"] == 1 and out["appended"] == 0
    assert out["summary"]["distinct_decisions_resolved"] == 1
    assert not (tmp_path / OR.OUTCOMES_FILE).exists()


def test_the_stub_is_gone():
    import inspect
    src = inspect.getsource(ST.resolve_outcomes_step)
    assert "0 if ctx.dry_run else 0" not in src
    assert "OR.resolve(" in src
