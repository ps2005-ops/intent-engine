#!/usr/bin/env python3
"""§6: does MINIMUM_CORE say the same thing FULL says?

Runs each company TWICE on one tree — acquisition to the end of the approved
list, and acquisition stopped at the readiness contract — then compares the
composed results field by field against the parity contract frozen in
docs/PRE100_MINIMUM_CORE_PREREGISTRATION.md.

WHAT LOCAL CAN AND CANNOT ANSWER. Identity, business model, exposures,
observations, economic state, provenance and the readiness verdict are all
computed from retrieved evidence and are the same wherever the process runs.
The model-backed strategic reading is NOT: without a reasoning key both modes
land in the same un-analysed state, so this harness reports that state rather
than pretending to have compared a reading neither run produced.

A LATENCY WIN WITH A QUALITY LOSS IS A FAIL, and the change is reverted rather
than reported with a caveat.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

COHORT = [
    ("Apple Inc.", "apple.com"),
    ("Microsoft", "microsoft.com"),
    ("NVIDIA", "nvidia.com"),
    ("Amazon", "amazon.com"),
    ("Alphabet", "abc.xyz"),
    ("Meta Platforms", "meta.com"),
    ("Walmart", "walmart.com"),
    ("JPMorgan Chase", "jpmorganchase.com"),
    ("Visa", "visa.com"),
    ("Caterpillar", "caterpillar.com"),
]

#: The fields the preregistration froze. Compared as VALUES, never as prose.
PARITY_FIELDS = ("identity", "research_mode", "readiness_state",
                 "material_level", "business_model", "families",
                 "economic_state", "result_state")


def _run(company, domain, *, core_only):
    from intent_engine.company_ingestion import sufficiency
    from intent_engine.company_ingestion.service import (
        CompanyIngestionService,
    )
    web_app = importlib.import_module("intent_engine.webapp.app").WebApp
    ci = CompanyIngestionService(pathlib.Path(tempfile.mkdtemp()) / "ci.jsonl")
    run = ci.create_run(company_name=company, website=f"https://{domain}",
                        user_id="parity", as_of=dt.date.today().isoformat())
    run_id = run["run_id"] if isinstance(run, dict) else run
    began = time.monotonic()
    candidates = ci.discover(run_id)
    approved = web_app._recommended_candidate_ids.__func__(
        web_app, candidates, refusing_hosts=ci.refusing_hosts(run_id),
        subject_cik=(ci.run_meta(run_id) or {}).get("cik"))
    ci.approve(run_id, user_id="parity", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    probe = None
    if core_only:
        meta = ci.run_meta(run_id) or {}

        def probe(documents):                               # noqa: F811
            return sufficiency.evaluate(
                documents, identity=ci.entity_identity(run_id),
                failures=list(ci.store.failures(run_id)),
                subject_cik=str(ci.subject_cik(meta) or ""))

    fetched = ci.fetch_approved(run_id, sufficiency_probe=probe)
    acquisition_s = time.monotonic() - began
    deferred_count = len(fetched.get("deferred") or ())
    unaccounted: list = []
    if core_only == "then_deferred" and fetched.get("deferred"):
        # THE CLAIM THAT ACTUALLY MATTERS. "Nothing is dropped" is a statement
        # about the run AFTER the continuation, not about the moment CORE
        # stopped blocking. Comparing only the stop-point would let deferral
        # lose every deferred source and still pass, because the stop-point is
        # supposed to have fewer documents.
        from intent_engine.company_ingestion.deadline import Deadline
        ci.fetch_approved(run_id,
                          candidate_ids=list(fetched["deferred"]),
                          deadline=Deadline.for_continuation("tier1"))
        # WITHIN ONE RUN, WHICH IS THE ONLY PLACE THIS CAN BE ANSWERED.
        #
        # Comparing a CORE run against a separate FULL run cannot distinguish
        # deferral dropping a source from a host that answered once and
        # refused once. MEASURED: Amazon came back one family short and the
        # cross-run comparison called it a loss; the within-run audit showed
        # all six deferred candidates accounted for -- three retrieved, three
        # recorded as `http_status` against g2/trustpilot/capterra, which
        # refuse every path equally. The missing family was variance.
        #
        # So the claim is tested as an ACCOUNTING property: every deferred
        # candidate is either retrieved or carries a recorded failure. A
        # source that is neither has been silently dropped, and that is the
        # only thing "nothing is dropped" can mean.
        retrieved_ids = {r["source_id"] for r in ci.store.retrieved(run_id)}
        failed_ids = {f.get("candidate_id")
                      for f in ci.store.failures(run_id)}
        unaccounted = [cid for cid in fetched["deferred"]
                       if f"src-{cid[5:]}" not in retrieved_ids
                       and cid not in failed_ids]
    # THE REAL COMPOSITION SERVICE, not a stand-in. A parity comparison over a
    # substitute measures the substitute.
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    store = pathlib.Path(tempfile.mkdtemp()) / "fi.jsonl"
    composed = ci.compose_with_quality(
        run_id, fi_service=FounderIntelligenceService(store), deep=False)
    report = (composed or {}).get("strategic_report") or {}
    documents = list(ci.store.retrieved(run_id))
    identity = ci.entity_identity(run_id) or {}
    from intent_engine.company_ingestion.coverage import family_of
    from intent_engine.company_ingestion.readiness import assess_readiness
    verdict = assess_readiness(documents=documents, identity=identity,
                               failures=list(ci.store.failures(run_id)))
    return {
        "company": company,
        "acquisition_s": round(acquisition_s, 2),
        "documents": len(documents),
        "deferred": deferred_count,
        "silently_dropped": len(unaccounted),
        "bytes": sum(d.get("byte_count", 0) for d in documents),
        # THE KEYS THE PAYLOAD ACTUALLY HAS. The first version read
        # `company_name`/`cik`, which `ci.entity_identified` does not carry --
        # so this field was "|" for every company in both modes and could not
        # have detected an identity difference if there had been one.
        "identity": "|".join(str(identity.get(k) or "") for k in (
            "entity_id", "entity_resolved", "status", "fallback_subject",
            "fallback_domain", "fallback_cik", "legal_name", "cik")),
        "research_mode": verdict.get("research_mode"),
        "readiness_state": verdict.get("state"),
        "material_level": verdict.get("material_level"),
        "families": ",".join(sorted({family_of(d) for d in documents})),
        "business_model": json.dumps(report.get("business_model"),
                                     sort_keys=True, default=str),
        "economic_state": json.dumps(report.get("economic_state"),
                                     sort_keys=True, default=str),
        "result_state": str(report.get("result_state") or ""),
        "observations": len(report.get("observations") or ()),
        "thesis": json.dumps(report.get("thesis"), sort_keys=True,
                             default=str),
        "unsourced_claims": _unsourced(report),
        "has_report": bool(report),
    }


#: The field `StrategicObservation` actually carries its provenance in.
#:
#: The first version of this read `source_id`/`source_url`/`sources` -- three
#: keys the record does not have -- so EVERY observation counted as unsourced
#: in BOTH modes, all ten rows, and the "false specificity" column was really
#: just the difference in observation COUNT. A defect that is uniform across
#: every row is a fact about the instrument, not about the product.
_PROVENANCE_FIELDS = ("source_refs", "excerpt")


def _unsourced(report) -> int:
    """FALSE SPECIFICITY: an observation asserting something with no source."""
    count = 0
    for observation in (report.get("observations") or ()):
        if not isinstance(observation, dict):
            continue
        if not any(observation.get(f) for f in _PROVENANCE_FIELDS):
            count += 1
    return count


def _self_check() -> None:
    """The scorer must be able to return a NON-ZERO count.

    A provenance check that reads the wrong key reports a clean sheet and is
    indistinguishable from a product with perfect provenance. So it is driven
    against a deliberately unsourced observation before it is trusted with
    the real ones.
    """
    sourced = {"observations": [{"text": "x", "source_refs": ["src-1"]}]}
    bare = {"observations": [{"text": "x"}]}
    assert _unsourced(sourced) == 0, "the scorer flags a SOURCED observation"
    assert _unsourced(bare) == 1, (
        "the scorer cannot detect an unsourced observation -- it is reading a "
        "field the record does not carry")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="reports/perf/minimum_core_parity.json")
    args = ap.parse_args()
    _self_check()
    cohort = [c for c in COHORT
              if not args.only or args.only.lower() in c[0].lower()]

    rows, failures = [], []
    for company, domain in cohort:
        try:
            full = _run(company, domain, core_only=False)
            core = _run(company, domain, core_only=True)
            after = _run(company, domain, core_only="then_deferred")
        except Exception as exc:                            # noqa: BLE001
            failures.append((company, f"{type(exc).__name__}: {exc}"))
            print(f"  {company:22s} ERROR {type(exc).__name__}: "
                  f"{str(exc)[:120]}")
            continue
        differing = [f for f in PARITY_FIELDS if full[f] != core[f]]
        worse_uncertainty = (
            core["readiness_state"] == "READY_FOR_FULL_REPORT"
            and full["readiness_state"] != "READY_FOR_FULL_REPORT")
        # THE FAIL CONDITION IS THE ACCOUNTING, NOT THE CROSS-RUN DIFF.
        # `families` legitimately differs between two acquisitions minutes
        # apart; a deferred candidate that is neither retrieved nor recorded
        # as failed never legitimately differs.
        lost = ["silently_dropped"] * bool(after.get("silently_dropped"))
        drifted = [f for f in ("families", "readiness_state",
                               "material_level", "business_model",
                               "economic_state", "result_state")
                   if full[f] != after[f]]
        rows.append({"company": company, "full": full, "core": core,
                     "after_deferred": after, "lost_by_deferral": lost,
                     "drifted_after_deferral": drifted,
                     "differing": differing,
                     "false_specificity": core["unsourced_claims"]
                     - full["unsourced_claims"],
                     "more_certain_on_less": worse_uncertainty})
        flag = "LOSS" if lost else ("OK  " if not differing
                                    and not worse_uncertainty else "diff")
        print(f"  {flag} {company:22s} "
              f"docs full {full['documents']:>2} / core {core['documents']:<2}"
              f" / after {after['documents']:<2}  "
              f"deferred {core['deferred']:>2}  "
              f"acq {full['acquisition_s']:6.2f}->{core['acquisition_s']:6.2f}s"
              f"  {'DROPPED ' + str(after.get('silently_dropped')) if lost else ('drift: ' + ','.join(drifted) if drifted else '')}")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows, "errors": failures}, indent=1))

    reversals = [r for r in rows if "thesis" in r["differing"]
                 or "business_model" in r["differing"]
                 or "result_state" in r["differing"]]
    false_spec = [r for r in rows if r["false_specificity"] > 0]
    over_certain = [r for r in rows if r["more_certain_on_less"]]
    no_report = [r for r in rows if not r["core"]["has_report"]]
    lost_rows = [r for r in rows if r["lost_by_deferral"]]
    print("\n" + "=" * 68)
    print(f"  companies compared          {len(rows)}")
    print(f"  material field differences  {len(reversals)}")
    print(f"  false specificity           {len(false_spec)}")
    print(f"  more certain on less        {len(over_certain)}")
    print(f"  CORE composed no report     {len(no_report)}")
    print(f"  deferred sources DROPPED    {len(lost_rows)}"
          f"   <- 'nothing is dropped' is this line")
    print(f"  cross-run family drift      "
          f"{len([r for r in rows if r['drifted_after_deferral']])}"
          f"   (advisory: two acquisitions, host variance)")
    verdict = ("PASS" if not (reversals or false_spec or over_certain
                              or no_report or failures or lost_rows)
               else "FAIL")
    print(f"  VERDICT                     {verdict}")
    print("=" * 68)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
