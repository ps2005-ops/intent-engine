"""Measure the ACQUISITION LAYER on its own, with no model and no Render.

WHY A SEPARATE INSTRUMENT. The 50-company qualification measures the whole
product, so an abstention there is ambiguous between "retrieval could not
find evidence" and "reasoning could not use it". This drives the real
production call sites -- `discover`, `_recommended_candidate_ids`, `approve`,
`fetch_approved` with the real sufficiency probe -- and stops before
composition. What it reports is therefore a fact about the data plane only.

It costs no analysis quota and no model credit, so it can be run at any
concurrency the network will bear.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


def probe_one(name: str, website: str, *, root: pathlib.Path,
              cache_dir: pathlib.Path | None = None,
              memory: bool = True, budget: float = 0.0) -> dict:
    from intent_engine.company_ingestion.service import CompanyIngestionService
    from intent_engine.company_ingestion.filing_cache import FilingCache
    from intent_engine.company_ingestion import readiness as R
    from intent_engine.company_ingestion import coverage as C
    from intent_engine.webapp.app import WebApp

    started = time.monotonic()
    row = {"company": name, "website": website, "error": ""}
    try:
        # ONE FRESH STORE PER PROBE RUN.
        #
        # This was `root / f"{abs(hash(name)) % 10**8}.jsonl"` in a directory
        # shared by every probe invocation, and `create_run` is idempotent on
        # (domain, user, as_of) -- so the second probe of a company on the
        # same day rejoined the FIRST run's event log instead of opening a
        # new one, and reported that run's records as this one's.
        #
        # It manufactured a defect that does not exist: Oracle read
        # {investor: 5, independent: 4} and RETRYABLE_EVIDENCE_GAP under the
        # shared directory, and {identity: 2, independent: 4, investor: 1,
        # strategy: 1, talent: 1} and READY_FOR_FULL_REPORT with a fresh one --
        # same code, same company, minutes apart. Every measurement taken
        # through the shared directory is void.
        import uuid
        store = root / uuid.uuid4().hex / "ci.jsonl"
        store.parent.mkdir(parents=True, exist_ok=True)
        from intent_engine.company_ingestion.acquisition_memory import (
            AcquisitionMemory,
        )
        ci = CompanyIngestionService(
            store, filing_cache=(FilingCache(cache_dir)
                                 if cache_dir is not None else None),
            acquisition_memory=(None if memory
                                else AcquisitionMemory(enabled=False)))
        import datetime
        run = ci.create_run(
            company_name=name,
            website=(website if website.startswith("http")
                     else f"https://{website}"),
            user_id="probe",
            as_of=datetime.date.today().isoformat())
        run_id = run["run_id"] if isinstance(run, dict) else run
        # THE PRODUCTION BUDGET. `_run_analysis` runs discovery and
        # retrieval under `Deadline.for_tier(...)` reserving COMPOSE_RESERVE_S
        # -- 40s of a 60s tier-1 budget. A probe with no deadline measures an
        # acquisition layer the customer never gets, and on the preview's
        # ~15% CPU share the budget is the binding constraint, not the hosts.
        deadline = None
        if budget:
            from intent_engine.company_ingestion.deadline import Deadline
            deadline = Deadline(total_s=float(budget))
        t0 = time.monotonic()
        ci.discover(run_id, deadline=deadline)
        row["discovery_s"] = round(time.monotonic() - t0, 2)
        candidates = ci.store.candidates(run_id)
        row["candidates"] = len(candidates)
        # `memory=` IS PART OF THE PRODUCTION CALL. Omitting it made the
        # probe measure a selection that could not free a slot -- 211
        # known-failure skips and an unchanged 73% slot yield, because the
        # skips happened at fetch time when the slot was already spent.
        approved = WebApp._recommended_candidate_ids(
            candidates, refusing_hosts=ci.refusing_hosts(run_id),
            subject_cik=(ci.run_meta(run_id) or {}).get("cik"),
            memory=ci.acquisition_memory)
        ci.approve(run_id, user_id="probe", approved_ids=list(approved),
                   rejected_ids=[c["candidate_id"] for c in candidates
                                 if c["candidate_id"] not in set(approved)])
        row["approved"] = len(approved)
        t1 = time.monotonic()
        fetched = ci.fetch_approved(run_id, deadline=deadline)
        row["retrieval_s"] = round(time.monotonic() - t1, 2)
        # THE PRODUCTION REPLAN LOOP, not a probe-only shortcut.
        # `compose_with_quality` runs `evidence_gaps` -> `plan_retry` ->
        # `fetch_approved(candidate_ids=...)` for up to MAX_RETRY_PASSES.
        # Stopping before it would measure an earlier product than the one
        # that ships, and would invent a gap the retry already closes.
        from intent_engine.company_ingestion.quality import evidence_gaps
        from intent_engine.company_ingestion.retry import (
            MAX_RETRY_PASSES, plan_retry,
        )
        replan = []
        attempted: set = set()
        for _pass in range(1, MAX_RETRY_PASSES + 1):
            gaps = evidence_gaps(ci.store.retrieved(run_id))
            if gaps["sufficient"]:
                break
            approval = ci.store.approval(run_id) or {}
            already = set(approval.get("approved_candidate_ids", ())) | attempted
            failed_ids = {f.get("candidate_id")
                          for f in ci.store.failures(run_id)}
            failed_urls = {c["url"] for c in ci.store.candidates(run_id)
                           if c["candidate_id"] in failed_ids}
            extra = plan_retry(missing_families=gaps["missing_families"],
                               candidates=ci.store.candidates(run_id),
                               already_approved=already,
                               failed_urls=failed_urls,
                               refusing_hosts=ci.refusing_hosts(run_id))
            if not extra:
                replan.append({"pass": _pass, "planned": 0,
                               "missing": list(gaps["missing_families"])})
                break
            attempted.update(extra)
            before = len(list(ci.store.retrieved(run_id)))
            ci.fetch_approved(run_id, candidate_ids=extra)
            replan.append({"pass": _pass, "planned": len(extra),
                           "missing": list(gaps["missing_families"]),
                           "gained": len(list(ci.store.retrieved(run_id)))
                           - before})
        row["replan"] = replan
        documents = list(ci.store.retrieved(run_id))
        failures = list(ci.store.failures(run_id))
        row["documents"] = len(documents)
        row["deferred"] = len(fetched.get("deferred") or ())
        # --- what actually failed, by host and by kind ---------------------
        by_id = {c["candidate_id"]: c for c in candidates}
        fail_kinds: dict = {}
        fail_hosts: dict = {}
        statuses: dict = {}
        for f in failures:
            kind = f.get("failure_type") or "?"
            fail_kinds[kind] = fail_kinds.get(kind, 0) + 1
            host = urlparse((by_id.get(f.get("candidate_id")) or {}).get(
                "url") or "").hostname or "?"
            fail_hosts[host] = fail_hosts.get(host, 0) + 1
            msg = f.get("safe_message") or ""
            for code in ("401", "403", "404", "429", "500", "502", "503"):
                if code in msg:
                    statuses[code] = statuses.get(code, 0) + 1
                    break
        # WHERE THE APPROVED BUDGET ACTUALLY WENT, by how the URL was found.
        # A guessed known path and a publisher-rendered sitemap URL are not
        # the same bet, and reporting only a failure count hides which one
        # the run spent itself on.
        got = {r.get("source_id") for r in documents}
        method_ok, method_bad = {}, {}
        for cid in approved:
            c = by_id.get(cid) or {}
            m = c.get("discovery_method") or "?"
            sid = f"src-{cid[5:]}"
            if sid in got:
                method_ok[m] = method_ok.get(m, 0) + 1
            else:
                method_bad[m] = method_bad.get(m, 0) + 1
        row["approved_ok_by_method"] = method_ok
        row["approved_failed_by_method"] = method_bad
        row["failures"] = len(failures)
        row["failure_kinds"] = fail_kinds
        row["failure_hosts"] = dict(sorted(fail_hosts.items(),
                                           key=lambda kv: -kv[1])[:6])
        row["http_statuses"] = statuses
        # --- evidence roles (families) -------------------------------------
        fams: dict = {}
        for d in documents:
            fam = C.family_of(d)
            fams[fam] = fams.get(fam, 0) + 1
        row["families"] = fams
        forms = {}
        for d in documents:
            f = (d.get("filing") or {})
            key = f"{f.get('form') or 'web'}/{d.get('source_class','')}"
            forms[key] = forms.get(key, 0) + 1
        row["forms"] = forms
        row["family_count"] = len(fams)
        # --- the product's own verdict -------------------------------------
        verdict = R.assess_readiness(documents=documents,
                                     identity=ci.entity_identity(run_id),
                                     failures=failures)
        row["readiness"] = verdict.get("state")
        row["unmet"] = list(verdict.get("unmet_checks") or ())
        row["failed_checks"] = list(verdict.get("failed_checks") or ())
        row["research_mode"] = verdict.get("research_mode")
        row["retry"] = ci.retry_ledger_for(run_id).snapshot().get(
            "retries_by_host", {})
        row["cache"] = ci.filing_cache.snapshot()
        row["memory"] = ci.acquisition_memory.snapshot()
    except Exception as exc:                                # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc()[-800:]
    row["total_s"] = round(time.monotonic() - started, 2)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", default="")
    ap.add_argument("--cohort", default="")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-memory", action="store_true")
    ap.add_argument("--budget", type=float, default=0.0)
    args = ap.parse_args()

    if args.cohort:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import perf_progressive_matrix as M
        pairs = list(getattr(M, args.cohort))
    else:
        pairs = [tuple(p.split("=", 1)) for p in args.companies.split(";") if p]
    if args.limit:
        pairs = pairs[:args.limit]

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    root = out.parent / "stores"
    root.mkdir(parents=True, exist_ok=True)
    cache_dir = pathlib.Path(args.cache_dir) if args.cache_dir else None

    def one(pair):
        row = probe_one(pair[0], pair[1], root=root, cache_dir=cache_dir,
                        memory=not args.no_memory, budget=args.budget)
        print(f"  {row['company']:<28} docs={row.get('documents','-'):<3}"
              f" fams={row.get('family_count','-'):<2}"
              f" {row.get('readiness','ERR'):<24}"
              f" fails={row.get('failures','-'):<3} {row.get('total_s','-')}s"
              f" {row.get('error','')}", flush=True)
        return row

    print(f"probing {len(pairs)} companies at concurrency "
          f"{args.concurrency}", flush=True)
    t0 = time.monotonic()
    if args.concurrency <= 1:
        rows = [one(p) for p in pairs]
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            rows = list(pool.map(one, pairs))
    elapsed = round(time.monotonic() - t0, 1)
    out.write_text(json.dumps({"concurrency": args.concurrency,
                               "elapsed_s": elapsed, "rows": rows},
                              indent=2), "utf-8")
    ready = sum(1 for r in rows if r.get("readiness") == "READY_FOR_FULL_REPORT")
    print(f"\n{ready}/{len(rows)} READY_FOR_FULL_REPORT in {elapsed}s "
          f"-> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
