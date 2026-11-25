"""FX4 (preregistered 2026-11-25): declared intention vs actual behaviour.

HYPOTHESIS
  A company's revenue-guidance revision (its declared expectation) predicts
  the direction of its NEXT reported quarter's revenue acceleration (what it
  actually did), better than persistence of its own acceleration.

CONTRACT (fixed here, immutable once registered)
  trigger     a GUIDANCE_REVISION evidence item whose demand_reading.v2.1
              reading is a revenue/sales/volume move against the company's own
              past (raised -> UP, cut -> DOWN). Surprises and abstentions do
              not trigger.
  cutoff      the evidence's available_at (never seen_at alone)
  target      sign of (YoY revenue growth of the first quarter whose 10-Q/10-K
              is FILED after the cutoff) minus (YoY growth of the latest
              quarter filed before the cutoff), from SEC XBRL walled on `filed`
  baselines   PERSISTENCE: the sign of the last known acceleration;
              DECELERATE: always DOWN
  one forecast per company per trigger quarter; no daily forecasts.

This module is pure. The caller supplies evidence rows and an XBRL reader;
nothing here fetches or writes.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import re

from intent_engine.market import demand_reading as DR

CONTRACT = "fx4_intent_vs_behaviour.v1"
UP, DOWN = "UP", "DOWN"
DEMAND_QTY = {"revenue", "revenues", "sales", "volume", "volumes", "orders",
              "bookings", "shipments", "deliveries", "gmv"}


#: The first day a trigger may be used. A forward experiment registered on
#: 2026-11-25 may not reach back: the dry run on that day would otherwise have
#: registered NET with an August cutoff although the quarter it "predicts"
#: had been filed in November.
FIRST_TRIGGER_DATE = "2026-11-25"
_GUIDANCE = re.compile(r"\b(outlook|guidance|forecast|view|target)\b", re.I)
_INORGANIC = re.compile(r"\b(acquisition|acquir\w+|merger|deal|currency|fx|"
                        r"foreign exchange)\b", re.I)


def trigger(evidence: dict) -> Optional[str]:
    """UP/DOWN only for a revision of GUIDANCE about a demand quantity.

    A reported revenue rise in a guidance article is an outcome, not an
    intention. Growth attributed to an acquisition or currency is not organic
    demand, so it abstains."""
    if evidence.get("evidence_type") != "GUIDANCE_REVISION":
        return None
    text = evidence.get("fact", "")
    if _INORGANIC.search(text):
        return None
    r = DR.read(text)
    if r.quantity not in DEMAND_QTY or not _GUIDANCE.search(r.reason or ""):
        return None
    return {DR.STRENGTHENING: UP, DR.WEAKENING: DOWN}.get(r.family)


def _yoy(series: Sequence[Tuple[str, float]], i: int) -> Optional[float]:
    e, v = series[i]
    for e2, v2 in reversed(series[:i]):
        if 350 <= (date.fromisoformat(e) - date.fromisoformat(e2)).days <= 380:
            return v / v2 - 1 if v2 > 0 else None
    return None


def known_quarters(facts: Iterable[Tuple[str, str, float]], cutoff: str
                   ) -> List[Tuple[str, float]]:
    """(period_end, value) for quarters FILED strictly before `cutoff`;
    the latest filing of each period wins (revisions known by then)."""
    best: Dict[str, Tuple[str, float]] = {}
    for end, filed, val in facts:
        if filed < cutoff and (end not in best or filed >= best[end][0]):
            best[end] = (filed, val)
    return sorted((e, v) for e, (f, v) in best.items())


def acceleration_at(facts, cutoff: str) -> Optional[Tuple[str, float]]:
    s = known_quarters(facts, cutoff)
    if len(s) < 6:
        return None
    g0, g1 = _yoy(s, len(s) - 1), _yoy(s, len(s) - 2)
    if g0 is None or g1 is None:
        return None
    return s[-1][0], g0 - g1


def register(evidence_rows: Iterable[dict], *, revenue_facts: Callable[[str], list],
             company_of: Callable[[dict], Optional[str]], today: str,
             existing_ids: Sequence[str] = ()) -> List[dict]:
    """New FX4 forecasts from evidence knowable by `today`. Idempotent by id."""
    out, seen = [], set(existing_ids)
    for e in sorted(evidence_rows, key=lambda r: r.get("available_at", "")):
        d = trigger(e)
        sym = company_of(e)
        cutoff = (e.get("available_at") or "")[:10]
        if (not d or not sym or not cutoff or cutoff > today
                or cutoff < FIRST_TRIGGER_DATE):
            continue
        facts = revenue_facts(sym)
        acc = acceleration_at(facts, cutoff)
        if acc is None:
            continue
        last_end, last_acc = acc
        fid = f"fx4:{sym}:{last_end}"            # one per company per quarter
        if fid in seen:
            continue
        seen.add(fid)
        out.append({
            "contract": CONTRACT, "forecast_id": fid, "symbol": sym,
            "created_at": today, "information_cutoff": cutoff,
            "trigger_evidence_id": e.get("evidence_id"),
            "trigger_text": (e.get("fact") or "")[:200],
            "reader": DR.CONTRACT, "prediction": d,
            "mechanism": "declared revenue expectation (guidance) precedes "
                         "reported revenue acceleration",
            "target": "sign of next-filed quarter YoY revenue growth minus "
                      f"YoY growth of the quarter ended {last_end}",
            "last_known_quarter_end": last_end,
            "last_known_acceleration": round(last_acc, 6),
            "baselines": {"PERSISTENCE": UP if last_acc > 0 else DOWN,
                          "DECELERATE": DOWN},
            "resolution_rule": "first quarter with period end after "
                               f"{last_end} and filed after {cutoff}; SEC XBRL",
            "outcome_source": "SEC XBRL companyfacts (filed-date walled)",
            "invalidation": "no later quarter filed within 200 days of the "
                            "cutoff -> EXPIRED, never scored",
            "model_version": f"{CONTRACT}+{DR.CONTRACT}",
            "hash": hashlib.sha256(f"{fid}|{d}|{cutoff}".encode()).hexdigest()[:16],
        })
    return out


def resolve(forecast: dict, facts, *, today: str) -> Optional[dict]:
    """Score once the next quarter is filed. None while it is not."""
    s = known_quarters(facts, today)
    later = [i for i, (e, _v) in enumerate(s) if e > forecast["last_known_quarter_end"]]
    if not later:
        expiry = (date.fromisoformat(forecast["information_cutoff"])
                  .toordinal() + 200)
        if date.fromisoformat(today).toordinal() > expiry:
            return {**forecast, "state": "EXPIRED", "resolved_at": today}
        return None
    i = later[0]
    g_new, g_old = _yoy(s, i), _yoy(s, i - 1)
    if g_new is None or g_old is None:
        return None
    actual = UP if g_new - g_old > 0 else DOWN
    return {**forecast, "state": "RESOLVED", "resolved_at": today,
            "actual": actual, "correct": actual == forecast["prediction"],
            "baseline_correct": {k: actual == v
                                 for k, v in forecast["baselines"].items()}}
