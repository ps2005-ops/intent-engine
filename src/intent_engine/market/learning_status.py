"""What has the market intelligence system learned — from canonical stores.

THE QUESTION THIS ANSWERS
--------------------------
"What has the market intelligence system learned this week?" That question was
asked on 2026-08-12 and answered by reading a twenty-three-day-stale legacy
database, producing "it learned nothing". This module is the answer that
cannot make that mistake: it resolves every path through
`system_of_record.stores()` and reads nothing else.

FAILURE SEMANTICS (§25)
------------------------
Every channel reports one of RUNNING / RAN_NO_CHANGE / BLOCKED_DATA /
BLOCKED_EXTERNAL / DEGRADED / FAILED / DISABLED / LEGACY, and a channel with
no rows reports `NO_PRODUCER` rather than zero when its record type never
appears in the ledger at all. "This channel produced nothing this week" and
"this channel does not exist" are different facts and an operator acts on them
differently.

WINDOWS
-------
A window filters on the row's own `as_of`. Not every record type carries one;
rows without a date are counted in the all-time totals and reported separately
as `undated`, because silently dropping them would understate learning and
silently including them would fabricate recency.
"""
from __future__ import annotations

import collections
import datetime
import json
from typing import Dict, List, Optional

from . import system_of_record as SOR

CONTRACT = "market_learning_status.v1"

RUNNING = "RUNNING"
RAN_NO_CHANGE = "RAN_NO_CHANGE"
BLOCKED_DATA = "BLOCKED_DATA"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
DEGRADED = "DEGRADED"
FAILED = "FAILED"
DISABLED = "DISABLED"
LEGACY = "LEGACY"
NO_PRODUCER = "NO_PRODUCER"
#: The rows exist but carry no timestamp this reader can resolve, so they can
#: be counted but not placed in a window. Reporting these as RAN_NO_CHANGE
#: would understate the system in exactly the way the original incident did.
UNDATABLE = "UNDATABLE_BY_READER"

#: Effect types that represent the model actually moving. NO_CHANGE is
#: deliberately excluded and deliberately reported: most evidence SHOULD change
#: nothing, and a system where everything changes something is not learning,
#: it is thrashing.
CHANGING_EFFECTS = frozenset({"CREATED", "SUPPORTED", "CONTRADICTED",
                              "RESOLVED", "REVISED", "RETIRED"})

WINDOWS = {"24h": 1, "7d": 7, "30d": 30, "all": None}


def _read(path) -> List[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue          # a torn final line is not a learning fact
    return rows


#: WHEN THE SYSTEM LEARNED IT — in priority order, and read from the names the
#: producers actually use. Every one of these was taken from the live ledger,
#: not guessed: an earlier version of this reader asked only for `as_of` and
#: reported macro, beliefs and source health as "0 in window" when macro had
#: been retrieved that same morning. A status screen that names its fields
#: wrongly manufactures an outage.
#:
#: `observed_at` and `published_at` are deliberately ABSENT. They are
#: OCCURRENCE and PUBLICATION time — when the world did something — and this
#: window is about when the SYSTEM learned it. A filing published in July and
#: read today is learning that happened today.
_LEARNED_AT_FIELDS = ("recorded_at", "created_at", "retrieved_at",
                      "detected_at", "completed_at", "last_updated", "as_of",
                      "snapshot_as_of", "available_at")


def _learned_at(row: dict) -> tuple:
    """(date, field_used). Returns the FIELD so the instrument can audit itself.

    Field-by-field guessing is how this reader was wrong twice in one sitting.
    Returning the name that was used lets `date_field_coverage` show an
    operator exactly which record types fell through to undated, instead of
    letting them vanish quietly into a smaller window count.
    """
    for field in _LEARNED_AT_FIELDS:
        value = row.get(field)
        if value:
            return str(value)[:10], field
    return "", ""


def _as_of(row: dict) -> str:
    return _learned_at(row)[0]


def _counter_integrity(outcomes) -> dict:
    """Are `documents_attempted` and `documents_retrieved` the same population?

    They are not. `counterparty_sources.acquire` increments
    `documents_attempted` once per SUBJECT and `documents_retrieved` once per
    DOCUMENT, so one subject returning three documents produces 1 and 3. Their
    ratio is documents-per-subject, is not bounded by 1, and is not a
    retrieval yield — measured on the live ledger, retrieved EXCEEDS attempted
    in more than half of all rows.

    This function exists so that no consumer computes that ratio by accident.
    It reports the inversion rather than repairing the counter, because the
    field is persisted and renaming it is a migration, not a patch.
    """
    if not outcomes:
        return {"state": "NO_DATA"}
    inverted = [o for o in outcomes
                if int(o.get("documents_retrieved") or 0)
                > int(o.get("documents_attempted") or 0)]
    return {
        "state": "POPULATION_MISMATCH" if inverted else "CONSISTENT",
        "rows": len(outcomes),
        "rows_where_retrieved_exceeds_attempted": len(inverted),
        "safe_to_compute_yield": not inverted,
        "detail": (
            "`documents_attempted` counts SUBJECTS "
            "(counterparty_sources.acquire:284) and `documents_retrieved` "
            "counts DOCUMENTS (:291). Do not divide them — the result is "
            "documents-per-subject, not a yield."
            if inverted else ""),
    }


def _cutoff(window: str, today=None) -> Optional[str]:
    days = WINDOWS.get(window)
    if days is None:
        return None
    base = today or datetime.date.today()
    return (base - datetime.timedelta(days=days)).isoformat()


def _channel(rows_by_type, declared_types, window_rows_by_type,
             coverage=None) -> dict:
    """One learning channel: what exists, what moved, and which it is."""
    present = [t for t in declared_types if rows_by_type.get(t)]
    if not present:
        return {"status": NO_PRODUCER, "all_time": 0, "in_window": 0,
                "by_record": {},
                "reason": (f"no rows of type {'/'.join(declared_types)} have "
                           f"ever been written; this channel has no producer, "
                           f"which is not the same as producing nothing")}
    in_window = sum(len(window_rows_by_type.get(t, ())) for t in declared_types)
    all_time = sum(len(rows_by_type.get(t, ())) for t in declared_types)
    # Every row this channel has ever written is undatable, so a zero here is
    # a statement about the READER, not about the channel.
    cov = coverage or {}
    datable = sum(n for t in present
                  for field, n in (cov.get(t) or {}).items()
                  if field != "UNDATED")
    if present and not datable:
        return {"status": UNDATABLE, "all_time": all_time, "in_window": 0,
                "by_record": {t: len(rows_by_type.get(t, ()))
                              for t in present},
                "reason": (f"{all_time} row(s) exist but carry no timestamp "
                           f"this reader resolves, so they cannot be placed "
                           f"in a window; this is NOT a measured zero")}
    return {
        "status": RUNNING if in_window else RAN_NO_CHANGE,
        "all_time": all_time,
        "in_window": in_window,
        "by_record": {t: len(window_rows_by_type.get(t, ()))
                      for t in declared_types if rows_by_type.get(t)},
        "reason": ("" if in_window else
                   f"{all_time} row(s) all time, none inside the window"),
    }


def collect(root=None, window: str = "7d", today=None) -> dict:
    """The canonical learning picture. Reads ONLY declared canonical stores."""
    if window not in WINDOWS:
        raise ValueError(f"unknown window {window!r}; "
                         f"expected one of {sorted(WINDOWS)}")
    paths = SOR.stores(root)
    canonical = SOR.canonical()

    ledger = _read(paths["learning_ledger"])
    cycles = _read(paths.get("cycle_history"))
    cutoff = _cutoff(window, today)

    by_type: Dict[str, List[dict]] = collections.defaultdict(list)
    for row in ledger:
        by_type[str(row.get("record") or "")].append(row)

    win_by_type: Dict[str, List[dict]] = collections.defaultdict(list)
    undated = 0
    coverage: Dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for row in ledger:
        record = str(row.get("record") or "")
        stamp, field = _learned_at(row)
        coverage[record][field or "UNDATED"] += 1
        if not stamp:
            undated += 1
            continue
        if cutoff is None or stamp >= cutoff:
            win_by_type[record].append(row)

    # Which record types this reader cannot date, and by how much. An
    # UNDATED-heavy type is a reader defect until proven otherwise, so it is
    # surfaced rather than absorbed into a quietly smaller window.
    undated_types = {rec: dict(counts) for rec, counts in coverage.items()
                     if counts.get("UNDATED")}

    declared = canonical.get("ledger_records") or {}
    channels = {name: _channel(by_type, types, win_by_type, coverage)
                for name, types in declared.items()}

    # Knowledge effects, split. This is the one number that separates "busy"
    # from "learning", so it is computed here rather than left to the reader.
    effects = win_by_type.get("knowledge_effect", [])
    changed = [e for e in effects
               if str(e.get("effect_type")) in CHANGING_EFFECTS]
    effect_types = collections.Counter(str(e.get("effect_type") or "?")
                                       for e in effects)

    # Active learning, including the outcomes a survivorship-biased record
    # would drop (§13).
    # The producer writes `status` (see research_decision.ResearchOutcome).
    # Asking for `outcome`/`result` returned "?" for all 39 rows and made
    # `zero_result_captured` report False while NO_RESULT and FAILED were both
    # sitting in the ledger — a false negative on the one guard that keeps the
    # policy dataset from being survivorship-biased.
    outcomes = collections.Counter(
        str(r.get("status") or "UNRECORDED")
        for r in win_by_type.get("research_outcome", []))
    all_outcomes = collections.Counter(
        str(r.get("status") or "UNRECORDED")
        for r in by_type.get("research_outcome", []))

    last_cycle = cycles[-1] if cycles else None
    completed = [c for c in cycles
                 if str(c.get("status") or "").upper().startswith("COMPLET")]

    return {
        "contract": CONTRACT,
        "system_of_record": {
            "id": SOR.canonical_id(),
            "entrypoint": canonical.get("entrypoint"),
            "runtime_root": str(
                (canonical.get("scheduler") or {}).get("runtime_root") or ""),
            "trading_mode": (canonical.get("scheduler") or {}).get(
                "trading_mode"),
            "ledger": str(paths["learning_ledger"]),
            "ledger_exists": paths["learning_ledger"].exists(),
        },
        "window": window,
        "cutoff": cutoff or "all time",
        "cycles": {
            "recorded": len(cycles),
            "completed": len(completed),
            "last": (last_cycle or {}).get("started_at")
            or (last_cycle or {}).get("as_of"),
            "last_status": (last_cycle or {}).get("status"),
        },
        "ledger_rows": {"all_time": len(ledger),
                        "in_window": sum(len(v) for v in win_by_type.values()),
                        "undated": undated},
        "date_field_coverage": {rec: dict(counts)
                                for rec, counts in sorted(coverage.items())},
        "undated_record_types": undated_types,
        "channels": channels,
        "knowledge": {
            "effects_in_window": len(effects),
            "changed_something": len(changed),
            "changed_nothing": len(effects) - len(changed),
            "by_effect_type": dict(sorted(effect_types.items())),
            # A SHARE over effects — both populations are effects.
            "changing_share": (round(len(changed) / len(effects), 4)
                               if effects else None),
        },
        "active_learning": {
            "decisions_in_window": len(win_by_type.get(
                "research_decision", [])),
            "outcomes_in_window": dict(sorted(outcomes.items())),
            "outcomes_all_time": dict(sorted(all_outcomes.items())),
            # §13: a policy dataset that only records successes is
            # survivorship-biased and cannot support off-policy evaluation.
            "zero_result_captured": bool(
                {"NO_RESULT", "FAILED", "REFUSED"} & set(all_outcomes)),
            # NOT a yield, and deliberately not published as one. See
            # `acquisition_counter_integrity` below: the two counters measure
            # different populations, so their ratio is meaningless.
            "acquisition_counter_integrity": _counter_integrity(
                by_type.get("research_outcome", [])),
        },
        "legacy_pipelines": [
            {"id": p.get("id"), "status": p.get("status"),
             "store": p.get("store"), "last_write": p.get("last_write"),
             "scheduled": p.get("scheduled")}
            for p in SOR.legacy_pipelines()],
    }


def render(status: dict) -> str:
    """One screen. The header exists so a reader cannot mistake the source."""
    sor = status["system_of_record"]
    out = [
        "=" * 72,
        "MARKET INTELLIGENCE — SYSTEM OF RECORD",
        "=" * 72,
        f"  id          {sor['id']}",
        f"  entrypoint  {sor['entrypoint']}",
        f"  ledger      {sor['ledger']}",
        f"  mode        {sor['trading_mode']}",
        f"  window      {status['window']}  (since {status['cutoff']})",
        "",
        f"  cycles recorded {status['cycles']['recorded']}, "
        f"completed {status['cycles']['completed']}, "
        f"last {status['cycles']['last']} [{status['cycles']['last_status']}]",
        f"  ledger rows {status['ledger_rows']['all_time']} all time, "
        f"{status['ledger_rows']['in_window']} in window, "
        f"{status['ledger_rows']['undated']} undated"
        + (f"  <-- undatable types: "
           f"{', '.join(sorted(status['undated_record_types']))}"
           if status.get("undated_record_types") else ""),
        "",
        "LEARNING CHANNELS",
        "-" * 72,
    ]
    for name, ch in status["channels"].items():
        detail = ", ".join(f"{k}={v}" for k, v in ch["by_record"].items())
        out.append(f"  {name:<18}{ch['status']:<16}"
                   f"{ch['in_window']:>6} in window "
                   f"({ch['all_time']} all time)")
        if detail:
            out.append(f"  {'':<18}  {detail}")
        if ch["status"] == NO_PRODUCER:
            out.append(f"  {'':<18}  ↳ {ch['reason']}")

    k = status["knowledge"]
    share = ("UNMEASURABLE" if k["changing_share"] is None
             else f"{k['changing_share']:.1%}")
    out += [
        "",
        "KNOWLEDGE EFFECTS",
        "-" * 72,
        f"  effects {k['effects_in_window']}, "
        f"changed something {k['changed_something']}, "
        f"changed nothing {k['changed_nothing']}  ({share})",
        f"  by type  {k['by_effect_type'] or '-'}",
    ]

    a = status["active_learning"]
    out += [
        "",
        "ACTIVE LEARNING (prospective research policy)",
        "-" * 72,
        f"  decisions in window {a['decisions_in_window']}",
        f"  outcomes all time   {a['outcomes_all_time'] or '-'}",
        f"  zero-result captured {a['zero_result_captured']}"
        f"   (required for unbiased policy evaluation)",
    ]

    out += ["", "NOT THE SYSTEM OF RECORD", "-" * 72]
    for p in status["legacy_pipelines"]:
        out.append(f"  {p['id']:<28}{p['status']:<10}"
                   f"last write {p['last_write']}  "
                   f"scheduled={p['scheduled']}  {p['store']}")
    out.append("=" * 72)
    return "\n".join(out)
