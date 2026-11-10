#!/usr/bin/env python3
"""Assemble the evidence a twenty-dimension score has to be read from.

§14 FORBIDS SCORING A SURFACE THAT WAS NOT READ. This does not invent
scores. It reads what `pre100_batch_journey.py` captured from the deployed
product and, for each of the twenty dimensions, pulls out the exact passage a
score would have to be justified by — or records NOT_MEASURED when the
surface did not render.

It also computes the two things that ARE measurable rather than judged:

  COMPANY_SPECIFICITY  how much of the text is about THIS company rather than
                       about any company — the share of sentences carrying a
                       company-specific token (its name, its ticker, a number,
                       a named rival, a named product) out of the sentences on
                       the executive surfaces.

  TEMPLATE_COLLAPSE    pairwise similarity of the ten board answers ACROSS
                       companies. Two companies answering "who is the real
                       competitor?" with the same words is the defect §29
                       exists to catch, and it cannot be seen one company at
                       a time.

Usage:  python scripts/pre100_scorecard.py CAPTUREDIR [CAPTUREDIR ...]
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List

STEPS = ["intro", "slides", "full", "story", "history", "connect"]

#: The twenty dimensions, each with the surface it must be read on and the
#: cue that locates its passage. A dimension whose surface did not render is
#: NOT_MEASURED — never inferred from a backend test.
DIMENSIONS = [
    ("1_identity", "intro", r"(SEC CIK \d+|·\s*USA|Ticker)"),
    ("2_business_model", "intro", r"business that runs on [^.]{0,240}"),
    ("3_metric_selection", "full", r"(metric|measure|KPI|what to watch)[^.]{0,200}"),
    ("4_economic_reasoning", "full", r"(operating leverage|unit economics|"
                                     r"margin|contribution)[^.]{0,240}"),
    ("5_macro_relevance", "full", r"(rates?|inflation|cycle|macro|demand "
                                  r"environment)[^.]{0,240}"),
    ("6_micro_reasoning", "full", r"(price|pricing|volume|mix|cost)[^.]{0,240}"),
    ("7_competitive_specificity", "intro",
     r"(contested (?:most )?directly by[^.]{0,240}"
     r"|customers can substitute[^.]{0,240}"
     r"|an adjacent threat[^.]{0,240}"
     r"|sits in the same sector as[^.]{0,240})"),
    ("8_market_belief", "full", r"(market believes|market appears to|"
                                r"consensus|market-implied|structural "
                                r"expectation)[^.]{0,300}"),
    ("9_belief_challenge", "full", r"(strongest (?:reason|contradiction|"
                                   r"support)|may be wrong|against this)"
                                   r"[^.]{0,300}"),
    ("10_impossible_hypothesis", "full", r"(impossible|could not be true|"
                                         r"would have to be)[^.]{0,300}"),
    ("11_recommendation", "full", r"(management should|the decision in front|"
                                  r"what to do now|action now)[^.]{0,300}"),
    ("12_falsifier", "full", r"(would prove (?:this|us) wrong|falsif|"
                             r"change our mind)[^.]{0,300}"),
    ("13_mve", "full", r"(cheapest|measure next|information priority|"
                       r"minimum viable evidence)[^.]{0,300}"),
    ("14_presentation", "slides", r"."),
    ("15_full_analysis", "full", r"."),
    ("16_full_story", "story", r"."),
    ("17_history_rewind", "history", r"(actually happened|market expected|"
                                     r"better strategy)"),
    ("18_qa", "qa", r"."),
    ("19_step6_internal", "connect", r"."),
    ("20_reliability", "run", r"."),
]

#: Copy that means the product gave up.
ABSENCE = ["no information available", "not retrieved", "unable to determine",
           "could not be completed", "analysis failed", "no estimate retrieved"]

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if len(s.strip()) > 30]


def specificity(text: str, company: str, ticker: str, rivals: List[str]) -> float:
    """The share of sentences that could only be about THIS company."""
    tokens = {w.lower() for w in _WORD.findall(company) if len(w) > 3}
    tokens |= {r.lower() for r in rivals if r}
    if ticker:
        tokens.add(ticker.lower())
    sents = _sentences(text)
    if not sents:
        return 0.0
    hits = 0
    for s in sents:
        low = s.lower()
        if any(t in low for t in tokens) or re.search(r"\d[\d,.]*\s*(%|bn|m\b|"
                                                      r"billion|million)", low):
            hits += 1
    return round(hits / len(sents), 3)


def _bag(text: str) -> set:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 4}


def jaccard(a: str, b: str) -> float:
    x, y = _bag(a), _bag(b)
    return round(len(x & y) / len(x | y), 3) if (x | y) else 0.0


def digest(company_dir: str) -> dict:
    run_path = os.path.join(company_dir, "run.json")
    if not os.path.exists(run_path):
        return {"dir": company_dir, "error": "no run.json"}
    run = json.load(open(run_path))
    texts = {}
    for step in STEPS:
        p = os.path.join(company_dir, f"{step}.txt")
        texts[step] = open(p).read() if os.path.exists(p) else ""
    out = {"company": run.get("company"), "run_id": run.get("run_id"),
           "dir": company_dir, "evidence": {}, "not_measured": []}
    for name, surface, cue in DIMENSIONS:
        if surface == "run":
            out["evidence"][name] = json.dumps({
                "auto_advanced": run.get("auto_advanced"),
                "claimed_failure": run.get("claimed_failure"),
                "seconds": run.get("seconds"),
                "reliability": run.get("reliability")})
            continue
        if surface == "qa":
            qa = run.get("qa", {})
            answered = [q for q, a in qa.items()
                        if a.get("status") == 200 and len(a.get("text", "")) > 120]
            out["evidence"][name] = f"{len(answered)}/{len(qa)} answered"
            if not answered:
                out["not_measured"].append(name)
            continue
        body = texts.get(surface, "")
        if not body or any(a in body.lower() for a in ABSENCE):
            out["not_measured"].append(name)
            out["evidence"][name] = "NOT_MEASURED"
            continue
        found = re.search(cue, body, re.I)
        out["evidence"][name] = (found.group(0)[:320] if found
                                 else f"[surface rendered, {len(body)} chars]")
    rivals = re.findall(r"(?:contested (?:most )?directly by|substitute)\s+"
                        r"([^.]{0,200})", texts.get("intro", ""))
    rival_names = [w for r in rivals for w in re.split(r",| and ", r)]
    executive = " ".join(texts[s] for s in ("intro", "slides", "full", "story"))
    out["company_specificity"] = specificity(
        executive, run.get("company", ""), run.get("ticker", ""),
        [r.strip() for r in rival_names])
    out["position_sentence"] = run.get("position_sentence", "")
    out["model_sentence"] = run.get("model_sentence", "")
    out["qa"] = run.get("qa", {})
    return out


def main() -> int:
    dirs = []
    for root in sys.argv[1:]:
        for entry in sorted(os.listdir(root)):
            path = os.path.join(root, entry)
            if os.path.isdir(path):
                dirs.append(path)
    digests = [digest(d) for d in dirs]

    # §29 TEMPLATE COLLAPSE, measured ACROSS companies.
    collapse: Dict[str, float] = {}
    questions = set()
    for d in digests:
        questions |= set(d.get("qa", {}))
    for q in sorted(questions):
        answers = [d["qa"][q]["text"] for d in digests
                   if q in d.get("qa", {}) and d["qa"][q].get("text")]
        pairs = [jaccard(a, b) for i, a in enumerate(answers)
                 for b in answers[i + 1:]]
        if pairs:
            collapse[q] = round(sum(pairs) / len(pairs), 3)

    report = {"companies": [{k: v for k, v in d.items() if k != "qa"}
                            for d in digests],
              "template_collapse_by_question": collapse,
              "template_collapse_mean": (round(sum(collapse.values())
                                               / len(collapse), 3)
                                         if collapse else None)}
    print(json.dumps(report, indent=2)[:200])
    out = os.path.join(sys.argv[1], "scorecard_evidence.json")
    json.dump(report, open(out, "w"), indent=2)
    print(f"\nwrote {out}")
    for d in digests:
        print(f"{d.get('company','?'):32} specificity="
              f"{d.get('company_specificity')} "
              f"NOT_MEASURED={len(d.get('not_measured', []))}")
    print(f"\ntemplate collapse mean: {report['template_collapse_mean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
