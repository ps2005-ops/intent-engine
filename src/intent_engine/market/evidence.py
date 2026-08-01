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

# Source classes that are somebody OTHER than the company talking. The
# reasoner requires one of these before a reading can become a position, so
# which candidates get approved decides whether that gate is reachable at all.
_OUTSIDE_CLASSES = ("independent_reporting", "customer_voice",
                    "competitor_statement", "analyst_coverage")


def select_diverse(candidates: list, limit: int) -> list:
    """Approve a SPREAD of source classes, not the first N in discovery order.

    Measured defect, not a hypothetical. Discovery returns roughly thirty
    `company_owned` candidates ahead of three `customer_voice` ones, so a
    `candidates[:8]` slice took eight company pages and zero outside sources —
    for every company, every time. Across eleven fixtures that produced
    `independent_source: 0/11`, and every tradable company that formed a
    reading then died at `no_outside_source`. The slice made the gate it was
    feeding structurally unreachable, which is worse than a gate that
    sometimes fails: it could never pass.

    Round-robin across classes, outside classes drawn first so they cannot be
    crowded out by the company's own pages. Within a class, discovery order is
    preserved — that ranking is the ingestion layer's judgement and this is not
    the place to second-guess it.
    """
    by_class: Dict[str, List[dict]] = {}
    for candidate in candidates or ():
        key = candidate.get("source_class") or "company_owned"
        by_class.setdefault(key, []).append(candidate)

    # outside classes first, then everything else alphabetically for stability
    order = sorted(by_class, key=lambda k: (k not in _OUTSIDE_CLASSES, k))
    out: List[dict] = []
    while len(out) < limit and any(by_class[k] for k in order):
        for key in order:
            if len(out) >= limit:
                break
            if by_class[key]:
                out.append(by_class[key].pop(0))
    return out


def _observation_rows(report: dict, *, as_of: str) -> List[dict]:
    """Strategic observations as hosted evidence rows.

    Only observations carrying real text become evidence. An observation with
    no readable content is a retrieval artefact, and admitting it would inflate
    `evidence_count` — a number later used to judge whether a company was well
    covered — with rows that say nothing.
    """
    from intent_engine.market.session import leakage_cutoff
    _cutoff = leakage_cutoff(as_of)

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
        # LEAKAGE. The strategic layer dates an otherwise-undated observation
        # to the RETRIEVAL time, which is now -- not to the decision date. When
        # `as_of` is today (a live daily run) the two agree and nothing is
        # wrong. When `as_of` is in the past -- every historical replay, which
        # is the only way this engine can be evaluated -- the observation is
        # dated AFTER the decision it is feeding, and the decision is made with
        # information that did not exist.
        #
        # Dropped rather than clamped: moving the date back to `as_of` would
        # assert the evidence existed then, which is precisely what is not
        # known. A dropped row is a visible gap; a clamped one is an invisible
        # fabrication. Caught by the pre-commit suite on the day this project
        # was told to use only point-in-time information.
        #
        # DAY 17. The cutoff is timezone-aware. `published` is stamped in UTC;
        # `as_of` is a calendar day in the OPERATING timezone. Comparing them
        # naively dropped every observation between 20:00 and midnight local,
        # every night -- silently, as `evidence: 0`. Replay stays strict; see
        # `session.leakage_cutoff`.
        if published > _cutoff:
            continue
        # Express the admitted date in the OPERATING frame. An observation
        # retrieved at 21:00 Toronto carries a UTC stamp of tomorrow; the
        # decision frame calls that instant today, and leaving the row dated
        # `as_of + 1` would just make every downstream `<= as_of` check drop it
        # again -- the same bug, one layer further on.
        #
        # This is NOT the replay clamp the paragraph above forbids, and it
        # cannot become it: during replay `_cutoff == as_of`, so anything
        # later was already dropped and this line is unreachable. It only ever
        # renames "now, in UTC" to "now, in the operating timezone".
        if published > as_of[:10]:
            published = as_of[:10]
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
    industry: bool = True,
    industry_limit: int = 25,
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
            approved = [c["candidate_id"]
                        for c in select_diverse(candidates, max_sources)]
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

        # INDUSTRY EVIDENCE. Third-party coverage of this company, published on
        # or before `as_of`. The adapter enforces point-in-time itself
        # (anything newer is rejected, never clamped) and classifies by
        # AUTHORSHIP, so a company press release syndicated through a news feed
        # comes back as COMPANY and cannot corroborate anything.
        #
        # Failure here is recorded and skipped: a research sweep that stops
        # because one news feed is unreachable teaches less than one that
        # covers the rest and says which failed.
        industry_rows: List[dict] = []
        if industry:
            try:
                from intent_engine.market.industry import (
                    fetch_industry_evidence,
                )
                for doc in fetch_industry_evidence(name, as_of=as_of,
                                                   limit=industry_limit):
                    if doc.is_independent:
                        industry_rows.append(doc.as_evidence_row())
            except Exception as exc:  # noqa: BLE001 — one feed, not the sweep
                if on_error is not None:
                    on_error(getattr(company, "company_id", ""), exc)

        rows = rows + industry_rows
        return {
            "thesis": _thesis_of(report),
            "priorities": list(getattr(company, "strategic_priorities", ())),
            "evidence": rows,
            # carried for the record; the reasoner reads the rebuilt view
            "readiness_state": ((result or {}).get("readiness") or {}).get("state", ""),
            "industry_documents": len(industry_rows),
        }

    return research_fn
