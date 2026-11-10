#!/usr/bin/env python3
"""Break the Batch-5 executive read and bridge deliberately.

Load-bearing walls only, per §30: truth semantics, refusal routing, and the
standing->wording table. Field plumbing is not mutation-tested.

Run:  PYTHONPATH=src python3 scripts/v5_pre100_batch5_break_proofs.py
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "intent_engine"
E = "tests/test_the_executive_read_needs_no_model.py"
B = "tests/test_the_market_bridge_is_configured.py"

MUTATIONS = [
    # --- the standing -> wording table ---------------------------------
    ("an unknown standing reaches for the strongest wording",
     SRC / "executive/decision_synthesis.py",
     '    return _VERB.get(str(standing), _VERB[REFUSED])',
     '    return _VERB.get(str(standing), _VERB[SUPPORTED])',
     f"{E}::"
     "test_an_unknown_standing_gets_the_weakest_wording_not_the_strongest"),

    ("evidence with no belief over it becomes a supported reading",
     SRC / "executive/decision_synthesis.py",
     "    if not beliefs:\n"
     "        # Documents without a belief over them: the engine holds no "
     "position,",
     "    if False:\n"
     "        # Documents without a belief over them: the engine holds no "
     "position,",
     f"{E}::test_an_answered_causal_question_still_needs_a_belief_to_be_supported"),

    ("a refused causal question stops holding the reading back",
     SRC / "executive/decision_synthesis.py",
     '    if causal.get("is_refusal") or not _ran(dossier, "causal_results"):\n'
     "        return BOUNDED",
     '    if False:\n'
     "        return BOUNDED",
     f"{E}::test_a_refused_causal_question_holds_the_reading_at_bounded"),

    # THE NEGATIVE CONTROL. A gate that never passes looks identical to one
    # that always refuses, so the passing path is proven too.
    ("the standing gate refuses even an answered causal question",
     SRC / "executive/decision_synthesis.py",
     '    return SUPPORTED if causal.get("count") else BOUNDED',
     "    return BOUNDED",
     f"{E}::test_an_answered_causal_question_can_reach_supported"),

    # --- refusal routing (§9) -------------------------------------------
    ("PANEL_UNAVAILABLE dead-ends instead of routing to a next move",
     SRC / "executive/decision_synthesis.py",
     '    if causal_status != "CAUSAL_UNMEASURABLE":\n'
     "        return (), (), (), ()",
     "    if True:\n"
     "        return (), (), (), ()",
     f"{E}::test_panel_unavailable_is_routed_not_dead_ended"),

    ("a refusal is reported as the subsystem never running",
     SRC / "executive/decision_synthesis.py",
     '    if block.get("is_refusal"):',
     "    if False:",
     f"{E}::"
     "test_a_causal_refusal_is_never_reported_as_the_subsystem_not_running"),

    # The other negative control: the router must not invent a gap for a
    # company that never asked a causal question.
    ("the router invents an information gap for everybody",
     SRC / "executive/decision_synthesis.py",
     "        return (), (), (), ()",
     '        return ("No comparable control panel exists",), (), (), ()',
     f"{E}::test_a_company_with_no_refusal_gets_no_invented_gap"),

    # --- the no-risk wall ------------------------------------------------
    ("the composer is allowed to claim no risk",
     SRC / "executive/decision_synthesis.py",
     '        if phrase in low:',
     "        if False:",
     f"{E}::test_the_composer_refuses_to_emit_a_no_risk_claim"),

    # --- what changed ----------------------------------------------------
    ("an identical second reading reports a change",
     SRC / "executive/decision_synthesis.py",
     "    if not changes:\n"
     '        return ("Nothing in the published market record changed since '
     'the "',
     "    if False:\n"
     '        return ("Nothing in the published market record changed since '
     'the "',
     f"{E}::test_an_identical_second_reading_reports_no_change"),

    # --- the bridge (§30) -------------------------------------------------
    ("an unconfigured MARKET_SNAPSHOT_ROOT reads as current",
     SRC / "demo_dossier/bridge.py",
     "    if resolved is None:\n"
     "        return BridgeAssessment(\n"
     "            MISSING, configured=False,",
     "    if resolved is None:\n"
     "        return BridgeAssessment(\n"
     "            CURRENT, configured=False,",
     f"{B}::test_an_unconfigured_bridge_is_missing_and_says_so"),

    ("a stale snapshot is served as current",
     SRC / "demo_dossier/bridge.py",
     "    if snapshot.availability == V.STALE:",
     "    if False:",
     f"{B}::test_an_old_snapshot_is_stale_and_still_readable"),

    ("a snapshot filed under another company is joined anyway",
     SRC / "demo_dossier/bridge.py",
     "    if snapshot.availability in (V.REFUSED, V.INCOMPATIBLE):",
     "    if False:",
     f"{B}::test_a_snapshot_filed_under_another_company_is_invalid"),

    ("an unrecognised causal state is read as an estimate",
     SRC / "demo_dossier/vocabulary.py",
     "    return not is_causal_estimate(state)",
     "    return False",
     f"{B}::"
     "test_an_unrecognised_state_degrades_to_refusal_never_to_an_estimate"),
]

PY = sys.executable


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, text):
    p.write_text(text, encoding="utf-8")
    os.utime(p, (time.time() + 1, time.time() + 1))
    for cache in ROOT.rglob("__pycache__"):
        for f in cache.glob("*.pyc"):
            f.unlink(missing_ok=True)


def run_test(node):
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": "src",
           "HOME": str(pathlib.Path.home())}
    r = subprocess.run([PY, "-m", "pytest", node, "-q", "--no-header", "-x"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    out = (r.stdout or "") + (r.stderr or "")
    failed = " failed" in out or "FAILED" in out
    errored = " error" in out.lower() and not failed
    ran = "passed" in out or failed or errored
    return failed, (errored or not ran), out.strip().splitlines()[-1:]


def main():
    results = []
    for name, path, find, repl, node in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        before = sha(path)
        pre_failed, pre_bad, pre_tail = run_test(node)
        if pre_failed or pre_bad:
            results.append(("INVALID_NOT_GREEN_FIRST", name, node, pre_tail))
            continue
        if find not in original:
            results.append(("NO_OP_TARGET_MISSING", name, node,
                            ["the mutation target was not found"]))
            continue
        write(path, original.replace(find, repl, 1))
        try:
            if sha(path) == before:
                results.append(("NO_OP_HASH_UNCHANGED", name, node, []))
                continue
            failed, errored, tail = run_test(node)
            results.append((("CAUGHT" if failed else
                             "ERRORED_NOT_FAILED" if errored else
                             "NOT_CAUGHT"), name, node, tail))
        finally:
            write(path, original)
            assert sha(path) == before, f"restore was not exact for {path}"

    width = max(len(r[0]) for r in results)
    caught = sum(1 for r in results if r[0] == "CAUGHT")
    print(f"\n{'=' * 78}\nV5 PRE-100 BATCH-5 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
