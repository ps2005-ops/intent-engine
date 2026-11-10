#!/usr/bin/env python3
"""Where do candidate sources COME FROM, and which of them get a slot?

    PYTHONPATH=src python3 scripts/v5_discovery_composition.py --out FILE

THE QUESTION THIS ANSWERS
--------------------------
Batch 12 measured the OUTPUT of retrieval (72 documents, 9 independent, 0 from
an independent external source) and concluded the ceiling was structural. That
conclusion was reached from the output alone. This instrument reads the INPUT:
every candidate discovery proposes, where it came from, whether it is on the
company's own domain, and — the part that decides everything — whether it
survives into the bounded approval budget.

A candidate that is never approved cannot become evidence however good it is,
so "we have no independent sources" and "we never gave an independent source a
slot" are different findings with different repairs. Nothing here fetches: it
is discovery and selection only, so it is cheap and safe to run repeatedly.

MISSING IS NOT ZERO
-------------------
A company whose discovery raises an exception is recorded with its error, not
as a company with no candidates.
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import pathlib
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

CONTRACT = "discovery_composition.v1"

#: Vantage classes that could bear independence if retrieved. Read from the
#: canonical set rather than restated, so this instrument cannot drift from
#: the classifier it is measuring.
from intent_engine.company_ingestion.records import (  # noqa: E402
    INDEPENDENT_CLASSES, MAX_APPROVED_SOURCES,
)
from intent_engine.validation import breaker_ten, load  # noqa: E402


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _registrable(host: str) -> str:
    labels = [x for x in (host or "").split(".") if x]
    return ".".join(labels[-2:]) if len(labels) > 2 else ".".join(labels)


def _on_company_domain(url: str, domain: str) -> bool:
    host = _host(url)
    base = (domain or "").lower().lstrip("www.")
    if not host or not base:
        return False
    return host == base or host.endswith("." + base) or \
        _registrable(host) == _registrable(base)


def compose(company, *, app_cls, app) -> dict:
    """Discovery + selection for one company. Never fetches page bodies.

    Driven exactly as `v5_breaker_wave` drives it — same run creation, same
    `discover`, same `_recommended_candidate_ids` with the same
    `refusing_hosts` — so a difference between this instrument and the wave is
    never a difference in how the two called production.
    """
    created = app.ci.create_run(
        company_name=company.canonical_name,
        website=f"https://{company.domain}",
        user_id="discovery-composition",
        as_of=_dt.datetime.now(_dt.timezone.utc)
        .strftime("%Y-%m-%dT00:00:00+00:00"))
    run_id = created["run_id"]
    candidates = app.ci.discover(run_id)

    picked = set(app_cls._recommended_candidate_ids(
        candidates, refusing_hosts=app.ci.refusing_hosts(run_id)))

    rows = []
    for candidate in candidates:
        url = candidate.get("url", "")
        source_class = candidate.get("source_class", "")
        rows.append({
            "candidate_id": candidate.get("candidate_id"),
            "url": url,
            "host": _host(url),
            "registrable_domain": _registrable(_host(url)),
            "source_family": source_class,
            "source_role": candidate.get("source_type", ""),
            "discovery_method": candidate.get("discovery_method", ""),
            "on_company_domain": _on_company_domain(url, company.domain),
            "off_domain": not _on_company_domain(url, company.domain),
            "independence_bearing_class": source_class in INDEPENDENT_CLASSES,
            "approved": candidate.get("candidate_id") in picked,
        })

    off = [r for r in rows if r["off_domain"]]
    independent = [r for r in rows if r["independence_bearing_class"]]
    return {
        "company_id": company.company_id,
        "canonical_name": company.canonical_name,
        "domain": company.domain,
        "sector": company.sector,
        "candidates": len(rows),
        "on_domain": len(rows) - len(off),
        "off_domain": len(off),
        "independent_class_candidates": len(independent),
        "independent_class_approved": sum(1 for r in independent
                                          if r["approved"]),
        "off_domain_approved": sum(1 for r in off if r["approved"]),
        "approved_total": sum(1 for r in rows if r["approved"]),
        "approval_budget": MAX_APPROVED_SOURCES,
        "by_method": dict(collections.Counter(r["discovery_method"]
                                              for r in rows)),
        "by_family": dict(collections.Counter(r["source_family"]
                                              for r in rows)),
        "approved_by_method": dict(collections.Counter(
            r["discovery_method"] for r in rows if r["approved"])),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="discovery-composition-"))

    results, errors = [], []
    for company in breaker_ten(load()):
        store_dir = root / company.company_id
        store_dir.mkdir(parents=True, exist_ok=True)
        try:
            app = WebApp(AppConfig(
                env="development", secret="s" * 40, demo_mode=True,
                web_store_path=store_dir / "web.jsonl",
                fi_store_path=store_dir / "fi.jsonl",
                ci_store_path=store_dir / "ci.jsonl"),
                transport=None, resolver=False)
            results.append(compose(company, app_cls=WebApp, app=app))
            last = results[-1]
            print(f"{last['company_id']:26} cand={last['candidates']:3} "
                  f"off={last['off_domain']:2} "
                  f"indep={last['independent_class_candidates']:2} "
                  f"indep_approved={last['independent_class_approved']}")
        except Exception as exc:  # noqa: BLE001 - a failure IS the finding
            errors.append({"company_id": company.company_id,
                           "error": f"{type(exc).__name__}: {exc}"})
            print(f"{company.company_id:26} ERROR {type(exc).__name__}: {exc}")

    payload = {
        "contract": CONTRACT,
        "companies": results,
        "errors": errors,
        "cohort_size": len(results) + len(errors),
        "totals": {
            "candidates": sum(r["candidates"] for r in results),
            "on_domain": sum(r["on_domain"] for r in results),
            "off_domain": sum(r["off_domain"] for r in results),
            "independent_class_candidates":
                sum(r["independent_class_candidates"] for r in results),
            "independent_class_approved":
                sum(r["independent_class_approved"] for r in results),
            "off_domain_approved": sum(r["off_domain_approved"]
                                       for r in results),
        },
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\nwrote {out}")
    print(json.dumps(payload["totals"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
