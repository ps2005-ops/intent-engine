"""The pre-registration ledger: append-only, hash-chained, three events.

WHY NOT THE EXISTING STORES
---------------------------
`econ.forward_ledger` is append-only and refuses to move a field of an open
record, which is the right instinct, but nothing stops the FILE being
regenerated from scratch, and a regenerated file passes every per-record
guard. `core.prediction_ledger`, `learning.LearningStore` and
`paper.PaperStore` fold SQLite rows to the latest per id, so a later row
silently becomes the record. A forecast ledger that can be rewritten is not
a track record. So each line here carries the hash of the line before it:
deleting, reordering or editing any line breaks every hash after it, and
`verify()` names the first broken line.

THREE EVENTS, NO FOURTH
-----------------------
    REGISTER   the forecast, before its entry session exists
    RESOLVE    the outcome, only after the exit session has happened
    VOID       the forecast could not be scored (missing bar), with reason

There is no UPDATE. A registered forecast is never touched again; its
resolution is a separate line that refers to it.

THE FORWARD LEDGER REFUSES THE PAST
-----------------------------------
A FORWARD_SHADOW ledger refuses a registration whose decision timestamp is
older than `MAX_REGISTRATION_SKEW` before the wall clock, and refuses a
record labelled anything but FORWARD_SHADOW. The rehearsal ledger exists
precisely so backdated records have somewhere to go that is not the
forward record.
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import hashlib
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from intent_engine.paper_validation import schedule as SCH
from intent_engine.paper_validation.protocol import canonical

CONTRACT = "paper_validation_ledger.v1"

FORWARD_SHADOW = "FORWARD_SHADOW"
REHEARSAL = "REHEARSAL"
REPLAY = "REPLAY"
KINDS = (FORWARD_SHADOW, REHEARSAL, REPLAY)

REGISTER, RESOLVE, VOID = "REGISTER", "RESOLVE", "VOID"
EVENTS = (REGISTER, RESOLVE, VOID)

OPEN, RESOLVED, VOIDED = "OPEN", "RESOLVED", "VOIDED"

#: How far a forward registration's decision time may trail the clock.
MAX_REGISTRATION_SKEW = _dt.timedelta(hours=6)

#: Fields every registration must carry. A record missing any of them is
#: refused at write time, not discovered at analysis time.
REQUIRED = (
    "forecast_id", "ledger_kind", "decision_ts", "decision_date",
    "information_cutoff", "instrument", "universe", "signal_scope",
    "target", "direction", "probability", "horizon_sessions",
    "entry_rule", "exit_rule", "risk_budget", "invalidation_condition",
    "expected_cost_bps", "evidence_ids", "thesis", "causal_mechanism",
    "competing_hypotheses", "policy_id", "policy_version", "provenance",
    "feature_set", "model_version", "data_vintage", "protocol_hash",
    "regime_at_decision",
    # The due date, decided once from the exchange calendar and sealed into
    # the chain. Records registered before 2026-11-10 lack these; their
    # schedule is recomputed by `schedule.schedule_of` from the same rules.
    "scheduled_entry_session", "scheduled_exit_session", "schedule_calendar",
)
DIRECTIONS = ("LONG", "SHORT", "ABSTAIN")


class LedgerViolation(RuntimeError):
    """Something tried to make the record say what it did not say."""


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _ts(s: str) -> _dt.datetime:
    t = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def genesis(kind: str) -> str:
    return _sha(f"genesis:{CONTRACT}:{kind}")


def line_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return _sha(canonical(body))


@dataclass(frozen=True)
class State:
    forecast_id: str
    status: str
    registration: dict
    resolution: Optional[dict] = None
    void_reason: str = ""


def validate_registration(rec: dict, *, kind: str) -> None:
    missing = [f for f in REQUIRED if f not in rec]
    if missing:
        raise LedgerViolation(f"registration missing {missing}")
    if rec["ledger_kind"] != kind:
        raise LedgerViolation(
            f"a {rec['ledger_kind']} record may not enter a {kind} ledger")
    if rec["direction"] not in DIRECTIONS:
        raise LedgerViolation(f"direction {rec['direction']!r}")
    p = rec["probability"]
    if rec["direction"] == "ABSTAIN":
        # A rule that abstains states nothing (None). A fitted model still
        # states P(excess > 0) when its margin says not to trade, and that
        # statement is scored: abstaining from the TRADE is not abstaining
        # from the FORECAST.
        if p is not None and not (0.0 < float(p) < 1.0):
            raise LedgerViolation(f"probability {p!r} must be in (0, 1)")
        if not str(rec.get("abstention_reason") or "").strip():
            raise LedgerViolation("an abstention must say why")
    else:
        if p is None or not (0.0 < float(p) < 1.0):
            raise LedgerViolation(f"probability {p!r} must be in (0, 1)")
        # A LONG says the excess return is more likely positive; a SHORT
        # says it is more likely negative. A record whose probability
        # contradicts its own direction is incoherent, not bold.
        if rec["direction"] == "LONG" and float(p) < 0.5:
            raise LedgerViolation("LONG with P(excess > 0) < 0.5")
        if rec["direction"] == "SHORT" and float(p) > 0.5:
            raise LedgerViolation("SHORT with P(excess > 0) > 0.5")
    if str(rec["information_cutoff"]) > str(rec["decision_date"]):
        raise LedgerViolation("information cutoff after the decision date")
    if not isinstance(rec["evidence_ids"], list):
        raise LedgerViolation("evidence_ids must be a list")
    if not isinstance(rec["competing_hypotheses"], list):
        raise LedgerViolation("competing_hypotheses must be a list")
    _validate_schedule(rec)


def _validate_schedule(rec: dict) -> None:
    """A stored due date must be the one the calendar gives. Otherwise a
    registration could be written with its exit already postponed."""
    cal = SCH.CALENDARS.get(rec["schedule_calendar"])
    if cal is None:
        raise LedgerViolation(
            f"unknown schedule calendar {rec['schedule_calendar']!r}")
    if not isinstance(rec["horizon_sessions"], int):
        raise LedgerViolation("horizon_sessions must be an int")
    want = SCH.scheduled_window(rec["decision_date"], rec["horizon_sessions"],
                                cal)
    got = (rec["scheduled_entry_session"], rec["scheduled_exit_session"])
    if got != want:
        raise LedgerViolation(
            f"{rec['forecast_id']}: scheduled {got} but the {cal.calendar_id} "
            f"calendar gives {want} for a {rec['horizon_sessions']}-session "
            f"horizon from {rec['decision_date']}")


class Ledger:
    """One JSONL file, one kind, one writer at a time."""

    def __init__(self, path, kind: str, *,
                 clock: Callable[[], _dt.datetime] = _now):
        if kind not in KINDS:
            raise LedgerViolation(f"unknown ledger kind {kind!r}")
        self.path = pathlib.Path(path)
        self.kind = kind
        self.clock = clock

    # --- reading --------------------------------------------------------------
    def entries(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        for n, line in enumerate(
                self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                raise LedgerViolation(f"line {n}: blank line in a chained file")
            out.append(json.loads(line))
        return out

    def verify(self, entries: Optional[Sequence[dict]] = None) -> int:
        """Recompute the chain. Returns the entry count or raises."""
        rows = list(self.entries() if entries is None else entries)
        prev = genesis(self.kind)
        for i, e in enumerate(rows):
            n = i + 1
            if e.get("seq") != n:
                raise LedgerViolation(f"line {n}: seq {e.get('seq')} != {n}")
            if e.get("ledger_kind") != self.kind:
                raise LedgerViolation(
                    f"line {n}: kind {e.get('ledger_kind')} in a {self.kind} "
                    "ledger")
            if e.get("prev_hash") != prev:
                raise LedgerViolation(
                    f"line {n}: prev_hash does not match line {n - 1}; the "
                    "file was edited, reordered or truncated")
            if line_hash(e) != e.get("hash"):
                raise LedgerViolation(
                    f"line {n}: content does not match its hash; the line "
                    "was edited after it was written")
            prev = e["hash"]
        return len(rows)

    def states(self) -> Dict[str, State]:
        rows = self.entries()
        self.verify(rows)
        out: Dict[str, State] = {}
        for e in rows:
            fid = e["forecast_id"]
            if e["event"] == REGISTER:
                out[fid] = State(fid, OPEN, e["payload"])
            elif e["event"] == RESOLVE:
                s = out[fid]
                out[fid] = State(fid, RESOLVED, s.registration, e["payload"])
            elif e["event"] == VOID:
                s = out[fid]
                out[fid] = State(fid, VOIDED, s.registration,
                                 void_reason=e["payload"].get("reason", ""))
        return out

    def open_forecasts(self) -> List[State]:
        return [s for s in self.states().values() if s.status == OPEN]

    # --- writing --------------------------------------------------------------
    def _append(self, items: Sequence[tuple]) -> int:
        """items: (event, forecast_id, payload). All or nothing."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                rows = self.entries()
                self.verify(rows)
                states, regs = {}, {}
                for e in rows:
                    states.setdefault(e["forecast_id"], []).append(e["event"])
                    if e["event"] == REGISTER:
                        regs[e["forecast_id"]] = e["payload"]
                prev = rows[-1]["hash"] if rows else genesis(self.kind)
                seq = len(rows)
                now = self.clock()
                lines = []
                for event, fid, payload in items:
                    self._check(event, fid, payload, states, regs, now)
                    states.setdefault(fid, []).append(event)
                    if event == REGISTER:
                        regs[fid] = payload
                    seq += 1
                    entry = {"seq": seq, "prev_hash": prev,
                             "ledger_kind": self.kind, "contract": CONTRACT,
                             "event": event, "forecast_id": fid,
                             "recorded_at": now.isoformat(timespec="seconds"),
                             "payload": payload}
                    entry["hash"] = line_hash(entry)
                    prev = entry["hash"]
                    lines.append(canonical(entry))
                fh.seek(0, os.SEEK_END)
                for ln in lines:
                    fh.write(ln + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return len(lines)

    def _check(self, event, fid, payload, states, regs, now) -> None:
        if event not in EVENTS:
            raise LedgerViolation(f"unknown event {event!r}")
        history = states.get(fid, [])
        if event == REGISTER:
            if history:
                raise LedgerViolation(
                    f"{fid} is already registered; a forecast is never "
                    "re-registered, edited or replaced")
            validate_registration(payload, kind=self.kind)
            if payload["forecast_id"] != fid:
                raise LedgerViolation("forecast_id mismatch")
            decided = _ts(payload["decision_ts"])
            if decided > now:
                raise LedgerViolation("decision timestamp is in the future")
            if self.kind == FORWARD_SHADOW and \
                    now - decided > MAX_REGISTRATION_SKEW:
                raise LedgerViolation(
                    f"{fid}: decided {payload['decision_ts']}, registered "
                    f"{now.isoformat(timespec='seconds')}. A forward record "
                    "may not be backdated; backdated records belong in a "
                    "REHEARSAL ledger.")
            return
        if not history:
            raise LedgerViolation(f"{fid} was never registered")
        if RESOLVE in history or VOID in history:
            raise LedgerViolation(
                f"{fid} is already closed; an outcome is recorded once")
        reg = regs[fid]
        _entry, due_exit, _cal = SCH.schedule_of(reg)
        today_ny = _ny_date(now)
        if event == VOID:
            if not str(payload.get("reason", "")).strip():
                raise LedgerViolation("a VOID must give its reason")
            if due_exit >= today_ny:
                raise LedgerViolation(
                    f"{fid}: scheduled to exit {due_exit} (clock {today_ny}). "
                    "A forecast is not voided before its window has closed; "
                    "a bar that is missing today may still arrive.")
            return
        # RESOLVE: the outcome must have happened.
        for f in ("entry_date", "exit_date", "excess_return", "outcome"):
            if f not in payload:
                raise LedgerViolation(f"resolution missing {f}")
        if str(payload["exit_date"]) >= today_ny:
            raise LedgerViolation(
                f"{fid}: exit session {payload['exit_date']} has not "
                f"completed (clock {today_ny}). An outcome that has not "
                "happened cannot be recorded.")
        if payload["outcome"] not in (0, 1):
            raise LedgerViolation("outcome must be 0 or 1")
        if str(payload["entry_date"]) <= str(reg["decision_date"]):
            raise LedgerViolation(
                f"{fid}: entry {payload['entry_date']} is not after the "
                f"decision date {reg['decision_date']}; the forecast would "
                "be scored on a session it already saw")
        if str(payload["exit_date"]) <= str(payload["entry_date"]):
            raise LedgerViolation(f"{fid}: exit is not after entry")
        sched = (_entry, due_exit)
        got = (str(payload["entry_date"]), str(payload["exit_date"]))
        if got != sched:
            raise LedgerViolation(
                f"{fid}: scheduled entry/exit {sched}, resolution says {got}. "
                "A resolution may not move a forecast's due date; if the "
                "scheduled session has no bar, the forecast is voided.")

    def register(self, records: Sequence[dict]) -> int:
        return self._append([(REGISTER, r["forecast_id"], r) for r in records])

    def resolve(self, resolutions: Sequence[dict]) -> int:
        return self._append([(RESOLVE, r["forecast_id"], r)
                             for r in resolutions])

    def void(self, voids: Sequence[dict]) -> int:
        return self._append([(VOID, v["forecast_id"], v) for v in voids])


def _ny_date(t: _dt.datetime) -> str:
    """The New York calendar date of a UTC instant."""
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                   # pragma: no cover
        return (t - _dt.timedelta(hours=5)).date().isoformat()


def ny_date(t: _dt.datetime) -> str:
    return _ny_date(t)


def due_schedule(ledger: Ledger) -> Dict[str, dict]:
    """Per decision date: how many forecasts, when they are due, and how many
    are still open. Read from the registrations, so every caller that reports
    a due date reports the same one."""
    out: Dict[str, dict] = {}
    for s in ledger.states().values():
        reg = s.registration
        entry, exit_, cal = SCH.schedule_of(reg)
        row = out.setdefault(reg["decision_date"], {
            "forecasts": 0, "open": 0, "resolved": 0, "voided": 0,
            "scheduled_entry_session": entry,
            "scheduled_exit_session": exit_,
            "resolvable_from": SCH.resolvable_from(exit_),
            "schedule_calendar": cal,
            "schedule_stored": bool(reg.get("scheduled_exit_session"))})
        if (row["scheduled_entry_session"], row["scheduled_exit_session"]) \
                != (entry, exit_):
            raise LedgerViolation(
                f"decision date {reg['decision_date']} has forecasts with two "
                "different schedules")
        row["forecasts"] += 1
        row[{OPEN: "open", RESOLVED: "resolved", VOIDED: "voided"}[
            s.status]] += 1
    return dict(sorted(out.items()))


def summary(ledger: Ledger) -> dict:
    st = ledger.states()
    by = {}
    for s in st.values():
        by[s.status] = by.get(s.status, 0) + 1
    return {"path": str(ledger.path), "kind": ledger.kind,
            "entries": ledger.verify(), "forecasts": len(st),
            "by_status": by, "due": due_schedule(ledger)}
