"""Measure strategic-reading yield and the blocked_by distribution.

Runs the REAL Founder Intelligence ingestion + the opportunity reasoner over
every offline company fixture — eleven distinct companies, each on its own
domain, including the deliberately hard ones (blocked, nonexistent, a local
business, a hostile site). Deterministic and network-free.
"""
import collections
import json
import pathlib
import sys
import tempfile

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.market.daily import _report_for
from intent_engine.market.evidence import founder_intelligence_research_fn
from intent_engine.market.opportunity import classify
from intent_engine.market.signals import baseline_market_evidence
from intent_engine.product_eval.sites import SITES, site_transport

AS_OF = "2026-07-30"


class _Co:
    def __init__(self, site):
        self.company_id = site.key
        self.canonical_name = site.name
        self.website = site.website
        self.strategic_priorities = []
        # public fixtures are treated as tradable so the reasoner reaches the
        # evidence gates rather than exiting at `not_tradable`; that gate is
        # already measured and is not what this run is about.
        self.tradable_instrument = ("TST" if site.company_type == "public"
                                    else None)


def main():
    rows = []
    for key, site in SITES.items():
        tmp = pathlib.Path(tempfile.mkdtemp())
        ci = CompanyIngestionService(tmp / "ci.jsonl",
                                     transport=site_transport(site),
                                     resolver=False)
        fi = FounderIntelligenceService(tmp / "fi.jsonl")
        research = founder_intelligence_research_fn(ci, fi, max_sources=8)
        company = _Co(site)
        try:
            out = research(company, AS_OF)
        except Exception as exc:                       # noqa: BLE001
            out = {"evidence": [], "thesis": "", "error": type(exc).__name__}
        # A deterministic price series per company: a fixed drift so the
        # baseline has something real to read, and no randomness so the
        # measurement is reproducible.
        drift = {"shopify": 0.9, "palantir": -0.7, "sony": 0.2}.get(key, 0.0)

        def _price_at(symbol, day, _d=drift):
            idx = int(day[-2:])
            return 100.0 + _d * idx

        market = (baseline_market_evidence(
                      _price_at, company.tradable_instrument,
                      [f"2026-07-{d:02d}" for d in range(1, 31)])
                  if company.tradable_instrument else None)
        opp = classify(company, _report_for(out, out.get("evidence")),
                       as_of=AS_OF, market=market)
        rows.append({
            "company": key,
            "type": site.company_type,
            "evidence": len(out.get("evidence") or []),
            "thesis": bool(out.get("thesis")),
            "classification": opp.classification,
            "gate": opp.blocked_by[0] if opp.blocked_by else "",
            "quality": opp.quality,
            "dated": opp.dated_evidence_count,
            "indep": opp.independent_source,
            "resolvable": opp.to_signal() is not None,
            "src": opp.market_source,
        })

    print(f"{'company':<14}{'type':<9}{'ev':>3}{'dated':>6}{'ind':>5}"
          f"{'thesis':>7}  {'class':<9}{'gate':<22}{'q':>5}")
    print("-" * 84)
    for r in sorted(rows, key=lambda r: (-r["quality"], r["company"])):
        print(f"{r['company']:<14}{r['type']:<9}{r['evidence']:>3}"
              f"{r['dated']:>6}{str(r['indep']):>5}{str(r['thesis']):>7}  "
              f"{r['classification']:<9}{r['gate']:<22}{r['quality']:>5}")

    tradable = [r for r in rows if r["type"] == "public"]
    with_ev = [r for r in rows if r["evidence"] > 0]
    with_thesis = [r for r in rows if r["thesis"]]
    print()
    print(f"companies                : {len(rows)}")
    print(f"produced any evidence    : {len(with_ev)}/{len(rows)} "
          f"({len(with_ev)/len(rows):.0%})")
    print(f"STRATEGIC-READING YIELD  : {len(with_thesis)}/{len(rows)} "
          f"({len(with_thesis)/len(rows):.0%})   "
          f"[of those with evidence: "
          f"{len(with_thesis)}/{len(with_ev)} "
          f"({(len(with_thesis)/len(with_ev) if with_ev else 0):.0%})]")
    print(f"view-withheld rate       : "
          f"{sum(1 for r in with_ev if not r['thesis'])}/{len(with_ev)} "
          f"of companies WITH evidence")
    print(f"independent source found : "
          f"{sum(1 for r in rows if r['indep'])}/{len(rows)}")
    print()
    print("blocked_by:", json.dumps(
        dict(collections.Counter(r["gate"] for r in rows)), indent=1))
    print("classification:", json.dumps(
        dict(collections.Counter(r["classification"] for r in rows)), indent=1))
    gradable = [r for r in rows if r["resolvable"]]
    print("tradable fixtures:", len(tradable))
    print()
    print(f"LEARNING VELOCITY (gradable evaluations/cycle): {len(gradable)}")
    for r in gradable:
        print(f"   {r['company']:<12} {r['classification']:<5} via {r['src']}")
    return rows


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
