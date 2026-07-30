"""Stage 1 — real evidence collection, by reusing Founder Intelligence.

WHAT THIS REPLACES
------------------
`hosted/context._env_research_fn` returns `{"evidence": [], "thesis": ""}` in
production. Every company therefore reached the opportunity reasoner with
nothing to reason over and exited at the first gate, `no_strategic_reading`.
That is the reason a production daily cycle taught the engine nothing: not the
absence of a market signal, but the absence of any evidence at all.

WHY IT IS A WIRE AND NOT A NEW COLLECTOR
----------------------------------------
Founder Intelligence already does this, in production, verified: it discovers
public sources for a company, retrieves them, parses them, and derives dated
observations carrying a source class. Building a second research path would be
the duplicate infrastructure this phase is explicitly forbidden to create, and
it would be a worse one — the existing path has a readiness gate, a leakage
check, source-diversity accounting and a quality gate that took a milestone to
get right.

So this module owns exactly one thing: the translation between that pipeline's
output and the shape the hosted runtime stores.

PROVENANCE
----------
Runs are recorded with `actor_type="system"`. The webapp's own runs stay
"human". An autonomous job filed under a human actor would put a false answer
in the append-only trail whose entire job is to say who asked.

THE CEILING, STATED
-------------------
Founder Intelligence's measured limit carries over unchanged: roughly two
companies in five yield a full strategic reading, because JS-rendered sites
return metadata rather than body text (`/readyz` → `browser_rendering: false`).
This does not make every company reason. It makes the readable ones reason,
where today none do — and the ones that fail now fail with a *recorded reason*
rather than silently producing nothing.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# The evidence `kind` written for each observation, chosen so that
# `market.daily._KIND_TO_SOURCE_CLASS` maps it back to the SAME source class
# the strategic layer assigned. Round-tripping through the hosted store must
# not quietly reclassify a customer review as a company blog post.
_SOURCE_CLASS_TO_KIND = {
    "investor_material": "filing",
    "executive_statement": "investor",
    "independent_reporting": "news",
    "analyst_coverage": "analyst",
    "customer_voice": "customer",
    "competitor_statement": "competitor",
    "company_owned": "product",
}

# A system actor, not a person. Used as the run owner so the approval
# ownership check still holds without inventing a fake user account.
SYSTEM_ACTOR = "system:market-research"


def _observation_rows(report: dict, *, as_of: str) -> List[dict]:
    """Strategic observations as hosted evidence rows.

    Only observations carrying real text become evidence. An observation with
    no readable content is a retrieval artefact, and admitting it would inflate
    `evidence_count` — a number later used to judge whether a company was well
    covered — with rows that say nothing.
    """
    rows: List[dict] = []
    for obs in (report.get("observations") or ()):
        if not isinstance(obs, dict):
            continue
        summary = " ".join(str(obs.get("text") or obs.get("excerpt")
                               or "").split())
        if not summary:
            continue
        source_class = str(obs.get("source_class") or "company_owned")
        # An undated observation is dated to the run. It is honest -- we know
        # we saw it today -- and `refresh_company`'s leakage check then treats
        # it as same-day rather than future-dated.
        published = str(obs.get("date") or "")[:10] or as_of[:10]
        rows.append({
            "kind": _SOURCE_CLASS_TO_KIND.get(source_class, "product"),
            "summary": summary[:600],
            "source": obs.get("url") or obs.get("source_id") or source_class,
            "published_at": published,
            "confidence": 0.4 if obs.get("weak") else 0.7,
            "interpretation": " ".join(str(obs.get("signal") or "").split()),
        })
    return rows


def _thesis_of(report: dict) -> str:
    """The company's reading, or "" when the strategic layer withheld one.

    A withheld view is not a missing value to be filled in with the next-best
    sentence. It is the gate's answer, and it must survive into the hosted
    state so the reasoner sees the same refusal a human would.
    """
    thesis = (report or {}).get("thesis") or {}
    if thesis.get("view_withheld"):
        return ""
    return " ".join(str(thesis.get("view") or "").split())


def founder_intelligence_research_fn(
    ci_service, fi_service, *,
    max_sources: int = 8,
    actor: str = SYSTEM_ACTOR,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Callable[[Any, str], Dict]:
    """A `research_fn` that runs the real Founder Intelligence pipeline.

    Bounded by `max_sources` per company, which the hosted budget already
    carries (`MAX_SOURCES_PER_COMPANY`). One company's failure is recorded and
    skipped rather than allowed to end the daily cycle: a research sweep that
    stops on the first unreachable website teaches the engine less than one
    that covers the other twenty-four and says which one failed.
    """
    def research_fn(company, as_of: str) -> Dict:
        website = getattr(company, "website", "") or ""
        name = getattr(company, "canonical_name", "") or ""
        if not website:
            return {"evidence": [], "thesis": "", "priorities": [],
                    "skipped": "no website on the company profile"}
        try:
            run = ci_service.create_run(company_name=name, website=website,
                                        user_id=actor, as_of=as_of,
                                        actor_type="system")
            run_id = run["run_id"]
            candidates = ci_service.discover(run_id)
            approved = [c["candidate_id"] for c in candidates][:max_sources]
            if not approved:
                return {"evidence": [], "thesis": "", "priorities": [],
                        "skipped": "no public source could be discovered"}
            ci_service.approve(run_id, user_id=actor, approved_ids=approved,
                               rejected_ids=[], actor_type="system")
            ci_service.fetch_approved(run_id)
            result = ci_service.compose_with_quality(run_id,
                                                     fi_service=fi_service)
        except Exception as exc:  # noqa: BLE001 — one company, not the sweep
            if on_error is not None:
                on_error(getattr(company, "company_id", ""), exc)
            return {"evidence": [], "thesis": "", "priorities": [],
                    "error": type(exc).__name__}

        report = (result or {}).get("strategic_report") or {}
        rows = _observation_rows(report, as_of=as_of)
        return {
            "thesis": _thesis_of(report),
            "priorities": list(getattr(company, "strategic_priorities", ())),
            "evidence": rows,
            # carried for the record; the reasoner reads the rebuilt view
            "readiness_state": ((result or {}).get("readiness") or {}).get("state", ""),
        }

    return research_fn
