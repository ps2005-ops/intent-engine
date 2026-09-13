#!/usr/bin/env python3
"""Break the confirmed-pick CIK wiring deliberately.

The defect: `/analyze` assigned the confirmed CIK in an `elif` under the
domain branch, so every filer with BOTH — which is every large filer — opened
with no CIK, and every downstream ownership test had nothing to compare
against. Green tests, a passing real-EDGAR probe, and three deploys with an
unchanged page.

Run:  PYTHONPATH=src python3 scripts/break_proofs_confirmed_cik.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
A = ROOT / "src/intent_engine/webapp/app.py"
T = "tests/test_a_confirmed_pick_carries_its_cik.py"

PROOFS = [
    ("A1. the CIK goes back under the domain branch as an elif",
     A,
     "            if picked_cik:",
     "            elif picked_cik:",
     f"{T}::test_the_cik_is_not_assigned_inside_the_domain_branchs_else",
     "opens with no CIK"),

    ("A3. the confirmed CIK is dropped entirely rather than moved",
     A,
     "            if picked_cik:\n"
     "                # A CONFIRMED PICK CARRIES BOTH",
     "            if False:\n"
     "                # A CONFIRMED PICK CARRIES BOTH",
     f"{T}::test_the_cik_is_assigned_at_all",
     "never carried into the run"),

    ("A2. the run stops being opened with a CIK at all",
     A,
     "                    website=website, cik=filer_cik,",
     "                    website=website,",
     f"{T}::test_the_run_is_opened_with_both",
     "without a CIK at all"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
