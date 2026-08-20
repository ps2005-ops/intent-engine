#!/usr/bin/env python3
"""Break the single competitive state deliberately.

The defect: step 1 named the rivals and Q&A, one click later in the same run,
denied any had been identified. 3 of 3 companies on the deployed 0420fb0.

Run:  PYTHONPATH=src python3 scripts/break_proofs_one_competitive_state.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SR = ROOT / "src/intent_engine/executive/strategic_read.py"
QA = ROOT / "src/intent_engine/founder_brief/qa.py"
T = "tests/test_one_competitive_state_across_surfaces.py"

PROOFS = [
    ("A1. Q&A goes back to reading level4 only, and denies the rest",
     QA,
     "    if name == \"competitor\":\n        return _competition_answer(read)",
     "    if name == \"competitor\" and False:\n"
     "        return _competition_answer(read)",
     f"{T}::test_qa_does_not_deny_what_step_one_asserts[SAME_MODEL]",
     "No competitor has been selected"),

    ("A2. the competitor answer is gated on a strategy again",
     QA,
     "    if name == \"competitor\":\n        return _competition_answer(read)",
     "    if name == \"competitor\" and getattr(\n"
     "            read, \"puts_a_strategy_forward\", False):\n"
     "        return _competition_answer(read)",
     f"{T}::test_the_competitor_answer_is_not_gated_on_a_strategy",
     "assert"),

    ("B1. a class-level peer list is stated with the evidence verb",
     SR,
     "    if basis == COMPETITION_FROM_EVIDENCE:\n"
     "        return \"Its position is contested directly by \" "
     "+ _join(rivals) + \".\"",
     "    if True:\n"
     "        return \"Its position is contested directly by \" "
     "+ _join(rivals) + \".\"",
     f"{T}::test_the_verb_matches_the_basis",
     "contested directly by"),

    ("B2. the ladder's weakest rung counts as evidence again",
     SR,
     "    ranked = [c for c in (rivals_read or ())\n"
     "              if getattr(c, \"rung\", \"\") != \"STRUCTURAL_PEER\"]\n"
     "    if ranked:",
     "    ranked = list(rivals_read or ())\n"
     "    if ranked:",
     f"{T}::test_the_ladders_weakest_rung_is_not_evidence",
     "assert"),

    ("B3. a same-model peer is graded as strongly as the evidence",
     SR,
     "        return {\"rivals\": tuple(c.name for c in strong)[:3],\n"
     "                \"basis\": COMPETITION_FROM_MODEL, \"rows\": ()}",
     "        return {\"rivals\": tuple(c.name for c in strong)[:3],\n"
     "                \"basis\": COMPETITION_FROM_EVIDENCE, \"rows\": ()}",
     f"{T}::test_a_same_model_peer_is_a_weaker_basis_than_evidence",
     "assert"),

    ("D1. a populated row list is refused as an absence again",
     QA,
     "                rendered = _render_rows(value)\n"
     "                if rendered:\n"
     "                    return rendered, name",
     "                rendered = \"\"\n"
     "                if rendered:\n"
     "                    return rendered, name",
     f"{T}::test_a_populated_row_list_is_rendered_not_refused",
     "No competitor has been selected"),

    ("D2. an unrenderable row reaches for the absent copy instead of the read",
     QA,
     "                fallback = _from_read(row_name, read)\n"
     "                return (fallback or absent), name",
     "                return absent, name",
     f"{T}::test_an_unrenderable_row_asks_the_read_before_giving_up",
     "assert"),

    ("D3. the row branch stops firing, so rows join as raw dicts",
     QA,
     "            if value and any(isinstance(v, dict) for v in value):",
     "            if False:",
     f"{T}::test_a_populated_row_list_is_rendered_not_refused",
     "assert"),

    ("C1. step 1 stops deriving its rivals from the shared state",
     SR,
     "    state = competitive_state(profile, rivals_read)",
     "    state = {\"rivals\": (), \"basis\": COMPETITION_NONE, \"rows\": ()}",
     f"{T}::test_both_surfaces_read_the_same_fields",
     "assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
