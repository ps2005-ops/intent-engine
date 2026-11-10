"""One deployed Apple run that PROVES the repair, rather than timing it.

WHY A SEPARATE SCRIPT. The waterfall answers "where did the time go". This
answers a different question with a yes/no: did the work leave the blocking
path, and does it still happen afterwards? Those need different evidence, and
conflating them is how a latency repair gets accepted while quietly deleting a
feature -- which the pre-commit guard caught once already on this change.

THE CORE_READY BOUNDARY IS DERIVED, NOT ASSUMED. `core_composition` ends
microseconds before the `core_ready` marker is written, so its end offset is
the boundary. A span starting after it did not delay the reader; a span
starting before it did.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from perf_deployed_waterfall import own_time                     # noqa: E402
from perf_progressive_matrix import _opener, _req                # noqa: E402
from perf_deployed_waterfall import run as run_one               # noqa: E402

#: What must have left the blocking path, and why it was there.
MUST_BE_OFF_CORE = {
    "analyst_evidence": "REMOVED_DEAD_WORK",       # result was discarded
    "external_context": "DEFERRED_AFTER_CORE",     # enrichment, still runs
    "demo_dossier": "DEFERRED_AFTER_CORE",         # read-model write, still runs
}
#: Deferred work must still HAPPEN. Dead work must not.
MUST_STILL_RUN = ("external_context", "demo_dossier")

BASELINE = {  # 14fc0a1a, Apple, deployed
    "core_latency_s": 90.7,
    "analyst_evidence": 18010.0,
    "external_context": 3200.0,
    "demo_dossier": 2900.0,
    "core_composition": 50290.0,
}


def _opener_session(row):
    """The opener that OWNS this run.

    `/runs/<id>/timing` is session-scoped: a fresh opener gets the login page,
    which is how the attempt to recover a lost run came back as 14KB of HTML
    instead of JSON. `run()` returns its own opener under `_opener` for this
    reason; `_opener()` returns a (opener, jar) PAIR while that field holds
    the opener alone, so the two are normalised here rather than at each
    call site."""
    held = row.get("_opener")
    if held is not None:
        return held
    op, _jar = _opener()
    return op


def _reread(op, run_id):
    if not run_id:
        return None
    try:
        st, body, *_ = _req(op, f"/runs/{run_id}/timing")
        return json.loads(body) if st == 200 and body.lstrip().startswith("{") \
            else None
    except Exception:                                          # noqa: BLE001
        return None


def core_phase(row):
    for phase in ((row.get("timing") or {}).get("trace") or []):
        if phase.get("phase") == "core":
            return phase
    return {}


def verify(row) -> int:
    t = row.get("timing") or {}
    phase = core_phase(row)
    spans = {s["name"]: s for s in phase.get("spans", [])}
    comp = spans.get("core_composition")
    if not comp:
        print("  NO core_composition SPAN -- cannot locate the boundary")
        return ["core trace absent: nothing can be asserted"]
    boundary = comp.get("offset_s", 0.0) + comp.get("wall_ms", 0.0) / 1000.0

    print(f"\n{'=' * 78}\nREPAIR VERIFICATION  (core_ready boundary at "
          f"t+{boundary:.2f}s)")
    print(f"{'SPAN':<20}{'OFFSET':>9}{'WALL':>9}  WHERE          VERDICT")
    print("-" * 78)
    failures = []
    for name, kind in MUST_BE_OFF_CORE.items():
        sp = spans.get(name)
        if sp is None:
            where, ok = "ABSENT", kind == "REMOVED_DEAD_WORK"
            print(f"{name:<20}{'-':>9}{'-':>9}  {where:<14} "
                  f"{'PASS (removed)' if ok else 'FAIL (deferred work vanished)'}")
            if not ok:
                failures.append(f"{name} was deferred, not deleted, but never ran")
            continue
        off, wall = sp.get("offset_s", 0.0), sp.get("wall_ms", 0.0)
        after = off >= boundary - 0.05
        where = "AFTER core_ready" if after else "BLOCKING CORE"
        if kind == "REMOVED_DEAD_WORK":
            ok = False                       # dead work must not run at all
            verdict = "FAIL (dead work still runs)"
        else:
            ok = after
            verdict = "PASS (deferred)" if after else "FAIL (still blocks CORE)"
        print(f"{name:<20}{off:>8.2f}s{wall / 1000:>8.2f}s  {where:<14} {verdict}")
        if not ok:
            failures.append(f"{name}: {verdict}")

    # D: deferred work must STILL EXECUTE -- a guard that only proves removal
    # will always bless a deletion.
    print()
    for name in MUST_STILL_RUN:
        sp = spans.get(name)
        ran = sp is not None and sp.get("wall_ms", 0.0) > 0
        print(f"  {name:<20} still executes: "
              f"{'YES' if ran else 'NO  <<< FEATURE SILENTLY DELETED'}")
        if not ran:
            failures.append(f"{name} no longer runs at all")
    return failures


def compare(row, failures) -> None:
    t = row.get("timing") or {}
    phase = core_phase(row)
    spans = {s["name"]: s for s in phase.get("spans", [])}
    after_s = t.get("core_latency_s")
    before_s = BASELINE["core_latency_s"]
    print(f"\n{'=' * 78}\nAPPLE, SAME SERVICE, BEFORE vs AFTER")
    print(f"  BEFORE  14fc0a1a   {before_s:.1f}s")
    print(f"  AFTER   {t.get('sha', 'repair SHA')[:8] if t.get('sha') else '517180e6'}   "
          f"{after_s:.1f}s"
          if after_s else "  AFTER   (no core_latency_s)")
    if after_s:
        d = before_s - after_s
        print(f"  DELTA              {-d:+.1f}s   ({-100 * d / before_s:+.0f}%)")
        band = ("<=30s EXCELLENT" if after_s <= 30 else
                "30-45s STRONG PASS" if after_s <= 45 else
                "45-60s TIER-1 HARD-BUDGET PASS" if after_s <= 60 else
                ">60s PERFORMANCE GATE STILL FAILED")
        print(f"  BAND               {band}")
    print(f"\n{'STAGE':<20}{'BEFORE':>10}{'AFTER(block)':>14}{'AFTER(post)':>13}  KIND")
    print("-" * 78)
    for name, kind in MUST_BE_OFF_CORE.items():
        sp = spans.get(name)
        comp = spans.get("core_composition") or {}
        boundary = comp.get("offset_s", 0.0) + comp.get("wall_ms", 0.0) / 1000.0
        blk = post = 0.0
        if sp is not None:
            if sp.get("offset_s", 0.0) >= boundary - 0.05:
                post = sp.get("wall_ms", 0.0)
            else:
                blk = sp.get("wall_ms", 0.0)
        print(f"{name:<20}{BASELINE[name] / 1000:>9.2f}s{blk / 1000:>13.2f}s"
              f"{post / 1000:>12.2f}s  {kind}")
    cc = spans.get("core_composition", {}).get("wall_ms", 0.0)
    print(f"{'core_composition':<20}{BASELINE['core_composition'] / 1000:>9.2f}s"
          f"{cc / 1000:>13.2f}s{'-':>12}  ")
    print(f"\n  evidence_count {t.get('evidence_count')}   "
          f"run_state {t.get('run_state')}   result_state {t.get('result_state')}")
    print(f"  unaccounted {(phase.get('unaccounted_wall_ms') or 0) / 1000:.2f}s")
    print(f"\n  REPAIR ASSERTIONS: "
          f"{'ALL PASS' if not failures else 'FAILED -> ' + '; '.join(failures)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="Apple Inc.")
    ap.add_argument("--website", default="apple.com")
    ap.add_argument("--budget", type=float, default=420.0)
    ap.add_argument("--out", default="reports/perf/repair_verification.json")
    a = ap.parse_args()
    ver = _req(_opener()[0], "/version")[1]
    print(f"deployed: {ver[:120]}")
    if "517180e6" not in ver:
        print("  REFUSING: /version is not the repair SHA")
        return 2
    print(f"running ONE {a.company} analysis...", flush=True)
    row = run_one(a.company, a.website, a.budget)

    # SAVE BEFORE ANALYSING. The first attempt analysed the run and wrote the
    # file afterwards, so a TypeError in the analysis discarded a measurement
    # that had already cost a quota slot. The raw reading is the expensive
    # part; the interpretation can always be rerun.
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({k: v for k, v in row.items()
                               if not k.startswith("_")}, indent=2))
    print(f"  raw saved -> {out}")

    if row.get("status") != "OK":
        print(f"  {row['status']}: {row.get('detail', '')}")
        return 1

    # THE REPAIR MOVED THE TRACE WRITE. `record_trace` now runs AFTER
    # enrichment, which is ~6s after the `core_ready` marker the poller waits
    # on -- so the first read landed in that window and saw no spans at all.
    # That is a harness race introduced by the change, not a missing trace.
    import time as _t
    op2 = _opener_session(row)
    for attempt in range(12):
        if core_phase(row).get("spans"):
            break
        _t.sleep(5)
        fresh = _reread(op2, row.get("run_id"))
        if fresh:
            row["timing"] = fresh
            out.write_text(json.dumps({k: v for k, v in row.items()
                                       if not k.startswith("_")}, indent=2))
    if not core_phase(row).get("spans"):
        print("  trace never appeared after 60s -- reporting what exists")

    failures = verify(row)
    compare(row, failures)
    print(f"\n-> {out}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
