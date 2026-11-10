"""Two runs of one company, in one deployment lifetime: COLD then WARM.

WHAT THIS IS FOR. `plan_refresh` returning "WARM" proves nothing on its own --
a planner nothing consumes is architecture theatre. What has to be true is
that the SECOND run does materially less expensive work than the first, and
comes back with the same company.

So this reports the two things together: what the run cost, and what it found.
A warm run that is fast because it lost half the evidence is a regression
wearing a latency improvement.

NO REDEPLOY BETWEEN THE TWO RUNS. Snapshots live under the runtime root, which
is EPHEMERAL on this preview -- a deploy replaces the instance and takes them
with it. That is a real limitation and it is the reason cold/warm is measured
inside one lifetime; it is NOT evidence about restart durability and must
never be reported as such.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from perf_deployed_waterfall import own_time                    # noqa: E402,F401
from perf_deployed_waterfall import run as run_one              # noqa: E402
from perf_progressive_matrix import _opener, _req               # noqa: E402


def spans_of(row) -> dict:
    out = {}
    for ph in ((row.get("timing") or {}).get("trace") or []):
        for s in (ph.get("spans") or []):
            out[s["name"]] = s
    return out


def summarise(label, row) -> dict:
    t = row.get("timing") or {}
    sp = spans_of(row)
    g = lambda n, f="wall_ms": (sp.get(n) or {}).get(f, 0.0)      # noqa: E731
    return {
        "label": label,
        "run_id": row.get("run_id"),
        "core_latency_s": t.get("core_latency_s"),
        "usable_s": row.get("harness_observed_s"),
        "evidence_count": t.get("evidence_count"),
        "run_state": t.get("run_state"),
        "result_state": t.get("result_state"),
        "discovery_ms": g("discovery"),
        "retrieval_ms": g("retrieval"),
        "composition_ms": g("core_composition"),
        "documents": (sp.get("derive_observations") or {}).get("documents"),
        "text_chars": (sp.get("derive_observations") or {}).get("text_chars"),
        "observations": (sp.get("derive_observations") or {}).get("item_count"),
        # THE QUESTION THE FIRST WARM RUN ANSWERED WRONGLY. `result_state` is
        # set on every composed CORE payload, so its absence means no
        # strategic report was composed at all -- which is what "fast" looked
        # like when the warm path had skipped identity resolution. Named
        # explicitly rather than left to be inferred from a column of Nones.
        "has_report": t.get("result_state") is not None,
        # EVERY SPAN, NOT THREE. Apple's warm run reported discovery 0.2s,
        # retrieval 14.3s and composition 31.5s against an 80.2s CORE -- 34s
        # in no column at all. A summary that keeps only the stages I expected
        # to matter cannot show me the one that did, and re-running to find
        # out costs a quota slot the raw trace would have saved.
        "spans": {n: {"wall_ms": v.get("wall_ms"), "cpu_ms": v.get("cpu_ms"),
                      "offset_s": v.get("offset_s"), "depth": v.get("depth")}
                  for n, v in sp.items()},
        "unaccounted_ms": round(
            (t.get("core_latency_s") or 0) * 1000
            - sum(v.get("wall_ms", 0.0) for v in sp.values()
                  if v.get("depth") == 0 and not v.get("calibration")), 1),
    }


def table(cold, warm) -> bool:
    print(f"\n{'=' * 74}\nCOLD vs WARM   {cold['label']}")
    print(f"{'METRIC':<20}{'COLD':>14}{'WARM':>14}{'CHANGE':>14}")
    print("-" * 74)
    rows = [("CORE latency s", "core_latency_s", 1),
            ("usable s", "usable_s", 1),
            ("discovery ms", "discovery_ms", 1),
            ("retrieval ms", "retrieval_ms", 1),
            ("composition ms", "composition_ms", 1)]
    for name, key, _ in rows:
        c, w = cold.get(key) or 0, warm.get(key) or 0
        chg = f"{(w - c) / c * 100:+.0f}%" if c else "-"
        print(f"{name:<20}{c:>14.2f}{w:>14.2f}{chg:>14}")
    print("-" * 74)
    for name, key in (("evidence", "evidence_count"),
                      ("documents", "documents"),
                      ("observations", "observations"),
                      ("text chars", "text_chars")):
        print(f"{name:<20}{str(cold.get(key)):>14}{str(warm.get(key)):>14}"
              f"{'SAME' if cold.get(key) == warm.get(key) else 'DIFFERENT':>14}")

    print(f"{'unaccounted ms':<20}{cold.get('unaccounted_ms', 0):>14.0f}"
          f"{warm.get('unaccounted_ms', 0):>14.0f}"
          f"{'<<< LOOK HERE' if (warm.get('unaccounted_ms') or 0) > 5000 else '':>14}")
    print(f"{'strategic report':<20}{str(cold.get('has_report')):>14}"
          f"{str(warm.get('has_report')):>14}"
          f"{'OK' if warm.get('has_report') else 'MISSING':>14}")

    # --- the verdict, stated as a rule rather than an impression ------------
    c_disc, w_disc = cold["discovery_ms"] or 0, warm["discovery_ms"] or 0
    real = c_disc > 0 and w_disc < c_disc * 0.5
    # A run with no report is not a quality difference, it is a missing
    # product, so it is checked first and separately.
    produced = bool(warm.get("has_report")) and bool(cold.get("has_report"))

    # DIRECTIONAL, NOT EXACT. The first version failed on ANY difference,
    # which meant it failed when the warm run found MORE evidence -- and a
    # gate that reports a regression when the product improves is not a
    # quality gate, it is noise that will be ignored and then removed.
    #
    # These are live runs against real websites: a page that 200s on one run
    # and times out on the next changes the document set without anything in
    # this codebase changing. So the bar is DEGRADATION, with a tolerance of
    # one document, and the numbers are printed either way so a reader can
    # see drift the rule does not fail on.
    def _worse(key, tol=1):
        c, w = cold.get(key), warm.get(key)
        return (c is not None and w is not None) and w < c - tol

    degraded = [k for k in ("evidence_count", "documents", "observations")
                if _worse(k)]
    parity = produced and not degraded
    print(f"\n  WARM DID LESS WORK   {'YES' if real else 'NO'}"
          f"   (discovery {w_disc:.0f}ms vs {c_disc:.0f}ms)")
    print(f"  QUALITY PARITY       {'YES' if parity else 'NO'}"
          f"   (evidence {cold.get('evidence_count')} -> "
          f"{warm.get('evidence_count')}, observations "
          f"{cold.get('observations')} -> {warm.get('observations')})")
    if not real:
        print("  >>> SNAPSHOT INTEGRATION DID NOT REDUCE WORK. A status that "
              "says WARM while discovery costs the same is theatre.")
    if not produced:
        print("  >>> A RUN COMPOSED NO STRATEGIC REPORT. This is not a faster "
              "analysis, it is a missing one -- the failure mode where a "
              "latency win deletes the product.")
    elif degraded:
        print(f"  >>> QUALITY DEGRADED in {degraded}. Faster only counts if "
              f"the truth survives; investigate before accepting the latency.")
    print("\n  durability: EPHEMERAL -- one deployment lifetime. This says "
          "nothing about restart survival.")
    return real and parity


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="Microsoft Corporation")
    ap.add_argument("--website", default="microsoft.com")
    ap.add_argument("--budget", type=float, default=420.0)
    ap.add_argument("--sha", default="")
    ap.add_argument("--out", default="reports/perf/cold_warm.json")
    a = ap.parse_args()

    ver = _req(_opener()[0], "/version")[1]
    print(f"deployed: {ver[:110]}")
    if a.sha and a.sha not in ver:
        print(f"  REFUSING: /version is not {a.sha}")
        return 2

    print(f"\nCOLD  {a.company}", flush=True)
    cold_row = run_one(a.company, a.website, a.budget)
    if cold_row.get("status") != "OK":
        print(f"  cold failed: {cold_row.get('status')}")
        return 1
    cold = summarise("COLD", cold_row)

    # Same deployment, same company, immediately after: the only difference
    # is that the engine has now seen it.
    print(f"\nWARM  {a.company}", flush=True)
    warm_row = run_one(a.company, a.website, a.budget)
    if warm_row.get("status") != "OK":
        print(f"  warm failed: {warm_row.get('status')}")
        return 1
    warm = summarise("WARM", warm_row)

    ok = table(cold, warm)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"company": a.company, "cold": cold,
                               "warm": warm, "durability": "EPHEMERAL",
                               "at": time.time()}, indent=2))
    print(f"\n-> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
