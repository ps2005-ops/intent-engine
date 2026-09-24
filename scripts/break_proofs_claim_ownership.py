#!/usr/bin/env python3
"""Break the "whose claim is this" rule deliberately.

The defect: a signal detected in another registrant's filing was rendered as
the subject's own business model. Measured live on 0420fb0 — Wells Fargo's
capacity sentence under JPMorgan's "Distribution model".

Run:  PYTHONPATH=src python3 scripts/break_proofs_claim_ownership.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
M = ROOT / "src/intent_engine/strategic_intelligence/model.py"
O = ROOT / "src/intent_engine/strategic_intelligence/observations.py"

T = "tests/test_a_rivals_filing_is_not_our_business_model.py"
T2 = "tests/test_the_pattern_gate_is_told_who_the_company_is.py"
T3 = "tests/test_strategic_intelligence.py"

PROOFS = [
    ("A1. support goes back to every observation, whoever wrote it",
     M,
     "            for o in own_by_signal.get(s, []):",
     "            for o in by_signal.get(s, []):",
     f"{T}::test_a_third_partys_filing_cannot_state_our_distribution_model",
     "committing capital to capacity"),

    ("A2. an independent class is treated as the subject's own voice",
     M,
     "        own = (getattr(o, \"subject_owned\", True)\n"
     "               and (o.source_class or \"company_owned\") "
     "in speaks_for_subject)",
     "        own = True",
     f"{T}::test_provenance_never_names_another_registrant",
     "assert"),

    ("A3. contradiction is silenced along with support",
     M,
     "            for o in by_signal.get(s, []):\n"
     "                if o.observation_id not in cseen:",
     "            for o in own_by_signal.get(s, []):\n"
     "                if o.observation_id not in cseen:",
     f"{T}::test_the_independent_observation_may_still_contradict",
     "assert"),

    ("B1. the allowlist is hand-written instead of derived",
     O,
     "    return tuple(c for c in SOURCE_CLASSES if c not in "
     "INDEPENDENT_CLASSES)",
     "    return (\"company_owned\", \"executive_statement\", "
     "\"investor_material\", \"competitor\")",
     f"{T}::test_the_allowlist_is_derived_from_the_vocabulary_not_written_out",
     "assert"),

    ("B2. a filing under another registrant's CIK is accepted as ours",
     O,
     "        if subject and \"/data/\" in url and "
     "f\"/data/{subject}/\" not in url:",
     "        if False:",
     f"{T}::test_a_filing_under_another_cik_is_not_ours",
     "assert"),

    ("B3. an unrecognised source class is read as the subject's voice",
     O,
     "        if source_class and source_class not in allowed:",
     "        if False:",
     f"{T2}::test_an_unrecognised_source_class_fails_closed",
     "assert"),

    # --- D: the class gate alone shipped inert; ownership must be carried
    ("D1. the model decides ownership from source_class alone again",
     M,
     "        own = (getattr(o, \"subject_owned\", True)\n"
     "               and (o.source_class or \"company_owned\") "
     "in speaks_for_subject)",
     "        own = (o.source_class or \"company_owned\") "
     "in speaks_for_subject",
     f"{T}::test_a_third_party_filing_cannot_state_the_model_even_as_"
     "investor_material",
     "stating this company's business model"),

    ("D2. the producer stops deciding ownership from the URL",
     O,
     "            subject_owned=_document_url(doc) in owned_urls,",
     "            subject_owned=True,",
     f"{T}::test_another_registrants_filing_is_not_subject_owned",
     "marked as this company's own"),

    ("D3. the owned set is built without the subject's CIK",
     O,
     "    owned_urls = {_document_url(d)\n"
     "                  for d in subject_documents(documents,\n"
     "                                             subject_cik=subject_cik)}",
     "    owned_urls = {_document_url(d) for d in documents}",
     f"{T}::test_another_registrants_filing_is_not_subject_owned",
     "marked as this company's own"),

    ("E1. the mechanism evidence stops checking whose document it is",
     ROOT / "src/intent_engine/strategic_intelligence/reasoning.py",
     "            if not getattr(observation, \"subject_owned\", True):\n"
     "                continue",
     "            if False:\n                continue",
     f"{T}::test_a_third_partys_sentence_is_never_the_companys_own_words",
     "became the company's own"),

    # The repair must not re-create the failure it replaced.
    ("C1. observations are narrowed again, starving cross-source coverage",
     O,
     "                        subject_only: bool = False) -> list:",
     "                        subject_only: bool = True) -> list:",
     f"{T3}::test_live_pipeline_reaches_complete_multi_class",
     "customer_voice"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
