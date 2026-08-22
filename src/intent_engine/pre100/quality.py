"""The Executive Quality Gate: is this demo actually good, not merely working.

WHAT THIS IS AND IS NOT
-----------------------
Operational PASS is necessary and nowhere near sufficient. A run can render
every route, agree across surfaces, answer ten questions and still be a
template with a company name in it. This scores the twenty dimensions a chief
executive would actually judge the product on.

IT DOES NOT INVENT SCORES. §14 forbids scoring a surface that was not read,
and a subjective 8.7 that no one can check is worse than no number: it is a
number that stops the question being asked. Every dimension here is scored
from MEASURED features of the rendered text -- is the passage present, does it
name this company rather than any company, does it carry a quantity, is it
distinct from what the other forty-nine companies were told -- and every score
carries the exact passage it was read from. A dimension whose surface did not
render is NOT_MEASURED, never zero: "we could not look" and "we looked and it
was empty" are different findings.

WHERE HUMAN JUDGEMENT IS STILL REQUIRED, the report says so rather than
simulating it. A measured rubric can establish that the competition section
names three real rivals with a basis for each; it cannot establish that a PE
operating partner would find the recommendation worth acting on.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
from typing import Dict, List, Optional

from intent_engine.pre100 import audit as A

#: NOT_MEASURED is not a zero. It propagates, and a core dimension that is
#: NOT_MEASURED fails the gate rather than being averaged away.
NOT_MEASURED = None

#: The nine dimensions §20 calls core. A demo can be forgiven a weak history
#: rewind; it cannot be forgiven an economic model that is wrong.
#: §26's core list, which names `economic_reasoning`, `adversary` and
#: `impossible_hypothesis` -- the first had no dimension defined and the
#: other two were deliberately kept out of core while nothing produced them.
#: All three now have producers, so all three are scored as core.
CORE = ("business_model", "economic_reasoning", "market_belief",
        "competition", "adversary", "impossible_hypothesis",
        "recommendation", "full_analysis", "presentation", "history", "qa")

#: (key, surface, cue). The cue LOCATES the passage; it does not score it.
DIMENSIONS = (
    # A CUE MUST CAPTURE CONTENT, NOT ONLY ITS OWN ANCHOR. This alternation
    # had no trailing group, so the passage WAS the matched token -- and
    # because "— introduction" appears in the page title before "SEC CIK"
    # ever does, every company's passage was the two words "— introduction"
    # and every company scored 6. Nineteen identical passages, nineteen
    # identical scores, on a dimension nothing could move.
    ("intro", "intro",
     r"(SEC CIK \d+|·\s*USA|Ticker|— introduction)[^.]{0,300}"),
    # THE SUBJECT IS PART OF THE SENTENCE. This cue began at "is a…", which
    # excludes the company name that precedes it — so `_specific` looked for
    # the company in a passage the cue had just cut it out of, and every
    # business-model sentence read as generic. MEASURED on the deployed
    # f8c183f capture: Microsoft's sentence is drawn from its own 10-K
    # ("an array of services, including cloud-based solutions that provide
    # customers with AI, software, services, platforms, and content") and
    # scored 6, "present but not specific to this company".
    #
    # Whether two COMPANIES share a sentence is the specificity scorer's
    # question and it strips the name deliberately. Within one page, the
    # subject is what the sentence is about.
    ("business_model", "intro",
     r"[A-Z][\w.&,' -]{2,60} is an? [^.]{0,180}?business that runs on "
     r"[^.]{0,260}"),
    ("revenue_drivers", "story",
     r"(Revenue is decided by|where the money actually comes from)[^.]{0,300}"),
    ("margin_drivers", "story",
     r"(becomes margin is decided by|margin is decided|operating leverage)"
     r"[^.]{0,300}"),
    # THE SURFACE HAS TO BE THE ONE THE PRODUCT WRITES ON.
    #
    # A first version of this pointed market belief, belief challenge, the
    # falsifier and the MVE at `/full` and scored them 0-3 across all fifty
    # companies -- a uniform defect the instrument invented. Measured across
    # every capture: "the market's current belief" appears on `brief` in 79
    # and on `full` in 31; "what could break it" the same. The deep decision
    # memo is the executive brief, and the cue wording had to come from what
    # the product actually writes rather than from the rubric's vocabulary.
    ("capital_intensity", "brief",
     r"(capital|capex|asset[- ]intensit|balance sheet|fixed cost"
     r"|cost of funds)[^.]{0,240}"),
    ("macro", "full",
     r"(rates?|inflation|cycle|macro|demand environment)[^.]{0,240}"),
    ("micro", "full", r"(price|pricing|volume|mix|unit cost)[^.]{0,240}"),
    ("market_belief", "brief",
     r"(market'?s? current belief|market believes|market appears to"
     r"|consensus|market-implied|structural expectation)[^.]{0,300}"),
    ("belief_challenge", "brief",
     r"(Why it may be right|What could break it|strongest (?:reason|"
     r"contradiction|support)|may be wrong|the plainer account)[^.]{0,300}"),
    # THE PRODUCT'S WORDING MOVED. Measured on the deployed f8c183f capture
    # of Microsoft: the competitive sentence reads "the contest is most
    # direct with The customer's own engineering, Renewing nothing and
    # keeping the current process" -- a real, correct competitive read made
    # of substitutes rather than named firms. The old cue matched none of it
    # and would have scored 0 on every company whose rivals are substitutes,
    # which is a defect the instrument invents.
    ("competition", "intro",
     r"(contested (?:most )?directly by[^.]{0,260}"
     r"|the contest is most direct with[^.]{0,260}"
     r"|customers can substitute[^.]{0,260}"
     r"|the alternative may be[^.]{0,260}"
     r"|an adjacent threat[^.]{0,260}"
     r"|sits in the same sector as[^.]{0,260})"),
    # GENUINELY ABSENT, AND VERIFIED AS SUCH. Neither string appears on ANY
    # surface of ANY of the 50 companies' captures -- intro, slides, full,
    # story, history, connect, brief and report all zero. `deep.py` reads an
    # `adversary` key and an ADVERSARIAL scenario, so the concept exists in
    # the model and never reaches a reader. These two stay pointed at the
    # surface §23 says they belong on, and their zeros are the product's.
    # BOTH NOW RENDER, AND BOTH RENDER ON `full`.
    #
    # They scored 0.0 on all 44 measured companies, and the note below was
    # right that the zeros were the product's. They are no longer: the
    # adversary reaches the read and the decision, and the heresies have a
    # producer. The CUE MOVES TO THE SURFACE THAT WRITES THEM -- `deep.py`
    # renders both inside the full analysis -- because a cue pointed at a
    # surface the product does not write on invents a uniform defect, which
    # this instrument has already done once.
    # REACH THE ACTOR. The section opens with a heading and a generic lead
    # ("One rival, three ways it could behave"), and a cue that stops at the
    # first full stop scores that lead — so a section naming a real rival at
    # L0/L1/L2 read as "present but not specific". Measured on the f8c183f
    # Microsoft capture: the actor is 180 characters past the heading.
    ("adversary", "full",
     r"(?:If we move, what do they do|L[012]\s*—)"
     r"[\s\S]{0,600}?L[012]\s*—\s*[^.]{0,200}"),
    ("impossible_hypothesis", "full",
     r"(What could be true that we are not considering"
     r"|may be worth more|may not be the customer|may stop existing"
     r"|may be structurally unable|smallest test)[^.]{0,300}"),
    # §26 NAMES THIS AND NOTHING DEFINED IT, so every company reported it
    # NOT_MEASURED and the gate failed fifty companies on a dimension no
    # instrument was pointed at.
    # THE CUE MUST BE THE PRODUCT'S VOCABULARY, NOT THE RUBRIC'S. Measured
    # over the 21 live briefs on 589518f: "revenue engine", "margin engine",
    # "unit economics", "cost of revenue", "how the money" and "capital
    # intensity" appear on ZERO pages. The phrases below were collected from
    # what the product actually writes, and lift the dimension from 18 of 21
    # to 21 of 21. Negative control: none of them matches a plain factual
    # page with no economic mechanism in it.
    ("economic_reasoning", "full",
     r"(operating leverage|what it costs to serve|fully-loaded cost"
     r"|marginal cost|acquisition cost|incremental margin|margin narrowing"
     r"|fixed cost|volume or through price|subsidis)[^.]{0,300}"),
    # Same defect, same method. "management should" appears on ZERO of the 21
    # briefs; the old set matched 16 of 21 and the five misses each carried a
    # real recommendation the instrument could not see -- Bank of America's
    # brief says "whether the plan should be fundable from operating cash
    # rather than from a raise timed to a recovery in the price" and scored 0.
    #
    # "What we would watch next" appears on 21 of 21 and is deliberately NOT
    # here: it is a monitoring item, and borrowing it would let this
    # dimension score on step 6's content instead of its own.
    ("recommendation", "brief",
     r"(What to do next|The choice:|management should|the decision in front"
     r"|Commit to the reading|Hold and verify|bears on one choice"
     r"|the plan should|should be built on)[^.]{0,300}"),
    ("falsifier", "brief",
     r"(What could break it|would prove (?:this|us) wrong|falsif"
     r"|show it is wrong|change our mind)[^.]{0,300}"),
    ("mve", "brief",
     r"(cheapest way to find out|One check separates|measure next"
     r"|information priority|minimum viable|kill switch)[^.]{0,300}"),
    ("presentation", "slides", r"."),
    ("full_analysis", "full", r"."),
    # Same defect as `intro`: no trailing capture, so the passage was the
    # anchor itself ("Better strategy") for all nineteen companies.
    ("history", "history",
     r"(actually happened|market expected|better strategy|what happened)"
     r"[^.]{0,300}"),
    ("qa", "qa", r"."),
    ("step6", "connect",
     r"(your own|internal|connect|what this becomes)[^.]{0,300}"),
)

#: CORE must name dimensions that exist. When it did not, every company
#: reported `economic_reasoning` as NOT_MEASURED and the gate failed all
#: fifty for a dimension nothing scored.
_UNDEFINED = set(CORE) - {k for k, _s, _c in DIMENSIONS}
if _UNDEFINED:                                              # pragma: no cover
    raise AssertionError(f"CORE names undefined dimensions: {_UNDEFINED}")

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_QUANTITY = re.compile(r"\d[\d,.]*\s*(%|bn|bps|billion|million|x\b)|\$\s?\d")
_PROPER = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b")

#: Copy that means the product GAVE UP. Its presence caps a dimension.
#:
#: FULL ADMISSIONS ONLY. "not retrieved" was in this list, and it fired on
#: Microsoft's live Q&A -- inside the sentence "read from the business model,
#: not retrieved", which is the product correctly distinguishing a DERIVED
#: belief from a retrieved one. Ten substantive, company-specific answers
#: were capped at 3 by one honest provenance qualifier.
#:
#: A fragment that can appear inside a disclaimer is not an admission. Each
#: entry here has to be unusable as anything but a statement that nothing
#: was produced.
_ABSENCE = (
    "no information available", "unable to determine",
    "no strategic reading", "no reading cleared", "no estimate retrieved",
    "could not be completed", "analysis failed", "no history available",
    "cleared the evidence bar", "no market expectation",
    "do not act on this reading",
)

#: Below this a surface is short enough that one admission IS the surface.
#: Above it, an incidental phrase inside a long substantive page is not the
#: page giving up, and capping the whole dimension on it measures the phrase
#: rather than the product.
_ADMISSION_DOMINATES_BELOW = 800


def _text(company_dir: pathlib.Path, surface: str) -> str:
    if surface == "qa":
        rows = A.load_qa(company_dir)
        return " ".join(str(r.get("answer") or "") for r in rows)
    path = pathlib.Path(company_dir) / f"{surface}.txt"
    if not path.exists():
        return ""
    raw = path.read_text("utf-8", errors="replace")
    # The extractor folds inline <style> into the text stream; a CSS rule is
    # not prose and counting it inflated Pfizer's /full from 3,941 to 21,718.
    raw = re.sub(r"[.#a-zA-Z-]+\s*\{[^}]*\}", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _specific(passage: str, company: str, tickers=()) -> bool:
    """Could this sentence only be about THIS company?"""
    low = passage.lower()
    tokens = {v.lower() for v in A.name_variants(company)}
    tokens |= {t.lower() for t in tickers if t}
    if any(t in low for t in tokens if len(t) > 3):
        return True
    if _QUANTITY.search(passage):
        return True
    # A named proper noun that is NOT the company is a rival, a product or a
    # place -- all of which are company-specific.
    #
    # A CAPITAL LETTER IS NOT A NAME. Every sentence starts with one, and every
    # heading capitalises. "Better strategy" was read as carrying the proper
    # noun "Better", "The choice: Commit to..." as carrying "Commit" -- so two
    # phrases the product writes identically for every company were both
    # judged company-specific. Ordinary words are excluded by vocabulary; what
    # survives is a name.
    # A CAPITAL AT THE START OF A SENTENCE IS GRAMMAR, NOT A NAME.
    #
    # This was a stoplist, and a stoplist cannot work in either direction: it
    # let through every capitalised word nobody had thought to list. NEGATIVE
    # CONTROL, run against a capture whose every surface is generic filler
    # naming no company, no number and no mechanism -- "The business operates
    # in a competitive environment. Conditions may change over time." -- it
    # scored 10, "company-specific and substantiated", on six dimensions,
    # because "Conditions" and "Various" were read as names.
    #
    # Position is the discriminator that does not need a vocabulary: a name
    # appears mid-sentence too. "Adobe" in "contested by Adobe and Salesforce"
    # is a name; "Conditions" in "Conditions may change" is a sentence
    # opening.
    others = [m for m in _mid_sentence_proper_nouns(passage)
              if m.lower() not in tokens and len(m) > 4]
    return len(others) >= 1


def _mid_sentence_proper_nouns(passage: str):
    """Capitalised words that do NOT open a sentence."""
    out = []
    for match in _PROPER.finditer(passage or ""):
        before = (passage[:match.start()].rstrip())
        if not before:
            continue                        # opens the passage
        if before[-1] in ".!?:;·—–-":
            continue                        # opens a sentence or a list item
        out.append(match.group(0))
    return out


#: Capitalised words that are not names. These are the ones the product's own
#: headings and sentence openings actually produce -- collected from the live
#: passages that were being mis-read, not guessed at.
_NOT_A_NAME = frozenset("""
better commit choice hold verify these those there their which while would
could should about after before because between during against another other
every under above below since until whether within without through
company companies business businesses market markets customer customers
revenue margin margins price prices pricing product products service services
capital growth demand supply strategy strategic decision decisions evidence
analysis reading result results report reports source sources filing filings
quarter quarterly annual segment segments industry sector economy economic
management investors shareholders competitor competitors alternative
""".split())


def score_dimension(key: str, surface: str, cue: str, *, text: str,
                    company: str, tickers=()) -> dict:
    """One dimension, scored from what is on the page. Never invents.

    10  present, company-specific, quantified or entity-bearing, substantial
     8  present and company-specific
     6  present but generic -- true of any company in this sector
     3  present only as an admission that it is absent
     0  the surface rendered and the dimension is not on it
    NOT_MEASURED  the surface did not render
    """
    if not text:
        return {"dimension": key, "surface": surface, "score": NOT_MEASURED,
                "why": "surface did not render", "passage": ""}
    if cue == ".":
        # WHOLE-SURFACE DIMENSIONS. `presentation`, `full_analysis` and `qa`
        # are not located by a cue -- the surface IS the dimension. Matching
        # "." returns the first CHARACTER, and scoring "N" as the deck was
        # the instrument inventing a uniform defect across every company.
        passage = text[:1200]
    else:
        match = re.search(cue, text, re.I)
        if not match:
            return {"dimension": key, "surface": surface, "score": 0,
                    "why": "no passage for this dimension on the surface",
                    "passage": ""}
        passage = match.group(0)
    low = text.lower()
    admitted = [a for a in _ABSENCE if a in low]
    if admitted and len(text) < _ADMISSION_DOMINATES_BELOW:
        return {"dimension": key, "surface": surface, "score": 3,
                "why": f"surface admits absence: {admitted[0]!r}",
                "passage": passage[:300]}
    specific = _specific(passage, company, tickers)
    quantified = bool(_QUANTITY.search(passage))
    # SUBSTANTIATION IS A PROPERTY OF THE PASSAGE, NOT OF THE PAGE.
    #
    # This read `or len(text) >= 1500`, and `text` is the WHOLE SURFACE. Every
    # real analysis page is longer than 1500 characters, so the clause was
    # always true and the length of the passage never mattered.
    #
    # MEASURED across 19 live companies on 589518f: `history`'s cue captures
    # no trailing text at all, so its passage is the literal phrase "Better
    # strategy" -- byte-identical for all nineteen -- and it scored 10,
    # "company-specific and substantiated", for every one of them. So did
    # `recommendation` ("The choice: Commit to the reading now versus hold and
    # verify first", also identical across all nineteen). A dimension that
    # scores full marks on two shared words is a dimension that cannot fail.
    substantial = len(passage) >= 90
    if specific and (quantified or substantial):
        score, why = 10, "company-specific and substantiated"
    elif specific:
        score, why = 8, "company-specific"
    else:
        score, why = 6, "present but not specific to this company"
    return {"dimension": key, "surface": surface, "score": score,
            "why": why, "passage": passage[:300]}


def score_company(company_dir, *, tickers=()) -> dict:
    company_dir = pathlib.Path(company_dir)
    manifest = {}
    mpath = company_dir / "manifest.json"
    if mpath.exists():
        try:
            manifest = json.loads(mpath.read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            manifest = {}
    company = manifest.get("company") or company_dir.name
    cache: Dict[str, str] = {}
    rows = []
    for key, surface, cue in DIMENSIONS:
        if surface not in cache:
            cache[surface] = _text(company_dir, surface)
        rows.append(score_dimension(key, surface, cue, text=cache[surface],
                                    company=company, tickers=tickers))
    by_key = {r["dimension"]: r for r in rows}
    core = [by_key[k]["score"] for k in CORE if k in by_key]
    measured = [s for s in core if s is not NOT_MEASURED]
    unmeasured = [k for k in CORE
                  if by_key.get(k, {}).get("score") is NOT_MEASURED]
    everything = [r["score"] for r in rows if r["score"] is not NOT_MEASURED]
    return {
        "company": company,
        "deployed_sha": manifest.get("deployed_sha", ""),
        "outcome": manifest.get("outcome", ""),
        "dimensions": rows,
        "core_mean": round(statistics.mean(measured), 2) if measured else None,
        "core_min": min(measured) if measured else None,
        "core_unmeasured": unmeasured,
        "all_mean": round(statistics.mean(everything), 2)
        if everything else None,
    }


def gate(rows: List[dict], *, core_mean=9.0, core_min=8.5) -> dict:
    """§20. The bar, applied to what was measured.

    A core dimension that could not be measured FAILS rather than being
    averaged away: the alternative is a mean computed over the dimensions
    that happened to render, which is the number that always looks fine.
    """
    scored = [r for r in rows if r.get("core_mean") is not None]
    fails = []
    for r in rows:
        if r.get("core_unmeasured"):
            fails.append((r["company"],
                          f"core NOT_MEASURED: {','.join(r['core_unmeasured'])}"))
        elif r["core_mean"] < core_mean:
            fails.append((r["company"], f"core_mean {r['core_mean']}"))
        elif r["core_min"] < core_min:
            fails.append((r["company"], f"core_min {r['core_min']}"))
    means = [r["core_mean"] for r in scored]
    mins = [r["core_min"] for r in scored]
    return {
        "companies": len(rows),
        "scored": len(scored),
        "core_mean": round(statistics.mean(means), 2) if means else None,
        "core_min": min(mins) if mins else None,
        "failing": fails,
        "passes": not fails and len(scored) == len(rows) and bool(rows),
    }


# =============================================================================
# CROSS-COMPANY DISTINCTNESS (§14, §17)
# =============================================================================
#
# WHY A SECOND PASS EXISTS. `_specific` asks whether a passage NAMES this
# company, which is a proxy. The property the gate is actually about is
# whether the product said something DIFFERENT about this company than about
# the other forty-nine -- and no single-company scorer can see that.
#
# It matters in both directions, and both were measured live on 589518f:
#
#   over-scoring   `history`, `recommendation` and `step6` each rendered ONE
#                  passage, byte-identical across all nineteen companies, and
#                  each scored 10 on every one of them.
#   under-scoring  NVIDIA's margin passage ("manufacturing and foundry cost
#                  and yield"), Alphabet's ("infrastructure and compute per
#                  user served and content moderation") and Intel's ("the
#                  capacity is pre-sold under long-term agreements") are
#                  plainly different from each other and plainly about their
#                  companies. None names its company or carries a number, so
#                  all three scored 6.
#
# This is deliberately NOT a similarity threshold tuned until the numbers look
# right. It is exact repetition: the same words, for a different company.

#: A passage repeated for at least this share of the corpus is boilerplate.
#: Two companies in a sector legitimately share a sentence; a third of the
#: universe saying the same thing is the product's template showing through.
SHARED_PASSAGE_SHARE = 0.34

#: The ceiling a repeated passage may reach. 6 is the scorer's own "present
#: but not specific to this company", which is exactly what a shared passage
#: is -- so the cap reuses the band rather than inventing one.
SHARED_PASSAGE_CAP = 6


def _norm_passage(passage: str) -> str:
    return " ".join((passage or "").split()).lower()


def rescore_corpus(rows):
    """Apply cross-company distinctness to per-company scores.

    `rows` is [(company, scored_dict)] as `score_company` returned them. The
    same list comes back, with any dimension whose passage is repeated across
    the corpus capped and its `why` rewritten to say so.

    Scoring stays a pure function of what is on the pages: nothing here reads
    the product again, and a company scored alone is unchanged.
    """
    rows = [(name, row) for name, row in rows]
    counts: Dict[str, Dict[str, int]] = {}
    for _name, row in rows:
        for dim in row.get("dimensions", []):
            text = _norm_passage(dim.get("passage"))
            if not text:
                continue
            counts.setdefault(dim["dimension"], {})
            counts[dim["dimension"]][text] = \
                counts[dim["dimension"]].get(text, 0) + 1
    total = len(rows) or 1
    floor = max(2, int(total * SHARED_PASSAGE_SHARE))
    for _name, row in rows:
        kept = []
        for dim in row.get("dimensions", []):
            text = _norm_passage(dim.get("passage"))
            shared = counts.get(dim["dimension"], {}).get(text, 0)
            score = dim.get("score")
            if (text and shared >= floor and isinstance(score, int)
                    and score > SHARED_PASSAGE_CAP):
                dim = dict(dim, score=SHARED_PASSAGE_CAP,
                           why=(f"identical passage on {shared} of {total} "
                                f"companies — not specific to this one"))
            kept.append(dim)
        row["dimensions"] = kept
        core = [d["score"] for d in kept
                if d["dimension"] in CORE and isinstance(d["score"], int)]
        if core:
            row["core_mean"] = round(sum(core) / len(core), 2)
            row["core_min"] = min(core)
        scored = [d["score"] for d in kept if isinstance(d["score"], int)]
        if scored:
            row["mean"] = round(sum(scored) / len(scored), 2)
    return rows


# =============================================================================
# SCORING THE PROSE, NOT THE HEADING (§14, §15, §17)
# =============================================================================
#
# WHY THIS REPLACES THE HEADING-ANCHORED WINDOW.
#
# A cue is a LOCATOR. It finds the section a dimension lives in by matching
# that section's heading -- and then the score was computed on the ~100
# characters starting AT the heading, which is the heading and the explanatory
# subtitle underneath it. Both are written once, for every company.
#
# MEASURED on 21 live companies at 589518f:
#
#   history                passage = "Better strategy Counterfactual Where a
#                          named alternative available on the same information
#                          plausibly led" -- identical for all 21
#   impossible_hypothesis  "What could be true that we are not considering
#                          These are propositions this company's current
#                          framing rules out by construction" -- identical
#   step6                  the NAV BAR: "Home · Your analyses · Guest demo
#                          session Leave demo Connect your company"
#
# Those pages are not generic. Measured over whole surfaces, sentence by
# sentence, the share of sentences unique to ONE company is:
#
#   history 70.4%   full 63.1%   brief 57.6%   connect 26.9%
#
# So the product writes company-specific prose and the instrument was scoring
# the furniture in front of it. Fixing the cues one at a time would repeat the
# defect at the next heading, so location and scoring are separated instead:
# the cue still says WHERE, and what is scored is the prose that follows it
# with corpus-shared sentences removed.

#: How much prose after the anchor a dimension is judged on. Long enough to
#: clear a heading and its subtitle, short enough that two dimensions on one
#: surface are not scored on the same text.
PROSE_WINDOW = 900

#: A sentence written for at least this share of the corpus is furniture --
#: a heading, a subtitle, a nav item, an explainer. Removed before scoring
#: rather than penalised, because its presence says nothing either way.
FURNITURE_SHARE = 0.8


def _sentences(text: str):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\s{2,}", text or "")
            if len(x.strip()) > 30]


def _furniture(surface_texts, share=FURNITURE_SHARE):
    """Sentences repeated across the corpus on one surface."""
    seen: Dict[str, int] = {}
    for text in surface_texts:
        for sentence in set(_sentences(text)):
            seen[sentence] = seen.get(sentence, 0) + 1
    floor = max(3, int(len(surface_texts) * share))
    return {s for s, c in seen.items() if c >= floor}


def score_corpus(company_dirs, tickers_by_company=None):
    """Score every company against the corpus. §14's cross-company pass.

    Two things no single-company scorer can do:

      it removes FURNITURE -- the headings, subtitles and nav the product
      writes identically for everyone -- so a dimension is judged on what was
      written ABOUT THIS COMPANY;

      it caps a passage that survives that and is STILL identical elsewhere,
      which is template collapse and the thing §14 exists to catch.
    """
    company_dirs = [pathlib.Path(d) for d in company_dirs]
    tickers_by_company = tickers_by_company or {}
    surfaces = {s for _k, s, _c in DIMENSIONS}
    texts: Dict[str, Dict[str, str]] = {}
    for d in company_dirs:
        texts[d.name] = {}
        for surface in surfaces:
            f = d / f"{surface}.txt"
            texts[d.name][surface] = f.read_text("utf-8", errors="replace") \
                if f.exists() else ""
    furniture = {surface: _furniture([texts[n][surface] for n in texts])
                 for surface in surfaces}
    rows = []
    for d in company_dirs:
        manifest = {}
        mp = d / "manifest.json"
        if mp.exists():
            try:
                manifest = json.loads(mp.read_text("utf-8"))
            except Exception:                               # noqa: BLE001
                manifest = {}
        company = manifest.get("company") or d.name
        tickers = tickers_by_company.get(d.name, ())
        dims = []
        for key, surface, cue in DIMENSIONS:
            text = texts[d.name].get(surface) or ""
            if not text:
                dims.append({"dimension": key, "surface": surface,
                             "score": NOT_MEASURED,
                             "why": "surface did not render", "passage": ""})
                continue
            if cue == ".":
                window = text[:PROSE_WINDOW * 2]
            else:
                match = re.search(cue, text, re.I)
                if not match:
                    dims.append({"dimension": key, "surface": surface,
                                 "score": 0, "passage": "",
                                 "why": "no passage for this dimension on "
                                        "the surface"})
                    continue
                window = text[match.start():match.start() + PROSE_WINDOW]
            prose = " ".join(x for x in _sentences(window)
                             if x not in furniture[surface])
            if not prose:
                dims.append({"dimension": key, "surface": surface, "score": 6,
                             "why": "only shared section furniture here — "
                                    "nothing written about this company",
                             "passage": window[:300]})
                continue
            dims.append(_score_prose(key, surface, prose, company, tickers))
        rows.append((d.name, {"company": company, "dimensions": dims}))
    return rescore_corpus(rows)


def _score_prose(key, surface, prose, company, tickers):
    specific = _specific(prose, company, tickers)
    quantified = bool(_QUANTITY.search(prose))
    substantial = len(prose) >= 90
    if specific and (quantified or substantial):
        score, why = 10, "company-specific and substantiated"
    elif specific:
        score, why = 8, "company-specific"
    else:
        score, why = 6, "present but not specific to this company"
    return {"dimension": key, "surface": surface, "score": score,
            "why": why, "passage": prose[:300]}
