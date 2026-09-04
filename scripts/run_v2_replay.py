"""§23: replay every discovered episode, including the ones we got wrong.

WHAT A REPLAY IS FOR HERE
-------------------------
Not to show the system working. The episodes were DISCOVERED by the
contemporaneous classifier, the forecasts were made on blocked folds with
purging, and a majority of them are wrong -- which is the point. A replay
that only surfaced the episodes the model called correctly would be a
demonstration, and §23 says explicitly that the system must show failures
too.

WHAT EACH ROW CARRIES
    the regime as read AT THE TIME, from the walled panel
    the base and augmented probabilities
    the collective-state contribution (augmented minus base)
    what actually happened
    the Brier of each, so "confidently wrong" is distinguishable from
      "uncertain and wrong"
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import episodes as EPI               # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402

OUT = pathlib.Path("reports")


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    results = {}
    for arm in ("MODERN", "DEEP"):
        p = OUT / f"v2_paired_{arm.lower()}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        gated = [r for r in rows if r.get("gate_passed")] or rows
        origins = sorted({r["origin"] for r in rows})
        readings = {r.as_of: r for r in RG.classify_many(panel, origins)}
        eps = EPI.discover(list(readings.values()))

        print(f"\n{'=' * 78}\n=== {arm}: {len(eps)} episodes replayed "
              f"({len(gated)} scored forecasts)\n{'=' * 78}")
        print(f"  {'episode':<12}{'window':<26}{'n':>5}{'base':>8}{'aug':>8}"
              f"{'contrib':>9}{'called':>8}  verdict")
        per_ep = []
        for e in eps:
            sel = [r for r in gated
                   if e.start_as_known <= r["origin"] <= e.end_as_known]
            if not sel:
                per_ep.append({**e.as_dict(), "n": 0,
                               "verdict": "NO_FORECASTS_IN_WINDOW"})
                print(f"  {e.episode_id:<12}"
                      f"{e.start_as_known + '..' + e.end_as_known:<26}"
                      f"{0:>5}{'-':>8}{'-':>8}{'-':>9}{'-':>8}  "
                      f"NO_FORECASTS_IN_WINDOW")
                continue
            bb = sum((r["p_base"] - (1.0 if r["y"] else 0.0)) ** 2
                     for r in sel) / len(sel)
            ab = sum((r["p_aug"] - (1.0 if r["y"] else 0.0)) ** 2
                     for r in sel) / len(sel)
            called = sum(1 for r in sel
                         if (r["p_base"] >= 0.5) == r["y"]) / len(sel)
            contrib = bb - ab
            # FOUR OUTCOMES, not two. A model that was right while the
            # collective layer pushed it the wrong way has not been helped.
            if bb < 0.25 and contrib > 0:
                v = "BOTH_INFORMATIVE_LAYER_HELPED"
            elif bb < 0.25 and contrib <= 0:
                v = "BASE_INFORMATIVE_LAYER_HURT"
            elif bb >= 0.25 and contrib > 0:
                v = "BASE_UNINFORMATIVE_LAYER_HELPED"
            else:
                v = "BOTH_WRONG"
            per_ep.append({
                **e.as_dict(), "n": len(sel),
                "information_available_at": e.information_cutoff,
                "contemporaneous_regimes": list(e.regime_sequence),
                "base_brier": round(bb, 5), "augmented_brier": round(ab, 5),
                "collective_contribution": round(contrib, 5),
                "base_directional_calls_correct": round(called, 3),
                "verdict": v})
            print(f"  {e.episode_id:<12}"
                  f"{e.start_as_known + '..' + e.end_as_known:<26}"
                  f"{len(sel):>5}{bb:>8.4f}{ab:>8.4f}{contrib:>+9.5f}"
                  f"{called:>8.2f}  {v}")
        helped = sum(1 for x in per_ep
                     if x.get("collective_contribution", 0) > 0)
        scored = sum(1 for x in per_ep if x["n"])
        print(f"\n  the collective layer helped in {helped} of {scored} "
              f"replayed episodes")
        results[arm] = {"episodes": per_ep, "scored": scored,
                        "layer_helped": helped,
                        "reading": (
                            f"the layer improved the Brier in {helped} of "
                            f"{scored} episodes. On a coin flip you would "
                            f"expect about {scored / 2:.0f}; this is a "
                            "descriptive count, not a test -- the tests are "
                            "H3-H6 and none of them was supported.")}
    (OUT / "v2_replay.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v2_replay.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
