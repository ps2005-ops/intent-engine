#!/usr/bin/env python3
"""§16. Measure board-answer collapse across companies, correctly.

TWO MEASUREMENTS OF THIS LIED BEFORE THE THIRD ONE WORKED, so the method is
the point:

  * a naive similarity over the captured answers read 0.915 — inflated,
    because every answer carries the same page chrome;
  * masking the company name and testing byte-equality read 0/10 — deflated,
    because the chrome AFTER the answer differs per company;
  * masking the name AND truncating at the first chrome marker gives 9/10,
    which is the number.

Only the company name and the chrome are normalised. Business content is
never normalised away — two companies that genuinely face the same decision
are allowed to say so, and §22 asks for materially distinct answers across
INDUSTRIES, not for forced stylistic variety.

Usage:  python scripts/pre100_template_collapse.py CAPTUREDIR
"""
from __future__ import annotations

import json
import os
import re
import sys

#: Where the answer ends and the page furniture begins.
CHROME_MARKERS = (
    "Ask a follow-up", "Other views", "← Back to the analysis",
    "Suggested:", "The answer Executive X-Ray",
    # BOILERPLATE TAILS. These are appended to the answer, vary by run rather
    # than by company, and are what made three IDENTICAL answers to "Who's
    # the real competitor?" score as three distinct ones. An instrument that
    # counts a trailing caveat as content reports differentiation that the
    # reader does not get.
    "Why this matters", "Low, by construction", "Moderate, by construction",
    "High, by construction",
)
#: Leading furniture, before the answer.
LEAD_MARKERS = ("Leave demo",)


def answer_only(text: str, company: str) -> str:
    body = text or ""
    for lead in LEAD_MARKERS:
        i = body.find(lead)
        if i >= 0:
            body = body[i + len(lead):]
    for cut in CHROME_MARKERS:
        i = body.find(cut)
        if i > 0:
            body = body[:i]
    # Only the identity is normalised — LONGEST FIRST.
    #
    # THE THIRD INSTRUMENT ERROR IN THIS ONE MEASUREMENT. Masking a set of
    # name variants iterates in arbitrary order, so "Caterpillar" was
    # replaced before "Caterpillar Inc." and left a stray " Inc." behind,
    # which made three identical answers look distinct and reported 0/10 for
    # a capture that is 9/10. Sort by length descending and the longest
    # variant always wins.
    variants = sorted({company, company.split(",")[0],
                       company.split(" Inc")[0], company.split(" Corp")[0]},
                      key=len, reverse=True)
    for token in variants:
        if token:
            body = body.replace(token, "<CO>")
    return " ".join(body.split())


def load(capture_dir: str) -> dict:
    out = {}
    for entry in sorted(os.listdir(capture_dir)):
        path = os.path.join(capture_dir, entry)
        qa_path = os.path.join(path, "qa.json")
        run_path = os.path.join(path, "run.json")
        if not (os.path.isdir(path) and os.path.exists(qa_path)):
            continue
        company = entry
        if os.path.exists(run_path):
            company = json.load(open(run_path)).get("company", entry)
        out[company] = json.load(open(qa_path))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    data = load(sys.argv[1])
    if len(data) < 2:
        print(f"need at least two companies, found {len(data)}")
        return 1
    companies = sorted(data)
    questions = sorted(set().union(*(set(v) for v in data.values())))

    rows, identical_questions = [], 0
    for q in questions:
        answers = {c: answer_only(data[c].get(q, {}).get("text", ""), c)
                   for c in companies if q in data[c]}
        distinct = len({a for a in answers.values() if a})
        pairs = [(a, b) for i, a in enumerate(answers) for b in
                 list(answers)[i + 1:]]
        identical_pairs = sum(1 for a, b in pairs
                              if answers[a] and answers[a] == answers[b])
        rate = identical_pairs / len(pairs) if pairs else 0.0
        if distinct == 1 and len(answers) > 1:
            identical_questions += 1
        rows.append({"question": q, "distinct_answers": distinct,
                     "companies": len(answers),
                     "identical_pair_rate": round(rate, 3),
                     "example": next(iter(answers.values()), "")[:180]})

    report = {
        "companies": companies,
        "questions": len(questions),
        "identical_across_all_companies": identical_questions,
        "identical_rate": round(identical_questions / len(questions), 3)
        if questions else 0.0,
        "per_question": rows,
    }
    out = os.path.join(sys.argv[1], "template_collapse.json")
    json.dump(report, open(out, "w"), indent=2)

    print(f"{len(companies)} companies: {', '.join(companies)}\n")
    print(f"{'question':52} {'distinct':>8} {'identical pairs':>16}")
    for r in rows:
        flag = "  <-- COLLAPSED" if r["distinct_answers"] == 1 else ""
        print(f"{r['question'][:52]:52} {r['distinct_answers']:>8} "
              f"{r['identical_pair_rate']:>16.2f}{flag}")
    print(f"\nIDENTICAL ACROSS ALL COMPANIES: "
          f"{identical_questions}/{len(questions)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
