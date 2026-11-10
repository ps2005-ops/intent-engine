#!/usr/bin/env python3
"""§3/§4: every outbound request one cold acquisition makes, and what it bought.

WHY A LEDGER AND NOT A TIMER
----------------------------
"Network wait" is a category, not a root cause. The deployed decomposition put
~37s in it and could not say which host, which branch, or which bytes — so the
next repair would have been aimed by guess. This wraps BOTH production
transports and records url, host, wall, bytes and outcome for every request, so
the bucket is accounted rather than named.

LOCAL, AND ONLY FOR WHAT LOCAL CAN ANSWER. Request counts, byte counts and
evidence composition are the same wherever the process runs. LATENCY IS NOT:
the deployed instance runs at 7-12% of a local core, so a local second is not a
deployed second and no timing here is evidence about the gate.

    python scripts/perf_acquisition_ledger.py "NVIDIA" nvidia.com [--core-only]

`--core-only` runs acquisition through the sufficiency probe, exactly as the
interactive worker does, so the two modes can be compared on the same tree.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib
import json
import pathlib
import sys
import tempfile
import time
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LEDGER: list = []


def _wrap(name, fn):
    def inner(url, timeout, *args, **kwargs):
        began = time.monotonic()
        try:
            out = fn(url, timeout, *args, **kwargs)
            LEDGER.append({"via": name, "url": url,
                           "ms": round((time.monotonic() - began) * 1000, 1),
                           "bytes": len(out[2]) if out and len(out) > 2 else 0,
                           "ok": True})
            return out
        except Exception as exc:                            # noqa: BLE001
            LEDGER.append({"via": name, "url": url,
                           "ms": round((time.monotonic() - began) * 1000, 1),
                           "bytes": 0, "ok": False,
                           "err": type(exc).__name__})
            raise
    return inner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("company")
    ap.add_argument("domain")
    ap.add_argument("--core-only", action="store_true",
                    help="stop CORE acquisition at the readiness contract")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from intent_engine.company_ingestion import edgar as E
    from intent_engine.company_ingestion import fetch as F
    from intent_engine.company_ingestion import httppool
    from intent_engine.company_ingestion import public_metadata as PM
    F._default_transport = _wrap("web", F._default_transport)
    E._sec_transport = _wrap("sec", E._sec_transport)

    from intent_engine.company_ingestion import sufficiency
    from intent_engine.company_ingestion.service import (
        CompanyIngestionService,
    )
    web_app = importlib.import_module("intent_engine.webapp.app").WebApp

    ci = CompanyIngestionService(pathlib.Path(tempfile.mkdtemp()) / "ci.jsonl")
    run = ci.create_run(company_name=args.company,
                        website=f"https://{args.domain}", user_id="ledger",
                        as_of=dt.date.today().isoformat())
    run_id = run["run_id"] if isinstance(run, dict) else run

    began = time.monotonic()
    candidates = ci.discover(run_id)
    discovery_s = time.monotonic() - began
    discovery_mark = len(LEDGER)

    approved = web_app._recommended_candidate_ids.__func__(
        web_app, candidates, refusing_hosts=ci.refusing_hosts(run_id),
        subject_cik=(ci.run_meta(run_id) or {}).get("cik"))
    ci.approve(run_id, user_id="ledger", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])

    probe = None
    if args.core_only:
        meta = ci.run_meta(run_id) or {}

        def probe(documents):                               # noqa: F811
            return sufficiency.evaluate(
                documents, identity=ci.entity_identity(run_id),
                failures=list(ci.store.failures(run_id)),
                subject_cik=str(ci.subject_cik(meta) or ""))

    began = time.monotonic()
    result = ci.fetch_approved(run_id, sufficiency_probe=probe)
    retrieval_s = time.monotonic() - began

    core = LEDGER[discovery_mark:]
    documents = list(ci.store.retrieved(run_id))
    mode = "CORE_ONLY" if args.core_only else "FULL"
    print(f"\n=== {args.company} [{mode}] ===")
    print(f"  discovery {discovery_s:6.2f}s   retrieval {retrieval_s:6.2f}s")
    print(f"  approved {len(approved)}  documents {len(documents)}  "
          f"deferred {len(result.get('deferred') or ())}  "
          f"failed {len(result['failed'])}")
    print(f"  requests {len(LEDGER)} (discovery {discovery_mark}, "
          f"retrieval {len(core)})   "
          f"bytes {sum(r['bytes'] for r in LEDGER):,}")
    if result.get("sufficiency"):
        print(f"  stopped: {result['sufficiency']['reason']} "
              f"after {result['sufficiency']['documents']} document(s)")
    print(f"  connections {httppool.stats()}")
    print(f"  metadata cache {PM.stats()}")

    hosts = collections.Counter(urlparse(r["url"]).hostname or "?"
                                for r in LEDGER)
    print("\n  per host:")
    for host, count in hosts.most_common():
        rows = [r for r in LEDGER
                if (urlparse(r["url"]).hostname or "?") == host]
        print(f"    {host:34s} n={count:<3d} "
              f"{sum(r['ms'] for r in rows) / 1000:6.2f}s "
              f"{sum(r['bytes'] for r in rows):>11,}B "
              f"fail={sum(1 for r in rows if not r['ok'])}")
    duplicates = [(u, n) for u, n in
                  collections.Counter(r["url"] for r in LEDGER).most_common()
                  if n > 1]
    if duplicates:
        print("\n  SAME URL REQUESTED MORE THAN ONCE:")
        for url, n in duplicates:
            print(f"    x{n}  {url[:104]}")
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(
            {"company": args.company, "mode": mode,
             "discovery_s": discovery_s, "retrieval_s": retrieval_s,
             "documents": len(documents), "approved": len(approved),
             "deferred": len(result.get("deferred") or ()),
             "requests": len(LEDGER),
             "bytes": sum(r["bytes"] for r in LEDGER),
             "ledger": LEDGER}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
