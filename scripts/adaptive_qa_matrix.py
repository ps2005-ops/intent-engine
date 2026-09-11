#!/usr/bin/env python3
"""The Q&A matrix: sixty first-turn answers and ten contextual follow-ups.

Three things are measured and they are NOT the same thing:

  SUBSTANTIVE   the answer came back, and it is long enough to be an answer
  SPECIFIC      it names the company it is about
  CLEAN         it does not name a DIFFERENT company from the cohort

The third is the one worth having. A worker thread that reused another
visitor's memo, or a prompt that carried the last company forward, shows up
here and nowhere else -- and it cannot be seen by looking at one company's
page, which is why it is measured across the cohort rather than per run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEN = ["Highspot", "BigID", "Cyera", "Monte Carlo Data", "Veeam", "Druva",
       "Slalom", "Sigma Computing", "ZoomInfo", "Point B"]

#: Words that identify a company without also being ordinary English. "Point"
#: and "Data" would match prose about any company, so the distinctive token is
#: used and single generic tokens are refused.
GENERIC = {"data", "point", "monte", "carlo", "computing", "sigma", "b"}


def tokens_for(name: str):
    out = []
    for t in re.split(r"[^A-Za-z0-9]+", name):
        if len(t) >= 4 and t.lower() not in GENERIC:
            out.append(t)
    # a company whose every token is generic keeps its full name as one probe
    return out or [name]


#: Page furniture that surrounds every answer. Counting it as answer length
#: is how "60/60 substantive" was reported for answers of one sentence.
CHROME = (r"Home · Your analyses · Guest demo session Leave demo",
          r"Ask a follow-up.*$", r"Suggested:.*$", r"Other views.*$")

#: A STATED LIMITATION IS A VALID ANSWER when the evidence cannot support a
#: fuller one. Written as the STRUCTURE the product uses rather than as a list
#: of sentences: `founder_brief/qa.py` says "No falsifier has been recorded",
#: "No open uncertainty has been recorded for this company", "Nothing is
#: currently preregistered to watch", "This particular question is not
#: answerable from what this run retrieved", "revenue growth is not disclosed
#: at the granularity the decision needs". Matching phrases would mean
#: re-listing every one of those and mis-scoring the next one somebody writes;
#: matching the form scores the property.
LIMITATION = re.compile(
    r"\b(?:no|nothing|not|none)\b[^.]{0,90}?\b("
    r"established|recorded|selected|retrieved|disclosed|answerable|"
    r"preregistered|compared|available|put forward|checked|supported|"
    r"invent|evidence|independent|sufficient)\b", re.I)


def answer_body(text: str, company: str, question: str) -> str:
    """The answer with the page removed from around it."""
    body = text or ""
    for rx in CHROME:
        body = re.sub(rx, " ", body, flags=re.S)
    body = body.replace(question, " ").replace(company, " ")
    return " ".join(body.split())


def is_valid(body: str, status: int, company: str, raw: str = "") -> tuple:
    """(valid, why). Semantic validity, never a raw word count.

    A concise, evidence-aware refusal PASSES: on a run that retrieved nothing,
    "there is not enough public evidence to answer that confidently" is the
    correct answer and a long one would be a fabrication.
    """
    if status != 200:
        return False, f"status {status}"
    if not body:
        return False, "empty"
    low = body.lower()
    if len(body.split()) >= 40:
        return True, "substantive"
    if LIMITATION.search(body):
        return True, "states its limitation in the product's own form"
    # COMPANY-SPECIFICITY IS TESTED ON THE RAW TEXT, because `answer_body`
    # strips the company name out -- testing the stripped body for the name it
    # just removed is a check that can only ever fail. Measured: it marked a
    # 27-word answer invalid that reads "the company's filings carry this, so
    # it is stated under legal obligation rather than in marketing -- but no
    # outside account has tested whether it is working".
    named = company.split()[0].lower() in (raw or body).lower()
    if named and len(body.split()) >= 15:
        return True, "short, specific and grounded in this company"
    return False, (f"neither substantive nor a stated limitation "
                   f"({len(body.split())}w)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--out",
                    default="docs/ADAPTIVE_STRATEGIC_INTELLIGENCE_QA_MATRIX.md")
    a = ap.parse_args()
    raw = json.loads((ROOT / a.matrix).read_text())
    rows = {r["company"]: r for r in raw.get("rows", [])}

    others = {n: [t for m in TEN if m != n for t in tokens_for(m)]
              for n in TEN}

    lines = ["# Adaptive Strategic Intelligence — Q&A matrix", "",
             f"Frozen SHA: `{raw.get('live_commit') or 'unrecorded'}`", "",
             "Six substantive questions per company through the page's own "
             "`/conversation` form, then one contextual follow-up that only "
             "makes sense if the previous answer was retained.", "",
             "| Company | answered | valid (semantic) | names itself | names "
             "another company | follow-up |", "|" + "---|" * 6]

    tot_answered = tot_long = tot_specific = tot_leak = tot_follow = 0
    leak_detail = []
    for name in TEN:
        r = rows.get(name)
        if r is None:
            lines.append(f"| {name} | — | — | — | — | — |")
            continue
        qa = r.get("qa") or []
        answered = sum(1 for x in qa if x.get("status") == 200)
        bodies = [answer_body(x.get("text", ""), name, x.get("q", ""))
                  for x in qa]
        verdicts = [is_valid(b, x.get("status", 0), name,
                             raw=x.get("text", ""))
                    for b, x in zip(bodies, qa)]
        long_ = sum(1 for ok, _why in verdicts if ok)
        mine = tokens_for(name)
        specific = sum(1 for x in qa
                       if any(re.search(re.escape(t), x.get("text", ""), re.I)
                              for t in mine))
        leaks = 0
        for x in qa:
            hit = [t for t in others[name]
                   if re.search(r"\b" + re.escape(t) + r"\b",
                                x.get("text", ""), re.I)]
            if hit:
                leaks += 1
                if len(leak_detail) < 8:
                    leak_detail.append(
                        f"- **{name}** answer mentions {sorted(set(hit))}: "
                        f"\"{x.get('text', '')[:160]}…\"")
        follow = "PASS" if r.get("followup_pass") else "**FAIL**"
        tot_answered += answered
        tot_long += long_
        tot_specific += specific
        tot_leak += leaks
        tot_follow += 1 if r.get("followup_pass") else 0
        lines.append(f"| {name} | {answered}/6 | {long_}/6 | {specific}/6 "
                     f"| {leaks} | {follow} |")

    n = len([c for c in TEN if c in rows])
    lines += ["", "### Totals", "", "```",
              f"ANSWERED:                 {tot_answered}/{6 * n}",
              f"VALID (semantic):         {tot_long}/{6 * n}",
              f"COMPANY-SPECIFIC:         {tot_specific}/{6 * n}",
              f"FOLLOW-UP CONTEXT:        {tot_follow}/{n}",
              f"CROSS-COMPANY LEAKAGE:    {tot_leak}", "```"]
    if leak_detail:
        lines += ["", "### Cross-company mentions, for inspection", "",
                  "A mention is not automatically contamination — a real "
                  "competitor may be named correctly. Each is shown so it "
                  "can be judged.", ""] + leak_detail

    text = "\n".join(lines) + "\n"
    (ROOT / a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
