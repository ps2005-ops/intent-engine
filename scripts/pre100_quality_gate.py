#!/usr/bin/env python3
"""Score every company in the universe on the newest capture it has.

Usage: PYTHONPATH=src python3 scripts/pre100_quality_gate.py [OUT.json]
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys

sys.path.insert(0, "src")

from intent_engine.pre100 import audit as A          # noqa: E402
from intent_engine.pre100 import quality as Q        # noqa: E402
from intent_engine.pre100.verdict import verdict     # noqa: E402

ROOT = pathlib.Path("docs/execution/v5/pre100_50")
CAPTURES = ROOT / "live_captures"
#: oldest -> newest. The newest capture a company has is the only one that
#: describes the product as it stands.
ORDER = ["8397d67", "49b6c3a", "517e7ae", "5d43053", "10d1620", "b37bee2",
         "0d02c0b", "e78c2a0", "b0050e3", "dc17a9d", "743df06", "cb9e6b7",
         "a22929c", "8fd6c82", "5e1218e", "61a7981", "ea55870", "16bc5af"]


def newest_capture_per_company() -> dict:
    universe = json.loads((ROOT / "UNIVERSE.json").read_text("utf-8"))
    by_name = {c["entry_name"]: c for c in universe["companies"]}
    latest = {}
    for sha in ORDER:
        for manifest in sorted((CAPTURES / sha).glob("*/manifest.json")):
            try:
                m = json.loads(manifest.read_text("utf-8"))
            except Exception:                               # noqa: BLE001
                continue
            name = m.get("company")
            if name in by_name:
                latest[name] = (sha, manifest.parent, m)
    return by_name, latest


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    out_path = pathlib.Path(argv[0]) if argv else None
    by_name, latest = newest_capture_per_company()

    rows, mech, texts = [], {}, {}
    for name in sorted(by_name):
        if name not in latest:
            rows.append({"company": name, "core_mean": None, "core_min": None,
                         "core_unmeasured": ["NO_CAPTURE"], "dimensions": [],
                         "deployed_sha": "", "outcome": "NOT_EXECUTED"})
            continue
        sha, cdir, manifest = latest[name]
        ticker = by_name[name].get("ticker") or ""
        row = Q.score_company(cdir, tickers=(ticker,))
        row["sha"] = sha
        row["outcome"] = manifest.get("outcome") or "NO_OUTCOME"
        row["first_useful"] = manifest.get("first_useful")
        rows.append(row)
        try:
            mech[name] = [f["code"] for f in verdict(str(cdir))
                          .get("failures", [])]
        except Exception as exc:                            # noqa: BLE001
            mech[name] = [f"VERDICT_ERROR:{type(exc).__name__}"]
        texts[name] = cdir

    g = Q.gate(rows)
    clean = sorted(n for n, f in mech.items() if not f)
    print(f"EXECUTED            {sum(1 for r in rows if r.get('sha'))}/{len(rows)}")
    print(f"MECHANICAL_PASS     {len(clean)}/{len(mech)}")
    print(f"CORE_MEAN           {g['core_mean']}")
    print(f"CORE_MIN            {g['core_min']}")
    print(f"EXECUTIVE_QUALITY   {'PASS' if g['passes'] else 'FAIL'}")

    print("\nWHICH DIMENSIONS COST THE MOST, across all fifty")
    tally = collections.defaultdict(list)
    for r in rows:
        for d in r.get("dimensions", ()):
            if d["score"] is not None:
                tally[d["dimension"]].append(d["score"])
    for k in sorted(tally, key=lambda k: statistics.mean(tally[k])):
        v = tally[k]
        core = "CORE" if k in Q.CORE else "    "
        print(f"  {core} {k:<22}mean={statistics.mean(v):>5.1f}  "
              f"zeros={sum(1 for x in v if x == 0):>3}  "
              f"threes={sum(1 for x in v if x == 3):>3}  n={len(v)}")

    print("\nMECHANICAL FAILURES, most common first")
    codes = collections.Counter(c for f in mech.values() for c in f)
    for code, n in codes.most_common(12):
        who = [w for w, f in mech.items() if code in f][:4]
        print(f"  {code:<34}{n:>3}  {', '.join(x[:18] for x in who)}")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {"gate": g, "rows": rows, "mechanical": mech}, indent=1), "utf-8")
        print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
