"""Replay the EVIDENCE-JUDGING path over stored bundles, with no network.

WHY. A 50-company qualification measures the whole product, so an abstention
there is ambiguous between "retrieval could not find evidence" and "the
judgement over that evidence is broken". This replays the second half alone:
it reads documents that were already retrieved and persisted, and runs every
deterministic gate the product uses to decide whether a report may exist --
`coverage.assess`, `readiness.assess_readiness`, `quality.evidence_gaps` --
with the network unreachable.

WHAT IT DOES AND DOES NOT PROVE. It proves the deterministic judgement layer
is healthy, stable and reproducible on fixed evidence. It does NOT exercise
the model-backed synthesis, which needs a configured reasoning key; that half
is proven live. Saying so is the point -- a replay that quietly skipped the
model and reported "reasoning healthy" would be measuring the wrong thing.

DETERMINISM IS ASSERTED, NOT ASSUMED. Every bundle is judged twice and the
two verdicts must be identical. A gate that reads a clock, a random seed or
the filesystem would show up here rather than as drift in a live cohort.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class _NoNetwork(socket.socket):
    def __init__(self, *a, **k):                            # noqa: D401
        raise OSError("replay runs with the network unreachable")


def judge(documents, identity=None, failures=()) -> dict:
    from intent_engine.company_ingestion import coverage as C
    from intent_engine.company_ingestion import readiness as R
    from intent_engine.company_ingestion.quality import evidence_gaps
    verdict = R.assess_readiness(documents=documents, identity=identity,
                                 failures=list(failures))
    gaps = evidence_gaps(documents)
    cov = C.assess(documents)
    return {
        "readiness": verdict.get("state"),
        "unmet": sorted(verdict.get("unmet_checks") or ()),
        "failed_checks": sorted(verdict.get("failed_checks") or ()),
        "research_mode": verdict.get("research_mode"),
        "families": sorted(cov.get("families") or ()),
        "family_counts": dict(cov.get("family_counts") or {}),
        "documents": cov.get("document_count"),
        "missing_roles": list(gaps.get("missing_families") or ()),
        "coverage_state": cov.get("state"),
    }


def bundles_from_stores(root: pathlib.Path):
    """Every persisted run under ``root``, as (label, documents, failures)."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    for store in sorted(root.rglob("ci.jsonl")):
        try:
            ci = CompanyIngestionService(store)
            for run_id in ci.store.run_ids():
                documents = list(ci.store.retrieved(run_id))
                if not documents:
                    continue
                meta = ci.run_meta(run_id) or {}
                yield (meta.get("company_name") or run_id, documents,
                       list(ci.store.failures(run_id)),
                       ci.entity_identity(run_id))
        except Exception as exc:                            # noqa: BLE001
            print(f"  unreadable store {store}: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = pathlib.Path(args.stores)
    bundles = list(bundles_from_stores(root))
    if not bundles:
        print("NO BUNDLES FOUND — a zero denominator is not a pass")
        return 2

    # The network is cut only AFTER the stores are read: reading a local
    # event log is not a retrieval, and leaving it cut for the whole process
    # would fail on the file handles rather than prove anything.
    real_socket = socket.socket
    socket.socket = _NoNetwork

    rows, unstable = [], []
    try:
        for label, documents, failures, identity in bundles:
            first = judge(documents, identity=identity, failures=failures)
            second = judge(documents, identity=identity, failures=failures)
            if first != second:
                unstable.append(label)
            rows.append(dict(first, company=label,
                             deterministic=(first == second)))
    finally:
        socket.socket = real_socket

    ready = [r for r in rows if r["readiness"] == "READY_FOR_FULL_REPORT"]
    limited = [r for r in rows if r["readiness"] == "READY_FOR_LIMITED_REPORT"]
    print(f"REPLAY over {len(rows)} stored evidence bundles, no network\n")
    print(f"{'company':<26}{'documents':>10}{'families':>10}  readiness")
    for r in sorted(rows, key=lambda x: x["company"]):
        print(f"  {r['company'][:23]:<24}{r['documents']:>10}"
              f"{len(r['families']):>10}  {r['readiness']}")
    print(f"\n  READY_FOR_FULL_REPORT    {len(ready)}/{len(rows)}"
          f"  ({len(ready)/len(rows):.0%})")
    print(f"  READY_FOR_LIMITED_REPORT {len(limited)}/{len(rows)}")
    print(f"  deterministic            {len(rows)-len(unstable)}/{len(rows)}")
    if unstable:
        print(f"  NON-DETERMINISTIC: {unstable}")
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(rows, indent=2), "utf-8")
    return 1 if unstable else 0


if __name__ == "__main__":
    raise SystemExit(main())
