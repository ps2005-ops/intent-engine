#!/usr/bin/env python3
"""Break the executive-quality repairs deliberately.

Run:  PYTHONPATH=src python3 scripts/break_proofs_quality_wave.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
EA = ROOT / "src/intent_engine/executive/economic_architecture.py"
CQ = ROOT / "src/intent_engine/executive/competitive_qualification.py"
AS = ROOT / "src/intent_engine/executive/analysis_selection.py"
DS = ROOT / "src/intent_engine/executive/decision_synthesis.py"

TM = "tests/test_the_model_sentence_is_this_company.py"
TH = "tests/test_a_heading_is_not_a_competitor.py"
TA = "tests/test_the_adversary_reaches_a_reader.py"
TS = "tests/test_a_missing_snapshot_is_not_a_refusal.py"

PROOFS = [
    # --- Q1. the sentence is this company ---------------------------------
    Proof("Q1a. the class prior takes the sentence back",
          EA,
          "    if architecture.what_is_sold:\n        parts.append(architecture.what_is_sold)",
          "    if False:\n        parts.append(architecture.what_is_sold)",
          f"{TM}::test_each_sentence_carries_that_company_s_own_economics",
          "assert"),
    Proof("Q1b. a rival's filing describes the subject again",
          EA,
          "        if filer and filer.group(1).lstrip(\"0\") == digits:",
          "        if filer:",
          f"{TM}::test_a_rivals_filing_never_describes_the_subject",
          "assert"),
    Proof("Q1c. the segment count stops disambiguating the split",
          EA,
          "    tail = [_clean(x) for x in re.split(r\"\\s+and\\s+\", last, maxsplit=need)]",
          "    tail = [_clean(x) for x in re.split(r\"\\s+and\\s+\", last)]",
          f"{TM}::test_segments_use_the_count_the_filing_states",
          "assert"),
    # BOTH HALVES AT ONCE, because they are defence in depth and not two
    # guards. The verb list keeps "operate" out; the lookahead would refuse
    # "operate in ..." if it ever came back. Mutating either alone changes
    # no outcome and the harness says NOT_CAUGHT, correctly -- so the proof
    # removes the protection rather than half of it.
    Proof("Q1d. 'we operate in a market' is what we sell again",
          EA,
          "     r\"[Ww]e (?:sell|offer|provide|deliver|design|manufacture|produce)\\s\"\n"
          "     r\"(?!in\\s|under\\s|as\\s|through\\s|primarily in\\s)\"",
          "     r\"[Ww]e (?:sell|offer|provide|deliver|operate)\\s\"",
          f"{TM}::test_we_operate_in_a_market_is_not_what_a_company_sells",
          "assert"),
    Proof("Q1e. a company that says nothing loses its fallback",
          EA,
          "    if not parts and class_prior:\n        parts.append(class_prior)",
          "    if False:\n        parts.append(class_prior)",
          f"{TM}::test_the_class_prior_still_serves_a_company_that_says_nothing",
          "assert"),

    # --- Q2. a heading is not a competitor --------------------------------
    Proof("Q2a. the activity test is removed",
          CQ,
          "    if names_an_activity(name):\n"
          "        return ENTITY_CATEGORY, \"names an activity, not an actor\"",
          "    if False:\n"
          "        return ENTITY_CATEGORY, \"names an activity, not an actor\"",
          f"{TH}::test_the_live_defect_is_typed_as_a_category",
          "assert"),
    Proof("Q2b. the gerund floor is dropped and Li Ning is refused",
          CQ,
          "        floor = _MIN_GERUND if low.endswith(\"ing\") else _MIN_ABSTRACT",
          "        floor = 0",
          f"{TH}::test_a_real_firm_is_never_refused[Li Ning]",
          "assert"),
    Proof("Q2c. a corporate designator stops settling it",
          CQ,
          "    if not text or _DESIGNATOR.search(text):\n        return False",
          "    if not text:\n        return False",
          f"{TH}::test_a_corporate_designator_settles_it_immediately",
          "assert"),

    # --- Q3. the adversary reaches a reader -------------------------------
    Proof("Q3a. the manifest gate is restored",
          AS,
          "    if not selected:\n        selected = tuple(rivals or ())",
          "    if not selected:\n        selected = ()",
          f"{TA}::test_an_unmanifested_company_gets_an_adversary_from_its_filing",
          "assert"),
    Proof("Q3b. a placeholder adversary is invented",
          AS,
          "    if not selected:\n        return ()",
          "    if not selected:\n        selected = (type(\"R\", (), {\"name\": \"a rival\", \"why\": \"\"})(),)",
          f"{TA}::test_no_rival_from_either_source_invents_nothing",
          "assert"),

    # --- Q4. absence is not refusal ---------------------------------------
    Proof("Q4a. a missing snapshot refuses the whole reading again",
          DS,
          "    if availability not in (\"AVAILABLE\", \"STALE\") and not evidence:",
          "    if availability not in (\"AVAILABLE\", \"STALE\"):",
          f"{TS}::test_no_snapshot_published_is_not_a_refusal",
          "assert"),
    Proof("Q4b. a rejected snapshot stops being refused",
          DS,
          "    if availability == \"REFUSED\":\n        return REFUSED",
          "    if False:\n        return REFUSED",
          f"{TS}::test_a_published_snapshot_that_cannot_be_read_is_still_refused",
          "assert"),
    Proof("Q4c. an empty run is promoted out of its honest page",
          DS,
          "    if availability not in (\"AVAILABLE\", \"STALE\") and not evidence:",
          "    if False:",
          f"{TS}::test_a_run_with_no_evidence_keeps_the_page_it_had",
          "assert"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title=__doc__.splitlines()[0]))
