#!/usr/bin/env python3
"""Break the ownership record deliberately.

The defect it exists for: `subject_cik` was unobservable after a run ended,
so "did this run have a CIK?" could not be answered and the run that would
have answered it was destroyed before the question was framed. Four deploys,
six wrong hypotheses.

Run:  PYTHONPATH=src python3 scripts/break_proofs_ownership_record.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
S = ROOT / "src/intent_engine/company_ingestion/service.py"
R = ROOT / "src/intent_engine/company_ingestion/records.py"
T = "tests/test_the_run_records_what_it_decided_about_ownership.py"

PROOFS = [
    ("A1. the run stops recording what it decided",
     S,
     "        if run_id:\n"
     "            owned = sum(1 for o in observations",
     "        if False:\n"
     "            owned = sum(1 for o in observations",
     f"{T}::test_a_composed_run_records_its_subject_cik",
     "recorded nothing about ownership"),

    ("A2. a run with no CIK is indistinguishable from an unrecorded one",
     S,
     '                payload={"subject_cik": subject_cik,\n'
     '                         "subject_cik_present": bool(subject_cik),',
     '                payload={"subject_cik": subject_cik or "unknown",\n'
     '                         "subject_cik_present": True,',
     f"{T}::test_a_run_with_no_cik_records_that_too",
     "assert"),

    ("A3. the event type leaves the vocabulary",
     R,
     '    "ci.ownership_resolved",',
     '    "ci.ownership_resolved_unused",',
     f"{T}::test_the_event_type_is_registered",
     "assert"),

    ("B1. the record is read from memory rather than the store",
     S,
     "            for row in self.store.for_run(run_id):\n"
     "                if row.event_type == \"ci.ownership_resolved\":\n"
     "                    return dict(row.payload)",
     "            return {}",
     f"{T}::test_the_record_survives_a_fresh_process",
     "KeyError"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
