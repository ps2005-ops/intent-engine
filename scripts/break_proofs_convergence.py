"""Six proofs for the PRE-100 convergence wave. §14: load-bearing only.

Each mutation is the SPECIFIC WAY the seam was broken in production, not a
cosmetic edit near it — because the failures this wave repaired were all of
one kind: a repair that was correct in isolation and unreachable in place.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

APP = ROOT / "src/intent_engine/webapp/app.py"
DS = ROOT / "src/intent_engine/executive/decision_synthesis.py"
SR = ROOT / "src/intent_engine/executive/strategic_read.py"
IH = ROOT / "src/intent_engine/executive/impossible_hypothesis.py"
CQ = ROOT / "src/intent_engine/executive/competitive_qualification.py"
EA = ROOT / "src/intent_engine/executive/economic_architecture.py"

T = "tests/test_pre100_convergence_wave.py"

PROOFS = [
    # A. bypass company-specific EconomicArchitecture -> specificity RED
    Proof("A. the segment engines collapse to one business again",
          EA,
          "        found.update({k: v for k, v in _engines(text, segments)"
          ".items() if v})",
          "        found.update({})",
          f"{T}::test_a_multi_engine_filer_keeps_its_engines_apart",
          "assert"),

    # B. adversary dropped at the projection seam -> adversary RED
    Proof("B. the adversary stops reaching the canonical read",
          SR,
          "        adversary=tuple(_adversary_row(m)\n"
          "                        for m in (selection.adversary or ())),",
          "        adversary=(),",
          f"{T}::test_compose_puts_the_adversary_on_the_read",
          "assert"),

    # C. impossible hypothesis dropped -> quality RED
    Proof("C. the heresies stop being produced",
          SR,
          "        impossible_hypotheses=tuple(\n"
          "            h.as_dict() for h in hypotheses_for(\n"
          "                name, architecture, rivals=_rivals, "
          "market_belief=_belief)),",
          "        impossible_hypotheses=(),",
          f"{T}::test_compose_puts_the_heresies_on_the_read",
          "assert"),

    # D. Q&A routed to the market-only refusal producer -> Q&A RED
    Proof("D. the run's own evidence stops reaching the standing",
          APP,
          "                evidence_ids=_evidence_ids,",
          "",
          f"{T}::test_the_call_site_supplies_the_runs_evidence_ids",
          "assert"),
    Proof("D4. a dossier with no market snapshot is a market reading again",
          APP,
          "            if str((getattr(dossier, \"market_block\", None) or {})\n"
          "                   .get(\"availability\") or \"\") not in "
          "(\"AVAILABLE\", \"STALE\"):\n"
          "                market, usable = None, False",
          "            if False:\n                market, usable = None, False",
          f"{T}::"
          "test_the_contract_is_not_told_a_market_reading_exists_without_one",
          "assert"),
    Proof("D2. absence is inferred as refusal again, off the market block",
          DS,
          "    if availability not in (\"AVAILABLE\", \"STALE\") and not "
          "has_own_evidence:",
          "    if availability not in (\"AVAILABLE\", \"STALE\"):",
          f"{T}::test_a_run_with_its_own_evidence_is_not_refused",
          "assert"),
    Proof("D3. the reading's denominator becomes the market's again",
          DS,
          "    if not evidence and not has_own_evidence:",
          "    if not evidence:",
          f"{T}::test_a_run_with_its_own_evidence_is_not_unmeasurable_either",
          "assert"),

    # E. CATEGORY_OR_PRACTICE allowed as a direct rival -> competitor RED
    Proof("E. a filing heading is a company again",
          CQ,
          "    if names_a_measure(_bare):\n        return ENTITY_CATEGORY, "
          "\"names a financial measure, not an actor\"",
          "    if False:\n        return ENTITY_CATEGORY, \"x\"",
          f"{T}::test_a_heading_measure_rule_or_index_is_not_a_company"
          "[Net Interest Income]",
          "typed as a company"),
    # THE ACRONYM TEST AND THE CORPORATE-TAIL TEST ARE DEFENCE IN DEPTH:
    # measured, either alone saves "ASML Holding", so mutating one is a no-op
    # and a proof against it can only ever report NOT_CAUGHT. The single
    # load-bearing decision is the VOCABULARY -- which word counts as naming
    # a process -- so that is what this mutates, back to the suffix wall it
    # replaced.
    Proof("E2. the suffix wall returns and refuses real firms again",
          CQ,
          "    return sum(1 for word in words if word.lower() in "
          "_PROCESS_WORD)",
          "    return sum(1 for word in words\n"
          "               if word.lower() in _PROCESS_WORD\n"
          "               or (len(word) >= 6 and word.lower()\n"
          "                   .endswith((\"ing\", \"tion\", \"ance\"))))",
          f"{T}::test_a_real_firm_is_never_reduced_to_a_thing"
          "[Ping An Insurance]",
          "refused as"),

    # F. multi-engine company flattened to one engine -> multi-engine RED
    Proof("F. a company nothing was read from gets a heresy anyway",
          IH,
          "        if architecture is None or not architecture.measured:",
          "        if architecture is None:",
          f"{T}::"
          "test_an_unreadable_company_gets_no_heresy_rather_than_a_generic_one",
          "assert"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title=__doc__.splitlines()[0]))
