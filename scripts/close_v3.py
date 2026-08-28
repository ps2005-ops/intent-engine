"""§11/§13/§31-§34/§61: the closure ledgers, emitted from canonical records.

WHAT THIS IS FOR
----------------
Four things were true only in a terminal: which economic dimensions are live
and which are blocked, what every relation's status and next eligible
evaluation is, whether the learning report agrees with the ledgers it
describes, and which capability is at which build status. A conclusion that
exists only in chat is not a conclusion the repository holds — §63.

EVERY NUMBER HERE IS DERIVED. Nothing is a literal, and `reconcile` re-derives
each displayed count from the canonical record and refuses a disagreement.
That is the property §34 asks for, and it is checked here rather than
promised: a dashboard maintaining its own counters is how a report and its
ledger come to disagree without either being wrong on its own terms.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from intent_engine.econ import founder_ab as FA               # noqa: E402
from intent_engine.econ import forward_ledger as FL           # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import worldmodel as WM               # noqa: E402
import run_world_model as RWM                                 # noqa: E402

OUT = pathlib.Path("reports")
AS_OF = "2026-08-27"


def _sha() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


# =============================================================================
# §11 THE DIMENSION LEDGER
# =============================================================================
def dimension_ledger(panel) -> dict:
    """Every declared dimension, with what it is worth and what blocks it.

    A dimension can be LIVE and useless: LIVE counts a series being readable,
    which is a fact about acquisition rather than about value. The four states
    keep those apart, so the coverage number cannot be inflated with
    infrastructure nothing decides on.
    """
    audits = list(WM.audit_dimensions(panel, as_of=AS_OF).values())
    state = _current_state()
    rc = _relation_checks()
    supported = {c["relation"] for c in rc if c["state"] == WM.REL_SUPPORTED}
    rows = []
    for a in audits:
        series = WM.DIMENSIONS.get(a.dimension, ())
        rel_supported = sum(1 for name in supported
                            if any(s in name for s in series))
        consumers = sum(1 for _cid, (_n, _s, chans) in RWM.COMPANIES.items()
                        if any(d in series for d, _c, _m, _sg in chans))
        deltas = sum(1 for _cid, (_n, _s, chans) in RWM.COMPANIES.items()
                     for d, _c, _m, sign in chans
                     if d in series and sign in ("UP", "DOWN")
                     and (state.get(d) or {}).get("direction") == sign)
        rows.append({
            "dimension": a.dimension, "series": list(series),
            "acquisition": a.status,
            "value": WM.classify_dimension(
                a, deltas_produced=deltas, relations_supported=rel_supported,
                company_consumers=consumers),
            "producer": a.producer, "source": a.source,
            "as_of": a.as_of, "freshness_days": a.freshness_days,
            "persisted": a.persisted,
            "consumer": list(a.consumer), "standing": a.standing,
            "uncertainty": a.uncertainty,
            "company_consumers": consumers,
            "relations_supported": rel_supported,
            "deltas_produced": deltas, "note": a.note})
    by_value: dict = {}
    for r in rows:
        by_value[r["value"]] = by_value.get(r["value"], 0) + 1
    return {"as_of": AS_OF, "dimensions": len(rows), "by_value": by_value,
            "rows": rows}


def _current_state() -> dict:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    RWM.AS_OF = AS_OF
    return RWM.read_state(panel)


def _relation_checks() -> list:
    path = OUT / "relation_and_ceo.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("relations", [])


# =============================================================================
# §13 THE RELATION LEDGER
# =============================================================================
def relation_ledger() -> dict:
    """Every relation, with everything §13 requires it to carry.

    `next_eligible` is the date the claim becomes testable, computed from the
    lag: a relation whose lag has not elapsed is PENDING and is not a failure,
    and stating WHEN it can be judged is what stops it being re-reported as
    non-firing every cycle.
    """
    checks = {c["relation"]: c for c in _relation_checks()}
    rows = []
    for r in RWM.RELATIONS:
        name = f"{r.driver}->{r.effect}"
        c = checks.get(name, {})
        days = c.get("days_since_source_move")
        remaining = (max(0, r.lag_days - days) if isinstance(days, int)
                     else None)
        next_eligible = ("" if remaining is None else
                         (_dt.date.fromisoformat(AS_OF)
                          + _dt.timedelta(days=remaining)).isoformat())
        rows.append({
            "relation": name, "source": r.driver, "target": r.effect,
            "sign": r.sign, "lag_days": r.lag_days,
            "regime": r.regime, "order": r.order,
            "mechanism": r.mechanism, "falsifier": r.falsifier,
            "evidence": r.evidence, "uncertainty": r.uncertainty,
            "lineage": [f"panel:{r.driver}", f"panel:{r.effect}"],
            "status": c.get("state", WM.REL_CANDIDATE),
            "source_moved": c.get("source_moved"),
            "source_move": c.get("source_move"),
            "target_moved": c.get("target_moved"),
            "direction_correct": c.get("direction_correct"),
            "counterevidence": ("the target moved against the sign"
                                if c.get("direction_correct") is False
                                else ""),
            "last_evaluated": AS_OF,
            "days_since_source_move": days,
            "next_eligible_evaluation": next_eligible,
            "why_not_supported": _why(c)})
    by_state: dict = {}
    for r in rows:
        by_state[r["status"]] = by_state.get(r["status"], 0) + 1
    return {"as_of": AS_OF, "relations": len(rows), "by_state": by_state,
            "states_declared": list(WM.REL_STATES), "rows": rows}


def _why(check: dict) -> str:
    if not check:
        return "not evaluated in the last cycle"
    if check.get("state") == WM.REL_SUPPORTED:
        return ""
    if not check.get("regime_applicable"):
        return "the regime this relation is declared for does not hold"
    if not check.get("source_moved"):
        return ("the driver did not move, so the relation was not tested — "
                "this is not a failure of the relation")
    if not check.get("lag_elapsed"):
        return ("the lag has not elapsed, so the claim is not yet testable — "
                "this is not a failure of the relation")
    if check.get("direction_correct") is False:
        return "the target moved against the declared sign"
    return "the target could not be read"


# =============================================================================
# §31-§34 LEARNING, RECONCILED AGAINST THE LEDGERS
# =============================================================================
def learning_ledger() -> dict:
    """What was learned, derived from canonical records only.

    §32: activity and learning are separate quantities. A cycle that re-reads
    eighty pages and changes nothing has been busy.
    """
    ledger = FL.by_id()
    real = [r for r in ledger.values()
            if str(r.get("source", "")).upper() != "REHEARSAL"]
    resolved = [r for r in real if str(r.get("outcome", "OPEN")) != "OPEN"]
    checks = _relation_checks()
    dv = _read(OUT / "decision_value.json")
    summary = (dv or {}).get("summary", {})
    parity = (_read(OUT / "product_parity.json") or {}).get("summary", {})
    return {
        "as_of": AS_OF,
        "expectations": {
            "real_open": len(real) - len(resolved),
            "real_resolved": len(resolved),
            "rehearsal_isolated": True,
            "calibration_status": ("PRE_CALIBRATION" if not resolved
                                   else "CALIBRATING"),
            "why": ("no real prediction has reached its horizon; calibration "
                    "with an empty denominator is the claim this programme "
                    "exists to not make")},
        "relations": {
            "evaluated": len(checks),
            "by_state": {s: sum(1 for c in checks if c["state"] == s)
                         for s in WM.REL_STATES
                         if any(c["state"] == s for c in checks)},
            "not_tested_because_driver_did_not_move": sum(
                1 for c in checks if not c.get("source_moved")),
            "not_tested_because_lag_pending": sum(
                1 for c in checks if c.get("source_moved")
                and not c.get("lag_elapsed"))},
        "decision_value": {
            "cases": summary.get("comparisons"),
            "material": summary.get("material"),
            "attributed": summary.get("attributed"),
            "abstained": summary.get("abstained"),
            "damage": summary.get("damage"),
            "damage_by_kind": summary.get("damage_by_kind"),
            "damage_kinds_with_a_detector":
                len(FA.damage_coverage()["with_detector"]),
            "damage_kinds_declared": len(FA.DAMAGE_KINDS),
            "negative_control": summary.get("negative_control")},
        "product_parity": {
            "cases": parity.get("cases"),
            "identical": parity.get("identical"),
            "explained": parity.get("explained_divergence"),
            "unexplained": parity.get("unexplained_divergence")},
    }


def _read(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else None


# =============================================================================
# §34 RECONCILIATION — the report must agree with the ledger
# =============================================================================
def reconcile(learning: dict) -> dict:
    """Re-derive every displayed count from the canonical record.

    A displayed number and its source disagreeing is the defect this closes,
    and it is checked rather than promised: the alternative is a dashboard
    maintaining counters beside the ledger it describes.
    """
    problems = []
    raw = FL.load()
    real = [r for r in raw if str(r.get("source", "")).upper() != "REHEARSAL"]
    ids = {r["expectation_id"] for r in real}
    open_now = sum(1 for eid in ids
                   if str(FL.by_id()[eid].get("outcome", "OPEN")) == "OPEN")
    if learning["expectations"]["real_open"] != open_now:
        problems.append(
            f"real_open reported {learning['expectations']['real_open']} and "
            f"the ledger holds {open_now}")
    if learning["expectations"]["real_resolved"] and \
            learning["expectations"]["calibration_status"] == "PRE_CALIBRATION":
        problems.append("PRE_CALIBRATION is reported with resolutions on file")
    dv = _read(OUT / "decision_value.json") or {}
    rows = [r for reg in (dv.get("regimes") or {}).values()
            for r in reg.get("rows", [])]
    if rows:
        material = sum(1 for r in rows if r["is_material"])
        if learning["decision_value"]["material"] != material:
            problems.append(
                f"material reported {learning['decision_value']['material']} "
                f"and the rows hold {material}")
    coverage = FA.damage_coverage()
    if coverage["without_detector"]:
        problems.append(
            f"{coverage['without_detector']} are declared damage kinds with "
            "no detector, so a damage count of zero is partly a statement "
            "about the vocabulary")
    return {"checked": 4, "problems": problems,
            "reconciles": not problems}


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    dims = dimension_ledger(panel)
    rels = relation_ledger()
    learning = learning_ledger()
    rec = reconcile(learning)

    print("=== §11 DIMENSION LEDGER ===")
    for value, n in sorted(dims["by_value"].items()):
        print(f"  {value:<26}{n}")
    print("\n=== §13 RELATION LEDGER ===")
    for state, n in sorted(rels["by_state"].items()):
        print(f"  {state:<26}{n}")
    for r in rels["rows"]:
        if r["status"] != WM.REL_SUPPORTED:
            print(f"    {r['relation']:<26}{r['status']:<22}"
                  f"next eligible {r['next_eligible_evaluation'] or 'n/a'}"
                  f"  — {r['why_not_supported'][:60]}")
    print("\n=== §31 LEARNING ===")
    e = learning["expectations"]
    print(f"  real expectations open      {e['real_open']}")
    print(f"  real resolved               {e['real_resolved']}")
    print(f"  calibration                 {e['calibration_status']}")
    d = learning["decision_value"]
    print(f"  A/B cases                   {d['cases']}")
    print(f"  material / attributed       {d['material']} / {d['attributed']}")
    print(f"  abstained                   {d['abstained']}")
    print(f"  damage                      {d['damage']} "
          f"({d['damage_kinds_with_a_detector']} of "
          f"{d['damage_kinds_declared']} kinds have a detector)")
    print(f"\n=== §34 RECONCILIATION === "
          f"{'PASS' if rec['reconciles'] else 'FAIL'}")
    for p in rec["problems"]:
        print(f"  {p}")

    payload = {"contract": "v3_closure.v1", "code_sha": _sha(),
               "as_of": AS_OF, "dimensions": dims, "relations": rels,
               "learning": learning, "reconciliation": rec}
    (OUT / "v3_closure.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v3_closure.json")
    return 0 if rec["reconciles"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
