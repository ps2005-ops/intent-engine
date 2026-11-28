"""The ORIGINAL search metric (scripts/prospect100/search_matrix.py) applied to
prospect-98: the same queries (live_pass._prefixes(typed) + typed) and the same
verdict rules, copied line for line and keyed by the prospect-98 entity id.
A baseline tree with no prospect-98 catalog has no entity ids, so every query
there is EMPTY or WRONG_FIRST by construction -- that IS its baseline.

  PYTHONPATH=<tree>/src python scripts/prospect98/search_matrix98.py --out F
"""
from __future__ import annotations
import json, pathlib, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/prospect100"))
from intent_engine.company_ingestion import suggest as SG  # noqa: E402
from live_pass import _prefixes  # noqa: E402

TYPED = {59: "Runway Financial", 48: "Safe Security", 63: "Chargebee"}
EIDS = {59: "cfo-ai", 48: "safe-security", 40: "zip-procurement", 13: "writer-ai", 95: "launch-consulting"}


def main():
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    reg = json.loads((ROOT / "docs/engineering/prospect98/IDENTITY_REGISTRY.json").read_text())["companies"]
    try:
        from intent_engine.company_ingestion.catalog_prospects98 import PROSPECT98_CATALOG
        eid = {r["prospect98_position"]: r["entity_id"] for r in PROSPECT98_CATALOG}
    except ImportError:
        eid = {}
    SG.suggest("Hammer")
    rows, times = [], []
    for r in reg:
        pid = r["position"]; want = eid.get(pid, "<unregistered>")
        typed = TYPED.get(pid) or r["analysis_target"]
        results = []
        for q in _prefixes(typed) + [typed]:
            t = time.perf_counter(); got = SG.suggest(q); times.append((time.perf_counter() - t) * 1000)
            top = got[0] if got else None
            verdict = "EMPTY"
            if top is not None:
                if top.entity_id == want:
                    verdict = "PASS"
                elif top.ticker and top.ticker.upper() == q.strip().upper():
                    verdict = "BOUNDED_EXACT_TICKER"
                elif (top.match == SG.LEADING and any(g.entity_id == want and g.match == SG.LEADING for g in got)
                      and len(top.common_name or top.legal_name) <= len(typed)):
                    verdict = "BOUNDED_SHARED_PREFIX"
                else:
                    verdict = "WRONG_FIRST"
            results.append({"typed": q, "verdict": verdict, "top": top.legal_name if top else None,
                            "top_ticker": top.ticker if top else None})
        found = any(x["verdict"] == "PASS" for x in results)
        wrong = [x for x in results if x["verdict"] in ("WRONG_FIRST", "EMPTY")]
        rows.append({"prospect_id": pid, "entity_id": want, "typed": typed, "split": r["split"], "queries": results,
                     "search_status": ("PASS" if found and not wrong else "FAIL" if not found else "PARTIAL_WRONG_PREFIX")})
    times.sort()
    summ = {"companies": len(rows), "pass": sum(r["search_status"] == "PASS" for r in rows),
            "partial": [r["typed"] for r in rows if r["search_status"] == "PARTIAL_WRONG_PREFIX"],
            "fail": [r["typed"] for r in rows if r["search_status"] == "FAIL"],
            "shared_prefix": [(r["typed"], q["typed"], q["top"]) for r in rows for q in r["queries"] if q["verdict"] == "BOUNDED_SHARED_PREFIX"],
            "p50_ms": round(statistics.median(times), 2), "p95_ms": round(times[int(.95 * len(times))], 2)}
    out.write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))
    print(json.dumps({k: (v if not isinstance(v, list) else (len(v), v[:12])) for k, v in summ.items()}, indent=1))


if __name__ == "__main__":
    main()
