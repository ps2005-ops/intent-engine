"""§4/§6: one deployed analysis, read from canonical timing, compared to local.

ONE QUOTA SLOT, ONE QUESTION: what turns ~15s of local CORE work into ~135s
on the preview? Every previous answer to that was a ratio between two runs
that differed in several variables at once, and two of those answers were
wrong. This reads `/runs/<id>/timing` -- lifecycle markers the worker wrote
and spans it recorded -- so nothing here is inferred from rendered text.

ACCOUNTING CLOSURE IS THE FIRST CHECK, before any stage is called a
bottleneck. If the spans cover 40s of a 135s CORE, the interesting 95s is
somewhere uninstrumented and ranking the covered 40s would send the next
repair to the wrong place.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

BASELINE = pathlib.Path("reports/perf/cpu_yardstick_local_baseline.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from perf_progressive_matrix import (                          # noqa: E402
    BASE, POLL_S, _opener, _req, visible,
)

#: Stages that provably CANNOT perform I/O. Only these may CONFIRM CPU
#: starvation -- everything else can merely be consistent with it.
# MEASURED, NOT ASSUMED. A control may only be a stage observed at ~100% CPU
# on an unloaded machine across runs. `classification` was in this set and is
# not eligible: it read 47% CPU in one local trace and 9% in the next, and a
# ratio that swings like that belongs to something that waits. Parent spans
# are excluded too -- a parent inherits whatever its children do, so it can
# never be a clean control for anything.
IO_FREE = {"derive_observations", "analyst_evidence", "build_report"}
#: Stages whose work is a write to the persistent volume.
WRITES_DISK = {"demo_dossier", "ownership_append", "memory_snapshot",
               "memory_publish"}

CPU_COMPUTE, CPU_STARVED = "CPU_COMPUTE", "CPU_STARVED"
NETWORK_WAIT, MIXED_WAIT = "NETWORK_WAIT", "MIXED_WAIT"
STORAGE_WAIT, UNKNOWN = "STORAGE_WAIT", "UNKNOWN"


def classify(name, local_wall, local_cpu, dep_wall, dep_cpu, slowdown,
             stretch=None, tol=0.35):
    """What a span's numbers mean, judged against a MEASURED CPU yardstick.

    THE RULE THIS REPLACES WAS WRONG. It read `cpu_ms/wall_ms` and called
    anything under 0.15 NETWORK_WAIT. Two different conditions produce a low
    ratio -- blocking on I/O, and being descheduled while READY to run -- and
    they demand opposite repairs. `build_report` assembles in-memory
    structures and cannot do I/O at all, yet it was labelled NETWORK_WAIT on
    a 15% ratio. Every NETWORK_WAIT verdict that rule produced on a
    compute-bound stage was false.

    The yardstick makes the question answerable. Starvation predicts

        expected = local_wall * scheduling_slowdown

    so a stage landing there is starved and a stage well beyond it has a
    SECOND cause that still has to be named. That excess is what stops an
    infrastructure diagnosis from quietly absorbing an application defect.
    """
    if not slowdown or local_wall <= 0:
        return UNKNOWN, "no calibration reading -- refusing to guess", 0.0
    # PREDICT FROM THE STAGE'S OWN DEPLOYED CPU, NOT FROM ITS LOCAL WALL.
    #
    # `local_wall * slowdown` charges the machine for a workload difference.
    # Measured: the deployed run scanned 457,220 characters against 244,712
    # locally -- 1.87x the work -- and comparing walls across that reported
    # 25.3s "unexplained" when every stage was in fact within what the CPU
    # share predicts. A stage's own CPU is what it actually consumed, so
    # multiplying it by the stretch the probe measured isolates scheduling
    # from workload.
    expected = dep_cpu * stretch if stretch else local_wall * slowdown
    excess = dep_wall - expected
    frac = excess / dep_wall if dep_wall else 0.0
    local_ratio = local_cpu / local_wall if local_wall else 0.0

    if local_ratio < 0.30:
        # Never CPU-bound to begin with, so its deployed wall says nothing
        # about scheduling either way.
        kind = STORAGE_WAIT if name in WRITES_DISK else NETWORK_WAIT
        why = f"I/O-bound locally ({local_ratio:.0%} cpu), grew {dep_wall / local_wall:.1f}x"
    elif frac > tol:
        kind = MIXED_WAIT
        why = f"{excess / 1000:+.1f}s BEYOND starvation -- a second cause is present"
    elif abs(frac) <= tol:
        kind = CPU_STARVED if name in IO_FREE else MIXED_WAIT
        why = (f"within {frac:+.0%} of starvation's prediction"
               + ("; cannot do I/O, so CONFIRMED" if name in IO_FREE
                  else "; consistent, but this stage can also wait"))
    else:
        kind = CPU_COMPUTE
        why = f"faster than starvation predicts ({frac:+.0%})"
    return kind, why, excess


def run(company: str, website: str, budget_s: float) -> dict:
    op, _ = _opener()
    st, entry, *_ = _req(op, "/demo")
    csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)
    fields = {"consent": "on", "company_name": company,
              "website": f"https://{website}"}
    if csrf:
        fields["csrf"] = csrf.group(1)
    began = time.monotonic()
    st, body, url, *_ = _req(op, "/analyze", fields)
    if st == 429:
        return {"status": "QUOTA_EXHAUSTED", "detail": visible(body)[:200]}
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        return {"status": "NO_RUN", "detail": visible(body)[:240]}
    rid = m.group(1)
    print(f"  run_id={rid}", flush=True)

    # Poll the CANONICAL surface. The progress page is not consulted at all:
    # its redirect is a UX fact, and this is a latency measurement.
    timing, opened_at = {}, None
    while time.monotonic() - began < budget_s:
        st, body, *_ = _req(op, f"/runs/{rid}/timing", timeout=60)
        if st == 200:
            try:
                timing = json.loads(body)
            except ValueError:
                timing = {}
            if timing.get("core_latency_s") is not None:
                opened_at = round(time.monotonic() - began, 1)
                break
        time.sleep(POLL_S)
    return {"status": "OK", "run_id": rid, "timing": timing,
            "harness_observed_s": opened_at,
            "total_s": round(time.monotonic() - began, 1)}


def own_time(spans):
    """Each span's OWN wall/cpu -- its total minus its direct children.

    WHY THIS IS NOT OPTIONAL. Spans nest: `derive_observations` is inside
    `strategic_report` is inside `compose_proper` is inside
    `core_composition`. Summing a quantity across all of them counts the same
    seconds up to four times. Adding "excess beyond starvation" that way
    reported 68.8s unexplained out of a 90.2s run -- 76% -- when the real
    figure is a quarter of that. The identical mistake drove `unaccounted`
    negative when the sub-spans were first added, and it is worth stating
    that a double-counted number does not look wrong; it looks alarming and
    precise.

    A child is a BREAKDOWN OF a parent, so a parent's own contribution is
    what its children do not account for.
    """
    order = sorted(spans, key=lambda x: (x.get("offset_s", 0.0),
                                         x.get("depth", 0)))
    out = {}
    for i, sp in enumerate(order):
        if sp.get("calibration"):
            continue
        beg = sp.get("offset_s", 0.0)
        end = beg + sp.get("wall_ms", 0.0) / 1000.0
        kid_w = kid_c = 0.0
        for other in order[i + 1:]:
            if other.get("calibration"):
                continue
            if other.get("depth", 0) != sp.get("depth", 0) + 1:
                continue
            o_beg = other.get("offset_s", 0.0)
            if beg - 1e-6 <= o_beg <= end + 1e-6:
                kid_w += other.get("wall_ms", 0.0)
                kid_c += other.get("cpu_ms", 0.0)
        out[sp["name"]] = {
            "own_wall_ms": max(0.0, sp.get("wall_ms", 0.0) - kid_w),
            "own_cpu_ms": max(0.0, sp.get("cpu_ms", 0.0) - kid_c),
            "children_wall_ms": kid_w}
    return out


def table(deployed: dict, local: dict) -> None:
    dep_spans, loc_spans = {}, {}
    for phase in (deployed.get("timing", {}).get("trace") or []):
        if phase.get("phase") == "core":
            dep = phase
            for s in phase.get("spans", []):
                dep_spans[s["name"]] = s
            break
    else:
        dep = {}
    for s in ((local.get("waterfall") or {}).get("spans") or []):
        loc_spans[s["name"]] = s

    # --- CALIBRATION FIRST. Nothing below is interpretable without it. ---
    probes = [v for k, v in dep_spans.items() if k.startswith("cpu_yardstick")]
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    local_probe = base.get("wall_median_ms")
    slowdown = stretch = None
    print(f"\n{'=' * 78}\nCPU CALIBRATION")
    if local_probe and probes:
        print(f"  local probe median      {local_probe:.2f}ms "
              f"(n={base.get('n')}, CV={base.get('wall_cv_pct')}%)")
        for pr in probes:
            sd = pr["wall_ms"] / local_probe
            cpu_x = pr["cpu_ms"] / base["cpu_median_ms"] if base.get("cpu_median_ms") else 0
            print(f"  {pr['name']:<22} {pr['wall_ms']:>8.2f}ms wall  "
                  f"{pr['cpu_ms']:>8.2f}ms cpu  -> {sd:.2f}x slower, "
                  f"probe CPU {cpu_x:.2f}x")
        slowdown = max(p_["wall_ms"] for p_ in probes) / local_probe
        # WALL WAITED PER MS OF CPU GRANTED -- the workload-free factor.
        stretch = max(p_["wall_ms"] / p_["cpu_ms"] for p_ in probes
                      if p_.get("cpu_ms"))
        cpu_growth = (max(p_["cpu_ms"] for p_ in probes)
                      / base.get("cpu_median_ms", 1))
        print(f"\n  EFFECTIVE_CPU_SHARE_ESTIMATE  ~{100 / slowdown:.1f}% of one local core")
        print(f"  (an ESTIMATE of share, not a guarantee Render sells that number)")
        # THE DISCRIMINATION THE WALL-ONLY PROBE COULD NOT MAKE.
        if cpu_growth > 3.0:
            print(f"  probe CPU grew {cpu_growth:.1f}x -> SLOWER CORE, not a smaller "
                  f"share. More CPU allocation would NOT fix this.")
        else:
            print(f"  probe CPU grew only {cpu_growth:.1f}x while wall grew "
                  f"{slowdown:.1f}x -> READY BUT DESCHEDULED. A larger share is "
                  f"the lever.")
    else:
        print("  NO PROBE RECORDED -- every classification below is UNKNOWN.")

    print(f"\n{'STAGE':<21}{'LOCAL':>9}{'DEPLOYED':>10}{'MULT':>7}{'DEP CPU':>9}"
          f"{'EXPECT':>9}{'EXCESS':>9}  CLASS")
    names = [n for n in ("discovery", "source_selection", "retrieval",
                         "derive_observations", "ownership_append",
                         "classification", "build_report", "strategic_report",
                         "analyst_evidence", "compose_proper",
                         "external_context", "demo_dossier",
                         "core_composition") if n in dep_spans or n in loc_spans]
    dep_own = own_time(list(dep_spans.values()))
    loc_own = own_time(list(loc_spans.values()))
    unexplained = 0.0
    for name in names:
        d, l = dep_spans.get(name), loc_spans.get(name)
        dw = d.get("wall_ms", 0.0) if d else 0.0
        lw = l.get("wall_ms", 0.0) if l else 0.0
        dc = d.get("cpu_ms", 0.0) if d else 0.0
        lc = l.get("cpu_ms", 0.0) if l else 0.0
        kind, why, excess = classify(name, lw, lc, dw, dc, slowdown,
                                     stretch=stretch)
        exp = (dc * stretch if stretch else lw * slowdown) or 0.0
        # SUMMED ON OWN TIME ONLY, so a parent does not re-count its
        # children's seconds. See `own_time`.
        o_d = dep_own.get(name, {})
        if o_d and stretch:
            # OWN time, and predicted from OWN deployed CPU. Both corrections
            # matter: summing parents double-counts, and predicting from local
            # wall charges the machine for a larger workload.
            own_excess = o_d["own_wall_ms"] - o_d["own_cpu_ms"] * stretch
            if own_excess > 0:
                unexplained += own_excess
        mult = f"{dw / lw:.1f}x" if lw and dw else "-"
        print(f"{name:<21}{lw / 1000:>8.2f}s{dw / 1000:>9.2f}s{mult:>7}"
              f"{dc / 1000:>8.2f}s{exp / 1000:>8.2f}s{excess / 1000:>+8.2f}s  {kind}")
        print(f"{'':<21}  {why}")
        if d and d.get("text_chars"):
            print(f"{'':<21}  scanned {d['text_chars']:,} chars across "
                  f"{d.get('documents')} documents")
        if d and "used_on_this_path" in d and not d["used_on_this_path"]:
            print(f"{'':<21}  *** RESULT DISCARDED ON THIS PATH -- "
                  f"{dw / 1000:.1f}s of work nothing reads ***")

    core_s = (deployed.get("timing") or {}).get("core_latency_s") or 0
    # --- BOTTLENECK DECOMPOSITION (§46) ------------------------------------
    #
    # Three buckets, on OWN time so nothing is counted twice. They are not
    # ranked against each other -- they are bought differently. Network wait
    # is not "unexplained": it is explained by I/O, and calling it unexplained
    # was how a CPU verdict nearly absorbed 40s of waiting on SEC.
    net = cpu_starved = beyond = 0.0
    for nm, o in dep_own.items():
        ow, oc = o["own_wall_ms"], o["own_cpu_ms"]
        if not ow:
            continue
        predicted = oc * stretch if stretch else 0.0
        if ow > 0 and oc / ow < 0.10:          # barely used a CPU at all
            net += ow
        elif stretch and ow > predicted * 1.35:
            cpu_starved += predicted
            beyond += ow - predicted
        else:
            cpu_starved += ow
    waste = sum(sp.get("wall_ms", 0.0) for sp in dep_spans.values()
                if sp.get("used_on_this_path") is False)
    print(f"\n  BOTTLENECK DECOMPOSITION of {core_s}s CORE")
    print(f"    network wait (I/O)            {net / 1000:>7.1f}s   "
          f"bounded by timeouts/concurrency, not by CPU")
    print(f"    CPU-starved compute           {cpu_starved / 1000:>7.1f}s   "
          f"a larger CPU share is the lever")
    print(f"    beyond the measured share     {beyond / 1000:>7.1f}s   "
          f"{'needs a named cause' if beyond > 2000 else 'none material'}")
    print(f"\n    of which WORK NOTHING READS  {waste / 1000:>7.1f}s   "
          f"removable regardless of machine"
          + (f"  ({waste / 10 / core_s:.0f}% of CORE)" if core_s else ""))

    dep_total = dep.get("total_wall_ms", 0.0)
    dep_unacc = dep.get("unaccounted_wall_ms", 0.0)
    core = (deployed.get("timing") or {}).get("core_latency_s")
    print(f"\n  deployed core_latency_s   {core}")
    print(f"  deployed span total       {dep_total / 1000:.2f}s")
    print(f"  deployed unaccounted      {dep_unacc / 1000:.2f}s")
    if core:
        pct = dep_unacc / 1000 / core * 100
        verdict = ("OK (<=1%)" if pct <= 1
                   else "<<< INSTRUMENT THE GAP BEFORE RANKING STAGES")
        print(f"  UNACCOUNTED SHARE         {pct:.1f}% of CORE   {verdict}")
    print(f"  evidence_count            "
          f"{(deployed.get('timing') or {}).get('evidence_count')}")
    print(f"  provenance                "
          f"{(deployed.get('timing') or {}).get('provenance', {}).get('core_latency_s')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="Apple Inc.")
    ap.add_argument("--website", default="apple.com")
    ap.add_argument("--budget", type=float, default=420.0)
    ap.add_argument("--local", default="reports/perf/local_control.json")
    ap.add_argument("--out", default="reports/perf/deployed_waterfall.json")
    a = ap.parse_args()

    ver = _req(_opener()[0], "/version")[1]
    print(f"deployed: {ver[:120]}")
    print(f"running ONE {a.company} analysis...", flush=True)
    row = run(a.company, a.website, a.budget)
    if row.get("status") != "OK":
        print(f"  {row['status']}: {row.get('detail', '')}")
        return 1
    local = json.loads(pathlib.Path(a.local).read_text()) \
        if pathlib.Path(a.local).exists() else {}
    table(row, local)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"deployed": row, "local": local}, indent=2))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
