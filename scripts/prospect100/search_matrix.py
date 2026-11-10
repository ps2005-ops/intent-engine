"""Every prospect, every prefix, through the product's own suggest() -- the
live harness's rule applied locally to all 100.

For each prospect: the three prefixes the live pass types plus the full name.
A query passes when the first suggestion carries the prospect's entity id; an
exact ticker match on another company is BOUNDED (recorded with the ticker,
never waived by name), exactly as public_journey_ten treats it. Timing is the
in-process suggest() call with the real SEC registrant table loaded (warm),
plus one cold call measured first.

Usage: PYTHONPATH=src python scripts/prospect100/search_matrix.py [--out f]
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402

from intent_engine.company_ingestion import suggest as SG  # noqa: E402
from live_pass import TYPED, _prefixes  # noqa: E402

REG = ROOT / "docs/engineering/prospect100/PROSPECT_REGISTRY.yaml"


def main() -> int:
    out_path = ROOT / "docs/engineering/prospect100/search_matrix.json"
    if "--out" in sys.argv:
        out_path = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    reg = yaml.safe_load(REG.read_text())["prospects"]
    t0 = time.perf_counter()
    SG.suggest("Hammer")
    cold_ms = (time.perf_counter() - t0) * 1000
    times, rows = [], []
    for r in reg:
        pid = r["prospect_id"]
        typed = TYPED.get(pid) or r.get("common_name") or r["name_as_listed"]
        queries = _prefixes(typed) + [typed]
        results = []
        for q in queries:
            t = time.perf_counter()
            got = SG.suggest(q)
            times.append((time.perf_counter() - t) * 1000)
            top = got[0] if got else None
            verdict = "EMPTY"
            if top is not None:
                if top.entity_id == r["entity_id"]:
                    verdict = "PASS"
                elif top.ticker and top.ticker.upper() == q.strip().upper():
                    verdict = "BOUNDED_EXACT_TICKER"
                elif (top.match == SG.LEADING
                      and any(g.entity_id == r["entity_id"]
                              and g.match == SG.LEADING for g in got)
                      and len(top.common_name or top.legal_name)
                      <= len(typed)):
                    # A SHARED PREFIX, NOT A WRONG ANSWER: another company's
                    # name begins with the typed text just as fully, is no
                    # longer, and the prospect is still in the visible list.
                    # Recorded with the competing name, never counted a pass.
                    verdict = "BOUNDED_SHARED_PREFIX"
                else:
                    verdict = "WRONG_FIRST"
            results.append({"typed": q, "verdict": verdict,
                            "top": top.legal_name if top else None,
                            "top_ticker": top.ticker if top else None,
                            "status_shown": bool(top and top.status)})
        found = any(x["verdict"] == "PASS" for x in results)
        wrong = [x for x in results if x["verdict"] in ("WRONG_FIRST", "EMPTY")]
        rows.append({"prospect_id": pid, "entity_id": r["entity_id"],
                     "typed": typed, "queries": results,
                     "search_status": ("PASS" if found and not wrong else
                                       "FAIL" if not found else
                                       "PARTIAL_WRONG_PREFIX")})
    times.sort()
    summary = {
        "prospects": len(rows),
        "pass": sum(r["search_status"] == "PASS" for r in rows),
        "partial": [(r["prospect_id"], r["typed"],
                     [q["typed"] + "->" + str(q["top"]) for q in r["queries"]
                      if q["verdict"] in ("WRONG_FIRST", "EMPTY")])
                    for r in rows if r["search_status"] == "PARTIAL_WRONG_PREFIX"],
        "fail": [(r["prospect_id"], r["typed"]) for r in rows
                 if r["search_status"] == "FAIL"],
        "bounded_exact_ticker": [(r["prospect_id"], q["typed"], q["top"])
                                 for r in rows for q in r["queries"]
                                 if q["verdict"] == "BOUNDED_EXACT_TICKER"],
        "bounded_shared_prefix": [(r["prospect_id"], q["typed"], q["top"])
                                  for r in rows for q in r["queries"]
                                  if q["verdict"] == "BOUNDED_SHARED_PREFIX"],
        "queries": len(times),
        "cold_first_query_ms": round(cold_ms, 1),
        "warm_p50_ms": round(statistics.median(times), 2),
        "warm_p95_ms": round(times[int(len(times) * 0.95) - 1], 2),
        "warm_max_ms": round(times[-1], 2),
        "registrant_table_loaded": bool(SG._TICKERS) if hasattr(SG, "_TICKERS") else None,
    }
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0 if not summary["fail"] and not summary["partial"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
