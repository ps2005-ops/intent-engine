"""Does the product say a different thing about each company? §12.

WHY A SEPARATE INSTRUMENT
-------------------------
Quality scoring asks whether a dimension is present and substantiated. It
cannot see the failure this programme has hit repeatedly: five companies each
scoring 8 on business model, with ONE SENTENCE between them. A class-level
constant is locally excellent and globally worthless, and only a comparison
ACROSS companies can see it.

WHAT IT REPORTS
---------------
For each compared field: every byte-identical pair, and every pair above the
similarity floor. It names the PAIR and the FIELD, because "specificity is
low" is not a defect report and cannot be repaired.

WHAT IT EXCLUDES, AND WHY THAT IS NOT A LOOPHOLE
------------------------------------------------
Universal UI copy is identical on purpose -- navigation, the evidence stamp,
the standing legend. Excluding it is required or every pair is a duplicate;
excluding anything else would hide the defect. So the exclusion is a fixed
list of the product's own chrome, applied to whole extracted passages only,
and the passages themselves are located by the same cues the quality gate
uses -- one locator, so the two instruments cannot disagree about where a
field is.
"""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Sequence, Tuple

CONTRACT = "pre100_specificity.v1"

#: Above this, two passages are the same passage with the names changed.
SIMILAR = 0.90

#: (field, surface, cue). Deliberately the SAME cues the quality gate uses
#: where a field is shared, so a passage cannot be "present" for one
#: instrument and "absent" for the other.
FIELDS = (
    ("business_model", "intro",
     r"is an? [^.]{0,180}?business that runs on [^.]{0,260}"),
    ("central_question", "intro",
     r"(The question[^.]{0,240}|decision worth arguing about[^.]{0,240}"
     r"|what to charge[^.]{0,240})"),
    # THE SUBSTANTIVE SENTENCE, NOT THE FRAMING LINE.
    #
    # `The choice:` is a constant lead-in and it matched FIRST, so 166 pairs
    # reported identical on a field whose actual content is specific --
    # Alphabet's "is a measurable and growing share of orders originating
    # from AI-agent surfaces rather than human browsing?" against Amazon's
    # "segment disclosure showing no material inter-segment revenue". The
    # instrument was reading the label above the answer.
    ("recommendation", "brief",
     r"(What to do next|One check separates them|management should"
     r"|Hold this decision)[^.]{0,300}"),
    # `the risk is` matched `_LIKELIHOOD[SUBSTITUTE]` in competitive_ground:
    # "the risk is that they are not responding to us at all" -- a correct
    # constant about a KIND OF RIVAL, not a claim about the company. Two
    # companies whose nearest rival is a substitute SHOULD share it, so
    # counting it as a duplicate measured the vocabulary, not the product.
    ("biggest_risk", "brief",
     r"(biggest risk|what would hurt|the risk to this reading)[^.]{0,300}"),
    ("competitors", "intro",
     r"(contested (?:most )?directly by[^.]{0,260}"
     r"|customers can substitute[^.]{0,260})"),
    ("adversary", "full",
     r"(If we move, what do they do)[^.]{0,400}"),
    ("impossible_hypothesis", "full",
     r"(What could be true that we are not considering)[^.]{0,400}"),
    # 1035 OF A POSSIBLE 1128 PAIRS -- 92% -- came from this cue matching the
    # section's opening, which is identical BY DESIGN: "What this becomes with
    # your own context. Everything you have just read was built from public
    # evidence alone." A defect that uniform is the instrument, not the
    # product. Step 6's company-specific material is the list of measures a
    # business of this kind is judged on, which is where this now points.
    ("step6", "connect",
     r"(?:Internal intelligence|still bounded)[^A-Za-z]{0,4}(.{60,600})"),
    ("board_answer", "qa", r"^.{0,600}"),
)

#: The product's own chrome. Identical across companies BY DESIGN.
_CHROME = (
    "home · your analyses", "guest demo session", "leave demo",
    "back to the analysis", "ask a follow-up", "your question",
    "answers use only this run's approved evidence",
    "executive x-ray", "evidence — why this reading exists",
    "sources", "executive brief", "other views", "suggested:",
    # OUR OWN QUESTIONS. The board questions are the same ten for every
    # company by design, and the Q&A page prints the question above the
    # answer -- so leaving them in makes every pair share their opening.
    "what should management do?", "why now?", "what's the biggest risk?",
    "what proves this wrong?", "who's the real competitor?",
    "what does the market believe?", "what's the weakest assumption?",
    "what should we measure next?", "what would you tell the board?",
    "what impossible hypothesis should we test?",
    "what would prove this wrong?",
)


def _normalise(passage: str, company: str) -> str:
    """The passage with THIS company's own name removed.

    THE NAME IS THE POINT. Two sentences differing only in the company name
    are the same sentence, and leaving the name in is how a template scores
    as distinct fifty times over. Removing it is what makes the comparison a
    test of the CONTENT.
    """
    text = " ".join(str(passage or "").split()).lower()
    for chrome in _CHROME:
        text = text.replace(chrome, " ")
    for token in sorted(_variants(company), key=len, reverse=True):
        if len(token) > 3:
            text = text.replace(token.lower(), " ")
    return " ".join(text.split())


def _variants(company: str) -> List[str]:
    name = str(company or "").strip()
    out = {name}
    bare = re.sub(r",?\s+(inc\.?|corp\.?|corporation|company|co\.?|plc|"
                  r"n\.?v\.?|s\.?a\.?|ltd\.?|limited|group|holdings?|"
                  r"& co\.?)$", "", name, flags=re.I).strip()
    out.add(bare)
    first = bare.split(" ")[0] if bare else ""
    if len(first) > 3:
        out.add(first)
    return [o for o in out if o]


def extract(field_cue: str, text: str) -> str:
    if not text:
        return ""
    match = re.search(field_cue, text, re.I | re.S)
    return match.group(0) if match else ""


def compare(rows: Sequence[Dict]) -> dict:
    """`rows` are {company, fields: {field: passage}}. Returns the report.

    A field only ONE company has is not evidence of anything, so a field is
    compared only where at least two companies produced a passage. Reporting
    "0 duplicates" over a field nobody rendered is how an instrument passes a
    gate on an absence.
    """
    identical: List[Tuple[str, str, str]] = []
    similar: List[Tuple[str, str, str, float]] = []
    coverage: Dict[str, int] = {}
    for field, _surface, _cue in FIELDS:
        present = [(r["company"], _normalise(r["fields"].get(field, ""),
                                             r["company"]))
                   for r in rows if str(r["fields"].get(field) or "").strip()]
        # A PASSAGE THAT NORMALISES TO ALMOST NOTHING carries no content to
        # compare, and calling two of them identical measures the chrome
        # filter rather than the product.
        present = [(c, t) for c, t in present if len(t) >= 40]
        coverage[field] = len(present)
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                (a, ta), (b, tb) = present[i], present[j]
                if ta == tb:
                    identical.append((field, a, b))
                    continue
                ratio = difflib.SequenceMatcher(None, ta, tb).ratio()
                if ratio >= SIMILAR:
                    similar.append((field, a, b, round(ratio, 3)))
    pairs = max(0, len(rows) * (len(rows) - 1) // 2)
    return {
        "contract": CONTRACT,
        "companies": len(rows),
        "comparable_pairs_per_field": pairs,
        "field_coverage": coverage,
        "byte_identical": [
            {"field": f, "a": a, "b": b} for f, a, b in identical],
        "near_identical": [
            {"field": f, "a": a, "b": b, "similarity": r}
            for f, a, b, r in similar],
        "byte_identical_count": len(identical),
        "near_identical_count": len(similar),
        # THE FIELDS THAT ARE ACTUALLY COLLAPSING, ranked. A total is not a
        # defect report; the field with 40 duplicate pairs is.
        "worst_fields": sorted(
            {f for f, *_ in identical} | {f for f, *_ in similar},
            key=lambda f: -(sum(1 for x, *_ in identical if x == f)
                            + sum(1 for x, *_ in similar if x == f))),
    }
