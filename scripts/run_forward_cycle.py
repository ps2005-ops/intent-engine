"""§3/§5/§10: one forward cycle — inspect, resolve what can resolve, report.

WHAT A CYCLE DOES
-----------------
    1. read every expectation and place it in the state machine
    2. attach a machine-readable resolution contract where one is missing,
       as a SUPERSEDING record that changes nothing else
    3. resolve everything ELIGIBLE
    4. score the BASE/AUGMENTED tournament on resolved pairs only
    5. report the calibration rung and what it permits

None of the twelve real expectations comes due before 2027-02. That is not a
reason to ship an unexercised resolver: the day the first one is due is the
worst possible day to discover the resolver is wrong, and the property that
makes the record valuable — that nobody could have fitted it — is destroyed by
fixing it afterwards.

So the cycle also runs a REHEARSAL on backdated expectations built from the
real panel. They live in their own file, are labelled REHEARSAL in every
record, and are never mixed into the real ledger or the calibration ladder.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import forward_engine as FE            # noqa: E402
from intent_engine.econ import forward_ledger as FL            # noqa: E402
from intent_engine.econ import panel as PN                     # noqa: E402
from intent_engine.econ import release as RL                   # noqa: E402

OUT = pathlib.Path("reports")
REHEARSAL = OUT / "forward_rehearsal.jsonl"
TODAY = "2026-08-27"

#: quantity fragment -> the series that resolves it.
SERIES_FOR = {"DRCCLACBS": "DRCCLACBS", "HOUST": "HOUST", "INDPRO": "INDPRO",
              "UNRATE": "UNRATE", "PCEC96": "PCEC96"}


def series_of(record: dict) -> str:
    q = record.get("quantity", "")
    for frag, sid in SERIES_FOR.items():
        if q.startswith(frag):
            return sid
    return ""


def derive_contract(record: dict, panel) -> dict:
    """The machine-readable form of the prose rule the expectation opened with.

    DERIVED, NOT CHOSEN. The series comes from the quantity, the horizon and
    cutoff from the record, and the baseline is the latest period of that
    series knowable at the cutoff. Nothing here is a decision that could have
    gone another way after seeing an outcome, which is why appending it does
    not compromise the record.

    The vintage policy is LATEST_REVISION because the prose rule these
    expectations opened with says "the ALFRED vintage available N days from
    now" -- the value in force at resolution time, not the first print.
    Reading it as FIRST_RELEASE would score a different prediction.
    """
    sid = series_of(record)
    if not sid:
        return {}
    hist = panel.history(sid, as_of=record["information_cutoff"], lookback=2)
    if not hist:
        return {}
    return FE.ResolutionContract(
        series_id=sid, baseline_period=hist[-1][0],
        direction=record.get("expected_direction", "UP"),
        horizon_days=record["horizon_days"],
        vintage_policy=FE.LATEST_REVISION,
        resolves_from=record["expires_at"]).as_dict()


def cycle(path, panel, *, at=TODAY, label="REAL"):
    recs = FL.by_id(path)
    states, added = {}, []
    for eid, r in sorted(recs.items()):
        if "resolution_contract" not in r:
            con = derive_contract(r, panel)
            if con:
                added.append({
                    **r, "resolution_contract": con,
                    "superseding_note": (
                        "a machine-readable resolution contract, DERIVED from "
                        "the prose rule this expectation opened with. Series "
                        "from the quantity, baseline from the last period "
                        "knowable at the cutoff, vintage policy "
                        "LATEST_REVISION because the prose says 'the vintage "
                        "available N days from now'. Nothing else changed.")})
    if added:
        FL.append(added, path=path)
        recs = FL.by_id(path)
    for eid, r in sorted(recs.items()):
        states[eid] = FE.state_of(r, at=at, panel=panel)

    resolutions = []
    for eid, r in sorted(recs.items()):
        if states[eid] != FE.ELIGIBLE:
            continue
        res = FE.resolve_one(r, panel=panel, at=at)
        if res is not None:
            FE.assert_transition(FE.ELIGIBLE, FE.RESOLVED)
            resolutions.append(res)
    if resolutions:
        FL.append(resolutions, path=path)
        recs = FL.by_id(path)
        for eid, r in sorted(recs.items()):
            states[eid] = FE.state_of(r, at=at, panel=panel)

    by_state = {}
    for s in states.values():
        by_state[s] = by_state.get(s, 0) + 1
    return {"label": label, "at": at, "expectations": len(recs),
            "contracts_added": len(added), "resolved_this_cycle":
                len(resolutions), "by_state": by_state,
            "states": states,
            "ladder": FE.ladder_stage(list(recs.values())),
            "tournament": FE.tournament(list(recs.values()))}


def build_rehearsal(panel) -> int:
    """Backdated BASE/AUGMENTED pairs that the real panel CAN resolve.

    Cutoffs in 2022-2023 with 180-day horizons, so every one is due and
    resolvable today. Their whole purpose is to drive the resolver, the
    tournament and the ladder through real transitions before the real
    expectations come due.
    """
    if REHEARSAL.exists():
        return 0
    import hashlib
    recs = []
    for cutoff in ("2022-03-15", "2022-09-15", "2023-03-15", "2023-09-15",
                   "2024-03-15", "2024-09-15"):
        for sid, horizon in (("INDPRO", 180), ("UNRATE", 180),
                             ("HOUST", 180)):
            hist = panel.history(sid, as_of=cutoff, lookback=2)
            if not hist:
                continue
            con = FE.ResolutionContract(
                series_id=sid, baseline_period=hist[-1][0], direction="UP",
                horizon_days=horizon, vintage_policy=FE.LATEST_REVISION,
                resolves_from=(_dt.date(*map(int, cutoff.split("-")))
                               + _dt.timedelta(days=horizon)).isoformat())
            for model, p in (("BASE", 0.55), ("AUGMENTED", 0.60)):
                eid = "rh-" + hashlib.sha256(
                    f"{sid}{cutoff}{horizon}{model}".encode()).hexdigest()[:14]
                recs.append({
                    "expectation_id": eid, "label": "REHEARSAL",
                    "model": model, "family": f"{sid}_{horizon}d",
                    "quantity": f"{sid}/{model}",
                    "expected_direction": "UP", "confidence": p,
                    "information_cutoff": cutoff,
                    "horizon_days": horizon,
                    "expires_at": con.resolves_from,
                    "resolution_rule": (
                        f"{sid} higher at the horizon than at "
                        f"{con.baseline_period}, under {con.vintage_policy}"),
                    "resolution_contract": con.as_dict(),
                    "outcome": FE.OPEN,
                    "note": ("REHEARSAL. Never enters the real ledger, the "
                             "real tournament or the real calibration "
                             "ladder. It exists to drive the resolver "
                             "through real transitions before the real "
                             "expectations come due.")})
    FL.append(recs, path=REHEARSAL)
    return len(recs)


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")

    print("=== REAL FORWARD CYCLE ===")
    real = cycle(FL.DEFAULT_PATH, panel, label="REAL")
    print(f"  expectations {real['expectations']}  contracts added "
          f"{real['contracts_added']}  resolved this cycle "
          f"{real['resolved_this_cycle']}")
    print(f"  by state {json.dumps(real['by_state'])}")
    print(f"  ladder   {real['ladder']['stage']} — "
          f"{real['ladder']['may_report']}")
    print(f"  gap      {json.dumps(real['ladder']['gap_to_next'])} to "
          f"{real['ladder']['next_stage']}")
    print(f"  pairs    {real['tournament']['pairs']} matched, "
          f"{real['tournament']['resolved_pairs']} resolved, "
          f"{real['tournament']['unmatched']} unmatched — "
          f"{real['tournament']['verdict']}")

    print("\n=== REHEARSAL (backdated; never mixed into the real record) ===")
    n = build_rehearsal(panel)
    print(f"  built {n} rehearsal expectations" if n else
          "  rehearsal ledger already present")
    reh = cycle(REHEARSAL, panel, label="REHEARSAL")
    print(f"  expectations {reh['expectations']}  resolved this cycle "
          f"{reh['resolved_this_cycle']}")
    print(f"  by state {json.dumps(reh['by_state'])}")
    print(f"  ladder   {reh['ladder']['stage']}")
    print(f"  sample   {reh['ladder']['sample']['headline']}")
    t = reh["tournament"]
    print(f"  tournament: {t['resolved_pairs']} resolved pairs — "
          f"{t['verdict']}")
    if t.get("base"):
        print(f"    BASE      {json.dumps(t['base'])}  "
              f"correct {t['base_correct']}/{t['resolved_pairs']}")
        print(f"    AUGMENTED {json.dumps(t['augmented'])}  "
              f"correct {t['augmented_correct']}/{t['resolved_pairs']}")
        print(f"    the rehearsal's probabilities are FIXED CONSTANTS (0.55 "
              f"and 0.60), not model output. This proves the machinery, not "
              f"a model.")

    payload = {"real": real, "rehearsal": reh,
               "note": ("the rehearsal exists to exercise the resolver, the "
                        "state machine, the tournament and the ladder "
                        "through real transitions. Its scores are about the "
                        "machinery and are never reported as evidence about "
                        "any model.")}
    (OUT / "forward_cycle.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/forward_cycle.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
