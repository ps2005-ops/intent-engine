"""Measure, before spending any analysis, what the product's own search does
with each of the 100 prospect names.

Runs the SAME two functions the deployed web app calls:
  - company_ingestion.suggest.suggest      (the /api/companies search box)
  - company_ingestion.name_entry.resolve   (what /analyze does with a typed name)

with the SEC registrant table ON, as it is in production. Writes JSON rows;
judging whether a row is the RIGHT company is done against the registry, not
here -- a row existing is not the same as a row being correct.

Usage:
  PYTHONPATH=src python scripts/prospect100/identity_baseline.py \
      --list docs/engineering/prospect100/PROSPECT_LIST.yaml \
      [--queries extra_queries.json] --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import time

import yaml

from intent_engine.company_ingestion import name_entry, suggest


def _probe(query: str) -> dict:
    t0 = time.perf_counter()
    rows = suggest.suggest(query, limit=8, allow_registrant=True)
    suggest_ms = (time.perf_counter() - t0) * 1000
    entry = name_entry.resolve(query, allow_registrant=True)
    return {
        "query": query,
        "suggest_ms": round(suggest_ms, 2),
        "suggestions": [
            {"legal_name": r.legal_name, "domain": r.domain, "cik": r.cik,
             "ticker": r.ticker, "source": r.source, "match": r.match,
             "entity_id": r.entity_id}
            for r in rows],
        "resolve_state": entry.state,
        "resolve_name": entry.company_name,
        "resolve_website": entry.website,
        "resolve_source": entry.source,
        "resolve_company_id": entry.company_id,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--queries", default="",
                    help="optional JSON {prospect_id: [extra typed forms]}")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    prospects = yaml.safe_load(open(args.list))["prospects"]
    extra = json.load(open(args.queries)) if args.queries else {}

    # Warm the SEC table once so the first row's latency is not the fetch.
    suggest.suggest("warm", allow_registrant=True)

    out = []
    for p in prospects:
        pid = p["prospect_id"]
        forms = [p["name_as_listed"]] + list(extra.get(str(pid), []))
        out.append({"prospect_id": pid, "tier": p["tier"],
                    "name_as_listed": p["name_as_listed"],
                    "probes": [_probe(q) for q in forms]})
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"wrote {len(out)} prospects to {args.out}")


if __name__ == "__main__":
    main()
