"""Search acceptance on the DEPLOYED preview: every prospect, every prefix.

The same rule as `search_matrix.py` (first suggestion must carry the
prospect's entity id; an exact ticker or a shared prefix is BOUNDED and
recorded with the competing name), but through the live `/api/companies`
endpoint the combobox calls, spaced so it is not a burst. Autocomplete is not
an analysis, so it spends none of the demo quota.

Usage: .venv/bin/python scripts/prospect100/live_search.py
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402

import public_journey_ten as PJT  # noqa: E402
from live_pass import TYPED, _prefixes  # noqa: E402
from perf_progressive_matrix import _opener, _req  # noqa: E402


def main() -> int:
    reg = yaml.safe_load((ROOT / "docs/engineering/prospect100/"
                          "PROSPECT_REGISTRY.yaml").read_text())["prospects"]
    op, _jar = _opener()
    _st, ver, *_ = _req(op, "/version")
    _req(op, "/demo")
    rows, times = [], []
    for r in reg:
        typed = TYPED.get(r["prospect_id"]) or r.get("common_name") \
            or r["name_as_listed"]
        verdicts = []
        for q in _prefixes(typed) + [typed]:
            got, took, _code = PJT.suggest_live(op, q)
            times.append(took)
            top = got[0] if got else {}
            ids = [g.get("entity_id") for g in got]
            if top.get("entity_id") == r["entity_id"]:
                v = "PASS"
            elif str(top.get("ticker") or "").upper() == q.strip().upper():
                v = "BOUNDED_EXACT_TICKER"
            elif r["entity_id"] in ids:
                v = "BOUNDED_SHARED_PREFIX"
            else:
                v = "WRONG_FIRST" if got else "EMPTY"
            verdicts.append({"typed": q, "verdict": v,
                             "top": top.get("legal_name")})
            time.sleep(0.25)
        ok = any(x["verdict"] == "PASS" for x in verdicts) and not any(
            x["verdict"] in ("WRONG_FIRST", "EMPTY") for x in verdicts)
        rows.append({"prospect_id": r["prospect_id"], "typed": typed,
                     "status": "PASS" if ok else "FAIL",
                     "queries": verdicts})
    times.sort()
    summary = {
        "served": json.loads(ver).get("commit") if ver.startswith("{") else ver,
        "prospects": len(rows),
        "pass": sum(r["status"] == "PASS" for r in rows),
        "fail": [(r["prospect_id"], r["typed"],
                  [q for q in r["queries"]
                   if q["verdict"] in ("WRONG_FIRST", "EMPTY")])
                 for r in rows if r["status"] == "FAIL"],
        "bounded": [(r["prospect_id"], q["typed"], q["verdict"], q["top"])
                    for r in rows for q in r["queries"]
                    if q["verdict"].startswith("BOUNDED")],
        "round_trip_p50_ms": round(statistics.median(times) * 1000),
        "round_trip_p95_ms": round(times[int(len(times) * .95) - 1] * 1000),
    }
    out = ROOT / "docs/engineering/prospect100/live_search_deployed.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "bounded"},
                     indent=1))
    print("bounded:", len(summary["bounded"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
