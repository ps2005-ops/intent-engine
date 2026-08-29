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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from perf_progressive_matrix import (                          # noqa: E402
    BASE, POLL_S, _opener, _req, visible,
)

CLASSES = {  # cpu/wall ratio -> what the number is telling you
    "network": lambda r: r < 0.15,
    "mixed": lambda r: 0.15 <= r < 0.6,
    "cpu": lambda r: r >= 0.6,
}


def classify(wall_ms: float, cpu_ms: float) -> str:
    if wall_ms <= 0:
        return "-"
    ratio = cpu_ms / wall_ms
    for name, test in CLASSES.items():
        if test(ratio):
            return {"network": "NETWORK_WAIT", "mixed": "MIXED",
                    "cpu": "CPU_COMPUTE"}[name]
    return "-"


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

    print(f"\n{'STAGE':<20}{'LOCAL':>10}{'DEPLOYED':>11}{'MULT':>7}"
          f"{'DEP CPU':>10}{'CPU/WALL':>10}  CLASSIFICATION")
    for name in ("discovery", "source_selection", "retrieval",
                 "core_composition"):
        d, l = dep_spans.get(name), loc_spans.get(name)
        dw = d.get("wall_ms", 0.0) if d else 0.0
        lw = l.get("wall_ms", 0.0) if l else 0.0
        dc = d.get("cpu_ms", 0.0) if d else 0.0
        mult = f"{dw / lw:.1f}x" if lw and dw else "-"
        ratio = f"{dc / dw * 100:.0f}%" if dw else "-"
        print(f"{name:<20}{lw / 1000:>9.2f}s{dw / 1000:>10.2f}s{mult:>7}"
              f"{dc / 1000:>9.2f}s{ratio:>10}  "
              f"{classify(dw, dc) if d else 'NOT RECORDED'}")

    dep_total = dep.get("total_wall_ms", 0.0)
    dep_unacc = dep.get("unaccounted_wall_ms", 0.0)
    core = (deployed.get("timing") or {}).get("core_latency_s")
    print(f"\n  deployed core_latency_s   {core}")
    print(f"  deployed span total       {dep_total / 1000:.2f}s")
    print(f"  deployed unaccounted      {dep_unacc / 1000:.2f}s")
    if core:
        pct = dep_unacc / 1000 / core * 100
        print(f"  UNACCOUNTED SHARE         {pct:.1f}% of CORE"
              f"   {'OK (<=1%)' if pct <= 1 else '<<< INSTRUMENT THE GAP '
                                                 'BEFORE RANKING STAGES'}")
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
