"""Search and identity matrix for prospect-98 through the product's own suggest().

Variants per company (Section 6): full analysis-target name, the as-listed name,
the legal name, each registry alias, the domain, ticker (when listed), a
lower-case and an upper-case form, a 3+-char prefix, and one typographical
variant (adjacent transposition). A query is:

  PASS        first suggestion carries the verified domain, or the company's
              current/former CIK when its row has no domain
  WRONG_FIRST first suggestion is a DIFFERENT company (a wrong-company risk)
  EMPTY       nothing offered (a visitor must type the website)
  BOUNDED_EXACT_TICKER another company owns the exact typed ticker

search_status: PASS (full name passes, nothing WRONG_FIRST), PARTIAL (full name
passes, some variant is WRONG_FIRST/EMPTY), FAIL. WRONG_FIRST on the FULL name
is reported separately as an identity hazard: it is what produces a
wrong-company analysis.

  PYTHONPATH=<tree>/src python scripts/prospect98/search98.py --out F
"""
from __future__ import annotations
import argparse, json, pathlib, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
from intent_engine.company_ingestion import suggest as SG  # noqa: E402


def _typo(s):
    s = s.strip()
    return s[:1] + s[2] + s[1] + s[3:] if len(s) >= 4 else s


def variants(c):
    v = [("full", c["analysis_target"]), ("listed", c["name_as_listed"]), ("legal", c["legal_name"])]
    v += [("alias", a) for a in c["aliases"]]
    v += [("domain", c["primary_domain"]), ("lower", c["analysis_target"].lower()),
          ("upper", c["analysis_target"].upper()),
          ("prefix", c["analysis_target"][:max(3, len(c["analysis_target"]) // 2)]),
          ("typo", _typo(c["analysis_target"]))]
    if c.get("public_listing"):
        v.append(("ticker", c["public_listing"]["ticker"]))
    seen, out = set(), []
    for k, q in v:
        if q and q.lower() not in seen:
            seen.add(q.lower()); out.append((k, q))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    ap.add_argument("--splits", default="DEVELOPMENT,VALIDATION,FINAL_UNTOUCHED")
    a = ap.parse_args()
    reg = [c for c in json.loads((ROOT / "docs/engineering/prospect98/IDENTITY_REGISTRY.json").read_text())["companies"]
           if c["split"] in a.splits.split(",")]
    t0 = time.perf_counter(); SG.suggest("Hammer"); cold = (time.perf_counter() - t0) * 1000
    rows, times = [], []
    for c in reg:
        ciks = {x for x in [(c.get("public_listing") or {}).get("cik"), (c.get("former_sec_filer") or {}).get("cik")] if x}
        dom = c["primary_domain"].removeprefix("www.")
        res = []
        for kind, q in variants(c):
            t = time.perf_counter(); got = SG.suggest(q); ms = (time.perf_counter() - t) * 1000; times.append(ms)
            got = [g if isinstance(g, dict) else getattr(g, "__dict__", {"repr": repr(g)}) for g in (got or [])]
            first = got[0] if got else None
            if not first:
                verdict = "EMPTY"
            else:
                fd = str(first.get("domain") or first.get("primary_domain") or "").removeprefix("www.")
                fc = str(first.get("cik") or first.get("sec_cik") or "").lstrip("0")
                if (fd and fd == dom) or (fc and fc in {x.lstrip("0") for x in ciks}):
                    verdict = "PASS"
                elif kind == "ticker" and str(first.get("ticker") or "").upper() == q.upper():
                    verdict = "BOUNDED_EXACT_TICKER"
                else:
                    verdict = "WRONG_FIRST"
            res.append({"kind": kind, "typed": q, "verdict": verdict, "ms": round(ms, 1),
                        "top": (first or {}).get("legal_name") or (first or {}).get("common_name") if first else None,
                        "top_domain": (first or {}).get("domain") if first else None,
                        "top_cik": (first or {}).get("cik") if first else None})
        full = next(r for r in res if r["kind"] == "full")
        bad = [r for r in res if r["verdict"] in ("WRONG_FIRST", "EMPTY")]
        status = ("PASS" if full["verdict"] == "PASS" and not bad else
                  "PARTIAL" if full["verdict"] == "PASS" else "FAIL")
        rows.append({"prospect_id": c["position"], "company": c["analysis_target"], "split": c["split"],
                     "search_status": status, "full_name_verdict": full["verdict"],
                     "wrong_company_hazards": [r for r in res if r["verdict"] == "WRONG_FIRST"],
                     "queries": res})
    summ = {"companies": len(rows), "cold_ms": round(cold, 1),
            "p50_ms": round(statistics.median(times), 1), "p95_ms": round(sorted(times)[int(.95 * len(times))], 1),
            "status": {s: sum(r["search_status"] == s for r in rows) for s in ("PASS", "PARTIAL", "FAIL")},
            "full_name": {v: sum(r["full_name_verdict"] == v for r in rows) for v in ("PASS", "EMPTY", "WRONG_FIRST")},
            "companies_with_wrong_first_any_variant": sum(1 for r in rows if r["wrong_company_hazards"])}
    pathlib.Path(a.out).write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, default=str))
    print(json.dumps(summ, indent=1))
    for r in rows:
        if r["full_name_verdict"] == "WRONG_FIRST":
            q = next(x for x in r["queries"] if x["kind"] == "full")
            print("  FULL-NAME WRONG:", r["prospect_id"], r["company"], "->", q["top"], q["top_domain"], q["top_cik"])


if __name__ == "__main__":
    main()
