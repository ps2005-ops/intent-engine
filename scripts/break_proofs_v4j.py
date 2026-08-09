"""Break proofs for E-DEM-001: the filing prose that never reached the engine.

The defect these attack is not a wrong answer. It is a document silently
losing 79% of itself between the fetch and the classifier, so every layer
downstream reported an honest zero about text it had never seen.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

CI = ROOT / "src/intent_engine/company_ingestion"
M = ROOT / "src/intent_engine/market"
T = "tests"
FP = f"{T}/test_market_filing_prose_survives_parsing.py"

PROOFS = [
    # --- 1. div prose discarded again ----------------------------------
    ("1. <div> is dropped from the block set, losing filing prose",
     CI / "parsing.py",
     '          "div", "section"}',
     '          }',
     f"{FP}::test_adjacent_divs_are_separate_blocks_not_one_run_on"),

    # --- 2. loose text requires an open block --------------------------
    ("2. text outside a recognised block is dropped on the floor",
     CI / "parsing.py",
     "        if self._skip_depth == 0:\n"
     "            self._buffer.append(data)",
     "        if self._skip_depth == 0 and self._block_stack:\n"
     "            self._buffer.append(data)",
     f"{FP}::test_loose_body_text_is_captured"),

    # --- 3. a nested block discards what preceded it -------------------
    ("3. a block starting resets the buffer instead of emitting it",
     CI / "parsing.py",
     "            self._emit(self._block_stack[-1] if self._block_stack else \"\")\n"
     "            self._block_stack.append(tag)",
     "            self._block_stack.append(tag)",
     f"{FP}::test_text_before_a_nested_block_is_not_discarded"),

    # --- 5. the document tail is never flushed -------------------------
    ("5. text the document never closed a tag for is lost",
     CI / "parsing.py",
     "    extractor._emit(\"\")",
     "    pass",
     f"{FP}::test_loose_body_text_is_captured"),

    # --- 6. script and style leak back in ------------------------------
    ("6. skipped regions are buffered now that a block is not required",
     CI / "parsing.py",
     "        if self._skip_depth == 0:\n"
     "            self._buffer.append(data)",
     "        if True:\n"
     "            self._buffer.append(data)",
     f"{FP}::test_script_and_style_are_still_skipped"),

    # --- 7. the vocabulary disagrees with itself again -----------------
    ("7. a type the classifier returns is refused by the constructor",
     M / "micro_evidence.py",
     "    COMMITTED_DEMAND, COST_SHOCK,\n"
     "})",
     "})",
     f"{FP}::test_every_type_the_classifier_can_produce_is_constructible"),

    # --- 8. the type gate stops gating --------------------------------
    ("8. any string is accepted as an evidence type",
     M / "micro_evidence.py",
     "    if evidence_type not in EVIDENCE_TYPES:",
     "    if False:",
     f"{FP}::test_an_unknown_type_is_still_refused"),
]

# --- NOT_BUILT ------------------------------------------------------------
#
# "a demand state reaches demand_chain from a live filing" has no guard to
# break yet. The parser fix puts the sentence in front of the classifier and
# the classifier still returns None for narrative demand ("Strong order rates
# and a growing backlog reflect broadening momentum") because no family
# carries orders/bookings/shipments as objects. That is the second half of
# E-DEM-001 and it is not built, so a proof against it would be demonstrating
# the absence of a code path.
NOT_BUILT = 1

if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4j — E-DEM-001 filing prose: {len(PROOFS)} proofs, "
               f"{NOT_BUILT} recorded NOT_BUILT")))
