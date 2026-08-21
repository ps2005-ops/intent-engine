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
CORE = ("business_model", "revenue_drivers", "margin_drivers",
        "market_belief", "competition", "recommendation", "full_analysis",
        "presentation", "history", "qa")

#: (key, surface, cue). The cue LOCATES the passage; it does not score it.
DIMENSIONS = (
    ("intro", "intro", r"(SEC CIK \d+|·\s*USA|Ticker|— introduction)"),
    ("business_model", "intro",
     r"is an? [^.]{0,180}?business that runs on [^.]{0,260}"),
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
    ("competition", "intro",
     r"(contested (?:most )?directly by[^.]{0,260}"
     r"|customers can substitute[^.]{0,260}"
     r"|an adjacent threat[^.]{0,260}"
     r"|sits in the same sector as[^.]{0,260})"),
    # GENUINELY ABSENT, AND VERIFIED AS SUCH. Neither string appears on ANY
    # surface of ANY of the 50 companies' captures -- intro, slides, full,
    # story, history, connect, brief and report all zero. `deep.py` reads an
    # `adversary` key and an ADVERSARIAL scenario, so the concept exists in
    # the model and never reaches a reader. These two stay pointed at the
    # surface §23 says they belong on, and their zeros are the product's.
    ("adversary", "brief",
     r"(would respond|competitor response|if they match|retaliat"
     r"|adversar)[^.]{0,300}"),
    ("impossible_hypothesis", "brief",
     r"(impossible|could not be true|would have to be)[^.]{0,300}"),
    ("recommendation", "brief",
     r"(What to do next|The choice:|management should|the decision in front"
     r"|Commit to the reading|Hold and verify)[^.]{0,300}"),
    ("falsifier", "brief",
     r"(What could break it|would prove (?:this|us) wrong|falsif"
     r"|show it is wrong|change our mind)[^.]{0,300}"),
    ("mve", "brief",
     r"(cheapest way to find out|One check separates|measure next"
     r"|information priority|minimum viable|kill switch)[^.]{0,300}"),
    ("presentation", "slides", r"."),
    ("full_analysis", "full", r"."),
    ("history", "history",
     r"(actually happened|market expected|better strategy|what happened)"),
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

#: Copy that means the product gave up. Its presence caps a dimension.
_ABSENCE = (
    "no information available", "not retrieved", "unable to determine",
    "no strategic reading", "no reading cleared", "no estimate retrieved",
    "could not be completed", "analysis failed", "no history available",
    "cleared the evidence bar", "no market expectation",
)


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
    others = [m for m in _PROPER.findall(passage)
              if m.lower() not in tokens and len(m) > 4]
    return len(others) >= 1


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
    if admitted:
        return {"dimension": key, "surface": surface, "score": 3,
                "why": f"surface admits absence: {admitted[0]!r}",
                "passage": passage[:300]}
    specific = _specific(passage, company, tickers)
    quantified = bool(_QUANTITY.search(passage))
    substantial = len(passage) >= 90 or len(text) >= 1500
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
