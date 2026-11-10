"""§2: freeze WORLD_MODEL_RESEARCH_V2 as a canonical, superseding-only record.

WHY A CHECKPOINT AND NOT A TAG
------------------------------
A git tag records the code. It does not record what the code CONCLUDED, and
the conclusion is the thing a later run has to beat. This writes the
scientific state -- verdicts, power, constructs, episodes, the one observed
signal, the open forward expectations -- into the append-only evaluation
registry, so a V3 that reports a better number has something specific to be
better than.

APPEND, NEVER REWRITE
---------------------
`evaluation_record.append` refuses a reused id. A checkpoint that could be
edited would become whatever the current run needed it to have been.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import evaluation_record as ER       # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402

OUT = pathlib.Path("reports")
CHECKPOINT = OUT / "world_model_research_v2.json"


def main() -> int:
    v2 = json.loads((OUT / "v2_experiment.json").read_text())
    mech = json.loads((OUT / "v2_mechanism.json").read_text())
    close = json.loads((OUT / "v2_closure.json").read_text())
    replay = json.loads((OUT / "v2_replay.json").read_text())
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()

    deep = v2["arms"]["DEEP"]
    payload = {
        "checkpoint_id": "WORLD_MODEL_RESEARCH_V2",
        "code_sha": sha,
        "panel_hash": v2["panel"]["content_hash"],
        "preregistration_hashes": {
            "V1": PR.declaration_hash(),
            "H2": PR.regime_hypothesis_hash(),
            "V2_H3_H6": PR.v2_hash()},
        "hypothesis_verdicts": close["hypothesis_verdicts"],
        "power": {arm: v2["arms"][arm]["sample"] for arm in v2["arms"]},
        "median_mde": {arm: (v2["arms"][arm].get("h3") or {}).get("mde")
                       for arm in v2["arms"]},
        "constructs": {arm: v2["arms"][arm]["constructs"] for arm in v2["arms"]},
        "baseline_gate_passing": {
            arm: v2["arms"][arm]["baseline_gate_passing_families"]
            for arm in v2["arms"]},
        "episodes": {arm: v2["arms"][arm]["episodes"] for arm in v2["arms"]},
        "observed_signal": {
            "claim": ("consumer sentiment leads housing starts by 6-8 months "
                      "and industrial production by 7-8 months"),
            "state": "OBSERVED",
            "not": ["PREDICTIVE", "CAUSAL", "PROMOTED"],
            "replicated_across_arms":
                close["world_model"]["replicated_across_arms"],
            "evidence": {
                arm: {k: v for k, v in
                      mech["arms"][arm]["temporal_order"].items()
                      if v["classification"] == "LEADING"}
                for arm in mech["arms"]}},
        "real_forward": {
            "opened": close["real_forward"]["opened"],
            "expectation_ids": [e["expectation_id"]
                                for e in close["real_forward"]["expectations"]]},
        "calibration": close["calibration"],
        "founder_integration": close["founder"],
        "replay": {arm: {"scored": replay[arm]["scored"],
                         "layer_helped": replay[arm]["layer_helped"]}
                   for arm in replay},
        "supersedes": None,
        "note": ("the state a V3 has to beat. Every verdict here was reached "
                 "with the episode-aware interval and a per-family baseline "
                 "gate; a later result that uses a looser estimator is not a "
                 "better result."),
    }
    CHECKPOINT.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                     default=str))

    existing = {e.evaluation_id for e in ER.load()}
    if "WORLD_MODEL_RESEARCH_V2" not in existing:
        s = deep["sample"]
        ER.append(ER.Evaluation(
            evaluation_id="WORLD_MODEL_RESEARCH_V2",
            supersedes="GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED_PHASES",
            method=ER.EPISODE_AWARE,
            reason=("the deep monthly arm, on the corrected panel with a "
                    "per-family baseline gate and episode-aware verdicts. "
                    "Supersedes V1 as the comparator: it is the same "
                    "question asked with roughly three times the independent "
                    "information."),
            delta=deep["h3"]["delta"],
            ci_low=(deep["h3"]["episode_ci"] or deep["h3"]["ci"])[0],
            ci_high=(deep["h3"]["episode_ci"] or deep["h3"]["ci"])[1],
            raw_rows=s["raw_rows"], unique_origins=s["unique_origins"],
            effective_origins=s["effective_origins"],
            independent_episodes=s["independent_episodes"],
            code_sha=sha, panel_hash=v2["panel"]["content_hash"],
            preregistration_hash=PR.v2_hash(), at="2026-08-27",
            original_method=ER.CLUSTER_BOOTSTRAP,
            original_ci=tuple(deep["h3"]["ci"]),
            mde=deep["h3"]["mde"],
            note=("H3 INSUFFICIENT_POWER on the episode-aware interval. The "
                  "origin-clustered interval excludes zero on the negative "
                  "side; fifteen episodes do not support that, and the "
                  "conservative reading is the one recorded.")))

    print("=== §2 CHECKPOINT WORLD_MODEL_RESEARCH_V2 ===")
    print(f"  code_sha        {sha}")
    print(f"  panel_hash      {payload['panel_hash']}")
    for arm, v in payload["hypothesis_verdicts"].items():
        print(f"  {arm:<8} " + "  ".join(f"{k.split('_')[0]}={v[k]}"
                                          for k in sorted(v)))
    print(f"  observed signal {payload['observed_signal']['state']}, "
          f"replicated {payload['observed_signal']['replicated_across_arms']}")
    print(f"  real_forward    {payload['real_forward']['opened']} open")
    print(f"  registry now    {len(ER.load())} evaluations")
    print(f"  wrote {CHECKPOINT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
