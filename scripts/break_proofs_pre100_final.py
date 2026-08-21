#!/usr/bin/env python3
"""Break the final-convergence repairs deliberately.

Run:  PYTHONPATH=src python3 scripts/break_proofs_pre100_final.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "src/intent_engine/webapp/app.py"
CON = ROOT / "src/intent_engine/executive/contract.py"
NAR = ROOT / "src/intent_engine/founder_brief/narrative.py"

TP = "tests/test_refusal_copy_needs_an_empty_page.py"
TG = "tests/test_a_gate_that_judged_nothing.py"
TR = "tests/test_the_read_is_composed_once.py"

PROOFS = [
    # --- P1. a page may not deny the reading it renders --------------------
    Proof("P1a. the bounded read stops counting as a reading",
          CON,
          "HAS_READING = frozenset({CURRENT_RUN_SUPPORTED, MARKET_SUPPORTED,\n"
          "                         BOTH_SUPPORTED, BOUNDED_READ_ONLY})",
          "HAS_READING = frozenset({CURRENT_RUN_SUPPORTED, MARKET_SUPPORTED,\n"
          "                         BOTH_SUPPORTED})",
          f"{TP}::test_a_bounded_read_is_a_reading",
          "assert"),
    Proof("P1b. the contract stops being told about the bounded read",
          CON,
          "    elif bounded_read:",
          "    elif False:",
          f"{TP}::test_a_bounded_read_is_a_reading",
          "assert"),
    Proof("P1c. an empty run is promoted to having a reading",
          CON,
          "    elif bounded_read:",
          "    elif True:",
          f"{TP}::test_a_genuinely_empty_run_still_refuses",
          "assert"),
    Proof("P1d. the answer section goes back to denying its own page",
          NAR,
          "            if getattr(contract, \"merge_state\", \"\") == BOUNDED_READ_ONLY:",
          "            if False:",
          f"{TP}::test_the_answer_section_stops_denying_the_page_it_is_on",
          "assert"),

    # --- P2. a gate that judged nothing is still re-gated ------------------
    Proof("P2a. the missing field switches the re-gate off again",
          APP,
          "        if seen is None:\n            seen = 0",
          "        if seen is None:\n            seen = None",
          f"{TG}::test_the_running_code_treats_a_missing_field_as_zero",
          "no longer normalises"),
    Proof("P2b. an empty store triggers a pointless re-gate",
          APP,
          "        if seen is None:\n            seen = 0",
          "        if seen is None:\n            seen = -1",
          f"{TG}::test_an_empty_store_does_not_trigger_a_pointless_pass",
          "assert"),

    # --- P3. the canonical read is composed once ---------------------------
    Proof("P3a. the memo is dropped and the page recomposes per call",
          APP,
          '        memo = getattr(self._request, "reads", None)\n'
          "        key = (run_id, name)\n"
          "        if memo is not None and key in memo:\n"
          "            return memo[key]",
          '        memo = None\n        key = (run_id, name)',
          f"{TR}::test_one_request_composes_it_once",
          "assert"),
    Proof("P3b. the memo outlives the request that made it",
          APP,
          "        self._request.reads = {}\n",
          "        self._request.reads = getattr(\n"
          '            self._request, "reads", {})\n',
          f"{TR}::test_the_next_request_does_not_inherit_it",
          "assert"),
    Proof("P3c. one run's read is served for another run",
          APP,
          '        memo = getattr(self._request, "reads", None)\n'
          "        key = (run_id, name)\n"
          "        if memo is not None and key in memo:\n"
          "            return memo[key]",
          '        memo = getattr(self._request, "reads", None)\n'
          "        key = (run_id, name)\n"
          "        if memo:\n"
          "            return next(iter(memo.values()))",
          f"{TR}::test_a_different_run_is_composed_separately",
          "assert"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title=__doc__.splitlines()[0]))
