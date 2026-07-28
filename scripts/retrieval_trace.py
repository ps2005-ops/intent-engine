#!/usr/bin/env python3
"""Run the REAL live retrieval pipeline for a company and emit a full trace.

    python scripts/retrieval_trace.py Palantir https://www.palantir.com \
        --out reports/trace_palantir.json

This drives the same code path the deployed guest flow uses — discovery,
recommended-source approval, retrieval, parsing — over the real network, and
records for every URL: the discovered and canonical URL, the redirect chain,
the robots verdict, the response code, timeout budget and whether it expired,
bytes received, which parser ran, whether extraction succeeded and FROM WHERE,
why a source was rejected, its evidence family, and the run's quality score.

It composes the report too, so the trace can be joined against what the reader
would actually have seen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intent_engine.company_ingestion.service import (            # noqa: E402
    CompanyIngestionService,
)
from intent_engine.company_ingestion.trace import RetrievalTrace  # noqa: E402
from intent_engine.founder_intelligence.service import (         # noqa: E402
    FounderIntelligenceService,
)

AS_OF = "2026-07-27T00:00:00+00:00"


def _robots_probe(trace: RetrievalTrace, website: str, transport) -> None:
    """Record the robots.txt verdict per host — including the case that matters
    most, a robots.txt that is itself refused."""
    from intent_engine.company_ingestion.fetch import safe_fetch
    from intent_engine.company_ingestion.sitemap import parse_robots

    host = urlparse(website).hostname or ""
    robots_url = f"https://{host}/robots.txt"
    result = safe_fetch(robots_url, transport=transport,
                        extra_mime_prefixes=("application/xml", "text/xml"))
    if not result["ok"]:
        trace.note_robots(host, allowed=True, reachable=False,
                          rule=f"robots.txt unreachable "
                               f"({result['failure_type']}: "
                               f"{result['safe_message'][:60]}) — no policy "
                               f"could be read")
        return
    policy = parse_robots(result["body"], base_url=robots_url)
    trace.note_robots(host, allowed=not policy["disallow"],
                      rule=("Disallow: " + ", ".join(policy["disallow"][:6]))
                      if policy["disallow"] else "Allow: /")


def run(company: str, website: str, *, out_path: str,
        max_sources: int) -> dict:
    trace = RetrievalTrace(label=company)
    tx = trace.transport()

    tmp = tempfile.mkdtemp(prefix="trace-ci-")
    ci = CompanyIngestionService(os.path.join(tmp, "ci.jsonl"), transport=tx)
    fi = FounderIntelligenceService(os.path.join(tmp, "fi.jsonl"))

    _robots_probe(trace, website, tx)

    created = ci.create_run(company_name=company, website=website,
                            user_id="trace-operator", as_of=AS_OF)
    run_id = created["run_id"]
    trace.run_id = run_id

    candidates = ci.discover(run_id)
    from intent_engine.company_ingestion.sitemap import classify_family
    for candidate in candidates:
        trace.note_candidate(
            candidate["url"],
            family=classify_family(candidate["url"]) or
            candidate.get("source_type", ""),
            discovery_method=candidate.get("discovery_method", ""),
            source_class=candidate.get("source_class", ""))
        trace.apply_robots(candidate["url"])

    # Approve exactly what the deployed guest flow would approve.
    from intent_engine.webapp.app import WebApp
    approved = WebApp._recommended_candidate_ids(
        candidates,
        refusing_hosts=ci.refusing_hosts(run_id))[:max_sources]
    rejected = [c["candidate_id"] for c in candidates
                if c["candidate_id"] not in approved]
    ci.approve(run_id, user_id="trace-operator", approved_ids=approved,
               rejected_ids=rejected)

    by_id = {c["candidate_id"]: c for c in candidates}
    for candidate_id in rejected:
        trace.note_rejected(by_id[candidate_id]["url"],
                            "not selected by source recommendation")

    outcome = ci.fetch_approved(run_id)

    # Join parsing + admission facts back onto the trace. The extraction mode
    # is READ from the record, never inferred from length — inferring it is how
    # a metadata-only admission passes for a document in the first place.
    for record in outcome["ok"]:
        url = record["original_url"]
        trace.row(url).canonical_url = record["final_url"]
        trace.note_parse(url, {"text": record["text_content"],
                               "parser_version": record["parser_version"],
                               "extraction_mode": record.get("extraction_mode"),
                               "blocks_found": record.get("blocks_found")},
                         parser=record["parser_version"])
        trace.note_admitted(url, family=classify_family(url) or
                            record.get("source_type", ""))
    for failure in outcome["failed"]:
        candidate = by_id.get(failure.get("candidate_id"))
        if candidate:
            trace.note_rejected(candidate["url"],
                                f"{failure['failure_type']}: "
                                f"{failure['safe_message'][:90]}")

    result = ci.compose_with_quality(run_id, fi_service=fi)

    # compose_with_quality runs its own bounded retrieval passes, so the store
    # — not the first fetch's return value — is the truth about what the run
    # ended up standing on. Re-read it, or the trace understates the run.
    for record in ci.store.retrieved(run_id):
        url = record["original_url"]
        trace.row(url).canonical_url = record["final_url"]
        trace.note_parse(url, {"text": record["text_content"],
                               "parser_version": record["parser_version"],
                               "extraction_mode": record.get("extraction_mode"),
                               "blocks_found": record.get("blocks_found")},
                         parser=record["parser_version"])
        trace.note_admitted(url, family=classify_family(url) or
                            record.get("source_type", ""))
    for failure in ci.store.failures(run_id):
        candidate = by_id.get(failure.get("candidate_id"))
        if candidate and not trace.row(candidate["url"]).admitted:
            trace.note_rejected(candidate["url"],
                                f"{failure['failure_type']}: "
                                f"{failure['safe_message'][:90]}")

    quality = result.get("quality") or {}
    for row in trace.rows:
        if row.admitted:
            row.quality_score = (quality.get("metrics") or {}).get(
                "populated_share")

    payload = trace.as_dict()
    payload["report"] = {
        "ingestion_status": result.get("ingestion_status"),
        "quality_outcome": quality.get("outcome"),
        "failed_rules": quality.get("failed_rules"),
        "metrics": quality.get("metrics"),
        "coverage_state": (result.get("coverage") or {}).get("state"),
        "families": (result.get("coverage") or {}).get("families"),
        "readiness": (result.get("readiness") or {}).get("decision"),
        "may_synthesize": (result.get("readiness") or {}).get("may_synthesize"),
        "has_strategic_report": bool(result.get("strategic_report")),
    }
    # Vocabulary check: did the named acceptance terms survive to the report?
    blob = json.dumps(result, default=str).lower()
    payload["report"]["vocabulary"] = {
        term: blob.count(term) for term in
        ("foundry", "gotham", "aip", "government", "commercial", "customer",
         "ontology", "defense", "platform")}

    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("website")
    parser.add_argument("--out", default="")
    from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
    parser.add_argument("--max-sources", type=int,
                        default=MAX_APPROVED_SOURCES)
    args = parser.parse_args()

    payload = run(args.company, args.website, out_path=args.out,
                  max_sources=args.max_sources)
    totals = payload["totals"]
    print(f"=== {args.company} — {args.website}")
    print(f"robots: {json.dumps(payload['robots'])}")
    print(f"urls={totals['urls_touched']} http_ok={totals['http_ok']} "
          f"admitted={totals['admitted']} "
          f"bytes={totals['bytes_received']:,} "
          f"chars={totals['chars_extracted']:,} "
          f"metadata_only={totals['metadata_only_admissions']}")
    print(f"report: {json.dumps(payload['report'], default=str)}")
    print()
    rows = sorted(payload["sources"], key=lambda r: r["discovered_url"])
    print(f"{'status':>6} {'bytes':>8} {'chars':>7} {'mode':<9} {'adm':<4} url")
    for row in rows:
        print(f"{str(row['status_code'] or '-'):>6} "
              f"{row['bytes_received']:>8} {row['extracted_chars']:>7} "
              f"{(row['extraction_mode'] or '-'):<9} "
              f"{('yes' if row['admitted'] else 'no'):<4} "
              f"{row['discovered_url'][:88]}"
              + (f"\n{'':>38}[{row['rejected_reason'][:100]}]"
                 if row["rejected_reason"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
