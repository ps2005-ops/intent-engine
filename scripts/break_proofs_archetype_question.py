#!/usr/bin/env python3
"""Break the archetype-question coverage deliberately.

The defect: ADVERTISING_PLATFORM proposes ENGAGEMENT and MONETISATION_RATE and
neither could ask a question, so Meta's and Alphabet's CENTRAL QUESTION was
the epistemic fallback with the company name swapped.

Run:  PYTHONPATH=src python3 scripts/break_proofs_archetype_question.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
A = ROOT / "src/intent_engine/executive/analysis_selection.py"
T = "tests/test_every_archetype_has_a_question.py"

PROOFS = [
    ("A1. ENGAGEMENT loses its subject again",
     A,
     '    "ENGAGEMENT": "how much of the audience\'s attention to convert into "\n'
     '                  "inventory, and where",',
     '    "ENGAGEMENT_UNUSED": "x",',
     f"{T}::test_meta_asks_an_advertising_question_not_an_epistemic_one",
     "What does the published record establish about"),

    ("A2. MONETISATION_RATE loses its subject",
     A,
     '    "MONETISATION_RATE": "what to charge for a unit of attention, and in "\n'
     '                         "which formats",',
     '    "MONETISATION_RATE_UNUSED": "x",',
     f"{T}::test_every_proposable_archetype_has_a_subject[MONETISATION_RATE]",
     "has no subject"),

    # The durable property: an archetype added to a class menu TOMORROW must
    # turn the suite red until somebody writes its question. Mutating a class
    # menu is how to prove that, because the guard discovers the menu rather
    # than enumerating it.
    ("B1. a new archetype joins a class menu with no question to ask",
     ROOT / "src/intent_engine/executive/company_profile.py",
     '        "archetypes": ("ENGAGEMENT", "MONETISATION_RATE", "PRICING",',
     '        "archetypes": ("BRAND_EQUITY", "ENGAGEMENT", '
     '"MONETISATION_RATE", "PRICING",',
     f"{T}::test_every_class_can_ask_a_question_of_its_own"
     "[ADVERTISING_PLATFORM]",
     "which cannot ask"),

    ("C1. the question stops naming this business's own driver",
     A,
     '        "ENGAGEMENT": f"given that ad load taken today is paid for out of "\n'
     '                      f"{driver} tomorrow",',
     '        "ENGAGEMENT": "given the trade-off involved",',
     f"{T}::test_meta_asks_an_advertising_question_not_an_epistemic_one",
     "engagement"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
