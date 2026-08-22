"""Where to look for the thing a document did not say.

THE BOTTLENECK THIS ADDRESSES
-----------------------------
Wave 7 ended with 5 real rival actions and **0 established competitive
objects**. Not because the extractor was wrong — its precision on a shaped
corpus was 1.0 — but because the documents it was fed were narrative pages
that never named a buyer. Asking a rival's homepage "what have you
published?" returns prose. The engine was retrieving the wrong FAMILY of
document and then honestly reporting that the right facts were absent.

So the question changes shape. Not:

    what has this rival published?

but:

    which source class is structurally likely to state who this action is
    for and what buying decision it contests?

THE LINE THIS MODULE MUST NOT CROSS
-----------------------------------
The relationship's competitive object is allowed to decide WHERE TO LOOK. It
is never allowed to become the answer.

    ALLOWED   the rivalry says "enterprise commerce", so search Magento's
              enterprise commerce pricing page
    REFUSED   the rivalry says "enterprise commerce", so the action found
              there is about enterprise commerce

The second is the circularity wave 6 found, wearing a search query as a
disguise. The guard is structural rather than advisory: the routing hint
lives in a field called `routing_hint_not_evidence`, `competitive_objects.
extract` has no parameter that could receive it, and a test asserts that a
plan's hint never appears in the object extracted from the document it
retrieves unless the DOCUMENT contains that text.

WHY PLANS ARE RANKED AND NOT MERELY LISTED
------------------------------------------
Measured yields differ by two orders of magnitude. Wave 7 measured the
customer case study at 0.500 for a named customer and **0.000** for an
action object, and one number had been recommending that family for all
three questions. A planner that ignores per-question performance is a
planner that keeps buying the family that already failed at this question.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "action_object_query.v1"

# --- source families, as retrieval targets ----------------------------------
PRICING_PAGE = "pricing_page"
PLAN_COMPARISON = "plan_comparison_page"
MIGRATION_PAGE = "migration_page"
PRODUCT_LAUNCH_PAGE = "product_launch_page"
RELEASE_NOTES = "release_notes"
SOLUTION_PAGE = "solution_page"
COMPARISON_PAGE = "comparison_page"
CUSTOMER_MIGRATION_STORY = "customer_migration_story"
MARKETPLACE_LISTING = "marketplace_listing"
DEVELOPER_ANNOUNCEMENT = "developer_announcement"
PRODUCT_DOCS = "product_documentation"
NEWSROOM = "newsroom"
HOMEPAGE = "homepage"

FAMILIES = (PRICING_PAGE, PLAN_COMPARISON, MIGRATION_PAGE,
            PRODUCT_LAUNCH_PAGE, RELEASE_NOTES, SOLUTION_PAGE,
            COMPARISON_PAGE, CUSTOMER_MIGRATION_STORY, MARKETPLACE_LISTING,
            DEVELOPER_ANNOUNCEMENT, PRODUCT_DOCS, NEWSROOM, HOMEPAGE)

#: A family that has never established an object for anybody. Kept nameable
#: so "we tried it and it produced nothing" stays distinct from "we never
#: tried it", which are opposite findings about the same zero.
GENERIC_FAMILIES = frozenset({HOMEPAGE, NEWSROOM})

#: Which dimension each family is EDITORIALLY likely to supply. This is a
#: claim about what the page exists to say, not about any particular page: a
#: pricing page must name tiers and who they suit or it cannot sell, and a
#: migration page must name what you are leaving or it has no subject.
_SUPPLIES: Dict[str, Tuple[str, ...]] = {
    PRICING_PAGE: ("WHAT", "WHO", "BUDGET"),
    PLAN_COMPARISON: ("WHAT", "WHO", "BUDGET"),
    MIGRATION_PAGE: ("WHAT", "SUBSTITUTE", "WHO"),
    CUSTOMER_MIGRATION_STORY: ("SUBSTITUTE", "WHO", "WHAT"),
    COMPARISON_PAGE: ("SUBSTITUTE", "WHAT"),
    PRODUCT_LAUNCH_PAGE: ("WHAT", "WHO"),
    SOLUTION_PAGE: ("WHO", "WHAT"),
    RELEASE_NOTES: ("WHAT",),
    DEVELOPER_ANNOUNCEMENT: ("WHAT",),
    MARKETPLACE_LISTING: ("WHAT", "WHO"),
    PRODUCT_DOCS: ("WHAT",),
    NEWSROOM: (),
    HOMEPAGE: (),
}

#: Path fragments that identify a family on a vendor's own site.
_PATHS: Dict[str, Tuple[str, ...]] = {
    PRICING_PAGE: ("/pricing", "/plans", "/plan-pricing", "/essentials/pricing"),
    PLAN_COMPARISON: ("/compare-plans", "/plans/compare", "/pricing/compare"),
    MIGRATION_PAGE: ("/migration", "/migrate", "/replatform", "/switch",
                     "/move-to"),
    COMPARISON_PAGE: ("/vs", "/alternatives", "/compare", "/versus"),
    PRODUCT_LAUNCH_PAGE: ("/news", "/press", "/blog", "/announcements",
                          "/whats-new"),
    RELEASE_NOTES: ("/release-notes", "/changelog", "/releases", "/updates"),
    SOLUTION_PAGE: ("/solutions", "/industries", "/use-cases"),
    CUSTOMER_MIGRATION_STORY: ("/customers", "/case-studies",
                               "/customer-stories", "/success-stories"),
    MARKETPLACE_LISTING: ("/apps", "/marketplace", "/integrations"),
    DEVELOPER_ANNOUNCEMENT: ("/developers", "/dev", "/api/changelog"),
    PRODUCT_DOCS: ("/docs", "/documentation", "/help"),
    NEWSROOM: ("/newsroom",),
    HOMEPAGE: ("/",),
}

# --- standing ---------------------------------------------------------------
PLANNED = "PLANNED"
ATTEMPTED = "ATTEMPTED"
RETRIEVED = "RETRIEVED"
ESTABLISHED = "ESTABLISHED"
EXHAUSTED = "EXHAUSTED"
STANDINGS = (PLANNED, ATTEMPTED, RETRIEVED, ESTABLISHED, EXHAUSTED)


class PlanRejected(ValueError):
    """A query was proposed that could not close the gap it names."""


@dataclass(frozen=True)
class ActionObjectQueryPlan:
    query_id: str
    actor: str
    action_id: str
    missing_dimensions: Tuple[str, ...]
    candidate_source_family: str
    query_terms: Tuple[str, ...]
    why_this_source: str
    expected_information_gain: str
    standing: str
    #: The rivalry's object, carried ONLY to choose where to look. The name
    #: is the guard: anything reading this field to fill an object is
    #: visibly doing the thing the module forbids.
    routing_hint_not_evidence: str = ""
    #: The measured per-question yield that ranked this family, and the
    #: sample it rests on. A plan that cannot say why it chose is a guess.
    measured_yield: Optional[float] = None
    measured_sample: int = 0
    priority: str = "MEDIUM"

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "query_id": self.query_id,
            "actor": self.actor, "action_id": self.action_id,
            "missing_dimensions": list(self.missing_dimensions),
            "candidate_source_family": self.candidate_source_family,
            "query_terms": list(self.query_terms),
            "why_this_source": self.why_this_source,
            "expected_information_gain": self.expected_information_gain,
            "standing": self.standing,
            "routing_hint_not_evidence": self.routing_hint_not_evidence,
            "measured_yield": self.measured_yield,
            "measured_sample": self.measured_sample,
            "priority": self.priority,
            "caution": ("the routing hint chose where to look and may not "
                        "appear in any object; the retrieved document must "
                        "establish the object on its own"),
        }


def _terms(actor: str, family: str, missing: Sequence[str],
           routing_hint: str) -> Tuple[str, ...]:
    """The literal search terms. The hint may appear HERE and nowhere else."""
    base = [actor]
    if family in (PRICING_PAGE, PLAN_COMPARISON):
        base += ["pricing", "plans", "plan comparison"]
    elif family == MIGRATION_PAGE:
        base += ["migrate from", "switch from", "replatform"]
    elif family == COMPARISON_PAGE:
        base += ["vs", "alternative to"]
    elif family == CUSTOMER_MIGRATION_STORY:
        base += ["case study", "migrated from"]
    elif family in (PRODUCT_LAUNCH_PAGE, DEVELOPER_ANNOUNCEMENT):
        base += ["launch", "announcement", "now available"]
    elif family == RELEASE_NOTES:
        base += ["release notes", "changelog"]
    elif family == SOLUTION_PAGE:
        base += ["solutions", "for"]
    if "SUBSTITUTE" in missing:
        base.append("migrate from")
    if "WHO" in missing:
        base.append("who it's for")
    if routing_hint:
        base.append(routing_hint)
    return tuple(dict.fromkeys(t for t in base if t))


def plan(*, actor: str, action_id: str, missing_dimensions: Sequence[str],
         action_type: str = "", routing_hint: str = "",
         performance: Optional[Dict[str, Tuple[int, int]]] = None,
         voi_priority: str = "MEDIUM",
         limit: int = 4) -> Tuple[ActionObjectQueryPlan, ...]:
    """Rank the families that could supply the dimensions this action lacks.

    `performance` maps family -> (established_objects, attempts) as MEASURED
    for the ACTION_OBJECT question specifically. A family with a measured
    zero over a real sample sinks below one never tried, because "we looked
    there and found nothing" is evidence and "we have not looked" is not.
    """
    missing = tuple(d.upper() for d in missing_dimensions if d)
    if not missing:
        raise PlanRejected(
            "an action whose object is already established needs no query; "
            "planning one would spend budget to re-learn what is known")
    measured = performance or {}

    scored: List[Tuple[float, str]] = []
    for family in FAMILIES:
        supplies = _SUPPLIES.get(family, ())
        covered = sum(1 for dim in missing if dim in supplies)
        # THIS is what keeps a homepage out of the plan, and a wave-8 break
        # proof is what established it: a generic family supplies no
        # dimension, so it never survives here and the score it would have
        # received is never computed. A separate penalty on GENERIC_FAMILIES
        # sat below this line for one commit and could not fire — the same
        # "guard that cannot fail" this project has now found twice.
        if not covered:
            continue
        established, attempts = measured.get(family, (0, 0))
        if attempts:
            rate = established / attempts
            # A measured zero is a finding, not a blank. It must outrank
            # nothing, so it sits below the untried prior rather than tying
            # with it.
            score = covered * (rate if rate else -0.5)
        else:
            score = covered * 0.5          # untried: the editorial prior only
        scored.append((score, family))

    scored.sort(key=lambda pair: (-pair[0], FAMILIES.index(pair[1])))
    out: List[ActionObjectQueryPlan] = []
    for score, family in scored[:limit]:
        established, attempts = measured.get(family, (0, 0))
        rate = (established / attempts) if attempts else None
        supplies = _SUPPLIES.get(family, ())
        covers = [dim for dim in missing if dim in supplies]
        raw = f"{actor}|{action_id}|{family}|{','.join(missing)}".lower()
        out.append(ActionObjectQueryPlan(
            query_id="aoq_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
            actor=actor, action_id=action_id, missing_dimensions=missing,
            candidate_source_family=family,
            query_terms=_terms(actor, family, missing, routing_hint),
            why_this_source=(
                f"a {family.replace('_', ' ')} exists in order to state "
                f"{' and '.join(covers)}; this action is missing "
                f"{', '.join(missing)}"),
            expected_information_gain=(
                f"would close {len(covers)} of {len(missing)} missing "
                f"dimensions" + (
                    f"; measured {established}/{attempts} on this question"
                    if attempts else "; never attempted for this question")),
            standing=PLANNED, routing_hint_not_evidence=routing_hint,
            measured_yield=rate, measured_sample=attempts,
            priority=voi_priority))
    return tuple(out)


def from_voi(items: Sequence, *, performance: Optional[Dict] = None,
             objects_by_action: Optional[Dict[str, object]] = None,
             limit_per_item: int = 2) -> Tuple[ActionObjectQueryPlan, ...]:
    """Turn competitive uncertainties into targeted retrieval.

    This is the join the wave asked for: an uncertainty that moves a named
    decision field chooses the family measured to answer THAT question,
    rather than every question being answered by whatever was fetched last.
    """
    plans: List[ActionObjectQueryPlan] = []
    for entry in items:
        subject = getattr(entry, "counterparty", "") or getattr(
            entry, "subject", "")
        if not subject:
            continue
        action_id = getattr(entry, "item_id", "")
        obj = (objects_by_action or {}).get(action_id)
        missing = tuple(d.upper() for d in getattr(obj, "missing", ())
                        ) or ("WHO", "WHAT")
        try:
            plans.extend(plan(
                actor=subject, action_id=action_id,
                missing_dimensions=missing,
                routing_hint=getattr(entry, "uncertainty", "")[:80],
                performance=performance,
                voi_priority=getattr(entry, "priority", "MEDIUM"),
                limit=limit_per_item))
        except PlanRejected:
            continue
    # Highest-value uncertainty first, then the planner's own ranking.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNRESOLVABLE": 3}
    plans.sort(key=lambda p: order.get(p.priority, 9))
    return tuple(plans)


def paths_for(family: str) -> Tuple[str, ...]:
    return _PATHS.get(family, ())


def family_of(url: str) -> str:
    """Which family a retrieved URL belongs to, by its own path."""
    low = (url or "").lower()
    best, best_len = "", 0
    for family, fragments in _PATHS.items():
        if family == HOMEPAGE:
            continue
        for fragment in fragments:
            if fragment in low and len(fragment) > best_len:
                best, best_len = family, len(fragment)
    return best or HOMEPAGE


def summarise(plans: Sequence[ActionObjectQueryPlan]) -> dict:
    by_family = collections.Counter(p.candidate_source_family for p in plans)
    return {
        "contract": CONTRACT,
        "plans": len(plans),
        "actors": sorted({p.actor for p in plans}),
        "by_family": dict(by_family),
        "by_priority": dict(collections.Counter(p.priority for p in plans)),
        "generic_families_planned": sum(
            1 for p in plans
            if p.candidate_source_family in GENERIC_FAMILIES),
        "missing_dimensions": dict(collections.Counter(
            dim for p in plans for dim in p.missing_dimensions)),
        "note": ("the rivalry's object may choose where to look and may "
                 "never become the answer; it is carried in "
                 "routing_hint_not_evidence and read by nothing that "
                 "builds an object"),
    }
