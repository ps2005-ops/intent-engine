"""Why this analysis is different for THIS company -- and the test that it is.

THE SECTION
-----------
Four parts, in the order a reader can check them:

    Generic interpretation      what an analysis of a company in this
                                position would say, said honestly and in the
                                product's own voice
    Company-specific difference what this company's own evidence changes
                                about that reading
    Decision implication        what management therefore has to consider
    Evidence                    where the difference came from

THE GENERIC HALF IS DELIBERATE AND IS NOT FILLER
------------------------------------------------
A claim of specificity that never states what it is specific AGAINST cannot be
checked. Printing the generic reading beside the company one is what makes the
difference legible -- and, when there is no difference, what makes THAT
legible too. A section that can only ever congratulate itself is decoration.

THE TEST
--------
`genericity` answers the question the section implicitly makes: could this be
shown, unchanged, to an unrelated company? It is answered by CONSTRUCTION for
one company, and by COMPARISON across two:

    single    what share of the company-specific half is drawn from this
              company's own evidence rather than from the class it belongs to
    pairwise  after normalising both company names away, how much of two
              companies' composed readings is byte-shared

The pairwise form is the one that catches template collapse, because a
template is invisible from inside a single report -- it is only when two
companies produce the same sentence that anybody can see it. The recorded
failure is exactly that: a constant decision question that survived to the
page for every company in a cohort and looked fine on each one.
"""
from __future__ import annotations

import dataclasses
import difflib
import re
from typing import Optional, Tuple

CONTRACT = "company_differentiation.v1"

#: Two normalised readings sharing more than this are the same reading with
#: the names swapped. Set from the measured shape of real prose: two genuinely
#: different analyses of different companies share connective tissue and
#: little else.
COLLAPSE_RATIO = 0.72

#: A company-specific half drawn less than this from the company's own
#: evidence is a class prior with a name attached.
#:
#: NOT TUNED TO MAKE A COHORT PASS, and it is worth writing down what it
#: excludes. `profile.specificity` divides by every dimension the profile
#: tries to establish, and without a strategic reading only about five of the
#: sixteen can come from the company itself -- its identity, its own
#: self-description, its named dependencies, its claimed assets, its stated
#: technology exposure. So a run with no analyst tops out near 0.31 and is
#: FLAGGED by this floor, deliberately: marketing copy plus a class prior is
#: not knowing a business, and the flag says "real but thin" rather than
#: hiding the section. A run with the analyst reaches roughly 0.41 on the
#: same company and clears it.
SPECIFICITY_FLOOR = 0.34


@dataclasses.dataclass(frozen=True)
class Differentiation:
    generic_interpretation: str = ""
    company_specific_difference: str = ""
    decision_implication: str = ""
    evidence: Tuple[str, ...] = ()
    #: What made this different: the fields that carried it
    carried_by: Tuple[str, ...] = ()
    #: 0..1, share of the company half drawn from this company's own evidence
    specificity: float = 0.0
    #: True when the company half could be said about an unrelated company
    flagged: bool = False
    flag_reason: str = ""
    contract: str = CONTRACT

    def __bool__(self) -> bool:
        return bool(self.company_specific_difference)

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["evidence"] = list(self.evidence)
        out["carried_by"] = list(self.carried_by)
        return out


def _sentence(text: str) -> str:
    """One part, ended and capitalised.

    The parts below come from six different producers and each writes its own
    grammar. Joining them with ". " produced ". and it depends on ..." on the
    product's most prominent new section -- a sentence beginning with "and",
    on the screen whose whole job is to look considered.
    """
    body = " ".join(str(text or "").split()).rstrip(" .;,")
    if not body:
        return ""
    return body[0].upper() + body[1:] + "."


def _generic_reading(*, lens_selection, profile, company: str) -> str:
    """What would be said about any company in this position.

    Composed from the LENS's declared generic reading and the CLASS PRIOR --
    both of which are, by construction, statements about a kind of business
    rather than about this one. That is the point: this half is supposed to
    be generic, and it is built out of the fields tagged as generic.
    """
    lens = getattr(lens_selection, "lens", None)
    bits = []
    if lens is not None and lens.generic_reading:
        bits.append(
            f"A general reading of a company in this position would say "
            f"{lens.generic_reading}")
    model = getattr(profile, "business_model_class", "UNKNOWN")
    prior = getattr(profile, "business_model", None)
    if prior is not None and prior.value and not prior.company_specific:
        bits.append(
            f"It would reason from the economics every "
            f"{model.replace('_', ' ').lower()} business shares -- "
            f"{prior.value}")
    elif model != "UNKNOWN":
        bits.append(
            f"It would reason from the economics every "
            f"{model.replace('_', ' ').lower()} business shares")
    if not bits:
        return ("A general reading would work from this company's industry "
                "alone, because nothing more specific had been established.")
    return " ".join(_sentence(b) for b in bits)


def build_differentiation(*, company: str, profile=None, lens_selection=None,
                          analysis=None, opportunity=None,
                          causal_chain=None) -> Differentiation:
    """Compose the section, and mark it when it did not earn its title."""
    generic = _generic_reading(lens_selection=lens_selection, profile=profile,
                               company=company)

    # --- the company half, built ONLY from company-specific facts -----------
    carried, parts, evidence = [], [], []

    # WHAT THIS COMPANY SAYS IT IS, FIRST AND IN ITS OWN WORDS.
    #
    # This carries more differentiation than everything under it combined,
    # and it was measured: without it, BigID and Cyera -- same class, same
    # lens, both real data-security companies -- produced BYTE-IDENTICAL
    # difference text, because everything else in this section came from the
    # class prior and the lens, which they share. Their own sentences about
    # themselves are nothing alike.
    said = getattr(profile, "self_description", None)
    if said is not None and said.company_specific:
        carried.append("self_description")
        parts.append(f"In its own words: \u201c{said.value.rstrip('.')}\u201d "
                     f"-- which is narrower, and more specific, than the "
                     f"general reading above")
        if said.evidence:
            evidence.append(said.evidence)

    # THE COMPANY'S OWN VOCABULARY, quoted from the phrases that selected the
    # lens. These are literally words from this company's material -- BigID's
    # are "data discovery", "access governance", "shadow data" and Cyera's are
    # "sensitive data", "DSPM", "least privilege". Same lens, different
    # sentences, and the difference is the company's own.
    fired = ()
    for score in (getattr(lens_selection, "scores", ()) or ()):
        if score.lens_id == getattr(lens_selection, "primary", ""):
            fired = tuple(phrase for phrase, _w in score.fired[:4])
            break
    if fired:
        carried.append("own_vocabulary")
        parts.append(
            f"The material it publishes is about "
            + ", ".join(f"{p}" for p in fired)
            + " -- its own terms, not ours")

    job = getattr(profile, "customer_job", None)
    if job is not None and job.company_specific:
        carried.append("customer_job")
        parts.append(f"What customers are actually paying {company} for "
                     f"is {job.value.rstrip('.').lstrip().lower()}")

    engine = getattr(profile, "economic_engine", None)
    if engine is not None and engine.company_specific:
        carried.append("economic_engine")
        parts.append(f"Its profit comes from "
                     f"{engine.value.rstrip('.').lstrip().lower()}")

    assets = tuple(getattr(profile, "strategic_assets", ()) or ())
    if assets:
        carried.append("strategic_assets")
        parts.append(f"It names {assets[0].value} as its own")
        if assets[0].evidence:
            evidence.append(assets[0].evidence)

    deps = tuple(getattr(profile, "critical_dependencies", ()) or ())
    if deps:
        carried.append("critical_dependencies")
        parts.append(f"It depends on {deps[0].value}, which it names "
                     f"itself")
        if deps[0].evidence:
            evidence.append(deps[0].evidence)

    tensions = tuple(getattr(profile, "current_strategic_tensions", ()) or ())
    if tensions:
        carried.append("strategic_tension")
        parts.append(f"The trade-off it is actually managing is "
                     f"{tensions[0].value.rstrip('.')}")

    tech = getattr(profile, "technology_exposure", None)
    if tech is not None and tech.company_specific:
        carried.append("technology_exposure")
        if tech.evidence:
            evidence.append(tech.evidence)

    insight = getattr(analysis, "the_insight", None) or {}
    if isinstance(insight, dict) and str(insight.get("sentence") or "").strip():
        carried.append("the_insight")
        parts.append(f"The reading that follows from that: "
                     f"{str(insight['sentence']).rstrip('.')}")
        evidence.extend(str(c) for c in (insight.get("citations") or [])[:3])

    lens_span = str(getattr(lens_selection, "evidence_span", "") or "")
    if lens_span:
        evidence.append(lens_span)

    if not parts:
        return Differentiation(
            generic_interpretation=generic,
            company_specific_difference="",
            decision_implication="",
            specificity=0.0, flagged=True,
            flag_reason=(
                "Nothing company-specific was established, so there is no "
                "difference to state. What is above is the general reading "
                "and it is labelled as one -- writing it again in this "
                "company's name would be the template this section exists "
                "to detect."))

    difference = " ".join(_sentence(p) for p in parts)

    implication = ""
    if opportunity is not None and opportunity.decision_description:
        implication = (
            f"So the question in front of management is not the general one. "
            f"It is: {opportunity.decision_description.rstrip('.')}."
            + (f" What would change how urgent that is: "
               f"{opportunity.what_would_change_priority.rstrip('.')}."
               if opportunity.what_would_change_priority else ""))
    elif causal_chain is not None and causal_chain.links:
        last = causal_chain.links[-1]
        implication = (f"So what management has to weigh is "
                       f"{last.text.rstrip('.')}.")

    specificity = float(getattr(profile, "specificity", 0.0) or 0.0)
    flagged = specificity < SPECIFICITY_FLOOR
    reason = ("" if not flagged else
              f"{specificity:.0%} of what this reading tries to establish "
              f"about a company was learned from this one's own evidence; "
              f"the rest is the economics of its business model, which every "
              f"company of the same kind shares. The difference stated above "
              f"is real but thin, and it is marked rather than dressed up.")

    return Differentiation(
        generic_interpretation=generic,
        company_specific_difference=difference,
        decision_implication=implication,
        evidence=tuple(dict.fromkeys(e for e in evidence if e))[:4],
        carried_by=tuple(dict.fromkeys(carried)),
        specificity=round(specificity, 3),
        flagged=flagged, flag_reason=reason)


# --- the test ---------------------------------------------------------------

def _normalise(text: str, company: str) -> str:
    """Strip the company's identity so what is left is the SHAPE.

    Names, domains, tickers and capitalised tokens all go: a template with two
    different companies' names in it differs by exactly those, and leaving
    them in is how a collapse check passes a collapsed pair.
    """
    body = str(text or "")
    # ONLY THE SUBJECT'S OWN IDENTITY. An earlier version stripped EVERY
    # capitalised token, which deleted "Salesforce", "Snowflake" and
    # "Microsoft Azure" -- the dependencies that are among the most
    # company-specific things on the page. Two genuinely different reports
    # then normalised to the same text and the detector reported a collapse
    # that was its own doing. What has to go is which company this is ABOUT;
    # a rival, a cloud or a vendor named inside it is content.
    for token in re.findall(r"[A-Za-z][A-Za-z0-9&.\-]{2,}",
                            str(company or "")):
        body = re.sub(r"\b" + re.escape(token) + r"\b", " ", body, flags=re.I)
    body = re.sub(r"https?://\S+|\b[\w.-]+\.(?:com|io|ai|net|org)\b", " ",
                  body, flags=re.I)
    body = re.sub(r"\d+(?:[.,]\d+)*%?", " ", body)
    return " ".join(body.lower().split())


@dataclasses.dataclass(frozen=True)
class GenericityFinding:
    collapsed: bool
    ratio: float
    left: str = ""
    right: str = ""
    shared_sentences: Tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["shared_sentences"] = list(self.shared_sentences)
        return out


def genericity(*, left_text: str, left_company: str,
               right_text: str, right_company: str) -> GenericityFinding:
    """Could these two readings be swapped? Answered by comparison, not taste.

    Both sides are normalised to remove every trace of WHICH company they are
    about, and what remains is compared. A high ratio means the two companies
    received the same analysis with the names changed, which is the defect;
    a low one means the shape itself differs, which is the product working.
    """
    a, b = _normalise(left_text, left_company), _normalise(right_text,
                                                           right_company)
    if not a or not b:
        return GenericityFinding(
            collapsed=False, ratio=0.0, left=left_company, right=right_company,
            reason="one side is empty, so nothing can be compared")
    ratio = round(difflib.SequenceMatcher(None, a, b).ratio(), 3)

    # WHICH SENTENCES ARE SHARED, not only how many. A ratio is a number an
    # engineer can argue with; a shared sentence is a defect a reader can see.
    left_sent = {s.strip() for s in re.split(r"(?<=[.!?])\s+", a)
                 if len(s.split()) >= 7}
    right_sent = {s.strip() for s in re.split(r"(?<=[.!?])\s+", b)
                  if len(s.split()) >= 7}
    shared = tuple(sorted(left_sent & right_sent, key=len, reverse=True))[:5]

    collapsed = ratio >= COLLAPSE_RATIO or len(shared) >= 3
    return GenericityFinding(
        collapsed=collapsed, ratio=ratio, left=left_company,
        right=right_company, shared_sentences=shared,
        reason=("" if not collapsed else
                f"After removing every trace of which company each is about, "
                f"{ratio:.0%} of the two readings is shared"
                + (f" and {len(shared)} whole sentence(s) are identical"
                   if shared else "")
                + ". Two different companies received the same analysis."))
