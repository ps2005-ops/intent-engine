#!/usr/bin/env python3
"""Would five different buyers act on this? §27.

WHY A RUBRIC AND NOT FIVE READING SESSIONS PER COMPANY
------------------------------------------------------
Reading fifty companies as five personas each is 250 sittings, and the last
programme that tried it got through six. What a persona actually wants is
CHECKABLE: a CEO needs a decision and a reason; a VP Finance needs a number
or an explicit statement that there is none; a PE operating partner needs a
lever and a horizon. Those are properties of the captured text.

WHAT THIS IS NOT
----------------
It is not a judgement of whether the analysis is RIGHT. It measures whether
the document is usable by the person it is aimed at. The lowest five, the
highest three and a representative five are still read by hand -- the rubric
decides WHICH fifteen are worth the sitting, which is the whole point.

Every criterion names the surface it read and the passage it matched, so a
score can be checked rather than trusted.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.pre100 import audit as A                 # noqa: E402

CONTRACT = "pre100_customer_acceptance.v1"

#: A number, a date, or a magnitude. What separates "margins are pressured"
#: from something a finance function can put in a model.
_QUANTITY = re.compile(r"\d[\d,.]*\s*(%|bn|bps|billion|million|x\b)|\$\s?\d"
                       r"|\b20\d\d\b")

#: (persona, criterion, surface, what must be present)
RUBRIC = (
    ("CEO", "decision_usefulness", "brief",
     r"(What to do next|The choice:|Commit to the reading|Hold and verify"
     r"|Hold this decision|management should)"),
    ("CEO", "non_obvious_insight", "full",
     r"(What could be true that we are not considering|may be worth more"
     r"|may not be the customer|may stop existing|may be structurally)"),
    ("CEO", "trust", "brief",
     r"(SEC 10-K|SEC 10-Q|Form 10-K|filing|disclosed|—\s*SEC)"),
    ("CEO", "board_readiness", "slides", r"."),

    ("Chief Strategy Officer", "competitive_specificity", "intro",
     r"(contested (?:most )?directly by|customers can substitute"
     r"|an adjacent threat)"),
    ("Chief Strategy Officer", "adversary", "full",
     r"(If we move, what do they do|L[012]\b)"),
    ("Chief Strategy Officer", "non_obvious_insight", "full",
     r"(What could be true that we are not considering|Smallest test)"),
    ("Chief Strategy Officer", "trust", "full", r"(SEC|filing|10-K)"),

    ("PE Operating Partner", "lever", "brief",
     r"(One check separates|cheapest way to find out|measure next"
     r"|minimum viable|smallest test)"),
    ("PE Operating Partner", "decision_usefulness", "brief",
     r"(What to do next|The choice:)"),
    ("PE Operating Partner", "downside", "full",
     r"(kill switch|Where we stop|if acted on wrongly|guardrail|falsif)"),
    ("PE Operating Partner", "trust", "full", r"(SEC|filing|10-K)"),

    ("VP Finance", "quantified", "full", None),          # None -> quantity test
    ("VP Finance", "revenue_mechanics", "story",
     r"(Revenue is decided by|where the money actually comes from"
     r"|revenue engine)"),
    ("VP Finance", "margin_mechanics", "story",
     r"(becomes margin is decided by|margin is decided|operating leverage)"),
    ("VP Finance", "bounded_honestly", "full",
     r"(bounded rather than measured|direction only|not measured"
     r"|could not be established)"),

    ("Enterprise buyer", "what_it_would_take", "connect",
     r"(Internal intelligence|what is still bounded|Available next)"),
    ("Enterprise buyer", "trust", "connect",
     r"(public evidence alone|checkable|nothing is sent|explicit approval)"),
    ("Enterprise buyer", "continued_use", "connect",
     r"(Decision log|CRM|Financial plan|Your documents)"),
    ("Enterprise buyer", "board_readiness", "full", r"."),
)

#: Copy that means the product gave up. Caps the criterion at 2.
_ABSENCE = ("no information available", "not retrieved", "analysis failed",
            "could not be completed", "no strategic reading",
            "no reading cleared", "do not act on this reading")


def _text(company_dir: pathlib.Path, surface: str) -> str:
    if surface == "qa":
        return " ".join(str(r.get("answer") or "")
                        for r in A.load_qa(company_dir))
    path = pathlib.Path(company_dir) / f"{surface}.txt"
    return path.read_text("utf-8", "replace") if path.exists() else ""


def score(company_dir) -> dict:
    """5 = present, specific and substantiated. 1 = the surface is silent."""
    company_dir = pathlib.Path(company_dir)
    cache: dict = {}
    rows = []
    for persona, criterion, surface, cue in RUBRIC:
        if surface not in cache:
            cache[surface] = _text(company_dir, surface)
        text = cache[surface]
        if not text:
            rows.append({"persona": persona, "criterion": criterion,
                         "surface": surface, "score": None,
                         "why": "surface did not render", "passage": ""})
            continue
        low = text.lower()
        if cue is None:
            match = _QUANTITY.search(text)
            passage = match.group(0) if match else ""
        elif cue == ".":
            match, passage = True, text[:400]
        else:
            found = re.search(cue, text, re.I)
            match, passage = bool(found), (found.group(0) if found else "")
        if not match:
            rows.append({"persona": persona, "criterion": criterion,
                         "surface": surface, "score": 1,
                         "why": "nothing this persona needs is on the surface",
                         "passage": ""})
            continue
        admitted = [a for a in _ABSENCE if a in low]
        if admitted:
            rows.append({"persona": persona, "criterion": criterion,
                         "surface": surface, "score": 2,
                         "why": f"surface admits absence: {admitted[0]!r}",
                         "passage": passage[:200]})
            continue
        # SUBSTANTIATED means the surface carries enough to act on, not that
        # the cue matched. A 400-character section and a one-line stub both
        # match a cue, and only one of them is usable.
        substantial = len(text) >= 2000
        quantified = bool(_QUANTITY.search(text))
        value = 5 if (substantial and quantified) else 4 if substantial else 3
        rows.append({"persona": persona, "criterion": criterion,
                     "surface": surface, "score": value,
                     "why": "present and usable", "passage": passage[:200]})
    by_persona: dict = {}
    for row in rows:
        if row["score"] is not None:
            by_persona.setdefault(row["persona"], []).append(row["score"])
    personas = {p: round(statistics.mean(v), 2)
                for p, v in by_persona.items()}
    means = list(personas.values())
    return {
        "contract": CONTRACT,
        "company": company_dir.name,
        "criteria": rows,
        "personas": personas,
        "mean": round(statistics.mean(means), 2) if means else None,
        "min_persona": min(means) if means else None,
    }


def main() -> int:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dm", str(ROOT / "scripts/pre100_development_matrix.py"))
    dm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dm)
    rows = [score(d) for _n, (_w, d, _m) in
            sorted(dm.newest_per_company().items())]
    means = [r["mean"] for r in rows if r["mean"] is not None]
    mins = [r["min_persona"] for r in rows if r["min_persona"] is not None]
    per_persona: dict = {}
    for row in rows:
        for persona, value in row["personas"].items():
            per_persona.setdefault(persona, []).append(value)
    report = {
        "contract": CONTRACT,
        "companies": len(rows),
        "mean": round(statistics.mean(means), 2) if means else None,
        "min": min(mins) if mins else None,
        "by_persona": {p: round(statistics.mean(v), 2)
                       for p, v in sorted(per_persona.items())},
        "lowest_five": [r["company"] for r in
                        sorted(rows, key=lambda r: r["mean"] or 0)[:5]],
        "highest_three": [r["company"] for r in
                          sorted(rows, key=lambda r: -(r["mean"] or 0))[:3]],
        "rows": rows,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
