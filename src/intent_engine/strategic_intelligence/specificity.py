"""Company-specificity gate for strategic claims.

THE SENTENCE THAT MOTIVATED THIS
--------------------------------
    "SEC 6-K is shifting where demand is captured."

Every word is a word an analyst might use. It parses. It has a subject, a verb
and an object. And it is not merely wrong — it is not *about* anything. A form
type has been made the actor in a business sentence, because the pipeline had a
document and needed a subject, and the document was all it had.

Its siblings are quieter but no better: "demand is shifting" (whose demand,
where to?), "distribution is changing" (which channel?), "leadership should
consider" (on what evidence?), "this affects strategy" (which decision?).

WHY THE OLD GATE COULD NOT CATCH THEM
-------------------------------------
`insights.passes_specificity` checks the text against a fixed vocabulary —
checkout, merchant, storefront, rails. That list was written while looking at
Shopify, so it certifies Shopify-shaped sentences and has nothing to say about
a semiconductor company, a Japanese conglomerate, or a hospital group. Worse,
it can be satisfied by a sentence that merely *contains* a listed word without
saying anything about this company.

THE TEST THAT WORKS
-------------------
Specificity cannot be judged against a global word list, because "specific"
means "specific to THIS company". So the gate is grounded in the run's own
evidence: a claim is company-specific when, with the company's name removed, it
still names something drawn from that company's sources — a product, a segment,
a named counterparty, a figure, a date.

That is the substitution test made mechanical. If a claim survives having its
subject swapped for an unrelated company, it was never a finding about the
first one.

Everything here is deterministic. It rejects and downgrades; it never rewrites
a claim into passing, because a claim that has to be repaired to pass was not
supported in the first place.
"""
from __future__ import annotations

import re

SPECIFICITY_VERSION = "si_specificity.v1"

# --- verdicts ---------------------------------------------------------------
ACCEPT = "ACCEPT"
DOWNGRADE = "DOWNGRADE"
REJECT = "REJECT"

# Document and artefact types. These describe the CONTAINER evidence arrived
# in. A container is never the actor in a business claim: a filing does not
# shift demand, and a sitemap does not enter a market.
_ARTEFACT_SUBJECTS = (
    "sec 6-k", "6-k", "sec 10-k", "10-k", "10-q", "20-f", "8-k", "40-f",
    "s-1", "form", "filing", "prospectus", "press release", "sitemap",
    "robots.txt", "homepage", "web page", "webpage", "landing page",
    "the document", "this document", "the page", "this page", "the pdf",
    "annual report", "the report", "this report", "the article",
    "the source", "the excerpt", "the title", "the url",
)

# Movement verbs that promise a direction and usually deliver none.
_MOVEMENT = (
    "is shifting", "are shifting", "is changing", "are changing",
    "is moving", "are moving", "is evolving", "are evolving",
    "is transforming", "are transforming", "is growing", "are growing",
    "is declining", "are declining", "is increasing", "are increasing",
)

# Recommendation stems that must be anchored to evidence.
_RECOMMENDATION = (
    "leadership should", "management should", "the company should",
    "executives should", "they should", "should consider", "must consider",
    "ought to consider", "needs to consider",
)

# Claims that gesture at strategy without naming a decision.
_UNNAMED_DECISION = (
    "affects strategy", "affects the strategy", "impacts strategy",
    "has strategic implications", "is strategically important",
    "matters strategically", "this affects strategy",
    "is important for strategy",
)

# Vocabulary so common it cannot make a claim specific to anyone.
_GENERIC_VOCAB = frozenset("""
a an the and or but if then than that this these those of in on at to for from
with without by as is are was were be been being it its their his her they them
we our us you your i me my he she who whom which what when where why how
company companies business businesses market markets customer customers
product products service services strategy strategic growth growth revenue
demand supply value platform solution solutions industry sector technology
technologies data digital global leading innovative innovation new more most
best better strong strength focus focused approach team teams people world
future today year years quarter quarterly annual report reports announced
announcement said says according public private inc llc ltd corp corporation
group holdings plc sa nv ag gmbh will can may might could should would
shifting changing moving evolving increasing decreasing across within into
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&.\-']*")
_NUMBER = re.compile(r"\b\d[\d,.]*\s*(%|percent|million|billion|bn|m\b|k\b)?",
                     re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9&.\-']{2,}\b")

# A concrete referent has to be one of: a named thing, a figure, or a date.
# Everything else is atmosphere.
_CHANNEL_WORDS = (
    "direct", "retail", "wholesale", "reseller", "marketplace", "partner",
    "channel", "distributor", "app store", "online", "in-store", "oem",
    "subscription", "licence", "license", "self-serve", "enterprise sales",
)


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def _company_tokens(company: str) -> set:
    return {t.lower() for t in _WORD.findall(company or "")
            if len(t) > 2} | {"the company", "it", "they"}


def distinctive_terms(documents, *, company: str = "", limit: int = 400) \
        -> set:
    """Terms this company's own evidence actually uses.

    This is the anchor the substitution test needs. A global vocabulary list
    cannot express "specific to this company" — only the company's sources can,
    which is also why the set is rebuilt per run rather than configured.

    Proper nouns, figures and dates survive; generic business vocabulary and
    the company's own name do not (a claim is not specific merely because it
    repeats the name).
    """
    company_words = _company_tokens(company)
    terms: set = set()
    for document in documents or ():
        text = ((document.get("text_content") or "") + " "
                + (document.get("title") or ""))
        for match in _PROPER.findall(text):
            token = match.lower()
            if token in _GENERIC_VOCAB or token in company_words:
                continue
            if len(token) < 3:
                continue
            terms.add(token)
        for match in _NUMBER.findall(text)[:40]:
            if match:
                terms.add(str(match).strip().lower())
        for match in _YEAR.findall(text):
            terms.add(match)
        if len(terms) >= limit:
            break
    return terms


def has_concrete_referent(claim: str, evidence_terms) -> bool:
    """Whether the claim names anything a reader could go and check."""
    lowered = _normalise(claim)
    if _NUMBER.search(claim) or _YEAR.search(claim):
        return True
    if any(channel in lowered for channel in _CHANNEL_WORDS):
        return True
    return any(term in lowered for term in (evidence_terms or ()) if
               len(term) >= 4)


def substitution_survives(claim: str, *, company: str, evidence_terms,
                          foil: str = "a completely unrelated company") \
        -> bool:
    """True when the claim is STILL plausible about an unrelated company —
    which means it was never a finding about this one.

    Mechanically: strip the company's name, put the foil in its place, and ask
    whether anything company-anchored remains. If nothing does, the sentence
    was carried entirely by the name.
    """
    stripped = claim or ""
    for token in sorted(_company_tokens(company), key=len, reverse=True):
        if len(token) > 2:
            stripped = re.sub(re.escape(token), foil, stripped,
                              flags=re.IGNORECASE)
    return not has_concrete_referent(stripped, evidence_terms)


def _finding(code, message, verdict):
    return {"code": code, "message": message, "verdict": verdict}


def evaluate_claim(claim, *, company: str, evidence_terms=(),
                   evidence_is_title_only: bool = False,
                   seen_statements=()) -> dict:
    """Judge one strategic claim. Returns {verdict, findings, statement}.

    `claim` may be a plain string or a dict carrying the claim's anatomy
    (statement, signal, evidence, implication, decision, confidence,
    limitation). The anatomy checks only run when the anatomy is supplied, so
    a caller can gate prose and structure separately.
    """
    if isinstance(claim, str):
        claim = {"statement": claim}
    statement = claim.get("statement") or claim.get("finding") or ""
    lowered = _normalise(statement)
    findings = []

    if not lowered:
        return {"verdict": REJECT, "statement": statement,
                "findings": [_finding("empty", "the claim says nothing",
                                      REJECT)]}

    # 1. A document type may not be the actor. This is the exact shape of
    #    "SEC 6-K is shifting where demand is captured".
    subject = lowered.split(" is ")[0].split(" are ")[0].strip()
    if any(subject == a or subject.startswith(a + " ") or subject.endswith(a)
           for a in _ARTEFACT_SUBJECTS):
        findings.append(_finding(
            "artefact_as_subject",
            f"\"{subject}\" is a kind of document, not a business actor; a "
            f"filing cannot shift demand", REJECT))

    # 2. Movement without a destination.
    if any(m in lowered for m in _MOVEMENT) and \
            not has_concrete_referent(statement, evidence_terms):
        findings.append(_finding(
            "movement_without_direction",
            "describes something changing without saying what, where, or by "
            "how much", REJECT))

    # 3. Advice without evidence.
    if any(r in lowered for r in _RECOMMENDATION) and \
            not (claim.get("evidence") or claim.get("evidence_ids")):
        findings.append(_finding(
            "recommendation_without_evidence",
            "recommends an action with no evidence behind it", REJECT))

    # 4. Strategy without a decision.
    if any(u in lowered for u in _UNNAMED_DECISION) and \
            not (claim.get("decision") or claim.get("decision_affected")):
        findings.append(_finding(
            "strategy_without_decision",
            "says something matters strategically without naming the decision "
            "it changes", REJECT))

    # 5. A title is a label, not a finding. Whoever wrote the title chose it
    #    for navigation, and inferring a business change from it is inventing
    #    the content the document was never read for.
    if evidence_is_title_only:
        findings.append(_finding(
            "title_only_evidence",
            "rests on a document title alone; the document's content was "
            "never read", REJECT))

    # 6. The substitution test.
    if substitution_survives(statement, company=company,
                             evidence_terms=evidence_terms):
        findings.append(_finding(
            "survives_substitution",
            "reads just as plausibly about an unrelated company, so it is not "
            "a finding about this one", DOWNGRADE))

    # 7. The same sentence under a second heading is not a second insight.
    normalised = re.sub(r"[^a-z0-9 ]", "", lowered)
    if normalised in {re.sub(r"[^a-z0-9 ]", "", _normalise(s))
                      for s in seen_statements}:
        findings.append(_finding(
            "repeated_statement",
            "repeats a statement already made elsewhere in the report",
            DOWNGRADE))

    verdict = ACCEPT
    if any(f["verdict"] == REJECT for f in findings):
        verdict = REJECT
    elif findings:
        verdict = DOWNGRADE
    return {"verdict": verdict, "statement": statement, "findings": findings}


# --- claim anatomy -----------------------------------------------------------
REQUIRED_ANATOMY = ("statement", "signal", "evidence", "implication",
                    "decision", "confidence", "limitation")

_ANATOMY_LABEL = {
    "statement": "a company-specific subject",
    "signal": "the concrete observed signal",
    "evidence": "a reference to the evidence",
    "implication": "the business implication",
    "decision": "the decision it is relevant to",
    "confidence": "a confidence level",
    "limitation": "a limitation or counterpoint",
}


def missing_anatomy(claim: dict) -> list:
    """Which required parts of a strategic claim are absent.

    A claim missing its implication is an observation; missing its decision, a
    fact; missing its limitation, an assertion. Each is a legitimate thing to
    publish — but not under the heading "strategic finding".
    """
    missing = []
    for field in REQUIRED_ANATOMY:
        value = claim.get(field)
        if isinstance(value, str):
            present = bool(value.strip())
        else:
            present = bool(value)
        if not present:
            missing.append(_ANATOMY_LABEL[field])
    return missing


def evaluate_report_claims(claims, *, company: str, evidence_terms=()) -> dict:
    """Judge every claim in a report and summarise. Order is preserved so a
    caller can drop rejected claims in place."""
    seen: list = []
    results = []
    for claim in claims or ():
        result = evaluate_claim(claim, company=company,
                               evidence_terms=evidence_terms,
                               seen_statements=list(seen))
        results.append(result)
        seen.append(result["statement"])
    accepted = [r for r in results if r["verdict"] == ACCEPT]
    rejected = [r for r in results if r["verdict"] == REJECT]
    return {
        "results": results,
        "accepted": accepted,
        "rejected": rejected,
        "downgraded": [r for r in results if r["verdict"] == DOWNGRADE],
        "accepted_ratio": (len(accepted) / len(results)) if results else 0.0,
        "specificity_version": SPECIFICITY_VERSION,
    }
