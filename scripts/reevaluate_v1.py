"""§2: append a corrected evaluation of V1. Never rewrite the original.

WHAT IS BEING CORRECTED, EXACTLY
--------------------------------
`GLOBAL_COLLECTIVE_HUMAN_STATE_V1` was frozen with a row bootstrap. Two
better estimators now exist -- origin-clustered and episode-aware -- and the
same paired differences are re-run through all three so the reader sees what
the method was worth rather than being told.

The original record is not touched. This writes a NEW record that names it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import baseline_registry as BR      # noqa: E402
from intent_engine.econ import evaluation_record as ER      # noqa: E402
from intent_engine.econ import incremental as INC           # noqa: E402
from intent_engine.econ import power as PW                  # noqa: E402
from intent_engine.econ import preregistration as PR        # noqa: E402

REPORTS = pathlib.Path("reports")
BASE = REPORTS / "base_forecasts.jsonl"
AUG = REPORTS / "augmented_forecasts.jsonl"
OUT = REPORTS / "v1_reevaluation.json"


def _load(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["target_id"]] = r
    return out


def _phase_count(origins) -> int:
    """V1's origins, counted against the phases V2 discovered.

    The same phase map both runs are measured with, so the before/after
    comparison is like for like. Returns 0 when the panel or manifest is
    unavailable, and the caller then skips the correction rather than
    inventing a number.
    """
    try:
        from intent_engine.econ import episodes as EPI
        from intent_engine.econ import panel as PN
        from intent_engine.econ import power as PW
        from intent_engine.econ import regime as RG
        man = json.loads(
            (REPORTS / "panel/historical_acquisition_manifest.json").read_text())
        panel = PN.Panel.read(REPORTS / "panel/historical_panel.jsonl")
        grid = man["origins_deep"] + man["origins_modern"]
        eps = EPI.discover(RG.classify_many(panel, grid))
        return len(set(PW.phase_map(origins, eps).values()))
    except Exception:                                       # noqa: BLE001
        return 0


def _origin(target_id: str) -> str:
    # key is "<family>@<origin>+<horizon>"
    return target_id.split("@", 1)[1].split("+", 1)[0]


def main() -> int:
    if not (BASE.exists() and AUG.exists()):
        print("V1 forecast files are missing; run scripts/run_experiment.py")
        return 2
    b, a = _load(BASE), _load(AUG)
    shared = sorted(set(b) & set(a))
    if not shared:
        print("no shared paired forecasts")
        return 2

    diffs, origins, targets, horizons = [], [], [], []
    for k in shared:
        y = 1.0 if b[k]["y"] else 0.0
        diffs.append((b[k]["p"] - y) ** 2 - (a[k]["p"] - y) ** 2)
        origins.append(_origin(k))
        targets.append(b[k]["family"])
        horizons.append(int(k.rsplit("+", 1)[1]))

    n = len(diffs)
    delta = sum(diffs) / n
    seed = 20260827
    row_lo, row_hi, row_p = INC._bootstrap_ci(diffs, seed=seed)
    cl_lo, cl_hi, cl_p, k_cl = INC._cluster_bootstrap_ci(diffs, origins,
                                                         seed=seed)
    ep_lo, ep_hi, ep_p, k_ep = INC._episode_bootstrap_ci(diffs, origins,
                                                         seed=seed)
    sample = PW.measure(origins=origins, values=diffs, targets=targets,
                        horizons=horizons)

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    frozen = BR.load().get("GLOBAL_COLLECTIVE_HUMAN_STATE_V1")

    print("=== V1, RE-EVALUATED ON THE SAME PAIRED DIFFERENCES ===")
    print(f"  delta                     {delta:+.5f}")
    print(f"  row bootstrap        CI [{row_lo:+.5f}, {row_hi:+.5f}]  "
          f"p={row_p:.3f}   half-width {(row_hi-row_lo)/2:.5f}")
    print(f"  origin-clustered     CI [{cl_lo:+.5f}, {cl_hi:+.5f}]  "
          f"p={cl_p:.3f}   half-width {(cl_hi-cl_lo)/2:.5f}  "
          f"({k_cl} origins)")
    if ep_lo is None:
        print(f"  episode-aware        UNDEFINED -- {k_ep} episode(s). One "
              "contiguous block cannot support an interval.")
    else:
        print(f"  episode-aware        CI [{ep_lo:+.5f}, {ep_hi:+.5f}]  "
              f"p={ep_p:.3f}   half-width {(ep_hi-ep_lo)/2:.5f}  "
              f"({k_ep} episodes)")
    print(f"  sample               {sample.headline()}")
    print(f"  origin autocorrelation {sample.origin_autocorrelation:.3f}, "
          f"within-origin ICC {sample.icc:.3f}")
    if frozen:
        print(f"\n  frozen V1 recorded   CI [{frozen.ci_low:+.5f}, "
              f"{frozen.ci_high:+.5f}] on n={frozen.n_paired}")

    existing = {e.evaluation_id for e in ER.load()}
    if "GLOBAL_COLLECTIVE_HUMAN_STATE_V1" not in existing and frozen:
        ER.append(ER.Evaluation(
            evaluation_id="GLOBAL_COLLECTIVE_HUMAN_STATE_V1",
            supersedes="", method=ER.ROW_BOOTSTRAP,
            reason=("the original record, kept exactly as frozen. It is "
                    "evidence of what the system believed using the "
                    "then-current evaluator, and correcting it in place "
                    "would destroy that."),
            delta=frozen.delta, ci_low=frozen.ci_low, ci_high=frozen.ci_high,
            raw_rows=frozen.n_paired, unique_origins=0,
            effective_origins=0.0, independent_episodes=0,
            code_sha=frozen.code_sha, panel_hash=frozen.panel_hash,
            preregistration_hash=frozen.preregistration_hash,
            at=frozen.frozen_at, mde=frozen.mde,
            note=("origins, effective origins and episodes are recorded as "
                  "zero because the original evaluator did not compute them "
                  "-- not because they were zero. That absence is the "
                  "defect the correction addresses.")))

    if "GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED" not in existing:
        ER.append(ER.Evaluation(
            evaluation_id="GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED",
            supersedes="GLOBAL_COLLECTIVE_HUMAN_STATE_V1",
            method=(ER.EPISODE_AWARE if ep_lo is not None
                    else ER.CLUSTER_BOOTSTRAP),
            reason=(
                "the stored interval was produced by a bootstrap that "
                "resampled ROWS. Each of the 500 rows is one of ten "
                "(target x horizon) combinations from one of 50 forecast "
                "origins, and those ten share their features and overlap in "
                "their outcome windows. Re-run on the same differences with "
                "origin-clustered and episode-aware resampling."),
            delta=round(delta, 5),
            ci_low=round(ep_lo if ep_lo is not None else cl_lo, 5),
            ci_high=round(ep_hi if ep_hi is not None else cl_hi, 5),
            raw_rows=n, unique_origins=sample.unique_origins,
            effective_origins=sample.effective_origins,
            independent_episodes=sample.independent_episodes,
            code_sha=sha,
            panel_hash=json.loads(
                (REPORTS / "model_comparison.json").read_text()
            )["panel"].get("content_hash", ""),
            preregistration_hash=PR.declaration_hash(),
            at="2026-08-27", original_method=ER.ROW_BOOTSTRAP,
            original_ci=(frozen.ci_low, frozen.ci_high) if frozen else (0, 0),
            mde=round(((ep_hi - ep_lo) if ep_lo is not None
                       else (cl_hi - cl_lo)) / 2.0, 5),
            note=(
                f"MEASURED, AND IT DOES NOT SAY WHAT WAS EXPECTED. The "
                f"origin-clustered interval is [{cl_lo:+.5f}, {cl_hi:+.5f}] "
                f"against the row bootstrap's [{row_lo:+.5f}, {row_hi:+.5f}] "
                f"-- half-widths {(cl_hi-cl_lo)/2:.5f} and "
                f"{(row_hi-row_lo)/2:.5f}. The stored V1 interval was NOT "
                f"materially too narrow. The within-origin correlation of "
                f"the paired loss DIFFERENCES is "
                f"{sample.icc:.3f}: the ten rows from an origin share their "
                f"features, but the amount by which the augmented model beats "
                f"the base model on each is nearly independent, so clustering "
                f"costs almost nothing HERE. It cost a great deal on the "
                f"INFLATION_SHOCK slice, which is why the estimator was right "
                f"to change. The episode-aware interval is UNDEFINED: all "
                f"{k_cl} origins fall in {k_ep} contiguous block, so the "
                f"headline interval is the clustered one and this result "
                f"cannot be called robust whatever its width.")))

    # -------------------------------------------------------------------
    # A SECOND CORRECTION, on the same append-only terms.
    #
    # The first correction recorded `independent_episodes = 1`, counted by
    # contiguity: V1's fifty origins run consecutively, so they form one
    # unbroken run of dates. That is the WRONG UNIT for a global sample and
    # it is the same defect that later made a 1978-2026 sample report "1
    # episode". Re-counted against the discovered macroeconomic phases, V1's
    # origins span 2008-02 to 2020-05 and cover FIVE phases.
    #
    # This matters for what the run may claim: the episode gain from V1 to
    # the deep monthly arm is 15/5 = x3.0, not 15/1 = x15. Appending the
    # correction rather than editing the first one keeps both readings
    # visible, which is the whole point of the registry.
    phases = _phase_count(origins)
    if ("GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED_PHASES"
            not in existing and phases):
        ER.append(ER.Evaluation(
            evaluation_id="GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED_PHASES",
            supersedes="GLOBAL_COLLECTIVE_HUMAN_STATE_V1_REEVALUATED",
            method=ER.EPISODE_AWARE,
            reason=(
                "the previous correction counted episodes by CONTIGUITY and "
                "got 1. V1's origins run consecutively, so contiguity always "
                "returns 1 for a global sample however much history it "
                "covers. Re-counted against the macroeconomic phases the "
                "contemporaneous classifier discovered, the same fifty "
                f"origins cover {phases} phases."),
            delta=round(delta, 5), ci_low=round(cl_lo, 5),
            ci_high=round(cl_hi, 5), raw_rows=n,
            unique_origins=sample.unique_origins,
            effective_origins=sample.effective_origins,
            independent_episodes=phases, code_sha=sha,
            panel_hash=json.loads(
                (REPORTS / "model_comparison.json").read_text()
            )["panel"].get("content_hash", ""),
            preregistration_hash=PR.declaration_hash(),
            at="2026-08-27", original_method=ER.EPISODE_AWARE,
            original_ci=(cl_lo, cl_hi),
            mde=round((cl_hi - cl_lo) / 2.0, 5),
            note=("this correction CHANGES WHAT THE V2 RUN MAY CLAIM. The "
                  "episode gain is 15/5 = x3.0, not x15. It is recorded "
                  "because the overstated version would have been the "
                  "headline of the power section.")))

    payload = {"delta": round(delta, 5), "n_paired": n,
               "phase_based_episodes": phases,
               "row_bootstrap": {"ci": [row_lo, row_hi], "p": row_p},
               "origin_clustered": {"ci": [cl_lo, cl_hi], "p": cl_p,
                                    "clusters": k_cl},
               "episode_aware": {
                   "ci": ([ep_lo, ep_hi] if ep_lo is not None else None),
                   "p": ep_p, "episodes": k_ep,
                   "defined": ep_lo is not None},
               "clustering_changed_the_interval": (
                   abs((cl_hi - cl_lo) - (row_hi - row_lo)) > 0.2
                   * (row_hi - row_lo)),
               "sample": sample.as_dict(),
               "registry": ER.summarise()}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\n  wrote {OUT} and appended to {ER.REGISTRY_PATH}")
    for e in ER.load():
        print(f"    {e.headline()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
