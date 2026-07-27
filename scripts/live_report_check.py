#!/usr/bin/env python
"""Supervised LIVE executive-report check.

Runs the real guest analysis path against real public sources for one or more
companies and prints/records the quality metrics. Used for release validation
and by the manually-triggered supervised-live workflow — never in ordinary CI,
because it makes real network requests.

Usage:
    python scripts/live_report_check.py --companies palantir.com,shopify.com
    python scripts/live_report_check.py --out metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from intent_engine.company_ingestion.service import (  # noqa: E402
    CompanyIngestionService,
)
from intent_engine.founder_intelligence.service import (  # noqa: E402
    FounderIntelligenceService,
)
from intent_engine.webapp.app import WebApp  # noqa: E402

KNOWN = {
    "palantir.com": ("Palantir Technologies", "https://www.palantir.com"),
    "microsoft.com": ("Microsoft", "https://www.microsoft.com"),
    "nvidia.com": ("NVIDIA", "https://www.nvidia.com"),
    "apple.com": ("Apple", "https://www.apple.com"),
    "shopify.com": ("Shopify", "https://www.shopify.com"),
    "snowflake.com": ("Snowflake", "https://www.snowflake.com"),
}


def analyse(name: str, website: str, as_of: str) -> dict:
    tmp = Path(tempfile.mkdtemp())
    started = time.time()
    ci = CompanyIngestionService(tmp / "ci.jsonl")          # real network
    fi = FounderIntelligenceService(tmp / "fi.jsonl")
    run_id = ci.create_run(company_name=name, website=website,
                           user_id="live-check", as_of=as_of)["run_id"]
    candidates = ci.discover(run_id)
    approved = WebApp._recommended_candidate_ids(candidates)
    ci.approve(run_id, user_id="live-check", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    ci.fetch_approved(run_id)
    result = ci.compose_with_quality(run_id, fi_service=fi)

    documents = ci.store.retrieved(run_id)
    failures = ci.store.failures(run_id)
    quality = result.get("quality") or {}
    metrics = quality.get("metrics") or {}
    coverage = result.get("coverage") or {}
    return {
        "company": name,
        "run_id": run_id,
        "sources_attempted": len(approved),
        "sources_successful": len(documents),
        "source_families": coverage.get("families", []),
        "family_counts": coverage.get("family_counts", {}),
        "pdfs_used": sum(1 for d in documents
                         if str(d.get("original_url", "")).lower()
                         .endswith(".pdf")),
        "failed_reasons": dict(Counter(f["failure_type"] for f in failures)),
        "retry_passes": result.get("quality_passes", 0),
        "quality_outcome": quality.get("outcome"),
        "failed_rules": quality.get("failed_rules", []),
        "populated_share": metrics.get("populated_share"),
        "placeholder_share": metrics.get("placeholder_share"),
        "has_product_evidence": metrics.get("has_product_evidence"),
        "has_customer_evidence": metrics.get("has_customer_evidence"),
        "has_strategy_evidence": metrics.get("has_strategy_evidence"),
        "legal_as_insight": metrics.get("legal_as_insight", []),
        "ingestion_status": result.get("ingestion_status"),
        "sections": len(result.get("sections", [])),
        "duration_s": round(time.time() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", default=",".join(KNOWN))
    parser.add_argument("--as-of", default="2026-07-27T00:00:00+00:00")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = []
    for token in [c.strip() for c in args.companies.split(",") if c.strip()]:
        if token in KNOWN:
            name, website = KNOWN[token]
        else:
            name, website = token, f"https://www.{token}"
        try:
            rows.append(analyse(name, website, args.as_of))
        except Exception as exc:                            # noqa: BLE001
            rows.append({"company": name, "error": f"{type(exc).__name__}: "
                                                   f"{exc}"})

    header = (f"{'company':<24}{'ok/try':>8}{'fams':>6}{'pop%':>7}"
              f"{'retry':>7}  outcome")
    print(header)
    print("-" * len(header))
    for row in rows:
        if "error" in row:
            print(f"{row['company']:<24} ERROR {row['error'][:44]}")
            continue
        print(f"{row['company']:<24}"
              f"{row['sources_successful']:>4}/{row['sources_attempted']:<3}"
              f"{len(row['source_families']):>6}"
              f"{int((row['populated_share'] or 0) * 100):>6}%"
              f"{row['retry_passes']:>7}  {row['quality_outcome']}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
