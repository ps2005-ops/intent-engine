"""§30: the SAME production path, locally, over the real network, traced.

WHY A CONTROL AND NOT ANOTHER DEPLOYED RUN. Every explanation of the deployed
CORE latency so far has been a ratio between two runs that differed in more
than one variable -- fixtures vs live network, model key vs no model key,
one-run ledger vs production ledger. Two such explanations were confidently
wrong. This runs the real worker, with the real transport, against the real
internet, and records the same spans the deployed service records, so the
comparison differs in ONE thing: where it executes.

Deep is left off. The model is not on the CORE path and a provider key is not
present here, so including it would reintroduce exactly the confound that
made "the model is the bottleneck" survive a cycle.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from intent_engine.webapp.app import WebApp                    # noqa: E402
from intent_engine.webapp.config import AppConfig              # noqa: E402


def run_one(name: str, website: str, cik: str = "") -> dict:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="perf-control-"))
    app = WebApp(AppConfig(env="development", secret="x" * 40,
                           web_store_path=tmp / "w.jsonl",
                           fi_store_path=tmp / "f.jsonl",
                           ci_store_path=tmp / "ci.jsonl"))
    run = app.ci.create_run(company_name=name, website=website, cik=cik,
                            user_id="control",
                            as_of=_dt.date.today().isoformat())
    rid = run["run_id"]
    from intent_engine.company_ingestion.deadline import Deadline
    app._analysis_deadlines[rid] = Deadline.for_tier(app._tier_for(rid))
    app.ci.mark_lifecycle(rid, "accepted")

    began = time.monotonic()
    app._run_analysis("control", rid)
    wall = time.monotonic() - began

    phases = app.ci.trace(rid)
    core = next((p for p in phases if p.get("phase") == "core"), {})
    return {"company": name, "run_id": rid,
            "wall_s": round(wall, 1),
            "documents": len(list(app.ci.store.retrieved(rid))),
            "lifecycle": app.ci.lifecycle(rid),
            "waterfall": core}


def show(row: dict) -> None:
    print(f"\n=== {row['company']}  wall={row['wall_s']}s  "
          f"documents={row['documents']} ===")
    wf = row.get("waterfall") or {}
    if not wf:
        print("  no core waterfall recorded"); return
    print(f"  {'span':<20}{'wall_ms':>10}{'cpu_ms':>10}{'cpu%':>7}  detail")
    for s in wf.get("spans", []):
        w, c = s.get("wall_ms", 0.0), s.get("cpu_ms", 0.0)
        pct = f"{(c / w * 100):.0f}%" if w else "-"
        detail = " ".join(f"{k}={v}" for k, v in s.items()
                          if k in ("item_count", "candidates", "status"))
        print(f"  {s['name']:<20}{w:>10.1f}{c:>10.1f}{pct:>7}  {detail}")
    print(f"  {'TOTAL':<20}{wf.get('total_wall_ms', 0):>10.1f}"
          f"{wf.get('total_cpu_ms', 0):>10.1f}")
    print(f"  {'unaccounted':<20}{wf.get('unaccounted_wall_ms', 0):>10.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="Apple Inc.")
    ap.add_argument("--website", default="https://apple.com")
    ap.add_argument("--cik", default="0000320193")
    ap.add_argument("--out", default="reports/perf/local_control.json")
    a = ap.parse_args()
    row = run_one(a.company, a.website, a.cik)
    show(row)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(row, indent=2))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
