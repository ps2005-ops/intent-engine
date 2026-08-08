"""Rivalry, and the one thing that makes a claim of it admissible.

WHY `COMPETES_WITH` IS NOT LIKE THE OTHER PREDICATES
---------------------------------------------------
`SELLS_TO` needs two named parties and a transaction. `PARTNERS_WITH` needs
two named parties and a stated relationship. Both are facts a document can
report directly.

Rivalry is not. Two companies compete only WITH RESPECT TO SOMETHING — a
buyer, a budget, a workflow, a procurement decision. "Apple competes with
Samsung" is true in phones and false in enterprise semiconductors, and a
graph that holds the unqualified claim cannot tell a strategist which. So:

    A COMPETES_WITH claim with no competitive object is REFUSED.

That single rule is what this module is. Everything else follows from it.

WHAT IS NOT RIVALRY, AND WHY EACH ONE IS TEMPTING
-------------------------------------------------
    same sector             ASML and Infosys are both "Technology". An
                            earlier version of the interaction binder used
                            exactly this and produced three fabricated
                            records.
    same customer           a merchant using Shopify and Stripe is a
                            merchant with two suppliers, not a fight.
    complementary products  an integration is the OPPOSITE of rivalry, and
                            it reads identically to a co-mention.
    analyst comparison      "NET vs DDOG" in a stock note compares
                            SECURITIES. Investors substitute between them;
                            their customers may not.
    co-mention              two names in one article is a fact about the
                            article.
    partner-of-both         a firm that partners with two others has told
                            you nothing about how those two relate.
    supplier/customer       a vertical relationship, and directional.

Each has a negative case in the precision corpus and a break proof.

WHY MIGRATION EVIDENCE IS THE STRONGEST KIND AVAILABLE
------------------------------------------------------
"Bombay Shaving Company migrated from Magento to Shopify Plus" is a single
sentence carrying everything the contract demands: both rivals NAMED, the
competitive object (that merchant's ecommerce platform), the buyer (the
merchant), and a direction — one of them won. It is also published by an
interested party, which bounds what it proves: that this buyer chose, not
that either product is better or that they compete everywhere.

It is already in the ledger. The customer-case-study family acquired in
wave 4 carries it, and nothing was reading it as rivalry.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import actor_relationships as AR

CONTRACT = "competitive_relationship.v1"

# --- evidence types, and only the ones the real corpus supports -------------
#
# Eight were specified. Four are built, because a taxonomy entry with no
# extractor and no corpus is a claim that the engine can recognise something
# it cannot. The unbuilt four are named so the gap is legible.
DIRECT_COMPETITOR_STATEMENT = "DIRECT_COMPETITOR_STATEMENT"
CUSTOMER_ALTERNATIVE_EVALUATION = "CUSTOMER_ALTERNATIVE_EVALUATION"
REPLACEMENT_MIGRATION = "REPLACEMENT_MIGRATION"
PRODUCT_SUBSTITUTE = "PRODUCT_SUBSTITUTE"

BUILT = (DIRECT_COMPETITOR_STATEMENT, CUSTOMER_ALTERNATIVE_EVALUATION,
         REPLACEMENT_MIGRATION, PRODUCT_SUBSTITUTE)

#: Specified, not built: no corpus in reach states them in a form this engine
#: can read. Listed rather than stubbed — a stub would be indistinguishable
#: from a working extractor that never fires.
NOT_BUILT = {
    "PROCUREMENT_ALTERNATIVE":
        "needs bid/finalist documents; USASpending publishes the AWARD, not "
        "the losing bidders",
    "REGULATORY_MARKET_PARTICIPANT":
        "needs antitrust or merger-review filings defining a relevant "
        "market; none retrieved by any integrated family",
    "PRICING_COMPARISON":
        "needs a like-for-like price comparison by a disinterested party",
    "DISTRIBUTION_SUBSTITUTE":
        "needs a channel stating it carries one product INSTEAD of another",
}

EVIDENCE_TYPES = tuple(BUILT) + tuple(sorted(NOT_BUILT))

#: What each built type proves, and — the load-bearing half — what it does
#: not. Carried onto every claim so a reader argues with the evidence rather
#: than with the extractor.
PROVES: Dict[str, Tuple[str, str]] = {
    DIRECT_COMPETITOR_STATEMENT: (
        "the subject states it competes with the named party",
        "the subject is an interested party; it may name a flattering rival "
        "and omit a threatening one"),
    CUSTOMER_ALTERNATIVE_EVALUATION: (
        "a named buyer weighed both parties for the same decision",
        "one buyer's shortlist is not the market's"),
    REPLACEMENT_MIGRATION: (
        "a named buyer moved from one party to the other for the same job",
        "published by the winner; it proves this buyer chose, not that "
        "either product is better or that the two compete everywhere"),
    PRODUCT_SUBSTITUTE: (
        "the two products serve the same stated job for the same buyer",
        "substitutability in one segment is not substitutability in all"),
}


class CompetitiveClaimRejected(ValueError):
    """The graph was asked to hold a rivalry it cannot say the terms of."""


@dataclass(frozen=True)
class CompetitiveClaim:
    """One rivalry, and the market it is a rivalry in."""
    claim_id: str
    actor_a: str
    actor_b: str
    competitive_object: str      # the job, workflow or product contested
    buyer_or_market: str         # who is choosing
    evidence_type: str
    evidence_span: str
    source: str
    event_date: str
    epistemic_status: str
    valid_from: str = ""
    valid_to: str = ""
    proves: str = ""
    does_not_prove: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "claim_id": self.claim_id,
            "actor_a": self.actor_a, "actor_b": self.actor_b,
            "competitive_object": self.competitive_object,
            "buyer_or_market": self.buyer_or_market,
            "evidence_type": self.evidence_type,
            "evidence_span": self.evidence_span, "source": self.source,
            "event_date": self.event_date,
            "epistemic_status": self.epistemic_status,
            "valid_from": self.valid_from, "valid_to": self.valid_to,
            "proves": self.proves, "does_not_prove": self.does_not_prove,
        }

    def as_relationship(self) -> AR.ActorRelationship:
        """The edge `interaction_binding` reads, with its terms attached."""
        return AR.relationship(
            subject_actor=self.actor_a, predicate=AR.COMPETES_WITH,
            object_actor=self.actor_b, evidence_ids=(self.claim_id,),
            source_document=self.source, subject_span=self.actor_a,
            object_span=self.actor_b,
            relationship_span=(
                f"{self.evidence_span} [competitive object: "
                f"{self.competitive_object}; buyer: {self.buyer_or_market}; "
                f"does not prove: {self.does_not_prove}]"),
            epistemic_status=self.epistemic_status,
            valid_from=self.valid_from, created_at=self.event_date)


#: A competitive object that names nothing. "the market", "business",
#: "technology" — each would make the claim unfalsifiable while looking
#: specific.
_VACUOUS_OBJECT = re.compile(
    r"^(?:the\s+)?(?:market|markets|business|businesses|industry|sector|"
    r"space|technology|technologies|products?|services?|solutions?|"
    r"customers?|general|everything|all|various|it)\b\s*$", re.I)

MIN_OBJECT_CHARS = 6


def claim(*, actor_a: str, actor_b: str, competitive_object: str,
          buyer_or_market: str, evidence_type: str, evidence_span: str,
          source: str, event_date: str,
          epistemic_status: str = AR.OBSERVED,
          valid_from: str = "", valid_to: str = "") -> CompetitiveClaim:
    """Admit one rivalry, or refuse it with the term it is missing.

    There is no argument to this function that produces a claim without a
    competitive object, and that is the whole design.
    """
    if evidence_type not in BUILT:
        raise CompetitiveClaimRejected(
            f"{evidence_type!r} has no extractor: "
            f"{NOT_BUILT.get(evidence_type, 'unknown evidence type')}")
    for end, value in (("actor_a", actor_a), ("actor_b", actor_b)):
        if not AR.is_named_actor(value):
            raise CompetitiveClaimRejected(
                f"{end} names no actor: {value!r} is a category. "
                f"'our competitors' is the sentence this engine has read "
                f"eleven thousand times")
    if AR.normalise_self(actor_a) == AR.normalise_self(actor_b):
        raise CompetitiveClaimRejected("an actor does not compete with itself")

    obj = " ".join((competitive_object or "").split())
    if len(obj) < MIN_OBJECT_CHARS or _VACUOUS_OBJECT.match(obj):
        raise CompetitiveClaimRejected(
            f"no competitive object: {competitive_object!r} names nothing "
            f"the two parties contest. Two companies compete only WITH "
            f"RESPECT TO SOMETHING, and a claim that omits it cannot be "
            f"argued with or refuted")
    if not (buyer_or_market or "").strip():
        raise CompetitiveClaimRejected(
            "no buyer or market: somebody has to be choosing between them")
    if not evidence_span.strip():
        raise CompetitiveClaimRejected("the span that states it is required")
    if epistemic_status not in AR.STATUSES:
        raise CompetitiveClaimRejected(f"unknown status {epistemic_status!r}")

    proves, does_not = PROVES[evidence_type]
    raw = f"{actor_a}|{actor_b}|{obj}".lower()
    return CompetitiveClaim(
        claim_id="cmp_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        actor_a=actor_a.strip(), actor_b=actor_b.strip(),
        competitive_object=obj, buyer_or_market=buyer_or_market.strip(),
        evidence_type=evidence_type, evidence_span=evidence_span.strip()[:320],
        source=source, event_date=event_date[:10],
        epistemic_status=epistemic_status, valid_from=valid_from or
        event_date[:10], valid_to=valid_to, proves=proves,
        does_not_prove=does_not)


# --- extraction -------------------------------------------------------------
#
# One pattern family per built evidence type. Every one of them must capture
# BOTH actors AND the object; a pattern that captures two names and no object
# is a co-mention detector wearing a rivalry schema.

#: "migrated from Magento to Shopify Plus", "replaced Zendesk with Intercom",
#: "switched from X to Y". The buyer is the sentence's subject.
_MIGRATION = re.compile(
    r"\b(?:migrat(?:ed|ing|es)|mov(?:ed|ing|es)|switch(?:ed|ing|es)|"
    r"transition(?:ed|ing|s)?|replac(?:ed|ing|es))\s+"
    r"(?:from\s+(?P<from>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+to\s+"
    r"(?P<to>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})"
    r"|(?P<old>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+with\s+"
    r"(?P<new>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3}))")

#: "we compete directly with X", "our principal competitors include X and Y"
_DIRECT = re.compile(
    r"\bcompet(?:e|es|ing)\s+(?:directly\s+)?(?:with|against)\s+"
    r"(?P<other>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})")

#: "customers evaluate us against X", "shortlisted X", "chose us over X".
#:
#: A bare "compared to" is NOT here, and its absence is deliberate. It
#: matched every year-over-year figure in the corpus — "increased 8.9%
#: compared to FY2026" — and produced a competitive claim reading "Toyota
#: Motor Corporation vs FY2026". A financial period comparison and a
#: competitive evaluation share a verb and share nothing else.
_ALTERNATIVE = re.compile(
    r"\b(?:evaluat(?:ed?|ing)\s+(?:us\s+)?against|"
    r"benchmarked?\s+(?:us\s+)?against|weighed\s+against|"
    r"shortlisted|chose\s+\w+\s+over|selected\s+\w+\s+over|"
    r"switch(?:ed|ing)?\s+away\s+from|rather\s+than\s+using)\s+"
    r"(?P<other>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})")

#: A fiscal period, a quarter, a year. Capitalised, actor-shaped, and not a
#: company. Every one of these appeared as a proposed "competitor".
_NOT_AN_ACTOR_TOKEN = re.compile(
    r"^(?:FY|CY|Q)\s?\d{1,4}$|^\d{4}$|^(?:January|February|March|April|May|"
    r"June|July|August|September|October|November|December)$", re.I)

#: Phrases that name two companies and establish NO rivalry. Counted, so
#: "found nothing" is distinguishable from "refused to round up".
_NOT_RIVALRY = re.compile(
    r"\b(?:integrat\w+\s+with|partners?\s+with|works?\s+with|alongside|"
    r"together\s+with|powered\s+by|built\s+on|in\s+partnership\s+with|"
    r"and\s+its\s+partner|both\s+use|also\s+uses?|as\s+well\s+as|"
    r"outperform\w*|shares?\s+(?:of|rose|fell)|stock|valuation|"
    r"price\s+target|analysts?)\b", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def extract(text: str, *, subject: str, aliases: Sequence[str],
            source: str, event_date: str, buyer: str = "",
            competitive_object: str = "") -> Tuple[
                Tuple[CompetitiveClaim, ...], Dict[str, int]]:
    """Pull admissible rivalry out of one document, or refuse with a reason.

    `competitive_object` is supplied by the caller when the DOCUMENT CLASS
    establishes it — a customer story on a commerce platform's own site is
    about that merchant's commerce platform, and the page does not need to
    say so in a sentence. It is never guessed from the text.
    """
    from . import counterparty_sources as CS

    refused: Dict[str, int] = collections.Counter()
    found: List[CompetitiveClaim] = []
    seen: set = set()
    names = list(aliases) + [subject]
    display = max((a for a in aliases if len(a) >= 4), key=len,
                  default=subject)

    for raw in _SENTENCE.split(" ".join((text or "").split())):
        sentence = raw.strip()
        if len(sentence) < 25:
            continue
        if _NOT_RIVALRY.search(sentence):
            refused["states_no_rivalry"] += 1
            continue

        pairs: List[Tuple[str, str, str]] = []
        hit = _MIGRATION.search(sentence)
        migration_buyer = ""
        if hit:
            old = hit.group("from") or hit.group("old")
            new = hit.group("to") or hit.group("new")
            if old and new:
                pairs.append((old, new, REPLACEMENT_MIGRATION))
                # The buyer is the sentence's own subject — the party that
                # did the migrating. Naming it is what makes the claim
                # checkable: "some customer switched" is not a fact anyone
                # can go and verify.
                head = AR._ACTOR.match(sentence)
                if head:
                    migration_buyer = head.group(1).strip(" .,;:")
        for pattern, kind in ((_DIRECT, DIRECT_COMPETITOR_STATEMENT),
                              (_ALTERNATIVE,
                               CUSTOMER_ALTERNATIVE_EVALUATION)):
            other = pattern.search(sentence)
            if other:
                pairs.append((display, other.group("other"), kind))

        if not pairs:
            continue
        for left, right, kind in pairs:
            left, right = left.strip(" .,;:"), right.strip(" .,;:")
            if not (AR.is_named_actor(left) and AR.is_named_actor(right)):
                refused["an_end_is_a_category"] += 1
                continue
            if _NOT_AN_ACTOR_TOKEN.match(left) or \
                    _NOT_AN_ACTOR_TOKEN.match(right):
                refused["an_end_is_a_fiscal_period"] += 1
                continue
            # A migration whose winner is not this subject is somebody
            # else's rivalry, reported on this page.
            if kind == REPLACEMENT_MIGRATION and not (
                    _is_subject_or_its_product(right, names)
                    or _is_subject_or_its_product(left, names)):
                refused["neither_party_is_the_subject"] += 1
                continue
            if not competitive_object:
                refused["no_competitive_object"] += 1
                continue
            key = tuple(sorted((left.lower(), right.lower())))
            if key in seen:
                refused["duplicate_in_document"] += 1
                continue
            try:
                found.append(claim(
                    actor_a=left, actor_b=right,
                    competitive_object=competitive_object,
                    buyer_or_market=(
                        buyer
                        or (migration_buyer
                            if kind == REPLACEMENT_MIGRATION else "")
                        or "the buyer named in the source"),
                    evidence_type=kind, evidence_span=sentence,
                    source=source, event_date=event_date))
                seen.add(key)
            except CompetitiveClaimRejected as exc:
                refused[f"contract:{str(exc)[:40]}"] += 1
    return tuple(found), dict(refused)


def _is_subject_or_its_product(name: str, names: Sequence[str]) -> bool:
    """The subject, or a product tier of it: "Shopify Plus" is Shopify.

    `counterparty_sources.resolves_to` deliberately refuses this — a
    one-token alias may not claim a longer name, which is the rule that stops
    "Linear" claiming "Linear Minerals Corp." That rule is right when
    resolving a name found in the wild.

    It is too strict here, and only here, because the CALLER has already
    established who published the document. On a vendor's own customer page,
    a name that begins with the vendor's own name is the vendor's product,
    not a coincidentally-similar third party. The allowance is therefore
    sound exactly as far as the provenance is, and no further: it is never
    applied to the counterparty side of a claim.
    """
    from . import counterparty_sources as CS

    if CS.resolves_to(name, names):
        return True
    got = CS.normalise_actor(name).split()
    for alias in names:
        want = CS.normalise_actor(alias).split()
        if want and len(alias) >= 4 and got[:len(want)] == want:
            return True
    return False


def summarise(claims: Sequence[CompetitiveClaim],
              refused: Optional[Dict[str, int]] = None) -> dict:
    by_type = collections.Counter(c.evidence_type for c in claims)
    return {
        "contract": CONTRACT,
        "competitive_claims": len(claims),
        "by_evidence_type": dict(by_type),
        "distinct_objects": len({c.competitive_object for c in claims}),
        "actors": len({c.actor_a for c in claims} | {c.actor_b
                                                     for c in claims}),
        "evidence_types_built": list(BUILT),
        "evidence_types_not_built": dict(NOT_BUILT),
        "refused": dict(sorted((refused or {}).items())),
        "note": ("a COMPETES_WITH claim with no competitive object is "
                 "refused: two companies compete only with respect to "
                 "something, and the unqualified claim cannot be refuted"),
    }
