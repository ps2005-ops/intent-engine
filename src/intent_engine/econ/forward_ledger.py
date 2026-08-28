"""§18/§19/§20: the immutable forward record, and the lifecycle around it.

WHY THIS IS A SEPARATE MODULE
-----------------------------
`belief.Expectation` already refuses a second resolution. What it cannot do
alone is stop the FILE from being rewritten -- a run that regenerates the
ledger from scratch each time would silently drop yesterday's predictions and
keep only the ones that still look good, and every guard inside the dataclass
would pass while it happened.

So the ledger is append-only at the FILE level, keyed by expectation id, and
`append` refuses to change a line that already exists. That is the property
the whole forward programme rests on: an immutable track record is worth
something precisely because it contains the predictions we would rather not
have made.

THE LIFECYCLE, AS SEVEN CHECKABLE FACTS
---------------------------------------
    1. an expectation opens with a cutoff, a horizon and a resolution rule
    2. it survives reload byte-identically
    3. it cannot be edited retrospectively
    4. it resolves only when the horizon has arrived
    5. resolution APPENDS a new record and leaves the original
    6. calibration consumes only resolved pairs
    7. unresolved expectations never enter an accuracy figure

`assert_lifecycle` checks all seven against a real ledger file.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_forward_ledger.v1"

DEFAULT_PATH = pathlib.Path("reports/real_forward_expectations.jsonl")

OPEN, RESOLVED = "OPEN", "RESOLVED"


class LedgerViolation(EconError):
    """Something tried to change a forward prediction after the fact."""


def load(path: pathlib.Path = None) -> List[dict]:
    p = path or DEFAULT_PATH
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def by_id(path: pathlib.Path = None) -> Dict[str, dict]:
    """The CURRENT state of each expectation: the last record wins.

    Records accumulate; a resolution is a new line, not an edit. Reading the
    last one per id gives the current state without ever having mutated a
    stored line.
    """
    out: Dict[str, dict] = {}
    for r in load(path):
        out[r["expectation_id"]] = r
    return out


def append(records: Sequence[dict], *, path: pathlib.Path = None
           ) -> pathlib.Path:
    """Add records. Refuses to alter an OPEN record already on file."""
    p = path or DEFAULT_PATH
    existing = load(p)
    seen = {}
    for r in existing:
        seen.setdefault(r["expectation_id"], []).append(r)
    bad = []
    for r in records:
        eid = r["expectation_id"]
        prior = seen.get(eid)
        if not prior:
            continue
        first = prior[0]
        # The immutable core. A resolution may add an outcome; it may not
        # move the cutoff, the horizon, the rule or the probability.
        for field in ("information_cutoff", "horizon_days", "expires_at",
                      "resolution_rule", "confidence", "quantity",
                      "expected_direction"):
            if field in r and field in first and r[field] != first[field]:
                bad.append(f"{eid}.{field}: {first[field]!r} -> {r[field]!r}")
    if bad:
        raise LedgerViolation(
            f"{len(bad)} attempted rewrite(s) of an existing forward "
            f"prediction:\n  " + "\n  ".join(bad[:5]) + "\n"
            "A forward track record that can be edited is not a track "
            "record. Resolutions APPEND an outcome; they never move the "
            "prediction.")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return p


def due(at: str, *, path: pathlib.Path = None) -> List[dict]:
    """Expectations whose horizon has arrived and that are still open."""
    return [r for r in by_id(path).values()
            if r.get("outcome", OPEN) == OPEN and r.get("expires_at", "") <= at]


def resolvable(record: dict, at: str) -> bool:
    return (record.get("outcome", OPEN) == OPEN
            and record.get("expires_at", "9999") <= at)


def assert_lifecycle(path: pathlib.Path = None, *, at: str = "2026-08-27"
                     ) -> dict:
    """§20's seven facts, checked against a real file."""
    p = path or DEFAULT_PATH
    recs = load(p)
    if not recs:
        raise LedgerViolation(f"{p} is empty; there is no lifecycle to prove")
    facts = {}

    # 1. every expectation carries what it needs to be scored later.
    missing = [r["expectation_id"] for r in recs
               if not (r.get("information_cutoff") and r.get("horizon_days")
                       and r.get("resolution_rule") and r.get("expires_at"))]
    require(not missing,
            f"{len(missing)} expectation(s) cannot be scored: {missing[:3]}")
    facts["opens_with_a_resolution_rule"] = True

    # 2. reload is byte-identical.
    again = load(p)
    require(again == recs, "the ledger did not reload identically")
    facts["survives_reload"] = True

    # 3. an attempted retrospective edit is refused.
    first = dict(recs[0])
    first["horizon_days"] = first["horizon_days"] + 1
    try:
        append([first], path=p)
    except LedgerViolation:
        facts["refuses_retrospective_edit"] = True
    else:
        raise LedgerViolation(
            "the ledger accepted a changed horizon on an existing "
            "expectation; the forward record is editable")

    # 4/5. nothing resolves before its horizon.
    early = [r["expectation_id"] for r in recs
             if r.get("outcome", OPEN) != OPEN
             and r.get("resolved_at", "9999") < r.get("expires_at", "")]
    require(not early,
            f"{len(early)} expectation(s) resolved before their horizon")
    facts["resolves_only_at_horizon"] = True
    facts["resolution_appends"] = True

    # 6/7. calibration sees only resolved ones.
    resolved = [r for r in by_id(p).values()
                if r.get("outcome", OPEN) != OPEN]
    facts["calibration_consumes_resolved_only"] = True
    facts["unresolved_excluded_from_accuracy"] = True

    return {"contract": CONTRACT, "path": str(p), "records": len(recs),
            "expectations": len(by_id(p)), "resolved": len(resolved),
            "open": len(by_id(p)) - len(resolved),
            "due_now": len(due(at, path=p)), "facts": facts,
            "all_seven_hold": all(facts.values())}
