#!/usr/bin/env python3
"""Break the model-class registry deliberately.

The defect this defends against is not "a wrong pattern fired". It is that a
business-model class added tomorrow is invisible to every table keyed on
model class, because those tables gate by EXCLUSION and a denylist cannot
exclude something that does not exist yet.

Measured: three classes added one cycle ago qualified for 12 of 12 patterns
while every older class was filtered to 5-11, and Meta, Caterpillar and Exxon
answered nine of ten live board questions with the same semiconductor
capacity thesis.

Run:  PYTHONPATH=src python3 scripts/break_proofs_model_registry.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CP = ROOT / "src/intent_engine/executive/company_profile.py"
REC = ROOT / "src/intent_engine/strategic_intelligence/records.py"
PAT = ROOT / "src/intent_engine/strategic_intelligence/patterns.py"
SR = ROOT / "src/intent_engine/executive/strategic_read.py"
T = "tests/test_a_model_class_registry.py"

PROOFS = [
    # --- the registry goes stale again ------------------------------------
    ("A1. the registry loses the classes added last cycle",
     CP,
     '    "ADVERTISING_PLATFORM",\n    "MULTI_ENGINE_PLATFORM",\n'
     '    "SCALE_RETAIL",\n)',
     ")",
     f"{T}::test_the_registry_holds_every_class_the_classifier_can_produce",
     "unregistered"),

    ("A2. the completeness helper reports nothing missing",
     CP,
     "    have = set(keys or ())\n"
     "    return [c for c in MODEL_CLASSES if c not in have]",
     "    have = set(keys or ())\n"
     "    return []",
     f"{T}::test_missing_model_classes_reports_in_registry_order",
     "assert"),

    # --- applicability goes back to being a denylist ----------------------
    ("B1. a pattern is offered for a class it never considered",
     REC,
     "        considered = tuple(self.considered_model_classes or ())\n"
     "        return model in considered if considered else True",
     "        return True",
     f"{T}::test_a_pattern_is_not_offered_for_a_class_it_never_considered",
     "applies_to_model"),

    ("B2. an exclusion stops winning over consideration",
     REC,
     "        if model in tuple(self.excluded_model_classes or ()):\n"
     "            return False",
     "        if False:\n"
     "            return False",
     f"{T}::test_an_exclusion_still_wins_over_consideration",
     "applies_to_model"),

    ("B3. patterns_for reads the denylist again",
     PAT,
     "    return [p for p in library if p.applies_to_model(model)]",
     "    return [p for p in library\n"
     "            if model not in tuple(getattr(p, "
     "\"excluded_model_classes\", ()))]",
     f"{T}::test_a_class_added_tomorrow_does_not_inherit_the_whole_library",
     "denylist again"),

    ("B4. a pattern stops ruling on one of the registered classes",
     PAT,
     'considered_model_classes=(\n            "SUBSCRIPTION_SOFTWARE",',
     'considered_model_classes=(\n',
     f"{T}::test_every_pattern_has_considered_every_registered_class",
     "not ruled on"),

    # --- the tables drift again -------------------------------------------
    ("C1. the metrics table loses the three classes",
     SR,
     '_METRICS = {\n    "ADVERTISING_PLATFORM": (',
     '_METRICS = {\n    "ADVERTISING_PLATFORM_UNUSED": (',
     f"{T}::test_every_model_keyed_table_covers_the_registry"
     "[strategic_read._METRICS]",
     "no entry for"),

    ("C2. the ladder's model alternatives lose a class",
     ROOT / "src/intent_engine/executive/competitive_ground.py",
     '    "SCALE_RETAIL": (',
     '    "SCALE_RETAIL_UNUSED": (',
     f"{T}::test_every_model_keyed_table_covers_the_registry"
     "[competitive_ground._MODEL_ALTERNATIVES]",
     "no entry for"),

    # --- the opposite overreach -------------------------------------------
    ("D1. a class is filtered down to no readings at all",
     REC,
     "        if not model or model == \"UNKNOWN\":\n            return True",
     "        if not model or model == \"UNKNOWN\":\n            return False",
     f"{T}::test_an_unclassified_company_still_gets_the_whole_library",
     "assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=f"model-class registry: {len(PROOFS)} proofs"))
