"""Cross-domain proof: does the economy reach a company, and the company the economy?

WHAT THIS PROVES, AND WHAT IT REFUSES TO ASSUME
------------------------------------------------
Two directions, on real retrieval, over named control companies:

    market economic state -> company economic state -> decision input
    company public evidence -> candidate indicator -> market learning

and one wall:

    a candidate indicator may not corroborate the evidence it was built from

Nothing here is a fixture. Each company is retrieved live through the same
`CompanyIngestionService` the founder product uses, its observations are
derived by the same `strategic_intelligence` code the demo renders, and the
economic state is whatever the market engine last published to the shared
core. If a company retrieves nothing, this reports that it retrieved nothing.

WHY IT ALSO RUNS THE MARKET ENGINE'S OWN EXPOSURE PATTERNS
-----------------------------------------------------------
`company_exposure` is how the market side conditions a macro state on a
specific company, and measured against the live ledger it rates FOUR
exposures across 28 companies. The corpus it reads is news headlines with a
median length of 95 characters, and its patterns need a sentence in which the
company is the subject of a dependency -- a construction headlines do not
contain. The founder side retrieves filings and extracts section prose. So
this runs the same patterns over both texts for the same company, which is
the measurement that says whether unification fixes it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
import traceback
from typing import Dict, List, Optional, Tuple

#: The Section 34 controls, with the domain each is retrieved from.
CONTROLS: Tuple[Tuple[str, str], ...] = (
    ("Cloudflare, Inc.", "https://www.cloudflare.com"),
    ("JPMorgan Chase & Co.", "https://www.jpmorganchase.com"),
    ("Caterpillar Inc.", "https://www.caterpillar.com"),
    ("NVIDIA Corporation", "https://www.nvidia.com"),
    ("Meta Platforms, Inc.", "https://about.meta.com"),
    ("Walmart Inc.", "https://corporate.walmart.com"),
)


def retrieve(name: str, website: str, *, as_of: str, max_sources: int
             ) -> Dict:
    """One company, through the real founder ingestion path."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    tmp = pathlib.Path(tempfile.mkdtemp())
    ci = CompanyIngestionService(tmp / "ci.jsonl", resolver=False)
    fi = FounderIntelligenceService(tmp / "fi.jsonl")
    run = ci.create_run(company_name=name, website=website,
                        user_id="econ-proof", as_of=as_of)
    run_id = run["run_id"]
    candidates = ci.discover(run_id)
    # FILINGS FIRST, AND THAT ORDERING IS THE POINT. Website discovery
    # returns pricing pages, about pages and blog indexes -- 19,518
    # characters of real prose for Cloudflare, and not one sentence in which
    # the company is the subject of an economic dependency. The exposure
    # language this proof is looking for is in Item 7 and Item 7A of an
    # annual report, so an approval budget spent on marketing pages measures
    # nothing. Filings are sorted to the front of the approval list.
    def _is_filing(candidate) -> bool:
        url = str(candidate.get("url") or candidate.get("final_url") or "")
        return ("sec.gov" in url
                or str(candidate.get("source_type") or "")
                in ("regulatory_filing", "filing", "annual_report"))

    ordered = ([c for c in candidates if _is_filing(c)]
               + [c for c in candidates if not _is_filing(c)])
    ids = [c["candidate_id"] for c in ordered][:max_sources]
    ci.approve(run_id, user_id="econ-proof", approved_ids=ids,
               rejected_ids=[])
    fetch = ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    report = (result or {}).get("strategic_report") or {}
    # The RETRIEVED ROWS, not the fetch summary. `fetch_approved` returns
    # {"ok": n, "failed": [...]}; the documents themselves are in the store,
    # which is also where the founder surfaces read them from.
    documents = [dict(d, observation_id=d.get("source_id") or "")
                 for d in ci.store.retrieved(run_id) if isinstance(d, dict)]
    return {"run_id": run_id, "name": name,
            "fetch": {"ok": fetch.get("ok"),
                      "failed": len(fetch.get("failed") or []),
                      "candidates": len(candidates), "approved": len(ids)},
            "documents": documents,
            "observations": [o for o in (report.get("observations") or ())
                             if isinstance(o, dict)],
            "retrieved": len(documents)}


def exposure_comparison(company_id: str, documents: List[dict],
                        ledger_rows: List[dict]) -> Dict:
    """The same patterns over headline text and over filing prose."""
    from intent_engine.market import company_exposure as CX

    def hits(texts: List[str]) -> Dict[str, str]:
        found: Dict[str, str] = {}
        for text in texts:
            for sentence in CX._sentences(text):
                for dimension, pattern in CX._COMPILED:
                    if dimension in found:
                        continue
                    if pattern.search(sentence):
                        found[dimension] = sentence[:160]
        return found

    headlines = [str(r.get("fact") or "") for r in ledger_rows
                 if r.get("record") == "evidence"
                 and r.get("subject_company") == company_id]
    prose = [str(d.get("text_content") or "") for d in documents]
    return {
        "headline_rows": len(headlines),
        "headline_chars": sum(len(t) for t in headlines),
        "headline_exposures": hits(headlines),
        "filing_documents": len(prose),
        "filing_chars": sum(len(t) for t in prose),
        "filing_exposures": hits(prose),
    }


def _ledger_id(company_id: str, ledger_rows: List[dict]) -> str:
    """The id the market ledger files this company under, or the slug.

    Prefix match on the slug's leading token, because the two sides derive
    their ids from the same name by different rules and neither can be
    changed without rewriting an append-only ledger.
    """
    known = {str(r.get("subject_company") or "") for r in ledger_rows
             if r.get("record") == "evidence"}
    head = company_id.split("-")[0]
    for candidate in sorted(known):
        if candidate == head or candidate.startswith(head + "_"):
            return candidate
    return company_id.replace("-", "_")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--ledger", default="")
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    from intent_engine.econ import aggregates as AG
    from intent_engine.econ import company as CO
    from intent_engine.econ import evidence as EV
    from intent_engine.econ import lineage as LI
    from intent_engine.econ import store as EST
    from intent_engine.external_intel import econ_context as EC
    from intent_engine.external_intel import econ_evidence as EE

    root = pathlib.Path(args.root)
    ledger_rows: List[dict] = []
    if args.ledger and pathlib.Path(args.ledger).exists():
        for line in pathlib.Path(args.ledger).read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                try:
                    ledger_rows.append(json.loads(line))
                except ValueError:
                    pass

    economy = EC.load(root, as_of=args.as_of)
    out: Dict = {"as_of": args.as_of,
                 "economy": {"available": economy.available,
                             "as_of": economy.as_of,
                             "conditions_known": len(economy.known_kinds()),
                             "known": economy.known_kinds(),
                             "beliefs": len(economy.beliefs),
                             "reason": economy.reason},
                 "companies": []}

    wanted = [c for c in CONTROLS
              if not args.only or args.only.lower() in c[0].lower()]
    all_nodes: List = []
    for name, website in wanted:
        row: Dict = {"company": name}
        try:
            got = retrieve(name, website, as_of=args.as_of,
                           max_sources=args.max_sources)
        except Exception as exc:  # noqa: BLE001 - one company, not the proof
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["traceback"] = traceback.format_exc()[-600:]
            out["companies"].append(row)
            continue

        from intent_engine.external_intel import strategic_contract as SC
        company_id = SC.company_key(name)
        row["run_id"] = got["run_id"]
        row["fetch"] = got.get("fetch") or {}
        row["documents_retrieved"] = got["retrieved"]
        row["observations"] = len(got["observations"])

        # --- company -> core ------------------------------------------------
        translated = EE.translate(got["observations"], company_id=company_id,
                                  company_name=name, as_of=args.as_of,
                                  documents=got["documents"])
        row["econ_nodes"] = translated["translated"]
        row["declined"] = translated["declined"]
        if translated["nodes"]:
            EST.append_many(root, "node",
                            [n.as_dict() for n in translated["nodes"]],
                            written_at=args.as_of)
            all_nodes.extend(translated["nodes"])

        # --- the exposure measurement --------------------------------------
        # THE LEDGER KEYS ON A DIFFERENT ID. The market universe uses short
        # ids ("cloudflare"); the founder side uses a slug of the legal name
        # ("cloudflare-inc"). Matching on the slug found nothing and reported
        # it as "this company has no headline evidence", which is a bridge
        # defect wearing the costume of a finding.
        row["exposure_text"] = exposure_comparison(
            _ledger_id(company_id, ledger_rows), got["documents"],
            ledger_rows)

        # --- core -> company ------------------------------------------------
        exposures = []
        for dimension, sentence in \
                row["exposure_text"]["filing_exposures"].items():
            quantity = _QUANTITY_FOR.get(dimension)
            node = next((n for n in translated["nodes"]), None)
            if quantity and node is not None:
                exposures.append(CO.MacroExposure(
                    quantity=quantity,
                    mechanism=sentence,
                    direction="UP", evidence_node=node.node_id,
                    confidence=0.5,
                    falsifier="the company stops stating this dependency in "
                              "its own filings"))
        state = CO.build(company_id=company_id, company_name=name,
                         as_of=args.as_of, evidence=translated["nodes"],
                         economy=None, exposures=exposures)
        row["exposures"] = [e.quantity for e in exposures]
        row["transmission"] = EC.relevant_to(
            economy, exposures=[e.quantity for e in exposures])
        row["transmission_note"] = EC.transmission_note(
            economy, exposures=[e.quantity for e in exposures])
        row["company_state_uncertainty"] = state.uncertainty()
        out["companies"].append(row)
        print(f"  {name}: {got['retrieved']} docs, "
              f"{len(got['observations'])} obs, "
              f"{translated['translated']} econ nodes, "
              f"{len(exposures)} exposures", flush=True)

    # --- the aggregate, and the wall ---------------------------------------
    graph = EV.EvidenceGraph(all_nodes)
    built = AG.build_all(nodes=all_nodes, as_of=args.as_of)
    out["aggregates"] = AG.summarise(built)
    out["double_counting_wall"] = []
    for agg in built.values():
        if not agg.sufficient:
            continue
        index = graph.add(AG.as_node(agg, as_of=args.as_of))
        parent = agg.contributors[0].node_ids[0]
        verdict = LI.independent(graph, index.node_id, parent)
        out["double_counting_wall"].append({
            "index": agg.name, "independent": verdict.independent,
            "reason": verdict.reason})

    payload = json.dumps(out, indent=1, default=str)
    if args.out:
        pathlib.Path(args.out).write_text(payload, encoding="utf-8")
        print(f"\nwrote {args.out}")
    else:
        print(payload)
    return 0


#: exposure dimension -> the shared economic quantity it is an exposure TO.
_QUANTITY_FOR = {
    "RATE_EXPOSURE": "policy_rate",
    "CREDIT_EXPOSURE": "financial_conditions",
    "FX_EXPOSURE": "fx_dxy",
    "COMMODITY_EXPOSURE": "commodity_copper",
    "ENERGY_EXPOSURE": "commodity_oil",
    "LABOR_EXPOSURE": "labour",
    "SUPPLY_EXPOSURE": "industrial_production",
    "CAPITAL_INTENSITY": "business_investment",
    "REGULATORY_EXPOSURE": "fiscal",
}


if __name__ == "__main__":
    sys.exit(main())
