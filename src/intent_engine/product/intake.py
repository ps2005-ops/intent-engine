"""Automatic opportunity intake (T020).

This closes the loops the earlier sessions opened. Gaps that used to
evaporate — an unanswered research question, an experiment that settled
nothing, a customer who left — become candidate opportunities that sit in
a review queue with their origin cited.

    T019 research debt              -> candidate opportunity
    T018 INCONCLUSIVE / TOO FEW /   -> candidate opportunity
         GUARDRAIL BREACHED
    T014 churn / at-risk facts      -> candidate opportunity

Bars, each individually tested:

    intake is deterministic and idempotent — re-running creates no
        duplicates, because every candidate's dedup key is derived from
        its origin rather than from when it was scanned
    every intake-created opportunity cites its origin artifact
    an intake-created opportunity is a CANDIDATE: it enters the index and
        the review queue, and it does not enter the roadmap
    the origin's uncertainty travels — an INCONCLUSIVE experiment does not
        produce a confidently-scored opportunity, because the origin label
        is recorded and the scoring cap reads it

Intake records a derived problem statement alongside each opportunity.
That is deliberate: an opportunity with no problem behind it is exactly
the artifact this subsystem exists to prevent, so intake states the
problem the origin implies rather than skipping the step.
"""
from __future__ import annotations

from intent_engine.product.problems import problem_dedup_key
from intent_engine.product.records import (
    REF_CRM_FACT, REF_EXPERIMENT, REF_RESEARCH_DEBT, ProductError,
)

INTAKE_VERSION = "product_intake.v1"

# The six named debt kinds, plus `need_methodology`, which T019 also emits.
# Mapping a kind to a phrasing is deterministic; nothing here is drafted.
RESEARCH_DEBT_TEMPLATES = {
    "need_customer_interview": "Interview affected users about {subject}",
    "need_experiment": "Design an experiment to settle {subject}",
    "need_primary_source": "Acquire a primary source for {subject}",
    "need_replication": "Replicate the finding for {subject} from a second "
                        "origin",
    "need_independent_corroboration": "Seek independent corroboration for "
                                      "{subject}",
    "need_newer_evidence": "Refresh the evidence for {subject}",
    "need_methodology": "Record a stated methodology for {subject}",
}

# T018 labels whose uncertainty is the reason an opportunity exists.
UNSETTLED_GROWTH_LABELS = ("INCONCLUSIVE", "TOO FEW OBSERVATIONS",
                           "GUARDRAIL BREACHED")

# T014 facts that indicate customer pain rather than customer activity.
CRM_PAIN_EVENTS = ("crm.churned", "crm.customer_at_risk")


def _candidate(*, intake_kind, statement, scope, title, origin,
               evidence_references, why_now, what_changes_if_ignored,
               work_category, first_observed_at, affected_customers=None):
    return {
        "intake_version": INTAKE_VERSION,
        "intake_kind": intake_kind,
        "candidate": True,
        "problem": {
            "statement": statement,
            "scope": scope,
            "evidence_references": evidence_references,
            "affected_customers": sorted(set(affected_customers or [])),
            "why_now": why_now,
            "what_changes_if_ignored": what_changes_if_ignored,
            "first_observed_at": first_observed_at,
        },
        "opportunity": {
            "title": title,
            "origin": origin,
            "work_category": work_category,
            "evidence_references": evidence_references,
        },
        "dedup_key": problem_dedup_key(statement, scope),
    }


def intake_candidates_from_research_debt(package: dict, *, request_id: str,
                                         as_of: str) -> list:
    """Every `research_debt` item from a T019 package becomes a candidate.

    The package is read, never recomputed: T019 owns coverage and debt.
    """
    debt_items = list(package.get("research_debt") or [])
    candidates = []
    for item in debt_items:
        kind = item.get("kind")
        template = RESEARCH_DEBT_TEMPLATES.get(kind)
        if template is None:
            raise ProductError(
                f"unmapped research-debt kind {kind!r} — intake maps every "
                f"kind T019 emits: {sorted(RESEARCH_DEBT_TEMPLATES)}")
        subject = item.get("question") or "an unstated question"
        title = template.format(subject=subject)
        statement = (f"A research gap is open: {subject} — recorded as "
                     f"{kind} in an evidence package")
        candidates.append(_candidate(
            intake_kind="research_debt",
            statement=statement,
            scope=f"research:{request_id}",
            title=title,
            origin={"kind": "research_package", "request_id": request_id,
                    "debt_kind": kind, "label": "INSUFFICIENT",
                    "detail": item.get("detail", ""),
                    "package_version": package.get("package_version")},
            evidence_references=[{"kind": REF_RESEARCH_DEBT,
                                  "ref_id": f"{request_id}:{kind}:{subject}",
                                  "request_id": request_id,
                                  "detail": item.get("detail", "")}],
            why_now=("the gap is open in the current evidence package, so "
                     "anything resting on it carries the gap forward"),
            what_changes_if_ignored=(
                "the question stays unsettled and any proposal that leans on "
                "it inherits an unstated dependency on it"),
            work_category="research",
            first_observed_at=as_of))
    return candidates


def intake_candidates_from_growth(result: dict, *, as_of: str) -> list:
    """A T018 result whose label settled nothing becomes a candidate that
    cites the experiment and the label."""
    label = result.get("label")
    if label not in UNSETTLED_GROWTH_LABELS:
        return []
    experiment_id = result.get("experiment_id")
    statement = (f"An experiment closed without settling its question: "
                 f"{experiment_id} carries the label {label}")
    title = f"Resolve what experiment {experiment_id} left unsettled"
    reasons = list(result.get("reasons") or [])
    return [_candidate(
        intake_kind="growth_result",
        statement=statement,
        scope=f"growth:{experiment_id}",
        title=title,
        origin={"kind": "growth_result", "experiment_id": experiment_id,
                "label": label, "label_rule_version":
                    result.get("label_rule_version"),
                "reasons": reasons},
        evidence_references=[{"kind": REF_EXPERIMENT,
                              "ref_id": experiment_id,
                              "experiment_id": experiment_id,
                              "label": label}],
        why_now=("the experiment has stopped and its label is the current "
                 "recorded state of the question"),
        what_changes_if_ignored=(
            "the question the experiment was registered to answer stays "
            "open, and the cost of running it is not recovered"),
        work_category="growth_bet",
        first_observed_at=as_of)]


def intake_candidates_from_crm(crm_facts, *, as_of: str,
                               minimum_entities: int = 1) -> list:
    """Repeated churn and at-risk facts become candidates citing the
    entities. Entities are referenced by id — never copied, and never
    described by anything this subsystem invents about them."""
    grouped = {}
    for fact in crm_facts:
        event_type = fact.get("event_type")
        entity = fact.get("crm_entity_id")
        if event_type in CRM_PAIN_EVENTS and entity:
            grouped.setdefault(event_type, set()).add(entity)

    candidates = []
    for event_type in sorted(grouped):
        entities = sorted(grouped[event_type])
        if len(entities) < minimum_entities:
            continue
        readable = event_type.split(".", 1)[1].replace("_", " ")
        statement = (f"{len(entities)} customer entity reference(s) carry a "
                     f"{readable} fact")
        title = f"Address the pattern behind {readable}"
        candidates.append(_candidate(
            intake_kind="crm_pain",
            statement=statement,
            scope=f"crm:{event_type}",
            title=title,
            origin={"kind": "crm_facts", "event_type": event_type,
                    "entity_count": len(entities), "label": "UNKNOWN"},
            evidence_references=[{"kind": REF_CRM_FACT,
                                  "ref_id": f"{event_type}:{entity}",
                                  "crm_entity_id": entity}
                                 for entity in entities],
            affected_customers=entities,
            why_now=("these facts are current in the CRM ledger and no "
                     "recovery fact supersedes them"),
            what_changes_if_ignored=(
                "the pattern behind the recorded facts stays unexamined and "
                "further entities may follow the same path"),
            work_category="customer_work",
            first_observed_at=as_of))
    return candidates
