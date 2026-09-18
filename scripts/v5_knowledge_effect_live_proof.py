#!/usr/bin/env python3
"""Drive the knowledge-effect vertical through the REAL production path.

    PYTHONPATH=src python3 scripts/v5_knowledge_effect_live_proof.py --out F

WHAT IS AND IS NOT SYNTHETIC
-----------------------------
The EVIDENCE is synthetic and is marked so in the artifact. Nothing else is:
the producer, the semantic comparison, the persistence, the reload, the
conversion consumer and the eligibility gate are the production objects, and
a failure in any of them fails this proof.

That distinction is the whole point. The reasoning backend is credit-blocked,
so a live analysis cannot be run — but the seam that was MISSING is
deterministic engineering and can be proven now. What this cannot prove is
that a real analysis produces a real effect; that needs the backend, and the
artifact says so rather than implying otherwise.

WHY A PROCESS RESTART IS PART OF IT
------------------------------------
Idempotency held in memory is not idempotency. Every replay check below
re-reads the ledger from disk, and the last one re-execs the module in a
fresh interpreter so a cached in-process set cannot carry the result.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intent_engine.company_ingestion.learning_attribution import (  # noqa: E402
    CHANGING, conversion,
)
from intent_engine.external_intel import decision_impact as di  # noqa: E402
from intent_engine.external_intel import effect_producer as ep  # noqa: E402

CONTRACT = "knowledge_effect_live_proof.v1"


def _state(**fields):
    return {field: list(fields.get(field, ())) for field in di.IMPACT_TYPES}


def _cycle(root, *, company, analysis, after, evidence, **kwargs):
    """One production learning cycle: compare, produce, persist.

    Mirrors `WebApp._record_learning` exactly — compare against the prior
    BEFORE recording this revision, or every run compares against itself.
    """
    prior = di.load_revisions(root).get(company)
    impact = di.assess_against_prior(root, analysis_id=analysis,
                                     company_id=company, after=after,
                                     provenance=evidence)
    effects = ep.effects_from_impact(
        impact, evidence_ids=evidence,
        prior_company_id=str((prior or {}).get("company_id") or ""), **kwargs)
    written = ep.record_effects(root, effects)
    di.record_revision(root, company_id=company, state=after)
    return {"materiality": impact.materiality,
            "effects": [e.effect_type for e in effects],
            "new_rows": written}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    root = pathlib.Path(tempfile.mkdtemp(prefix="ke-live-proof-"))
    results = {}

    # 1. FIRST OBSERVATION — a baseline, not an improvement.
    results["first_observation"] = _cycle(
        root, company="acme", analysis="run-1",
        after=_state(RECOMMENDATION=("hold capacity",)),
        evidence=["obs-1"])

    # 2. IDENTICAL SECOND OBSERVATION — tested and unchanged.
    results["no_change"] = _cycle(
        root, company="acme", analysis="run-2",
        after=_state(RECOMMENDATION=("hold capacity",)),
        evidence=["obs-2"])

    # 3. WORDING ONLY — casing and a trailing full stop.
    results["wording_only"] = _cycle(
        root, company="acme", analysis="run-3",
        after=_state(RECOMMENDATION=("Hold capacity.",)),
        evidence=["obs-3"])

    # 4. MATERIAL CHANGE — the recommendation is replaced.
    results["material_change"] = _cycle(
        root, company="acme", analysis="run-4",
        after=_state(RECOMMENDATION=("expand capacity in ohio",)),
        evidence=["obs-4"])

    # 5. DUPLICATE REPLAY — the SAME comparison re-derived and re-recorded.
    #
    #    An earlier version ran another cycle here, which is a DIFFERENT
    #    comparison (the prior had moved on), so it appended legitimately and
    #    the check was meaningless. A replay has to replay.
    before_rows = len(ep.load_effects(root))
    replayed_impact = di.assess(
        analysis_id="run-4", company_id="acme",
        before=_state(RECOMMENDATION=("hold capacity",)),
        after=_state(RECOMMENDATION=("expand capacity in ohio",)),
        provenance=("obs-4",))
    results["duplicate_replay"] = {
        "new_rows": ep.record_effects(root, ep.effects_from_impact(
            replayed_impact, evidence_ids=["obs-4"])),
        "ledger_before": before_rows,
        "ledger_after": len(ep.load_effects(root))}

    # 6. NON-TESTABLE RE-READ — must not earn a confirmation.
    results["non_testable_reread"] = _cycle(
        root, company="acme", analysis="run-6",
        after=_state(RECOMMENDATION=("expand capacity in ohio",)),
        evidence=["obs-6"], testable=False)

    # 7. DIFFERENT EVIDENCE WINDOW — refused, not scored.
    results["incomparable_window"] = _cycle(
        root, company="acme", analysis="run-7",
        after=_state(RECOMMENDATION=("retrench",)),
        evidence=["obs-7"], comparability=di.UNKNOWN_WINDOW)

    # 8. CROSS-COMPANY — another company's prior may never grade this one.
    impact = di.assess(analysis_id="run-8", company_id="globex",
                       before=_state(RECOMMENDATION=("a",)),
                       after=_state(RECOMMENDATION=("b",)),
                       provenance=("obs-8",))
    results["cross_company_refusal"] = {
        "effects": [e.effect_type for e in ep.effects_from_impact(
            impact, evidence_ids=["obs-8"], prior_company_id="acme")]}

    # 9. THE CONSUMER, reading what was actually persisted.
    persisted = ep.load_effects(root, company_id="acme")
    measured = conversion(
        evidence_rows=[{"source_id": f"obs-{i}"} for i in range(1, 8)],
        effects=persisted, knowledge_layer_ran=True)
    results["conversion"] = {
        "attribution_state": measured["attribution_state"],
        "knowledge_effects": measured["knowledge_effects"],
        "effect_producing_evidence_rows":
            measured["effect_producing_evidence_rows"],
        "learning_conversion": measured["learning_conversion"],
        "effects_by_type": measured["effects_by_type"]}

    # 10. PROCESS RESTART — a fresh interpreter re-reads the ledger and must
    #     still append nothing.
    # Re-derives the SAME comparison as case 4 in a fresh interpreter. An
    # in-process set would pass the replay above and fail here.
    probe = (
        "import sys; sys.path.insert(0,'src');"
        "from intent_engine.external_intel import decision_impact as di,"
        " effect_producer as ep;"
        f"root=r'{root}';"
        "b={f:[] for f in di.IMPACT_TYPES};"
        "a={f:[] for f in di.IMPACT_TYPES};"
        "b['RECOMMENDATION']=['hold capacity'];"
        "a['RECOMMENDATION']=['expand capacity in ohio'];"
        "imp=di.assess(analysis_id='run-4',company_id='acme',before=b,"
        "after=a,provenance=['obs-4']);"
        "eff=ep.effects_from_impact(imp,evidence_ids=['obs-4']);"
        "print(ep.record_effects(root,eff))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=pathlib.Path(__file__).parent.parent,
                         env={**os.environ, "PYTHONPATH": "src"})
    results["process_restart"] = {
        "new_rows": (out.stdout.strip() or out.stderr.strip()[-200:]),
        "ledger_rows": len(ep.load_effects(root))}

    payload = {"contract": CONTRACT,
               "evidence": "SYNTHETIC — drives the production seam, never "
                           "stands in for a live analysis",
               "mocked": "none: producer, comparison, persistence, reload, "
                         "eligibility and consumer are production objects",
               "intelligence_baseline": "BLOCKED_EXTERNAL_CREDITS — this "
                                        "proof cannot show that a real "
                                        "analysis produces a real effect",
               "cases": results}

    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.out:
        target = pathlib.Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"\nwrote {target}")

    # The proof asserts on itself; a proof that only prints is a report.
    assert results["first_observation"]["effects"] == ["FIRST_OBSERVATION"]
    assert results["no_change"]["effects"] and \
        all(e == "NO_CHANGE" for e in results["no_change"]["effects"])
    assert not [e for e in results["wording_only"]["effects"]
                if e in CHANGING]
    assert [e for e in results["material_change"]["effects"] if e in CHANGING]
    assert results["duplicate_replay"]["new_rows"] == 0
    assert results["duplicate_replay"]["ledger_before"] == \
        results["duplicate_replay"]["ledger_after"]
    assert "NO_CHANGE" not in results["non_testable_reread"]["effects"]
    assert results["incomparable_window"]["effects"] == ["REFUSED"]
    assert results["cross_company_refusal"]["effects"] == ["REFUSED"]
    assert results["process_restart"]["new_rows"] == "0"
    assert results["conversion"]["attribution_state"] == "MEASURED"
    assert results["conversion"]["effect_producing_evidence_rows"] > 0
    print("\nALL LIVE PROOF ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
