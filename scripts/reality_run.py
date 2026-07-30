"""First contact with reality: the real pipeline, real companies, live network.

Every measurement in this project so far has run against offline fixtures. This
runs the actual Founder Intelligence ingestion over the real websites of the
real universe and classifies each company with the real reasoner.

No prices: those need a credential this environment does not have, so the
market-evidence step is deliberately absent and every company will stop at
`no_market_evidence` at best. That is the honest ceiling of what reality
exposure is available today, and it is still the first real evidence the engine
has ever seen.
"""
import collections
import json
import pathlib
import sys
import tempfile
import time

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.market.coverage import assess, concentration
from intent_engine.market.daily import _report_for
from intent_engine.market.evidence import founder_intelligence_research_fn
from intent_engine.market.opportunity import classify
from intent_engine.universe.companies import default_universe

AS_OF = "2026-07-30"
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/reality")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    universe = default_universe()
    companies = universe.prediction_companies()
    rows = []
    started = time.time()

    for i, company in enumerate(companies, 1):
        tmp = pathlib.Path(tempfile.mkdtemp())
        ci = CompanyIngestionService(tmp / "ci.jsonl", resolver=False)
        fi = FounderIntelligenceService(tmp / "fi.jsonl")
        research = founder_intelligence_research_fn(ci, fi, max_sources=8)
        t0 = time.time()
        try:
            out = research(company, AS_OF)
        except Exception as exc:                       # noqa: BLE001
            out = {"evidence": [], "thesis": "", "error": type(exc).__name__}
        opp = classify(company, _report_for(out, out.get("evidence")),
                       as_of=AS_OF)
        rows.append({
            "company": company.company_id,
            "sector": company.sector, "cap": company.market_cap,
            "region": company.region,
            "evidence": len(out.get("evidence") or []),
            "thesis": bool(out.get("thesis")),
            "dated": opp.dated_evidence_count,
            "indep": opp.independent_source,
            "classification": opp.classification,
            "gate": opp.blocked_by[0] if opp.blocked_by else "",
            "quality": opp.quality,
            "error": out.get("error", ""),
            "seconds": round(time.time() - t0, 1),
        })
        print(f"[{i}/{len(companies)}] {company.company_id:<18}"
              f"ev={rows[-1]['evidence']:<3} thesis={str(rows[-1]['thesis']):<5} "
              f"gate={rows[-1]['gate']:<22} {rows[-1]['seconds']}s",
              flush=True)

    (OUT / "reality.json").write_text(json.dumps(rows, indent=1))

    with_ev = [r for r in rows if r["evidence"] > 0]
    with_th = [r for r in rows if r["thesis"]]
    indep = [r for r in rows if r["indep"]]
    errors = [r for r in rows if r["error"]]
    print("\n" + "=" * 66)
    print(f"companies (REAL, live network) : {len(rows)}")
    print(f"produced evidence              : {len(with_ev)}/{len(rows)} "
          f"({len(with_ev)/len(rows):.0%})")
    print(f"STRATEGIC-READING YIELD        : {len(with_th)}/{len(rows)} "
          f"({len(with_th)/len(rows):.0%})")
    print(f"independent source found       : {len(indep)}/{len(rows)}")
    print(f"errors                         : {len(errors)}")
    print(f"wall clock                     : {round(time.time()-started)}s")
    print("\nblocked_by:", json.dumps(
        dict(collections.Counter(r["gate"] for r in rows)), indent=1))
    reached = [r for r in rows if r["thesis"]]
    if reached:
        print("\ncompanies that formed a reading:")
        for r in sorted(reached, key=lambda r: -r["quality"]):
            print(f"   {r['company']:<18}{r['sector']:<24}"
                  f"q={r['quality']:<6} gate={r['gate']}")
    cov = assess(default_universe().prediction_companies(),
                 expected={"sector": sorted({r['sector'] for r in rows if r['sector']})})
    print(f"\nsector concentration: {concentration(companies,'sector')}")
    return rows


if __name__ == "__main__":
    main()
