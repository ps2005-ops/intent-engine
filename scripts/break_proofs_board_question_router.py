#!/usr/bin/env python3
"""Break the board-question router deliberately.

The defect: eight of the ten questions this programme asks reached no intent,
fell to the strategic catch-all, and were answered from the matched pattern's
own text — so two companies on one pattern gave the same answer to eight of
ten, and a company whose run concluded nothing gave a refusal to all eight
while its own introduction showed a Bounded read.

Run:  PYTHONPATH=src python3 scripts/break_proofs_board_question_router.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
Q = ROOT / "src/intent_engine/founder_brief/qa.py"
T = "tests/test_every_board_question_reaches_the_router.py"
T2 = "tests/test_two_companies_sharing_a_pattern.py"

PROOFS = [
    ("A1. the recommendation loses the question management actually asks",
     Q,
     '     ("what should we do", "what should i do", "what should management do",',
     '     ("what should we do", "what should i do",',
     f"{T}::test_every_board_question_routes[What should management do?]",
     "reaches no intent"),

    ("A2. the falsifier marker goes back to requiring 'proves'",
     Q,
     '     ("prove this wrong", "proves this wrong", "prove you wrong",',
     '     ("proves this wrong", "prove you wrong",',
     f"{T}::test_the_falsifier_marker_matches_the_question_actually_asked",
     "assert"),

    ("A3. monitoring forgets 'measure'",
     Q,
     '     ("monitor next", "measure next", "what should we monitor",\n'
     '      "what should we measure", "watch next", "check next", "monday"),',
     '     ("monitor next", "what should we monitor",\n'
     '      "watch next", "check next", "monday"),',
     f"{T}::test_the_monitoring_marker_knows_measure_as_well_as_monitor",
     "assert"),

    # Renaming an intent is NOT the defect — `intent_of` returns whatever
    # name is declared and the question still routes. The defect is markers
    # that do not match the question, so that is what the mutation removes.
    ("B1. why_now loses the markers that reach it",
     Q,
     '     ("why now", "why this now", "why is now", "timing"),',
     '     ("why the timing of this particular decision",),',
     f"{T}::test_every_board_question_routes[Why now?]",
     "reaches no intent"),

    ("B2. two intents route to one field, answering identically",
     Q,
     '     "expectations",\n'
     '     "No market expectation has been established for this company."),',
     '     "falsifier",\n'
     '     "No market expectation has been established for this company."),',
     f"{T}::test_no_two_intents_declare_the_same_field",
     "assert"),

    ("C1. a routed answer stops carrying whose filing made it true",
     Q,
     "        if not out.strongest_evidence:\n"
     "            grounding = _pattern_grounding(decision)\n"
     "            if grounding:\n"
     "                out.strongest_evidence = grounding\n"
     "        return out",
     "        return out",
     f"{T2}::test_the_qa_answer_carries_whose_filing_made_it_true",
     "assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
