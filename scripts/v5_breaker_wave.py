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
import collections
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
    """Source outcomes, read under the names the PRODUCER actually uses.

    An earlier version of this reader asked for `reason`/`error` and
    `families_present`, got neither, and reported "unknown" failures and zero
    evidence families for all ten companies — two convincing product defects
    that were entirely defects in this function. The producer writes
    `failure_type` / `safe_message` (see `service._fail`) and `families` (see
    `coverage.assess`). A measurement instrument that names its fields wrongly
    manufactures findings, which is worse than measuring nothing.
    """
    coverage = result.get("coverage") or {}
    failures = outcome.get("failed", []) or []
    from collections import Counter
    kinds = Counter(str(f.get("failure_type") or "unrecorded")
                    for f in failures)
    return {
        "attempted": len(outcome.get("ok", [])) + len(failures),
        "ok": len(outcome.get("ok", [])),
        "failed": len(failures),
        "fetch_status": outcome.get("status", ""),
        "failure_types": dict(sorted(kinds.items())),
        # COUNTED, not just listed. `failure_messages` below is a deduped SET,
        # which answers "which statuses occurred" and not "how many of each" —
        # so the 62 http_status failures in the first wave could not be split
        # into 403 (we are being blocked) and 404 (we asked for the wrong
        # URL). Those are different defects with different fixes, and the
        # deduped set silently could not tell them apart.
        "http_status_counts": dict(sorted(Counter(
            str(f.get("safe_message") or "").strip()
            for f in failures
            if f.get("failure_type") == "http_status").items())),
        "failure_messages": sorted({str(f.get("safe_message") or "")[:160]
                                    for f in failures if f.get("safe_message")
                                    })[:6],
        "retryable_failures": sum(1 for f in failures if f.get("retryable")),
        "families": coverage.get("families", []),
        "family_counts": coverage.get("family_counts", {}),
        "missing_core": coverage.get("missing_core", []),
        "evidence_report_state": coverage.get("state", ""),
    }


def _evidence(result, ci, run_id) -> dict:
    documents = ci.store.retrieved(run_id)
    library = result.get("evidence_library") or {}
    observations = result.get("observations") or []

    # Independence, from the canonical producer. Until Batch 12 this field
    # read UNAVAILABLE because no producer existed; the distinction between
    # "measured, and it is zero" and "nothing measured it" is preserved by
    # `state`, which the producer sets and this reader never invents.
    from intent_engine.company_ingestion import independence as IND
    try:
        assessed = IND.assess(documents)
    except Exception as exc:  # noqa: BLE001
        # A broad except that reports the failure. Swallowing it into a zero
        # is the exact defect this program has found repeatedly: a silent
        # zero is indistinguishable from a measured absence of independence.
        assessed = {"state": "PRODUCER_FAILED",
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}

    return {
        "documents_retrieved": len(documents),
        "evidence_library_entries": (len(library) if isinstance(library, list)
                                     else len(library or {})),
        "observations": len(observations),
        # A ROW COUNT, kept under a name that cannot be mistaken for
        # corroboration. It sits next to the independence block on purpose:
        # the pair is what stops "12 documents" reading as "12 signals".
        "raw_document_count": len(documents),
        "evidence_independence_state": assessed.get("state", "UNAVAILABLE"),
        "independence": {k: v for k, v in assessed.items() if k != "rows"},
        "independence_rows": assessed.get("rows", []),
    }


def _learning(result, assessed_rows, *, root=None, company_id="") -> dict:
    """Per-company evidence→knowledge attribution, read from the LEDGER.

    `effects=()` was hard-coded here, which is why this could only ever report
    NOT_ATTEMPTED however well retrieval performed. The effects are now read
    from the file the production producer writes, so a run that changed
    something reports it and a run that changed nothing still reports why.
    """
    from intent_engine.company_ingestion import learning_attribution as LA

    effects = ()
    if root is not None:
        try:
            from intent_engine.external_intel import effect_producer as EP
            effects = EP.load_effects(root, company_id=company_id)
        except Exception:  # noqa: BLE001 - a reader may not break the wave
            effects = ()

    report = result.get("strategic_report")
    usable = (isinstance(report, dict)
              and str(report.get("result_state") or "") not in ("FAILED", ""))
    return LA.conversion(
        evidence_rows=assessed_rows, effects=effects,
        independence_rows=assessed_rows,
        knowledge_layer_ran=usable,
        blocked_reason="" if usable else (
            "the run reached no usable strategic report, so no knowledge "
            "state existed for an evidence row to change"))


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
        record["learning"] = _learning(
            result, record["evidence"].get("independence_rows") or [],
            root=app._runtime_root, company_id=company.company_id)
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


#: Returned instead of a number when a ratio has no denominator. NEVER 0, and
#: never an epsilon in the denominator to force a number out: "we divided by
#: nothing" and "the answer is zero" are different facts, and only one of them
#: is a finding about the system.
UNMEASURABLE = "UNMEASURABLE"
#: Returned when no producer for a quantity exists at all. Distinct from
#: UNMEASURABLE, which means the producer ran and the denominator was empty.
UNAVAILABLE = "UNAVAILABLE"


def _ratio(numerator, denominator):
    return (round(numerator / denominator, 4) if denominator
            else UNMEASURABLE)


def _observations_state(records: list) -> dict:
    """Whether a zero observation count is about evidence or about the backend.

    A strategic report that is ABSENT, or PRESENT with a FAILED result state,
    means the reasoning layer never delivered. Observations are downstream of
    it, so their count says nothing about the documents in that case.
    """
    usable = 0
    for record in records:
        intel = record.get("intelligence") or {}
        if (intel.get("strategic_report") == "PRESENT"
                and str(intel.get("result_state") or "") not in
                ("FAILED", "")):
            usable += 1
    if usable:
        return {"state": "MEASURED", "companies_with_usable_report": usable,
                "of": len(records)}
    return {
        "state": "BLOCKED_EXTERNAL_CREDITS",
        "companies_with_usable_report": 0, "of": len(records),
        "reason": ("no company reached a usable strategic report, so the "
                   "observation count is downstream of the reasoning "
                   "backend and is NOT a measurement of the evidence"),
    }


def _learning_conversion(records: list) -> dict:
    """Did the evidence change anything — or why can that not be said?

    THE POPULATIONS ARE ROWS ON BOTH SIDES (§22). One evidence row can produce
    several effects, so the numerator counts ROWS THAT PRODUCED AN EFFECT and
    never the effects themselves. A rate built the other way can exceed 1 and
    has, in this programme, before.

    A company whose reasoning layer never ran contributes to NEITHER side.
    Folding it in as a zero-effect row would let an unpaid API bill read as
    evidence that taught the system nothing.
    """
    states = collections.Counter(
        str(_dig(r, "learning", "attribution_state") or "ABSENT")
        for r in records)
    eligible = [r for r in records
                if _dig(r, "learning", "attribution_state") == "MEASURED"]
    blocked = [r for r in records
               if _dig(r, "learning", "attribution_state")
               == "BLOCKED_EXTERNAL_CREDITS"]
    if not eligible:
        return {
            "state": "BLOCKED_EXTERNAL_CREDITS" if blocked else UNAVAILABLE,
            "reason": (
                f"{len(blocked)} of {len(records)} compan(ies) produced no "
                "knowledge state for evidence to change, so learning "
                "conversion is downstream of the reasoning backend and is "
                "NOT a measurement of the evidence"
                if blocked else
                "no company reported an attribution state"),
            "attribution_states": dict(sorted(states.items())),
            "companies_measured": 0,
            "of": len(records),
            "evidence_rows": UNAVAILABLE,
            "effect_producing_evidence_rows": UNAVAILABLE,
            "independent_effect_producing_evidence_rows": UNAVAILABLE,
            "zero_effect_evidence_rows": UNAVAILABLE,
            "learning_conversion": UNAVAILABLE,
        }
    rows = sum(_dig(r, "learning", "eligible_evidence_rows", default=0)
               for r in eligible)
    producing = sum(
        _dig(r, "learning", "effect_producing_evidence_rows", default=0)
        for r in eligible)
    independent = sum(
        _dig(r, "learning", "independent_effect_producing_evidence_rows",
             default=0) for r in eligible)
    return {
        "state": "MEASURED",
        "reason": "",
        "attribution_states": dict(sorted(states.items())),
        "companies_measured": len(eligible),
        "of": len(records),
        "evidence_rows": rows,
        "effect_producing_evidence_rows": producing,
        "independent_effect_producing_evidence_rows": independent,
        "zero_effect_evidence_rows": rows - producing,
        "learning_conversion": _ratio(producing, rows),
    }


def _cohort_summary(records: list) -> dict:
    """The retrieval → evidence → independence chain, over the whole cohort.

    Every ratio here is named for the POPULATIONS it divides. That is not
    pedantry: this program has already shipped a "per-evidence" rate whose
    numerator counted effects (many per row) against a denominator counting
    rows, which is not a fraction and cannot be read as one. Where the two
    populations would differ, the name says so (`observations_per_document`
    is a RATE and may exceed 1; `independent_document_share` is a SHARE and
    cannot).
    """
    attempted = sum(_dig(r, "source_health", "attempted", default=0)
                    for r in records)
    ok = sum(_dig(r, "source_health", "ok", default=0) for r in records)
    documents = sum(_dig(r, "evidence", "documents_retrieved", default=0)
                    for r in records)
    observations = sum(_dig(r, "evidence", "observations", default=0)
                       for r in records)
    fetch_seconds = sum(float(r.get("fetch_seconds") or 0) for r in records)

    measured = [r for r in records
                if _dig(r, "evidence", "evidence_independence_state")
                == "MEASURED"]
    independent = sum(
        _dig(r, "evidence", "independence", "independent_evidence_count",
             default=0) for r in measured)
    duplicates = sum(
        _dig(r, "evidence", "independence", "duplicate_document_count",
             default=0) for r in measured)
    republications = sum(
        _dig(r, "evidence", "independence", "republication_count", default=0)
        for r in measured)
    self_reports = sum(
        _dig(r, "evidence", "independence", "company_self_report_count",
             default=0) for r in measured)
    unknown = sum(
        _dig(r, "evidence", "independence", "unknown_lineage_count",
             default=0) for r in measured)
    concentrations = [
        _dig(r, "evidence", "independence", "concentration_ratio")
        for r in measured]
    concentrations = [c for c in concentrations if isinstance(c, (int, float))]

    failure_types: dict = {}
    http_statuses: dict = {}
    for record in records:
        for key, value in (_dig(record, "source_health", "failure_types",
                                default={}) or {}).items():
            failure_types[key] = failure_types.get(key, 0) + value
        for key, value in (_dig(record, "source_health",
                                "http_status_counts", default={}) or {}).items():
            http_statuses[key] = http_statuses.get(key, 0) + value

    return {
        "companies": len(records),
        "independence_measured_for": len(measured),
        "retrieval": {
            "attempted": attempted, "successful_documents": ok,
            "retrieval_yield": _ratio(ok, attempted),
            "failure_types": dict(sorted(failure_types.items())),
            "http_status_counts": dict(sorted(http_statuses.items())),
            "fetch_seconds": round(fetch_seconds, 1),
        },
        "evidence": {
            "documents": documents,
            "observations": observations,
            # A RATE, not a share: one document can carry many observations,
            # so this is not bounded by 1 and must never be read as a yield.
            "observations_per_document": _ratio(observations, documents),
            # WHY the rate is what it is. Observations are produced downstream
            # of the strategic layer, so when no company reached a usable
            # strategic report the rate is a fact about the BACKEND, not about
            # retrieval. Reported next to the number because 0.0 read alone
            # says "the documents carried nothing", which would be a finding
            # about the evidence and is not what happened.
            "observations_state": _observations_state(records),
        },
        "independence": {
            "independent_documents": independent,
            "duplicate_documents": duplicates,
            "republications": republications,
            "company_self_reports": self_reports,
            "unknown_lineage": unknown,
            # Both populations are DOCUMENTS, so this is a true share.
            "independent_document_share": _ratio(independent, documents),
            "mean_source_concentration": (
                round(sum(concentrations) / len(concentrations), 4)
                if concentrations else UNMEASURABLE),
            "seconds_per_independent_document": _ratio(
                round(fetch_seconds, 1), independent),
        },
        # THE SEAM NOW EXISTS, so this reports a STATE from the producer
        # rather than the absence of a producer.
        #
        # Batch 12 reported UNAVAILABLE here because nothing on the founder
        # path mapped an evidence row to a state change; that is now
        # `company_ingestion.learning_attribution`, which mirrors the market
        # ledger's vocabulary. What it reports on THIS cohort is still not a
        # number, because no company reached a strategic report — but the
        # reason is now BLOCKED_EXTERNAL_CREDITS, a fact about the backend,
        # rather than an architectural absence.
        "learning_conversion": _learning_conversion(records),
        "high_activity_low_learning": _high_activity_low_learning(
            documents, independent, duplicates, republications, len(measured),
            learning=_learning_conversion(records)),
    }


#: Below this share of documents carrying an independent vantage point, volume
#: is being produced without new information. Not a quality bar on the
#: COMPANY — a sparse private company legitimately has little outside
#: coverage — which is why the verdict needs the volume floor too.
LOW_INDEPENDENCE_SHARE = 0.20
MIN_DOCUMENTS_FOR_VERDICT = 20


def _first_starved_conversion(documents, independent, learning) -> str:
    """The FIRST conversion in the chain that is starved (§27).

    documents → independent evidence → effect-producing evidence → decision.

    Naming the first one matters more than naming them all: fixing a later
    stage while an earlier one is starved moves nothing, and this programme
    has repeatedly found the real zero one layer below where it was reported.
    """
    if not documents:
        return "retrieval → documents"
    share = independent / documents
    if share < LOW_INDEPENDENCE_SHARE:
        return "documents → independent evidence"
    state = str((learning or {}).get("state") or "")
    if state != "MEASURED":
        # NOT a starved conversion — an unmeasured one. Saying "independent
        # evidence → learning is starved" here would blame the evidence for
        # an unpaid API bill.
        return f"independent evidence → learning: {state or UNAVAILABLE}"
    producing = (learning or {}).get("effect_producing_evidence_rows") or 0
    if not producing:
        return "independent evidence → effect-producing evidence"
    return "none"


def _high_activity_low_learning(documents, independent, duplicates,
                                republications, measured_companies,
                                learning=None) -> dict:
    """Busy, and not learning — named in those words, with the counts.

    Mirrors the vocabulary of `market.learning_acceleration`, which owns the
    canonical detector. It is restated rather than imported because the
    founder branch structurally cannot import the market package; the states
    are kept identical so the two can be read side by side.

    This arm sees the RETRIEVAL half of the condition only. The belief half —
    "independent evidence rose but nothing moved" — needs the effect ledger
    and is reported UNMEASURABLE rather than assumed satisfied.
    """
    if not measured_companies or documents < MIN_DOCUMENTS_FOR_VERDICT:
        return {"detected": False, "status": UNMEASURABLE,
                "reason": (f"{documents} document(s) across "
                           f"{measured_companies} measured compan(ies) is "
                           f"too little volume for the share to mean "
                           f"anything"),
                "belief_arm": UNMEASURABLE}
    share = round(independent / documents, 4) if documents else 0.0
    detected = share < LOW_INDEPENDENCE_SHARE
    return {
        "detected": bool(detected),
        "status": "DEGRADING" if detected else "STABLE",
        "documents": documents,
        "independent_documents": independent,
        "independent_document_share": share,
        "duplicate_documents": duplicates,
        "republications": republications,
        "which_conversion_failed": (
            "documents → independent evidence" if detected else "none"),
        "reason": (
            f"{documents} documents produced {independent} independent "
            f"vantage point(s) ({share:.1%}), below the "
            f"{LOW_INDEPENDENCE_SHARE:.0%} floor; retrieval is producing "
            f"volume that is not new information"
            if detected else
            f"{independent} of {documents} documents carry an independent "
            f"vantage point ({share:.1%}), at or above the "
            f"{LOW_INDEPENDENCE_SHARE:.0%} floor"),
        # The second arm needs belief movement. The ledger now exists, so
        # this reports the attribution STATE rather than the absence of a
        # producer — and still never says STABLE, which would claim the
        # system IS learning when nothing measured whether it did.
        "belief_arm": str((learning or {}).get("state") or UNAVAILABLE),
        "belief_arm_reason": str(
            (learning or {}).get("reason")
            or "learning attribution reported no state"),
        "first_starved_conversion": _first_starved_conversion(
            documents, independent, learning),
    }


def resolve_runtime_root(requested):
    """Return (root, carried_company_ids) for this pass.

    An absent `requested` means a fresh temp root: pass one is a FIRST
    observation of everything, correctly. A `requested` root is a SECOND
    iteration, and it must be a root a previous pass actually wrote — so a
    missing directory raises rather than being created. Creating it would
    hand back an empty store, every company would report FIRST_OBSERVATION
    again, and the rerun would look like it passed while proving nothing.
    """
    if not requested:
        return pathlib.Path(tempfile.mkdtemp(prefix="breaker-wave-")), []
    root = pathlib.Path(requested).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(
            f"--root {root} does not exist. A second iteration must reuse a "
            "root a previous run actually wrote; creating an empty one would "
            "silently reproduce FIRST_OBSERVATION and look like a passing "
            "rerun.")
    return root, sorted(p.name for p in root.iterdir() if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/v5/breaker_10")
    ap.add_argument("--only", default="",
                    help="comma-separated company_ids, for a rerun")
    ap.add_argument("--label", default="baseline")
    # WHY THIS FLAG EXISTS. The runtime root was ALWAYS a fresh mkdtemp, so
    # every run met its own priors as absent: a second pass over the same ten
    # could only ever report FIRST_OBSERVATION again, and the temporal
    # machinery -- prior persisted, prior reloaded, comparison run -- had no
    # way to be exercised on real intelligence. That is not something credit
    # buys; a discarded store stays discarded at any price. Passing --root
    # with a previous run's root is what makes the second iteration a second
    # OBSERVATION rather than a first one repeated.
    ap.add_argument("--root", default="",
                    help="reuse a previous run's runtime root, so this pass "
                         "meets the priors that pass persisted (§12 second "
                         "iteration). Default: a fresh temp root.")
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
    try:
        root, carried = resolve_runtime_root(args.root)
    except NotADirectoryError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.root:
        print(f"REUSING runtime root: {root}\n"
              f"  {len(carried)} company store(s) carried forward: "
              f"{', '.join(carried) or 'NONE'}")
        if not carried:
            print("  !! the root holds no company stores, so this pass will "
                  "still be a FIRST observation for every company.",
                  file=sys.stderr)
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
               "cohort_summary": _cohort_summary(records),
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
