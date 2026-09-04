"""Turn a graded dossier comparison into knowledge effects that persist.

WHAT WAS ACTUALLY MISSING
--------------------------
Batch 14 found that nothing in production constructs a `KnowledgeEffect`.
Tracing one layer further found why it could not: the BEFORE state a learning
event needs was never recorded. `decision_impact` ships `record_revision`,
`load_revisions`, `assess_against_prior` and `record_impact` — the whole
temporal comparison — and **not one of them had a production call site**. No
revision was ever written, so no second run could ever compare against a
first, so no effect could ever exist.

This module does not add a second belief system, a second effect type or a
second comparison engine. It is the projection between two things that
already existed and had never been introduced:

    decision_impact.DecisionImpact      (semantic before/after, graded)
        -> company_ingestion.learning_attribution.KnowledgeEffect

WHY THE COMPARISON PRODUCTION ALREADY RAN IS NOT THIS ONE
----------------------------------------------------------
The live call site grades the same analysis WITH the market dossier against
the same analysis WITHOUT it. That answers "was the dossier decision-relevant"
and is worth keeping. It cannot answer "did we learn something", and
`decision_impact`'s own docstring says why: the without-dossier side is empty
on every field, so every field reads empty -> populated, nothing can ever
grade NONE, and the number is 100% by construction. Learning needs the BEFORE
to be what the founder saw LAST TIME.

THE EASIEST WRONG IMPLEMENTATION
---------------------------------
Emit one effect per evidence row and report enormous learning velocity. Every
gate here exists to refuse that: an effect requires a SEMANTIC field movement
that survived boilerplate stripping, the states that assert no movement are
four mechanically distinct things rather than one "no", and a re-read that
could not have tested anything earns UNMEASURABLE and never a confirmation.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Dict, List, Optional, Sequence

from intent_engine.company_ingestion.learning_attribution import (
    CONTRADICTED, CREATED, FIRST_OBSERVATION, NO_CHANGE, REFUSED, RETIRED,
    REVISED, SUPPORTED, UNMEASURABLE, WEAKENED, FOUNDER_DECISION_COMPONENT,
    KnowledgeEffect,
)
from intent_engine.external_intel import decision_impact as di

CONTRACT = "effect_producer.v1"

EFFECT_PATH = "reports/market/knowledge_effects.jsonl"

#: How a semantic field movement becomes a knowledge effect. Read from
#: `decision_impact`'s vocabulary rather than restated, so a change there is a
#: KeyError here and not a silently unmapped effect.
_CHANGE_TO_EFFECT: Dict[str, str] = {
    di.ADDED: CREATED,
    di.STRENGTHENED: SUPPORTED,
    di.WEAKENED: WEAKENED,
    di.REMOVED: RETIRED,
    di.BOUNDED: REVISED,
    # Content replaced rather than extended: the strongest available signal
    # short of an explicit reversal marker, and the one a founder most needs
    # surfaced.
    di.REVERSED: CONTRADICTED,
    di.UNCHANGED: NO_CHANGE,
}

# --- why an attribution was refused (closed) --------------------------------
NO_COMPANY = "NO_COMPANY"
NO_ANALYSIS = "NO_ANALYSIS"
NO_PROVENANCE = "NO_PROVENANCE"
CROSS_COMPANY_PRIOR = "CROSS_COMPANY_PRIOR"
INCOMPARABLE_WINDOW = "INCOMPARABLE_WINDOW"
NOT_TESTABLE = "NOT_TESTABLE"

REFUSAL_REASONS = (NO_COMPANY, NO_ANALYSIS, NO_PROVENANCE,
                   CROSS_COMPANY_PRIOR, INCOMPARABLE_WINDOW, NOT_TESTABLE)


class Ineligible(Exception):
    """Carries WHY, so a refusal is recorded rather than dropped."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def eligibility(*, company_id: str, analysis_id: str,
                impact, evidence_ids: Sequence[str],
                comparability: str = di.SAME_WINDOW,
                prior_company_id: str = "") -> Optional[Ineligible]:
    """The one gate. Returns the refusal, or None when an effect may be made.

    NONE OF THESE ARE LEARNING, and each was a plausible way to award it:
      * a report existing;
      * an analysis id changing;
      * a document count rising;
      * prose differing;
      * `generated_at` moving.

    So the gate asks only whether a SEMANTIC COMPARISON was possible: is there
    a company, an analysis, provenance for the claim, a prior belonging to
    THIS company, and an evidence window the two sides can be compared across.
    """
    if not str(company_id or "").strip():
        return Ineligible(NO_COMPANY, "an effect must name the company it is "
                                      "about")
    if not str(analysis_id or "").strip():
        return Ineligible(NO_ANALYSIS, "an effect must name the analysis that "
                                       "produced it")
    if prior_company_id and prior_company_id != company_id:
        # One company's prior can never grade another's analysis. This is a
        # correctness wall AND a tenancy wall, and it fails closed.
        return Ineligible(
            CROSS_COMPANY_PRIOR,
            f"the recorded prior belongs to {prior_company_id!r}, not "
            f"{company_id!r}")
    if comparability not in di.COMPARABILITY:
        return Ineligible(INCOMPARABLE_WINDOW,
                          f"unknown comparability {comparability!r}")
    if comparability == di.UNKNOWN_WINDOW:
        return Ineligible(
            INCOMPARABLE_WINDOW,
            "the evidence windows either side of this comparison were not "
            "recorded, so a difference between them cannot be attributed to "
            "learning rather than to having seen more")
    if impact is not None and getattr(impact, "materiality", "") != \
            di.FIRST_OBSERVATION and not list(evidence_ids):
        # A change with no evidence behind it is not a learning event, it is
        # an unexplained mutation. Refused rather than credited.
        return Ineligible(NO_PROVENANCE,
                          "the comparison moved with no evidence recorded "
                          "behind it")
    return None


def _digest(*parts: str) -> str:
    return hashlib.blake2b("|".join(parts).encode(), digest_size=8).hexdigest()


def effects_from_impact(impact, *, evidence_ids: Sequence[str] = (),
                        independence_rows: Sequence[dict] = (),
                        comparability: str = di.SAME_WINDOW,
                        prior_company_id: str = "",
                        testable: bool = True,
                        occurred_at: str = "") -> List[KnowledgeEffect]:
    """Every knowledge effect this graded comparison supports — and no more.

    One effect per DECISION COMPONENT that was compared, never one per
    evidence row: the object that changed is the component, and several
    evidence rows may stand behind one movement. Emitting per row is how an
    effect count is inflated to look like velocity.
    """
    company_id = str(getattr(impact, "company_id", "") or "")
    analysis_id = str(getattr(impact, "analysis_id", "") or "")
    created_at = str(getattr(impact, "created_at", "") or "")
    ids = [str(e) for e in evidence_ids]

    refusal = eligibility(company_id=company_id, analysis_id=analysis_id,
                          impact=impact, evidence_ids=ids,
                          comparability=comparability,
                          prior_company_id=prior_company_id)
    if refusal is not None:
        return [KnowledgeEffect(
            evidence_id=(ids[0] if ids else f"refused:{company_id}"),
            target_type=FOUNDER_DECISION_COMPONENT,
            target_id=company_id or "unknown",
            effect_type=REFUSED, created_at=created_at,
            occurred_at=occurred_at,
            reason=f"attribution refused ({refusal.reason}): "
                   f"{refusal.detail}")]

    # NO PRIOR MEANS NO TEST. A baseline, recorded as such, and never as an
    # improvement — the comparison the founder will be able to make is the
    # NEXT one.
    if getattr(impact, "materiality", "") == di.FIRST_OBSERVATION:
        return [KnowledgeEffect(
            evidence_id=(ids[0] if ids else f"baseline:{company_id}"),
            target_type=FOUNDER_DECISION_COMPONENT, target_id=company_id,
            effect_type=FIRST_OBSERVATION, created_at=created_at,
            occurred_at=occurred_at,
            reason="no prior revision existed, so this evidence had nothing "
                   "to change; the baseline is now recorded and the next "
                   "revision is comparable")]

    out: List[KnowledgeEffect] = []
    for delta in getattr(impact, "deltas", ()) or ():
        change = getattr(delta, "change", di.UNCHANGED)
        before = "; ".join(getattr(delta, "before", ()) or ())
        after = "; ".join(getattr(delta, "after", ()) or ())

        # A FIELD THAT IS EMPTY ON BOTH SIDES WAS NOT TESTED.
        #
        # `assess` returns a delta for every one of the twelve impact types,
        # so emitting one effect per delta produced TWELVE effects per cycle —
        # eleven of them confirmations of decision components that have never
        # had any content. That is the inflated-velocity implementation this
        # module's docstring warns about, arrived at by accident: the ledger
        # would have filled with confirmations nobody could dispute, and the
        # conversion rate would have looked excellent.
        #
        # An object with no state cannot be confirmed, contradicted or left
        # unchanged by evidence. It is silent, and silence is not an event.
        if not before and not after:
            continue

        effect_type = _CHANGE_TO_EFFECT[change]

        if effect_type == NO_CHANGE and not testable:
            # A RE-READ THAT COULD NOT TEST ANYTHING IS NOT A CONFIRMATION.
            # This is the cheapest confirmation rate in the system: re-fetch
            # the same page daily and every field "holds". The caller decides
            # testability from re-observation value; this refuses to award the
            # confirmation when it says no.
            effect_type = UNMEASURABLE
            before = after = ""

        out.append(KnowledgeEffect(
            evidence_id=(ids[0] if ids else f"unattributed:{company_id}"),
            target_type=FOUNDER_DECISION_COMPONENT,
            target_id=f"{company_id}:{getattr(delta, 'impact_type', '')}",
            effect_type=effect_type,
            before_state=before, after_state=after,
            created_at=created_at, occurred_at=occurred_at,
            reason=_reason(delta, effect_type, ids, independence_rows)))
    return out


def _reason(delta, effect_type: str, evidence_ids: Sequence[str],
            independence_rows: Sequence[dict]) -> str:
    """Why this effect was written, in words a reviewer can dispute.

    Carries the ORIGIN count and not just the row count, because "supported by
    six documents" and "supported by six documents from one publisher" license
    different confidence and the row count alone cannot tell them apart.
    """
    from intent_engine.company_ingestion.learning_attribution import (
        evidence_structure,
    )

    structure = evidence_structure(evidence_ids, independence_rows)
    origins = structure["independent_origin_count"]
    field = getattr(delta, "impact_type", "?")
    if effect_type == NO_CHANGE:
        return (f"{field} was tested against {len(evidence_ids)} evidence "
                f"row(s) from {origins} independent origin(s) and did not "
                f"move")
    if effect_type == UNMEASURABLE:
        return (f"{field} could not be tested by this evidence; no "
                f"confirmation is claimed")
    added = len(getattr(delta, "added", ()) or ())
    removed = len(getattr(delta, "removed", ()) or ())
    return (f"{field} moved (+{added}/-{removed}) on {len(evidence_ids)} "
            f"evidence row(s) from {origins} independent origin(s)")


# ---------------------------------------------------------------------------
# persistence — append only, idempotent on the SEMANTIC content
# ---------------------------------------------------------------------------
def record_effects(root, effects: Sequence[KnowledgeEffect], *,
                   path: str = EFFECT_PATH) -> int:
    """Append effects not already present. Returns how many were NEW.

    Idempotent on `effect_id`, which is a digest over the evidence, the target
    and the two states — NOT over the wall clock. That is the whole point: a
    rerun of the same semantic comparison appends nothing, and this holds
    across a process restart because the check reads the file rather than any
    in-memory set.
    """
    target = pathlib.Path(root) / path
    known = {row.get("effect_id") for row in load_effects(root, path=path)}
    new = [e for e in effects if e.effect_id not in known]
    if not new:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for effect in new:
            handle.write(json.dumps(effect.as_dict(), sort_keys=True) + "\n")
    return len(new)


def load_effects(root, *, path: str = EFFECT_PATH,
                 company_id: str = "") -> List[dict]:
    """Every persisted effect, optionally for one company.

    A corrupt line is skipped and never repaired: a half-written row is not
    evidence about anything, and guessing its contents would put a fabricated
    learning event into the ledger.
    """
    target = pathlib.Path(root) / path
    if not target.exists():
        return []
    out: List[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if company_id and not str(row.get("target_id", "")).startswith(
                company_id):
            continue
        out.append(row)
    return out
