#!/usr/bin/env python3
"""Break the per-company grounding of a shared pattern deliberately.

The defect: Caterpillar and Exxon, different classes, answered eight of ten
board questions with the identical sentence because every field of the
composed decision is the pattern's static text.

Run:  PYTHONPATH=src python3 scripts/break_proofs_shared_pattern.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "src/intent_engine/strategic_intelligence/decision.py"
Q = ROOT / "src/intent_engine/founder_brief/qa.py"
T = "tests/test_two_companies_sharing_a_pattern.py"
T2 = "tests/test_deep_intelligence_documents.py"

PROOFS = [
    ("A1. the qualifying sentence is no longer read at all",
     D,
     "        return MECH.because_line(hypothesis, limit=1)",
     "        return \"\"",
     f"{T}::test_each_company_has_its_own_qualifying_sentence",
     "assert"),

    ("A2. Q&A stops carrying whose filing made the answer true",
     Q,
     "    if not out.strongest_evidence:\n"
     "        grounding = _pattern_grounding(decision)",
     "    if False:\n"
     "        grounding = _pattern_grounding(decision)",
     f"{T}::test_the_qa_answer_carries_whose_filing_made_it_true",
     "assert"),

    ("A4. the decision stops carrying the grounding at all",
     D,
     "        grounded_in=grounding_of(hypothesis),",
     "        grounded_in=\"\",",
     f"{T}::test_the_decision_carries_the_grounding",
     "assert"),

    ("A3. Q&A overwrites evidence an answer already chose",
     Q,
     "    if not out.strongest_evidence:\n"
     "        grounding = _pattern_grounding(decision)\n"
     "        if grounding:\n"
     "            out.strongest_evidence = grounding",
     "    grounding = _pattern_grounding(decision)\n"
     "    if grounding:\n"
     "        out.strongest_evidence = grounding",
     f"{T}::test_an_answer_that_chose_its_own_evidence_keeps_it",
     "overwrote evidence the answer had already chosen"),

    ("B1. the quote is folded back into the shared mechanism",
     D,
     "    return claim\n\n\ndef grounding_of(hypothesis) -> str:",
     "    return f\"{claim} {grounding_of(hypothesis)}\".strip()\n\n\n"
     "def grounding_of(hypothesis) -> str:",
     f"{T2}::test_no_sentence_is_printed_twice_in_either_document",
     "assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
