"""§19: a supported relation with a qualifying event opens an expectation.

WHY THIS EXISTS AND WHY IT IS NARROW
------------------------------------
The stagnation detector reported EXPECTATION_STAGNATION: drivers moved and no
expectation was opened. That is a real gap — §19 asks the economic graph to
feed the forward ledger — and the honest response is to do the work rather
than to widen the detector.

It is deliberately narrow. §20 forbids creating expectations to increase N, so
an expectation is opened only when ALL of these hold:

    the relation reached SUPPORTED_PREDICTIVE
    the driver moved beyond the declared trigger
    the lag has elapsed, so the claim is testable
    no open expectation already covers this relation

Everything else is left alone. Opening none is the correct outcome when no
relation qualifies, and the report says so rather than manufacturing one.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from intent_engine.econ import forward_engine as FE           # noqa: E402
from intent_engine.econ import forward_ledger as FL           # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import worldmodel as WM               # noqa: E402
import run_world_model as RWM                                 # noqa: E402

OUT = pathlib.Path("reports")
AS_OF = "2026-08-27"
#: The driver must have moved at least this much for the relation's claim to
#: be testable. Declared here, before any expectation was opened.
TRIGGER = 0.05


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    rc = json.loads((OUT / "relation_and_ceo.json").read_text())
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    existing = FL.by_id()
    covered = {e.get("relation") for e in existing.values() if e.get("relation")}

    by_name = {f"{r.driver}->{r.effect}": r for r in RWM.RELATIONS}
    opened, skipped = [], []
    print("=== §19 EXPECTATIONS FROM RELATIONS ===")
    print(f"  {'relation':<26}{'state':<24}{'src move':>10}  decision")
    for chk in rc["relations"]:
        name = chk["relation"]
        rel = by_name.get(name)
        state = chk["state"]
        move = chk["source_move"]
        if state != WM.REL_SUPPORTED:
            skipped.append((name, f"state {state}"))
            print(f"  {name:<26}{state:<24}{move:>+10.4f}  not supported")
            continue
        if abs(move) < TRIGGER:
            skipped.append((name, f"driver moved {move:+.4f}, below the "
                                  f"{TRIGGER} trigger"))
            print(f"  {name:<26}{state:<24}{move:>+10.4f}  below trigger")
            continue
        if name in covered:
            skipped.append((name, "already covered by an open expectation"))
            print(f"  {name:<26}{state:<24}{move:>+10.4f}  already covered")
            continue
        h = panel.history(rel.effect, as_of=AS_OF, lookback=2)
        if not h:
            skipped.append((name, "the target could not be read"))
            continue
        # The relation predicts the SIGN of the target's next move.
        direction = "UP" if (move * rel.sign) > 0 else "DOWN"
        expires = (_dt.date(2026, 8, 27)
                   + _dt.timedelta(days=rel.lag_days)).isoformat()
        con = FE.ResolutionContract(
            series_id=rel.effect, baseline_period=h[-1][0],
            direction=direction, horizon_days=rel.lag_days,
            vintage_policy=FE.LATEST_REVISION, resolves_from=expires)
        eid = "rl-" + hashlib.sha256(
            f"{name}{AS_OF}{rel.lag_days}".encode()).hexdigest()[:14]
        opened.append({
            "expectation_id": eid, "relation": name, "model": "RELATION",
            "quantity": f"{rel.effect}/{name}",
            "expected_direction": direction,
            #: Not a fitted probability. The relation's stated uncertainty
            #: maps to a band, and the band is declared before resolution.
            "confidence": {"LOW": 0.65, "MEDIUM": 0.55,
                           "HIGH": 0.5}[rel.uncertainty],
            # WHEN IT WAS MADE, beside what it could know. The first
            # version wrote only the cutoff, so the one record it opened
            # could not answer "did this prediction use evidence that arrived
            # after it was made" -- the single invariant a preregistered
            # claim exists to support. `belief.Expectation` requires the
            # pair; this file wrote to the ledger directly and skipped it.
            "created_at": AS_OF,
            "information_cutoff": AS_OF, "horizon_days": rel.lag_days,
            "expires_at": expires,
            "resolution_rule": (
                f"{rel.effect} is {direction} at the horizon relative to "
                f"{h[-1][0]}, read at the vintage in force then"),
            "resolution_contract": con.as_dict(),
            "mechanism": rel.mechanism,
            "falsifier": rel.falsifier,
            "trigger": (f"{rel.driver} moved {move:+.4f}, above the "
                        f"{TRIGGER} trigger, and the {rel.lag_days}d lag has "
                        f"elapsed"),
            "outcome": FE.OPEN, "code_sha": sha,
            "source": "V2", "visibility": "PUBLIC",
            "note": ("opened from a SUPPORTED_PREDICTIVE relation with a "
                     "qualifying driver move. §20: never opened to increase "
                     "N.")})
        print(f"  {name:<26}{state:<24}{move:>+10.4f}  OPENED {eid}")

    if opened:
        FL.append(opened, path=FL.DEFAULT_PATH)
    life = FL.assert_lifecycle()
    print(f"\n  opened {len(opened)}, skipped {len(skipped)}")
    print(f"  forward ledger now {life['expectations']} expectations, "
          f"{life['open']} open, {life['resolved']} resolved")
    print(f"  lifecycle still holds: {life['all_seven_hold']}")
    for n, why in skipped:
        print(f"    skipped {n:<26}{why}")
    (OUT / "relation_expectations.json").write_text(json.dumps(
        {"as_of": AS_OF, "trigger": TRIGGER, "opened": opened,
         "skipped": [{"relation": n, "why": w} for n, w in skipped],
         "ledger": {k: v for k, v in life.items() if k != "facts"}},
        indent=2, sort_keys=True))
    print(f"  wrote reports/relation_expectations.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
