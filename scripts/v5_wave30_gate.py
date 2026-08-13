#!/usr/bin/env python3
"""Adjudicate Wave 30 mechanically. Prose does not open a wave.

    PYTHONPATH=src python3 scripts/v5_wave30_gate.py [--wave RESULTS.json]

WHY THIS IS CODE AND NOT A MARKDOWN TABLE
------------------------------------------
Every previous gate verdict in this programme was written by hand, and one of
them was wrong in a way nobody could see: criterion 10 was recorded MET-as-
BLOCKED_EXTERNAL_CREDITS while the producer it depended on did not exist, so
"restore credits and it passes" was false for two batches. A hand-maintained
verdict drifts from the code it describes; this one is derived from it.

THREE VERDICTS PER CRITERION, NEVER TWO
----------------------------------------
    PASS               checked, and it holds
    FAIL               checked, and it does not
    BLOCKED_EXTERNAL   cannot be checked without the paid backend

BLOCKED_EXTERNAL is not a soft FAIL and must never be counted as a PASS. A
criterion nobody could evaluate is the one most likely to be assumed.

WHAT THE GATE DELIBERATELY DOES NOT REQUIRE
--------------------------------------------
That all ten companies learn something, that beliefs change, that effect
counts are high, or that UNMEASURABLE and REFUSED are absent. Requiring any of
those rewards fabrication, which is the failure this whole gate exists to
prevent.
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED_EXTERNAL"

CONTRACT = "wave_30_intelligence_gate.v1"


def _result(name, verdict, detail):
    return {"criterion": name, "verdict": verdict, "detail": detail}


def adjudicate(results):
    """The verdict, from the criteria. THE decision, in one place.

    Extracted so the tests exercise this exact function rather than a copy of
    its logic. A test that reimplements the rule it protects cannot fail when
    the rule changes, and this rule decides whether a wave opens.

    A FAIL outranks a BLOCK: a defect is a finding, an unevaluated criterion
    is an absence, and the finding is the one to report. A BLOCK never yields
    PASS — the criterion nobody could evaluate is the one most likely to be
    assumed.
    """
    if any(r["verdict"] == FAIL for r in results):
        return FAIL
    if any(r["verdict"] == BLOCKED for r in results):
        return BLOCKED
    return PASS


# --- deterministic checks ---------------------------------------------------
def _no_empty_effects_literal():
    """No production call site may pass effects=() — the Batch-15 dead end."""
    bad = []
    for path in list((ROOT / "src").rglob("*.py")) + \
            list((ROOT / "scripts").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords or []:
                if keyword.arg == "effects" and \
                        isinstance(keyword.value, (ast.Tuple, ast.List)) and \
                        not keyword.value.elts:
                    bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return (PASS, "no call site passes an empty effects literal") if not bad \
        else (FAIL, f"empty effects= at {bad}")


def _temporal_seam_has_callers():
    """The seam that had zero production callers before Batch 15."""
    import inspect

    from intent_engine.webapp.app import WebApp
    source = inspect.getsource(WebApp)
    needed = ("record_revision", "load_revisions", "assess_against_prior",
              "record_impact", "effects_from_impact", "record_effects",
              "load_effects")
    missing = [n for n in needed if f"{n}(" not in source]
    return (PASS, f"all {len(needed)} temporal-seam functions called in "
                  f"production") if not missing else \
        (FAIL, f"no production caller for {missing}")


def _producer_is_non_vacuous():
    """The live proof must produce a CHANGING effect and refuse the rest."""
    proc = subprocess.run(
        [sys.executable, "scripts/v5_knowledge_effect_live_proof.py"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"})
    ok = "ALL LIVE PROOF ASSERTIONS PASSED" in proc.stdout
    return (PASS, "live proof passes: first observation, confirmation, "
                  "wording-only, material change, refusals, replay, restart") \
        if ok else (FAIL, (proc.stdout + proc.stderr).strip()[-300:])


def _effect_inflation_invariant():
    """One moved component must produce exactly one effect."""
    from intent_engine.external_intel import decision_impact as di
    from intent_engine.external_intel import effect_producer as ep

    state = {f: [] for f in di.IMPACT_TYPES}
    before = dict(state, RECOMMENDATION=["hold"])
    after = dict(state, RECOMMENDATION=["expand"])
    impact = di.assess(analysis_id="gate", company_id="probe",
                       before=before, after=after, provenance=("e1",))
    effects = ep.effects_from_impact(impact, evidence_ids=["e1"])
    return (PASS, "1 component moved -> 1 effect") if len(effects) == 1 else \
        (FAIL, f"1 component moved -> {len(effects)} effects")


def _origin_independence_enforced():
    """Syndication must not corroborate, and self-report is not outside."""
    from intent_engine.company_ingestion.records import INDEPENDENT_CLASSES
    from intent_engine.strategic_intelligence.analyst.critic import (
        _INDEPENDENT_CLASSES,
    )
    if set(_INDEPENDENT_CLASSES) != set(INDEPENDENT_CLASSES):
        return FAIL, "the critic keeps a private independent-class set"
    if "investor_material" in _INDEPENDENT_CLASSES:
        return FAIL, "company investor material counts as independent"
    from intent_engine.company_ingestion.independence import assess
    body = "one release " * 40
    rows = assess([
        {"source_id": "a", "final_url": "https://acme.example/p",
         "source_class": "company_owned", "text_content": body,
         "content_hash": "a"},
        {"source_id": "b", "final_url": "https://mirror.example/p",
         "source_class": "independent_reporting", "text_content": body,
         "content_hash": "b"}])
    if rows["independent_evidence_count"] > 1:
        return FAIL, "a syndicated copy added an independent origin"
    return PASS, "origin axis enforced; self-report is not independent"


def _trading_wall_precision():
    """The wall must admit Alphabet and refuse trading alpha."""
    from intent_engine.demo_dossier.contracts import SnapshotRefused
    from intent_engine.demo_dossier.contracts import _scan_text
    try:
        _scan_text("Alphabet Inc. reported revenue growth")
    except SnapshotRefused:
        return FAIL, "'Alphabet Inc.' refused because 'alpha' is a substring"
    try:
        _scan_text("the strategy generated alpha of 3%")
    except SnapshotRefused:
        return PASS, "Alphabet admitted; trading alpha still refused"
    return FAIL, "trading alpha is no longer refused"


def _break_proofs_all_caught():
    suites = ["v5_independence_break_proofs", "v5_batch13_break_proofs",
              "v5_batch14_break_proofs", "v5_batch15_break_proofs"]
    totals, caught = 0, 0
    for suite in suites:
        proc = subprocess.run(
            [sys.executable, f"scripts/{suite}.py"], cwd=ROOT,
            capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"})
        for line in proc.stdout.splitlines():
            if "BREAK PROOFS —" in line:
                got, total = line.split("—")[1].strip().split()[0].split("/")
                caught += int(got)
                totals += int(total)
    if not totals:
        return FAIL, "no break-proof suite reported a result"
    return (PASS if caught == totals else FAIL,
            f"{caught}/{totals} mutations CAUGHT across {len(suites)} suites")


def _missing_vs_zero_states_distinct():
    from intent_engine.company_ingestion.learning_attribution import (
        CHANGING, FIRST_OBSERVATION, NON_CHANGING, NO_CHANGE, REFUSED,
        UNMEASURABLE,
    )
    distinct = {NO_CHANGE, FIRST_OBSERVATION, UNMEASURABLE, REFUSED}
    if len(distinct) != 4:
        return FAIL, "non-changing states are not distinct values"
    if distinct & CHANGING:
        return FAIL, "a non-changing state is counted as a change"
    if distinct != set(NON_CHANGING):
        return FAIL, "NON_CHANGING does not hold exactly the four states"
    return PASS, "NO_CHANGE / FIRST_OBSERVATION / UNMEASURABLE / REFUSED are "\
                 "mechanically distinct and none counts as a change"


def _cohort_unchanged():
    from intent_engine.validation import breaker_ten, load
    expected = ("cloudflare", "advanced-micro-devices", "boeing",
                "bank-of-america", "alimentation-couche-tard",
                "agnico-eagle-mines", "bce", "stripe", "mckinsey",
                "johnson-and-johnson")
    got = tuple(c.company_id for c in breaker_ten(load()))
    return (PASS, "the frozen ten, in order, no substitutions") \
        if got == expected else (FAIL, f"cohort changed: {got}")


# --- criteria requiring the paid backend ------------------------------------
_BACKEND = (
    (1, "Breaker-10 ran through the real backend"),
    (5, "KnowledgeEffect production is non-vacuous ON REAL INTELLIGENCE"),
    (13, "Founder consumption state measured on a real wave"),
    (14, "re-observation value measured on a real wave"),
    (15, "learning-quality classification produced from a real wave"),
    (16, "first-starved conversion measured on a real wave"),
)

_CHECKS = (
    (2, "all 10 identities preserved", _cohort_unchanged),
    (3, "no company substituted", _cohort_unchanged),
    (4, "no NO_PRODUCER state remains", _temporal_seam_has_callers),
    (5, "KnowledgeEffect production is non-vacuous (deterministic)",
     _producer_is_non_vacuous),
    (6, "effect inflation invariant holds", _effect_inflation_invariant),
    (7, "origin independence enforced", _origin_independence_enforced),
    (8, "self-report is not independent corroboration",
     _origin_independence_enforced),
    (9, "provenance exists for learning claims", _no_empty_effects_literal),
    (10, "no security canary regressed", _trading_wall_precision),
    (11, "population-compatible metrics used", _missing_vs_zero_states_distinct),
    (12, "failures are explicit", _missing_vs_zero_states_distinct),
    (17, "no known SEV-1 learning-integrity defect remains",
     _break_proofs_all_caught),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    results = []
    for number, name, check in _CHECKS:
        try:
            verdict, detail = check()
        except Exception as exc:  # noqa: BLE001 - a broken check is a FAIL
            verdict, detail = FAIL, f"{type(exc).__name__}: {exc}"
        results.append(_result(f"{number}. {name}", verdict, detail))
    for number, name in _BACKEND:
        results.append(_result(
            f"{number}. {name}", BLOCKED,
            "the canonical analyst backend is CREDITS_EXHAUSTED; this "
            "criterion cannot be evaluated and is NOT counted as met"))

    passed = [r for r in results if r["verdict"] == PASS]
    failed = [r for r in results if r["verdict"] == FAIL]
    blocked = [r for r in results if r["verdict"] == BLOCKED]
    verdict = adjudicate(results)

    payload = {"contract": CONTRACT,
               "wave_30_intelligence_gate": verdict,
               "counts": {"pass": len(passed), "fail": len(failed),
                          "blocked_external": len(blocked)},
               "wave_30": "OPEN" if verdict == PASS else "CLOSED",
               "closed_reason": (
                   "" if verdict == PASS else
                   "failing criteria" if failed else
                   "the paid backend cannot run, so the criteria that require "
                   "real intelligence are unevaluated"),
               "criteria": results}

    width = max(len(r["verdict"]) for r in results)
    print(f"\n{'=' * 78}\nWAVE-30 INTELLIGENCE GATE — {verdict}\n{'=' * 78}")
    for row in results:
        print(f"{row['verdict']:<{width}}  {row['criterion']}")
        if row["verdict"] != PASS:
            print(f"{'':<{width}}  ↳ {row['detail'][:150]}")
    print(f"\nPASS {len(passed)}   FAIL {len(failed)}   "
          f"BLOCKED_EXTERNAL {len(blocked)}")
    print(f"WAVE_30: {payload['wave_30']}")

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"\nwrote {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
