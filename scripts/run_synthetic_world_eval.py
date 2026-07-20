#!/usr/bin/env python
"""T009 — synthetic-world reasoning eval runner (founder-approved
2026-07-19, HIGH priority). Two modes:

--offline (default): deterministic, ZERO model calls. Generates the world
  set, enforces every leakage wall, runs the matcher-level eval, derives
  the enum expressiveness map, and writes reports/synthetic_worlds_eval.md
  (+ .json). Runs anywhere, including the sandbox.

--live: the reasoning leg. For each world, ONE isolated extraction call
  (the frozen, gate-verified prompt from simulator/mechanism_section —
  used READ-ONLY; this script asserts its sha256 is byte-identical to the
  frozen value BEFORE any call and refuses to run otherwise) maps the
  fictional narrative -> conditions -> deterministic matcher. Scored by
  the same scorer as the offline leg. MAC ONLY (sandbox has no Anthropic
  egress). Budget: <=100 calls/run (89 worlds -> ~$1.78 at the standing
  $0.02/call over-estimate); the run PARKS if the world count exceeds the
  cap. No ledger writes, no scheduling (human-wired only), no retries.

Honest framing caveat (recorded, not patched): the frozen extraction
prompt says "business decision's description"; these narratives are
situation briefs. Editing the prompt would re-open the Task 3 gate — so
the mismatch is documented instead. If extraction quality on briefs is
poor, that is a FINDING, not a bug to prompt-patch around.

Usage: python scripts/run_synthetic_world_eval.py [--offline | --live]
       [--seed 20260719] [--max-live-calls 100]
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core import synthetic_worlds as sw  # noqa: E402

REPORT_DIR = REPO_ROOT / "reports"
OFFLINE_MD = REPORT_DIR / "synthetic_worlds_eval.md"
OFFLINE_JSON = REPORT_DIR / "synthetic_worlds_eval.json"
LIVE_MD = REPORT_DIR / "synthetic_worlds_eval_live.md"
LIVE_JSON = REPORT_DIR / "synthetic_worlds_eval_live.json"

# The gate-verified simulator extraction prompt's sha256 (recorded at the
# batch-1 merge, re-verified at batches 2-3). The live leg refuses to run
# against anything else — prompts are frozen; this harness only READS.
FROZEN_EXTRACTION_PROMPT_SHA256 = (
    "2067d21a0d2b36441708fa608dce8e0dcce05f64a53b2620b6313f50bd2205ca"
)

DEFAULT_MAX_LIVE_CALLS = 100
ESTIMATED_COST_PER_CALL_USD = 0.02  # same deliberate over-estimate as the daily runner


def _aggregate(results):
    by_type = {}
    for r in results:
        by_type.setdefault(r.world_type, []).append(r)
    agg = {}
    for wtype, rs in sorted(by_type.items()):
        agg[wtype] = {
            "n": len(rs),
            "identified": sum(1 for r in rs if r.identified),
            "unique_top": sum(1 for r in rs if r.unique_top),
            "tier_sizes": dict(sorted(Counter(r.tier_size for r in rs).items())),
        }
    return agg


def _render_offline_report(worlds, results, emap, seed) -> str:
    agg = _aggregate(results)
    unique = sorted(k for k, v in emap.items() if len(v) == 1)
    tied_classes = {}
    for k, v in emap.items():
        if len(v) > 1:
            tied_classes.setdefault(v, []).append(k)

    lines = [
        "# Synthetic-world reasoning eval — OFFLINE leg (matcher-level)",
        "",
        f"*Generated {date.today().isoformat()}, seed {seed}, "
        f"{len(worlds)} worlds ({agg.get('single', {}).get('n', 0)} single, "
        f"{agg.get('mixed', {}).get('n', 0)} mixed, "
        f"{agg.get('control', {}).get('n', 0)} control). Deterministic; "
        "0 model calls; all leakage walls enforced at generation time.*",
        "",
        sw.DIAGNOSTIC_DISCLAIMER,
        "",
        "## What the offline leg does and does not show",
        "",
        "Planting a mechanism's exact trigger set and running the",
        "deterministic matcher recovers that mechanism BY CONSTRUCTION —",
        "the interesting quantity is not the recovery rate but the SIZE of",
        "the tied top class: how sharply the frozen enum can discriminate",
        "the constructed truth from its neighbors on its own best evidence.",
        "The reasoning test proper is the LIVE leg (narrative -> extraction",
        "-> matcher), which is staged for the Mac.",
        "",
        "## Results by world type",
        "",
    ]
    for wtype, a in agg.items():
        lines.append(
            f"- **{wtype}** (n={a['n']}): constructed truth recovered in "
            f"{a['identified']}/{a['n']}; uniquely (tied with nothing) in "
            f"{a['unique_top']}/{a['n']}; top-tier size distribution {a['tier_sizes']}."
        )
    lines += [
        "",
        "## Enum expressiveness map (the extracted learning)",
        "",
        f"Uniquely identifiable mechanisms — {len(unique)}/23: "
        + ", ".join(f"`{m}`" for m in unique) + ".",
        "",
        "Tied classes (the frozen enum cannot separate these on the tied",
        "members' own best evidence; supersets tie because overlap is",
        "capped by what is observed):",
        "",
    ]
    for cls, members in sorted(tied_classes.items()):
        lines.append(f"- {{{', '.join(f'`{c}`' for c in cls)}}}")
    lines += [
        "",
        "Relevance to the (deferred) enum decision — evidence, not a",
        "recommendation: candidate #1 (`falling_price_level`) would split",
        "the leverage/deflation tie; #4 (`collateral_value_dependence`) and",
        "#5 (`opaque_securitized_exposure`) would each split a documented",
        "credit-side tie; the drawdown trio stays a deliberate dual-match",
        "class per the founder's ratified decisions.",
        "",
        "## Live leg",
        "",
        "STAGED, not run (sandbox has no Anthropic egress). Command:",
        "`python scripts/run_synthetic_world_eval.py --live` on the Mac.",
        f"Budget: {len(worlds)} calls ≈ "
        f"${len(worlds) * ESTIMATED_COST_PER_CALL_USD:.2f} at the standing "
        "over-estimate; capped at "
        f"{DEFAULT_MAX_LIVE_CALLS} calls; prompt sha256 asserted before any call.",
    ]
    report = "\n".join(lines) + "\n"
    sw.assert_report_language_walls(report)
    return report


def run_offline(seed: int) -> int:
    worlds = sw.generate_worlds(seed=seed)
    sw.assert_leakage_walls(worlds)
    sw.assert_fictional_entities(worlds)
    results = sw.run_offline_eval(worlds)
    emap = sw.enum_expressiveness_map()
    report = _render_offline_report(worlds, results, emap, seed)
    REPORT_DIR.mkdir(exist_ok=True)
    OFFLINE_MD.write_text(report)
    OFFLINE_JSON.write_text(json.dumps({
        "seed": seed,
        "generated": date.today().isoformat(),
        "aggregate": _aggregate(results),
        "expressiveness_map": {k: list(v) for k, v in emap.items()},
        "results": [r._asdict() for r in results],
    }, indent=1))
    print(f"OFFLINE eval: {len(worlds)} worlds, walls PASS, report -> {OFFLINE_MD.name}")
    agg = _aggregate(results)
    for wtype, a in agg.items():
        print(f"  {wtype}: identified {a['identified']}/{a['n']}, unique-top {a['unique_top']}/{a['n']}")
    return 0


def run_live(seed: int, max_calls: int, client=None) -> int:
    from intent_engine.simulator import mechanism_section as ms

    actual = hashlib.sha256(ms.EXTRACTION_SYSTEM_PROMPT.encode()).hexdigest()
    if actual != FROZEN_EXTRACTION_PROMPT_SHA256:
        print("PARKED: extraction prompt sha256 mismatch — prompts are frozen; "
              "refusing to run the live leg against an unverified prompt.")
        return 1

    worlds = sw.generate_worlds(seed=seed)
    sw.assert_leakage_walls(worlds)
    if len(worlds) > max_calls:
        print(f"PARKED: {len(worlds)} worlds exceeds the {max_calls}-call cap. "
              "Raising the cap is a human decision, not this script's.")
        return 1

    client = client or ms.LLMClient(model=ms.FAST_MODEL)
    rows, calls = [], 0
    for w in worlds:
        predicted = ms.extract_decision_trigger_conditions(w.narrative, client=client)
        calls += 1
        result = sw.evaluate_world_conditions(w, predicted)
        planted, pred = set(w.planted_conditions), set(predicted)
        rows.append({
            "world_id": w.world_id, "world_type": w.world_type,
            "planted": sorted(planted), "predicted": sorted(pred),
            "condition_precision": (len(planted & pred) / len(pred)) if pred else None,
            "condition_recall": (len(planted & pred) / len(planted)) if planted else None,
            "hallucinated": sorted(pred - planted),
            "missed": sorted(planted - pred),
            **result._asdict(),
        })

    singles = [r for r in rows if r["world_type"] == "single"]
    mixed = [r for r in rows if r["world_type"] == "mixed"]
    controls = [r for r in rows if r["world_type"] == "control"]
    clean_controls = sum(1 for r in controls if not r["predicted"])

    lines = [
        "# Synthetic-world reasoning eval — LIVE leg (extraction -> matcher)",
        "",
        f"*Run {date.today().isoformat()}, seed {seed}, {calls} extraction "
        f"calls (≈${calls * ESTIMATED_COST_PER_CALL_USD:.2f} estimated). "
        "Frozen prompt sha256 verified before the first call.*",
        "",
        sw.DIAGNOSTIC_DISCLAIMER,
        "",
        f"- single worlds: constructed truth recovered in "
        f"{sum(1 for r in singles if r['identified'])}/{len(singles)}",
        f"- mixed worlds: both mechanisms recovered in "
        f"{sum(1 for r in mixed if r['identified'])}/{len(mixed)}",
        f"- control worlds (healthy, condition-free): clean silence in "
        f"{clean_controls}/{len(controls)} — hallucinated conditions on the "
        "rest are the key negative finding, listed in the JSON.",
        "",
        "Per-world detail: synthetic_worlds_eval_live.json.",
    ]
    report = "\n".join(lines) + "\n"
    sw.assert_report_language_walls(report)
    REPORT_DIR.mkdir(exist_ok=True)
    LIVE_MD.write_text(report)
    LIVE_JSON.write_text(json.dumps({"seed": seed, "run": date.today().isoformat(),
                                     "calls": calls, "rows": rows}, indent=1))
    print(f"LIVE eval: {calls} calls, report -> {LIVE_MD.name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", default=True)
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--seed", type=int, default=sw.DEFAULT_SEED)
    parser.add_argument("--max-live-calls", type=int, default=DEFAULT_MAX_LIVE_CALLS)
    args = parser.parse_args(argv)
    if args.live:
        return run_live(args.seed, args.max_live_calls)
    return run_offline(args.seed)


if __name__ == "__main__":
    sys.exit(main())
