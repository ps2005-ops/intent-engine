#!/usr/bin/env python3
"""One row per company across every wave file, newest SHA wins.

A company measured on more than one SHA is STALE on all but the newest.
"""
import json, os, sys, glob, statistics

ROOT = "docs/execution/v5/pre100_50/live_captures"
# deploy order, oldest -> newest
ORDER = ["8397d67","49b6c3a","517e7ae","5d43053","10d1620","b37bee2","0d02c0b",
         "e78c2a0","b0050e3","dc17a9d","743df06"]

rows = {}
for sha in ORDER:
    for wf in sorted(glob.glob(os.path.join(ROOT, sha, "*.json"))):
        try:
            data = json.load(open(wf))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for r in data:
            c = r.get("company")
            if not c:
                continue
            r["_sha"] = sha
            r["_wave"] = os.path.basename(wf)[:-5]
            rows[c] = r          # later SHA overwrites

print(f"COMPANIES MEASURED: {len(rows)}\n")
hdr = f"{'company':<38}{'sha':<9}{'wave':<14}{'status':<9}{'outcome':<34}{'t':>5}{'fu':>5}"
print(hdr); print("-"*len(hdr))
by_outcome = {}
firsts = []
for c in sorted(rows):
    r = rows[c]
    out = r.get("outcome") or ("NO_OUTCOME(" + r.get("status","?") + ")")
    by_outcome.setdefault(out, []).append(c)
    fu = r.get("first_useful")
    if isinstance(fu,(int,float)): firsts.append(fu)
    print(f"{c[:37]:<38}{r['_sha']:<9}{r['_wave']:<14}{r.get('status','?'):<9}"
          f"{out[:33]:<34}{str(r.get('seconds','')):>5}{str(fu if fu is not None else '-'):>5}")

print("\nOUTCOME TALLY")
for k in sorted(by_outcome, key=lambda k:-len(by_outcome[k])):
    print(f"  {k:<40}{len(by_outcome[k]):>3}  {', '.join(by_outcome[k])[:100]}")

print(f"\nSTALE (measured before 743df06): "
      f"{[c for c in sorted(rows) if rows[c]['_sha']!='743df06']}")
if firsts:
    firsts.sort()
    print(f"\nFIRST_USEFUL n={len(firsts)} median={statistics.median(firsts):.0f}s "
          f"p95={firsts[int(len(firsts)*0.95)-1]:.0f}s max={max(firsts)}s")
