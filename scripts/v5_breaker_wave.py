#!/usr/bin/env python3
"""Run the frozen breaker cohort through the production path, once each.

    PYTHONPATH=src python3 scripts/v5_breaker_wave.py --out reports/v5/breaker_10

ONE RUNNER, TEN CASES. Not ten workflows: every company goes through the same
`WebApp._compose` the deployed guest flow uses, with the same candidate
selection, so a difference between two companies is a difference in the
COMPANIES and not in how they were driven.

THE COHORT IS READ, NEVER CHOSEN HERE
--------------------------------------
`breaker_ten()` derives the ten from the frozen manifest. This script asserts
the result against the list Batch 9 published and refuses to run if they
disagree — a runner that silently re-selected after a manifest edit would
destroy the property the deterministic selector exists to provide.

A COMPANY THAT FAILS, FAILS
----------------------------
No substitution, no retry with a friendlier company, no dropping a company for
sparse output. A crash is recorded as a result and the wave continues, because
the crash IS the finding. The only thing that would invalidate the wave is
running the ten on different code, so the runtime SHA is frozen up front and
stamped into every record.

NOTHING HERE ENCODES AN EXPECTED CONCLUSION
--------------------------------------------
The record captures STATES and COUNTS. It has no notion of a good answer, and
no company-specific branch. If this file ever needs to know which company it
is looking at, something upstream is wrong.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intent_engine.company_ingestion.records import (  # noqa: E402
    MAX_APPROVED_SOURCES,
)

CONTRACT = "breaker_wave_baseline.v1"

#: The cohort Batch 9 froze and published. Held here only to REFUSE a
#: divergence; the selector remains the source of truth.
EXPECTED_TEN = (
    "cloudflare", "advanced-micro-devices", "boeing", "bank-of-america",
    "alimentation-couche-tard", "agnico-eagle-mines", "bce", "stripe",
    "mckinsey", "johnson-and-johnson",
)


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _runtime_sha() -> str:
    """The COMMIT the wave ran on, not the marketing version.

    `version_info()` falls back to `app_version` when no git sha is embedded,
    which in a worktree yields something like "1.5.0-executive-intelligence".
    Two waves on different commits would then carry the same "sha" and §24's
    freeze would silently permit comparing them.
    """
    import subprocess
    here = pathlib.Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here,
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    from intent_engine._version import version_info
    info = version_info()
    return str(info.get("git_sha") or info.get("app_version") or "")


def _tree_dirty() -> bool:
    """A dirty tree means the recorded SHA does not describe the code that
    ran. Recorded so a later comparison can refuse rather than guess."""
    import subprocess
    here = pathlib.Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(["git", "status", "--porcelain",
                              "--untracked-files=no"], cwd=here,
                             capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return True


def analyst_state() -> dict:
    """Whether a reasoning backend is configured, recorded on every record.

    A wave run without one produces EVIDENCE_LIMITED for every company, and a
    later session comparing against it would read an environment difference as
    a product change. Stamping it is what keeps the two distinguishable.
    """
    import os as _os
    try:
        # The factory the WEBAPP uses. An earlier version of this probe
        # imported a name that does not exist and reported the resulting
        # ImportError as "no backend" — which is the same reading as an unset
        # key and would have sent the next session after the wrong fix.
        from intent_engine.strategic_intelligence.analyst.runner import (
            default_client,
        )
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "key_in_env": False,
                "detail": f"import failed: {type(exc).__name__}: "
                          f"{str(exc)[:180]}"}
    # Read the environment AFTER the import: `llm_client` calls load_dotenv()
    # at import time, so checking first would miss a key that arrives from a
    # .env rather than from the shell.
    seen = bool(_os.environ.get("ANTHROPIC_API_KEY"))
    try:
        client = default_client()
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "key_in_env": seen,
                "detail": f"client build failed: {type(exc).__name__}: "
                          f"{str(exc)[:180]}"}
    return {"configured": client is not None, "key_in_env": seen,
            "detail": "" if client is not None
            else ("ANTHROPIC_API_KEY is not set in this environment"
                  if not seen else "key present but no client was built")}


def _dig(node, *path, default=None):
    for key in path:
        if isinstance(node, dict):
            node = node.get(key)
        else:
            return default
    return node if node is not None else default


def _identity(result, meta, company) -> dict:
    report = result.get("strategic_report") or {}
    return {
        "requested_name": company.canonical_name,
        "requested_domain": company.domain,
        "resolved_company_name": meta.get("company_name", ""),
        "resolved_domain": meta.get("domain", ""),
        "domain_matches_manifest": (meta.get("domain", "") or "").endswith(
            company.domain),
        "manifest_identity_difficulty": company.identity_difficulty,
        "parent_company_id": company.parent_company_id,
        "report_subject": _dig(report, "mental_model", "company",
                               default="") or report.get("company_name", ""),
    }


def _source_health(result, outcome) -> dict:
    coverage = result.get("coverage") or {}
    return {
        "attempted": len(outcome.get("ok", [])) + len(
            outcome.get("failed", [])),
        "ok": len(outcome.get("ok", [])),
        "failed": len(outcome.get("failed", [])),
        "fetch_status": outcome.get("status", ""),
        "failure_reasons": sorted({
            str(f.get("reason") or f.get("error") or "unknown")
            for f in outcome.get("failed", [])}),
        "families_present": coverage.get("families_present", []),
        "missing_core": coverage.get("missing_core", []),
        "evidence_report_state": coverage.get("state", ""),
    }


def _evidence(result, ci, run_id) -> dict:
    documents = ci.store.retrieved(run_id)
    library = result.get("evidence_library") or {}
    return {
        "documents_retrieved": len(documents),
        "evidence_library_entries": (len(library) if isinstance(library, list)
                                     else len(library or {})),
        "observations": len(result.get("observations") or []),
        # NOT an independence measurement, and deliberately not named like
        # one: this is a ROW COUNT. Independence has no producer yet.
        "raw_document_count": len(documents),
        "evidence_independence_state": "UNAVAILABLE",
        "independence_note": ("no independence producer exists; a raw "
                              "document count is not corroboration"),
    }


def _intelligence(result) -> dict:
    """Strategic layer states. Every field is a STATE, never a judgement."""
    report = result.get("strategic_report")
    if not isinstance(report, dict):
        return {"strategic_report": "ABSENT",
                "reason": "no strategic report was composed for this run"}
    return {
        "strategic_report": "PRESENT",
        "result_state": str(report.get("result_state") or ""),
        "result_state_detail": str(report.get("result_state_detail") or ""),
        "reasoning_provenance": str(report.get("reasoning_provenance") or ""),
        "strategic_analysis": ("PRESENT"
                               if report.get("strategic_analysis")
                               else "ABSENT"),
        "hypotheses": len(report.get("hypotheses") or []),
        "shifts": len(report.get("shifts") or []),
        "critic_findings": len(report.get("critic_findings") or []),
        "readiness": _dig(result, "readiness", "may_synthesize"),
    }


def _dossier_record(dossier) -> dict:
    if dossier is None:
        return {"built": False,
                "reason": "no dossier was assembled for this run"}
    market_blocks = _dig(dossier.market_block, "blocks", default={}) or {}
    founder_blocks = _dig(dossier.founder_block, "blocks", default={}) or {}
    return {
        "built": True,
        "dossier_id": dossier.dossier_id,
        "dossier_version": dossier.dossier_version,
        "cohort": dossier.cohort,
        "manifest_version": dossier.manifest_version,
        "readiness": dossier.readiness,
        "crossing_state": dossier.crossing_state,
        "market_availability": _dig(dossier.market_block, "availability"),
        "founder_availability": _dig(dossier.founder_block, "availability"),
        "temporal_compatibility": dossier.temporal_compatibility,
        "population_compatibility": dossier.population_compatibility,
        "decision_impact_state": dossier.decision_impact_state,
        "coverage_class": dossier.coverage_class,
        "effective_evidence_cutoff": dossier.effective_evidence_cutoff,
        "quarantined": dossier.quarantined,
        "quarantine_reasons": list(dossier.quarantine_reasons),
        "market_block_states": {k: v.get("state")
                                for k, v in market_blocks.items()},
        "founder_block_states": {k: v.get("state")
                                 for k, v in founder_blocks.items()},
        "absent_blocks": _dig(dossier.quality_block, "absent_blocks",
                              default=[]),
        "visual_verification_state": _dig(dossier.product_block,
                                          "visual_verification_state"),
    }


def run_company(company, *, root: pathlib.Path, frozen: dict) -> dict:
    """One company, the production path, whatever comes out."""
    from intent_engine.demo_dossier.store import DossierStore
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    import logging

    class _Capture(logging.Handler):
        """Keep the WARNING/ERROR lines the run emitted.

        A record that says only `result_state: FAILED` cannot tell an
        exhausted API balance from a malformed request, and both look like
        the product failing to reach a conclusion. The wave records the
        diagnosis alongside the state.
        """

        def __init__(self):
            super().__init__(level=logging.WARNING)
            self.lines = []

        def emit(self, rec):
            try:
                self.lines.append(f"{rec.levelname} {rec.name}: "
                                  f"{rec.getMessage()[:400]}")
            except Exception:  # noqa: BLE001
                pass

    capture = _Capture()
    logging.getLogger("intent_engine").addHandler(capture)

    started = time.time()
    record = {
        "company_id": company.company_id,
        "canonical_name": company.canonical_name,
        "domain": company.domain,
        "country": company.country,
        "sector": company.sector,
        "cohort": company.cohort,
        "public_private": company.public_private,
        "entity_type": company.entity_type,
        "coverage_expectation": company.coverage_expectation,
        "breaker_dimensions": list(company.breaker_dimensions),
        "started_at": _utc(),
        "runtime_sha": frozen["runtime_sha"],
        "manifest_version": frozen["manifest_version"],
        "analyst_configured": frozen["analyst"]["configured"],
        "outcome": "PENDING",
    }
    store_dir = root / company.company_id
    store_dir.mkdir(parents=True, exist_ok=True)
    try:
        app = WebApp(AppConfig(
            # NOT "test": env="test" refuses to build an analyst client by
            # design, so a wave run under it would report EVIDENCE_LIMITED
            # for all ten and look like a product with no conclusions.
            env="development", secret="s" * 40, demo_mode=True,
            web_store_path=store_dir / "web.jsonl",
            fi_store_path=store_dir / "fi.jsonl",
            ci_store_path=store_dir / "ci.jsonl"),
            transport=None, resolver=False)
        # What the APP saw, not what a probe inferred. `_analyst_error`
        # already distinguishes a missing key from a key that built no
        # client, which need opposite fixes.
        record["analyst"] = {
            "client_present": app._analyst_client is not None,
            "key_present": bool(getattr(app, "_analyst_key_present", False)),
            "error": str(getattr(app, "_analyst_error", "")),
        }

        created = app.ci.create_run(
            company_name=company.canonical_name,
            website=f"https://{company.domain}",
            user_id="breaker-wave",
            as_of=datetime.datetime.now(
                datetime.timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00"))
        run_id = created["run_id"]
        record["run_id"] = run_id

        t0 = time.time()
        candidates = app.ci.discover(run_id)
        record["discovery_seconds"] = round(time.time() - t0, 2)
        record["candidates_discovered"] = len(candidates)

        approved = WebApp._recommended_candidate_ids(
            candidates, refusing_hosts=app.ci.refusing_hosts(run_id))
        if not approved:
            approved = [c["candidate_id"]
                        for c in candidates[:MAX_APPROVED_SOURCES]]
        app.ci.approve(
            run_id, user_id="breaker-wave", approved_ids=approved,
            rejected_ids=[c["candidate_id"] for c in candidates
                          if c["candidate_id"] not in approved])
        record["candidates_approved"] = len(approved)

        t0 = time.time()
        outcome = app.ci.fetch_approved(run_id)
        record["fetch_seconds"] = round(time.time() - t0, 2)

        t0 = time.time()
        result = app._compose(run_id) or {}
        record["compose_seconds"] = round(time.time() - t0, 2)

        meta = app.ci.run_meta(run_id) or {}
        record["identity"] = _identity(result, meta, company)
        record["source_health"] = _source_health(result, outcome)
        record["evidence"] = _evidence(result, app.ci, run_id)
        record["intelligence"] = _intelligence(result)
        record["dossier"] = _dossier_record(
            DossierStore(store_dir).latest(company.company_id))
        record["telemetry"] = app._demo_telemetry.as_dict()["counts"]
        record["outcome"] = "COMPLETED"
    except BaseException as exc:  # noqa: BLE001 - a crash IS a result
        record["outcome"] = "CRASHED"
        record["error"] = {"type": type(exc).__name__,
                           "message": str(exc)[:400],
                           "traceback": traceback.format_exc()[-1500:]}
    logging.getLogger("intent_engine").removeHandler(capture)
    record["diagnostics"] = capture.lines[-25:]
    record["finished_at"] = _utc()
    record["wall_seconds"] = round(time.time() - started, 2)
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/v5/breaker_10")
    ap.add_argument("--only", default="",
                    help="comma-separated company_ids, for a rerun")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--env-file", default="",
                    help="path to a .env supplying ANTHROPIC_API_KEY")
    args = ap.parse_args()

    # WHY THIS FLAG EXISTS. `default_client()` calls a bare `load_dotenv()`,
    # which python-dotenv resolves relative to the CALLING MODULE'S FILE — so
    # a checkout whose .env lives in a different worktree silently gets no
    # key, `analyse()` raises AnalystUnavailable, and every company in the
    # wave reports EVIDENCE_LIMITED. That reads exactly like a product with
    # no conclusions, which is the most expensive possible way to be wrong
    # about a baseline. The path is loaded, never logged.
    if args.env_file:
        from dotenv import load_dotenv
        loaded = load_dotenv(dotenv_path=args.env_file, override=False)
        print(f"env-file loaded: {loaded} ({args.env_file})")

    from intent_engine.demo_dossier.dossier import CONTRACT as DOSSIER_CONTRACT
    from intent_engine.validation import breaker_ten, load

    manifest = load()
    ten = breaker_ten(manifest)
    selected = tuple(c.company_id for c in ten)
    if selected != EXPECTED_TEN:
        print("REFUSING TO RUN: the selector no longer returns the frozen "
              "cohort.\n  expected: %s\n  selected: %s"
              % (list(EXPECTED_TEN), list(selected)), file=sys.stderr)
        return 2

    frozen = {
        "contract": CONTRACT,
        "label": args.label,
        "runtime_sha": _runtime_sha(),
        "runtime_tree_dirty": _tree_dirty(),
        "manifest_version": manifest.version,
        "dossier_contract_version": DOSSIER_CONTRACT,
        "analyst": analyst_state(),
        "max_approved_sources": MAX_APPROVED_SOURCES,
        "started_at": _utc(),
        "cohort": list(selected),
    }
    print(json.dumps({k: v for k, v in frozen.items() if k != "cohort"},
                     indent=2))
    if not frozen["analyst"]["configured"]:
        print("\n!! NO REASONING BACKEND. Every company will report "
              "EVIDENCE_LIMITED. This is a RETRIEVAL baseline only and must "
              "not be compared against a keyed run.\n", file=sys.stderr)

    wanted = ([x.strip() for x in args.only.split(",") if x.strip()]
              if args.only else list(selected))
    root = pathlib.Path(tempfile.mkdtemp(prefix="breaker-wave-"))
    print(f"runtime root: {root}\n")

    records = []
    for i, company in enumerate(ten, 1):
        if company.company_id not in wanted:
            continue
        print(f"[{i}/{len(ten)}] {company.company_id} ...", flush=True)
        rec = run_company(company, root=root, frozen=frozen)
        records.append(rec)
        print(f"    {rec['outcome']} in {rec['wall_seconds']}s "
              f"| docs={_dig(rec, 'evidence', 'documents_retrieved', default='-')}"
              f" | state={_dig(rec, 'intelligence', 'result_state', default='-')}"
              f" | dossier={_dig(rec, 'dossier', 'readiness', default='-')}",
              flush=True)

    frozen["finished_at"] = _utc()
    payload = {"frozen": frozen, "runtime_root": str(root),
               "results": records}
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{args.label}_{frozen['runtime_sha'][:12] or 'unknown'}.json"
    path = out_dir / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=False),
                    encoding="utf-8")
    print(f"\nwrote {path}  ({len(records)} companies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
