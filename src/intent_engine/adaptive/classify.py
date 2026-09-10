"""What kind of business this is, read from the company's own evidence.

WHY A THIRD CLASSIFIER
----------------------
`company_profile.profile_for` already has two, in strict order of authority:

    1. the validation manifest -- authored, reviewed, version-controlled;
    2. the SEC's industry code for the filer, corrected where the filer's own
       revenue sentence contradicts it.

Both are correct and neither reaches a private company. Measured on the ten
companies this phase qualifies against, all ten resolved `PROFILE_SPARSE` /
`business_model_class=UNKNOWN`, and UNKNOWN switches off the pattern library,
the per-class metrics, the macro transmission table, the causal questions and
the competitor set simultaneously. The product then has nothing left to
differentiate WITH, which is what "one report template with the names swapped"
actually is when you look underneath it.

THE EVIDENCE THIS TRUSTS, AND WHY IT IS THE SAME KIND
-----------------------------------------------------
`revenue_model_hint` already promotes a filer's own sentence about where its
revenue comes from over the regulator's industry code, on the reasoning that a
first-party statement of fact outranks a third party's bucket. This module
applies that same rule one step further out: a company's own published
description of what it sells, to whom, and how it is paid is a first-party
statement whether it appears in a 10-K or on the company's own site.

It is ranked BELOW both existing classifiers and can never override either.
`build_profile` consults it only where they returned UNKNOWN.

THE RULES IT FOLLOWS
--------------------
  * A signal must be a WHOLE WORD or phrase. Substring matching refuses real
    companies -- "alpha" inside "Alphabet Inc." is the recorded case -- and
    invents false ones.
  * A signal must come with an APPLICABILITY. A phrase that fires on any
    company's marketing is not a classifier, and a library entry firing on
    signal names alone reaches the wrong kind of company. Every rule below
    therefore needs a MODEL signal (how the money works) and not only a
    DOMAIN signal (what the product is about).
  * A margin is required. Two classes within one weighted point of each other
    is an unresolved classification, and it returns UNKNOWN with both named
    rather than picking the higher one.
  * The matching span is recorded. A classification whose evidence cannot be
    quoted back is not auditable, and "which span fired" is the only way to
    tell a real read from a coincidence.
  * UNKNOWN is a real answer and stays available. Not proven is not disproven.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "evidence_business_model.v1"

UNKNOWN = "UNKNOWN"

#: How much of the subject's own text is scanned. Past the excerpt a page
#: carries, and bounded so a 300-page filing cannot become a whole cycle's
#: work. Matches `evidence_text.SCAN_CHARS` in spirit; larger because this
#: reads a whole corpus rather than one document.
SCAN_CHARS = 200_000

#: A runner-up scoring at least this SHARE of the winner is not separated
#: from it by the evidence, and saying so is the answer.
#:
#: PROPORTIONAL, NOT ABSOLUTE, AND THIS IS THE SECOND TIME THAT LESSON WAS
#: LEARNED IN THIS PACKAGE. The first version used a flat 2.0 points. Real
#: winners score 8-30 depending only on how much material was retrieved, so
#: two points is no separation at all on a rich corpus and an impossible bar
#: on a thin one. Measured: a deliberately ambiguous company -- a consultancy
#: that also sells a subscription platform, which genuinely is both -- was
#: classified SUBSCRIPTION_SOFTWARE at 11.0 with the services reading right
#: behind it. The same defect had already been found and fixed in
#: `lens.SECONDARY_SHARE`, and was not carried across.
MARGIN_SHARE = 0.65

#: Below this the evidence is too thin to classify at all, whatever the
#: margin. One weak phrase in a marketing paragraph is not a business model.
FLOOR = 3.0


@dataclasses.dataclass(frozen=True)
class Signal:
    """One phrase, what it is evidence OF, and how much it is worth.

    `kind` is the applicability half of the rule:

        MODEL   how the money works -- a subscription, a fee per engagement,
                a spread, a shipped unit. Only these can carry a
                classification on their own.
        DOMAIN  what the product is about. Corroborating only: "data
                security" says nothing about whether the company sells
                software, consulting or an appliance, and a rule built on
                domain words alone is how a lens reaches the wrong company.
    """
    phrase: str
    kind: str            #: MODEL | DOMAIN
    weight: float


def _rx(phrase: str) -> "re.Pattern":
    """Whole-phrase, case-insensitive, punctuation-tolerant.

    `casefold`-equivalent via re.I is deliberately NOT relied on for the
    boundary: `\\b` around a phrase beginning or ending in a non-word
    character never matches, so the boundary is applied only where the
    adjacent character is a word character.
    """
    body = re.escape(phrase).replace(r"\ ", r"[\s\-]+")
    left = r"\b" if phrase[:1].isalnum() else ""
    right = r"\b" if phrase[-1:].isalnum() else ""
    return re.compile(left + body + right, re.I)


# --- the rules --------------------------------------------------------------
#
# Read each block as: "a company whose own published material says these
# things about how it is paid is a business of this KIND". Nothing here is a
# claim about a particular company, and nothing here names one.

_RULES = {
    "SUBSCRIPTION_SOFTWARE": (
        Signal("software as a service", "MODEL", 4.0),
        Signal("saas", "MODEL", 3.0),
        Signal("subscription", "MODEL", 3.0),
        Signal("annual recurring revenue", "MODEL", 4.0),
        Signal("per seat", "MODEL", 3.0),
        Signal("per user per month", "MODEL", 4.0),
        Signal("subscription revenue", "MODEL", 4.0),
        Signal("renewal", "MODEL", 1.5),
        Signal("our platform", "MODEL", 1.5),
        Signal("cloud platform", "MODEL", 2.0),
        Signal("software platform", "MODEL", 3.0),
        Signal("licence", "MODEL", 1.0),
        Signal("license", "MODEL", 1.0),
        Signal("free trial", "MODEL", 1.5),
        Signal("request a demo", "MODEL", 1.5),
        Signal("book a demo", "MODEL", 1.5),
        Signal("get a demo", "MODEL", 1.5),
        Signal("pricing plans", "MODEL", 2.0),
        # A COMPANY THAT PUBLISHES A PRICE IS STATING THAT IT SELLS.
        # Weaker than "subscription" on purpose -- it says the thing is sold,
        # not how it is billed. Added because a real product site often
        # carries only these: measured on Monte Carlo's own homepage, the
        # only matches were DOMAIN words and the classification was UNKNOWN
        # while the page plainly sells software.
        Signal("pricing", "MODEL", 2.0),
        Signal("talk to sales", "MODEL", 2.0),
        Signal("contact sales", "MODEL", 2.0),
        Signal("start free", "MODEL", 1.5),
        # DOMAIN vocabulary a real product page carries. Listed generously
        # ON PURPOSE: with only three domain words no page could ever clear
        # FLOOR on subject matter alone, so the applicability guard above
        # was unreachable and untestable -- a break proof that removed it
        # ran GREEN because the floor caught the mutation instead. A guard
        # that cannot be isolated is a guard nobody can prove.
        Signal("integrations", "DOMAIN", 1.0),
        Signal("api", "DOMAIN", 0.5),
        Signal("deploy", "DOMAIN", 0.5),
        Signal("dashboard", "DOMAIN", 0.5),
        Signal("workflow", "DOMAIN", 0.5),
        Signal("onboarding", "DOMAIN", 0.5),
        Signal("single sign on", "DOMAIN", 0.5),
        Signal("enterprise ready", "DOMAIN", 0.5),
    ),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        Signal("consulting firm", "MODEL", 4.0),
        Signal("consultancy", "MODEL", 4.0),
        Signal("our consultants", "MODEL", 4.0),
        Signal("professional services firm", "MODEL", 4.0),
        Signal("client engagements", "MODEL", 3.5),
        Signal("advisory services", "MODEL", 3.0),
        Signal("managed services", "MODEL", 2.0),
        Signal("billable", "MODEL", 3.0),
        Signal("staffing", "MODEL", 2.5),
        Signal("we help our clients", "MODEL", 2.5),
        Signal("our clients", "MODEL", 1.5),
        Signal("engagement", "DOMAIN", 0.5),
        Signal("practitioners", "DOMAIN", 1.0),
        Signal("delivery teams", "DOMAIN", 1.0),
    ),
    "DESIGN_AND_MANUFACTURE": (
        Signal("we manufacture", "MODEL", 4.0),
        Signal("manufacturing facilities", "MODEL", 3.5),
        Signal("our products are manufactured", "MODEL", 4.0),
        Signal("units shipped", "MODEL", 3.5),
        Signal("bill of materials", "MODEL", 3.0),
        Signal("fabrication", "MODEL", 2.5),
        Signal("assembly", "DOMAIN", 1.0),
        Signal("original equipment manufacturer", "MODEL", 3.0),
    ),
    "BRANDED_CONSUMER": (
        Signal("our brands", "MODEL", 3.5),
        Signal("consumer packaged goods", "MODEL", 4.0),
        Signal("retail partners", "MODEL", 2.5),
        Signal("shelf", "DOMAIN", 1.0),
        Signal("household", "DOMAIN", 0.5),
    ),
    "SCALE_RETAIL": (
        Signal("our stores", "MODEL", 4.0),
        Signal("comparable sales", "MODEL", 4.0),
        Signal("same store sales", "MODEL", 4.0),
        Signal("store count", "MODEL", 3.0),
        Signal("merchandise", "DOMAIN", 1.5),
    ),
    "ADVERTISING_PLATFORM": (
        Signal("advertising revenue", "MODEL", 4.0),
        Signal("advertisers", "MODEL", 3.0),
        Signal("ad impressions", "MODEL", 3.5),
        Signal("cost per click", "MODEL", 3.0),
        Signal("monetize", "DOMAIN", 1.0),
    ),
    "BALANCE_SHEET_OR_NETWORK": (
        Signal("net interest income", "MODEL", 4.5),
        Signal("assets under management", "MODEL", 4.0),
        Signal("underwriting", "MODEL", 3.5),
        Signal("interchange", "MODEL", 3.5),
        Signal("deposits", "MODEL", 2.5),
        Signal("loan", "DOMAIN", 1.0),
    ),
    "COMMODITY_PRODUCER": (
        Signal("proved reserves", "MODEL", 4.5),
        Signal("realised price", "MODEL", 3.5),
        Signal("realized price", "MODEL", 3.5),
        Signal("production volumes", "MODEL", 3.0),
        Signal("barrels", "DOMAIN", 1.5),
        Signal("ore", "DOMAIN", 1.0),
    ),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        Signal("rate base", "MODEL", 4.5),
        Signal("take or pay", "MODEL", 4.0),
        Signal("regulated tariff", "MODEL", 3.5),
        Signal("contracted capacity", "MODEL", 3.0),
        Signal("utility", "DOMAIN", 1.0),
    ),
    "MANUFACTURE_AND_AFTERMARKET": (
        Signal("aftermarket", "MODEL", 4.0),
        Signal("spare parts", "MODEL", 3.5),
        Signal("service contracts", "MODEL", 2.5),
        Signal("installed base", "DOMAIN", 1.5),
    ),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        # POSSESSIVE, AND THAT IS THE WHOLE FIX FOR THIS CLASS.
        #
        # `clinical trials` sat here as a MODEL signal worth 4.0 and
        # misclassified a CONSULTANCY. Measured on Slalom's own site:
        # "clinical trials" and "patients" appear because life sciences is a
        # client industry it serves, and they scored 5.0 against 4.5 for
        # people-based services -- so the industries a firm SELLS INTO
        # classified the firm itself.
        #
        # A signal that names a customer's activity is not evidence about the
        # vendor's revenue. The possessive forms are, because only the party
        # that runs the trial writes "our clinical trials".
        Signal("our clinical trials", "MODEL", 4.5),
        Signal("we received marketing authorisation", "MODEL", 4.5),
        Signal("marketing authorisation", "MODEL", 4.0),
        Signal("our pipeline of candidates", "MODEL", 4.5),
        Signal("reimbursed by payers", "MODEL", 4.0),
        Signal("clinical trials", "DOMAIN", 1.0),
        Signal("reimbursement", "DOMAIN", 1.0),
        Signal("payers", "DOMAIN", 1.0),
        Signal("patients", "DOMAIN", 1.0),
    ),
    # MULTI_ENGINE_PLATFORM is deliberately absent. It is a statement that a
    # single class describes NEITHER of a filer's engines, and that is a
    # finding about segment reporting -- `multi_engine_hint` reads it from a
    # filing and this module has no business inferring it from marketing copy.
}


@dataclasses.dataclass(frozen=True)
class EvidenceClassification:
    """What the company's own evidence says its business model is.

    `model_class` is UNKNOWN whenever the evidence did not separate two
    classes by `MARGIN` or did not clear `FLOOR`. `reason` says which, and
    `runner_up` names what it was confused with -- an unresolved
    classification a reader can see the shape of is worth more than a
    confident one they cannot check.
    """
    model_class: str = UNKNOWN
    confidence: str = "none"            #: high | moderate | low | none
    score: float = 0.0
    runner_up: str = ""
    runner_up_score: float = 0.0
    #: the exact matched span, quoted from the company's own text
    evidence_span: str = ""
    #: which phrases fired, strongest first, as (phrase, kind, weight)
    matched: Tuple[Tuple[str, str, float], ...] = ()
    reason: str = ""
    contract: str = CONTRACT

    @property
    def known(self) -> bool:
        return self.model_class != UNKNOWN

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["matched"] = [list(m) for m in self.matched]
        return out


def _span_around(text: str, match: "re.Match") -> str:
    """The sentence the match sits in, so the read can be quoted back.

    Delegated to `adaptive.spans`, which snaps to sentences and refuses page
    furniture using the rule `evidence_text` already owns. The arithmetic
    window this replaced produced quotes beginning mid-word on the deployed
    service.
    """
    from intent_engine.adaptive.spans import quote_around
    return quote_around(text, match.start(), match.end())


def classify_from_evidence(text: str) -> EvidenceClassification:
    """Classify from the subject's own published text, or say why not.

    `text` MUST be the subject's own material. A competitor's page describing
    ITS subscription revenue would classify this company from a rival's model,
    which is the recorded `subject_documents` failure in another shape --
    callers pass `_subject_evidence_text`-style output, never a whole corpus.
    """
    body = str(text or "")[:SCAN_CHARS]
    if not body.strip():
        return EvidenceClassification(
            reason="no subject-owned text was retrieved, so this company's "
                   "own account of how it is paid could not be read")

    scores, hits, spans = {}, {}, {}
    for model, signals in _RULES.items():
        total, fired, best_span, best_weight = 0.0, [], "", 0.0
        for sig in signals:
            m = _rx(sig.phrase).search(body)
            if m is None:
                continue
            total += sig.weight
            fired.append((sig.phrase, sig.kind, sig.weight))
            # THE SPAN COMES FROM A MODEL SIGNAL WHERE THERE IS ONE. A domain
            # word quoted as the evidence for a business model is exactly the
            # confusion the MODEL/DOMAIN split exists to prevent.
            if sig.kind == "MODEL" and sig.weight > best_weight:
                best_weight, best_span = sig.weight, _span_around(body, m)
        if fired:
            scores[model] = total
            hits[model] = sorted(fired, key=lambda f: -f[2])
            spans[model] = best_span
    if not scores:
        return EvidenceClassification(
            reason="the retrieved text carries no first-party statement of "
                   "how this company is paid")

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, top_score = ranked[0]
    second, second_score = (ranked[1] if len(ranked) > 1 else ("", 0.0))

    # APPLICABILITY, ENFORCED. A class carried entirely by DOMAIN words has
    # matched what the company is ABOUT, not how it is paid, and a rule that
    # fires on signal names alone reaches the wrong kind of company.
    model_weight = sum(w for _p, k, w in hits[top] if k == "MODEL")
    if model_weight < FLOOR:
        return EvidenceClassification(
            runner_up=top, runner_up_score=round(top_score, 1),
            matched=tuple(hits[top]),
            reason=(f"the text describes what this company is about but "
                    f"carries no first-party statement of how it is paid; "
                    f"the strongest reading ({top.replace('_', ' ').lower()}) "
                    f"rests on subject-matter words rather than on a revenue "
                    f"model"))

    if top_score < FLOOR:
        return EvidenceClassification(
            runner_up=top, runner_up_score=round(top_score, 1),
            matched=tuple(hits[top]),
            reason=(f"the strongest reading scored {top_score:.1f}, under the "
                    f"{FLOOR:.0f} needed to assert a business model from "
                    f"marketing text alone"))

    if second and second_score >= top_score * MARGIN_SHARE:
        return EvidenceClassification(
            runner_up=second, runner_up_score=round(second_score, 1),
            matched=tuple(hits[top]),
            reason=(f"this company's own material reads as both "
                    f"{top.replace('_', ' ').lower()} and "
                    f"{second.replace('_', ' ').lower()} "
                    f"({top_score:.1f} against {second_score:.1f}), which is "
                    f"not a separation. Companies that sell software AND "
                    f"deliver it as a service genuinely are both, and picking "
                    f"one would decide by rounding"))

    confidence = ("high" if top_score >= FLOOR * 3
                  and second_score <= top_score * (MARGIN_SHARE / 2.0)
                  else "moderate" if top_score >= FLOOR * 2
                  else "low")
    return EvidenceClassification(
        model_class=top, confidence=confidence, score=round(top_score, 1),
        runner_up=second, runner_up_score=round(second_score, 1),
        evidence_span=spans.get(top, ""), matched=tuple(hits[top]),
        reason=(f"read from this company's own published material, which "
                f"states how it is paid rather than only what it sells"))


def model_signals(model_class: str) -> Tuple[str, ...]:
    """The phrases that would classify a company into `model_class`.

    Exposed so a test can assert coverage against `MODEL_CLASSES` without
    importing the private table, and so the telemetry can say what was
    looked for as well as what was found.
    """
    return tuple(s.phrase for s in _RULES.get(model_class, ()))


def covered_classes() -> Tuple[str, ...]:
    return tuple(_RULES)
