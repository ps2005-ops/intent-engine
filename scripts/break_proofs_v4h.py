"""Break proofs for I-ACC-001: the seven derived learning channels.

Every proof attacks one way this layer can be made to look healthy while the
engine knows nothing more than it did. The list is the one the node's
acceptance names, and each entry is a SUBSTITUTION — a wrong quantity swapped
for the right one — because that is how a learning metric fails in practice.
It does not crash; it answers a different question convincingly.

Two of the listed attacks are recorded as NOT_BUILT rather than faked, with
the reason attached. A proof that passes because the code path does not exist
is the "test that cannot fail" this project has already found once.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"
LA = f"{T}/test_market_learning_acceleration_channels.py"
LAX = f"{T}/test_market_learning_acceleration.py"
KS = f"{T}/test_market_knowledge_step.py"

PROOFS = [
    # --- 1. raw volume counted as knowledge ----------------------------
    ("1. accepted evidence rows are counted as economic gain",
     S / "learning_acceleration.py",
     '    effects = [r for r in _rows(ledger, "knowledge_effect")\n'
     '               if r.get("target_type") in ECONOMIC_TARGETS]',
     '    effects = [r for r in _rows(ledger, "evidence")]',
     f"{LA}::test_accepted_evidence_is_not_economic_gain"),

    # --- 2. NO_CHANGE counted as gain ----------------------------------
    ("2. NO_CHANGE is counted as a state change",
     S / "learning_acceleration.py",
     '    changed = [e for e in effects\n'
     '               if str(e.get("effect_type")) in CHANGING_EFFECTS]\n'
     '    discriminating',
     '    changed = list(effects)\n'
     '    discriminating',
     f"{LA}::test_no_change_is_never_counted_as_gain"),

    # --- 3. system capability counted as economic gain -----------------
    ("3. engineering work is admitted to the economic channel",
     S / "learning_acceleration.py",
     'ECONOMIC_TARGETS = frozenset({\n'
     '    "EVENT", "BELIEF", "EXPECTATION", "CAUSAL_NODE", "CAUSAL_EDGE",\n'
     '    "MECHANISM", "HYPOTHESIS", "THESIS", "HIDDEN_STATE", "RELATIONSHIP",\n'
     '    "FALSIFIER", "COUNTERFACTUAL", "ECONOMIC_STATE", "COMPANY_EXPOSURE"})',
     'ECONOMIC_TARGETS = frozenset({\n'
     '    "EVENT", "BELIEF", "EXPECTATION", "CAUSAL_NODE", "CAUSAL_EDGE",\n'
     '    "MECHANISM", "HYPOTHESIS", "THESIS", "HIDDEN_STATE", "RELATIONSHIP",\n'
     '    "FALSIFIER", "COUNTERFACTUAL", "ECONOMIC_STATE", "COMPANY_EXPOSURE",\n'
     '    "FOUNDER_DECISION_COMPONENT", "RESEARCH_QUESTION"})',
     f"{LA}::test_founder_and_research_targets_are_not_economic_objects"),

    # --- 4. a small sample gets a mature verdict -----------------------
    ("4. an immature sample is allowed to carry DEGRADING",
     S / "learning_acceleration.py",
     "    mature_enough = denominator >= MIN_DENOMINATOR_FOR_VERDICT",
     "    mature_enough = True",
     f"{LA}::test_a_small_sample_cannot_carry_degrading"),

    # --- 5. a rate above one is accepted -------------------------------
    ("5. a share whose numerator outruns its denominator is returned",
     S / "learning_acceleration.py",
     "        if share and num > den:",
     "        if False:",
     f"{LAX}::test_a_share_above_one_raises_rather_than_being_clamped"),

    # --- 6. a zero denominator becomes zero instead of UNMEASURABLE ----
    ("6. an empty channel reports 0.0 rather than UNMEASURABLE",
     S / "learning_acceleration.py",
     '    if not effects:\n'
     '        return _unmeasurable(\n'
     '            ECONOMIC,',
     '    if False:\n'
     '        return _unmeasurable(\n'
     '            ECONOMIC,',
     f"{LA}::test_zero_denominator_is_unmeasurable_not_zero"),

    # --- 7. Founder publication counted as decision value --------------
    ("7. published dossiers are admitted as Founder decision value",
     S / "learning_acceleration.py",
     "    impacts = [i for i in decision_impacts if i]",
     "    impacts = [{'impact': 'MEANINGFUL'} for _ in range(99)]",
     f"{LA}::test_published_dossiers_are_not_founder_value"),

    # --- 8. unsupervised geometry treated as utility -------------------
    ("8. a partition scored on separation counts as useful",
     S / "learning_acceleration.py",
     '    scored = [d for d in discoveries if d.get("utility") is not None]',
     '    scored = [d for d in discoveries\n'
     '              if d.get("utility") is not None\n'
     '              or d.get("separation") is not None]',
     f"{LA}::test_unsupervised_utility_is_not_geometry"),

    # --- 9. duplicate evidence improves the learning rate --------------
    ("9. a duplicate effect id is counted as a second observation",
     S / "learning_acceleration.py",
     "    duplicates = len(ids) - len(set(ids))",
     "    duplicates = 0",
     f"{LA}::test_a_duplicate_id_is_a_storage_fault"),

    # --- 10. stale knowledge treated as intact -------------------------
    ("10. an orphaned change is counted as retained knowledge",
     S / "learning_acceleration.py",
     '    orphaned = [e for e in effects\n'
     '                if str(e.get("effect_type")) in CHANGING_EFFECTS\n'
     '                and not str(e.get("target_id") or "")]',
     "    orphaned = []",
     f"{LA}::test_an_orphaned_change_is_a_retention_failure"),

    # --- 11. the report omits the block silently -----------------------
    ("11. the dated report drops the learning acceleration block",
     ROOT / "src/intent_engine/market/report.py",
     '        "learning_acceleration": _learning_acceleration_summary(\n'
     '            knowledge.get("learning_acceleration") or {}),',
     '        "learning_acceleration_omitted": True,',
     f"{KS}::test_the_dated_report_carries_the_learning_channels"),

    # --- 12. an absent link is reported as a measured zero -------------
    ("12. outcomes that name no effects are graded as unproductive",
     S / "learning_acceleration.py",
     "    if outcomes and not linked_ids:",
     "    if False:",
     f"{LA}::test_an_absent_link_is_not_a_measured_zero"),

    # --- 13. the window key becomes a date field -----------------------
    ("13. effects are bucketed by created_at instead of append order",
     S / "learning_acceleration.py",
     '    return [[r for r in seg if r.get("record") == "knowledge_effect"]\n'
     '            for seg in cycle_segments(ledger)]',
     '    import collections as _c\n'
     '    buckets = _c.defaultdict(list)\n'
     '    for r in ledger:\n'
     '        if r.get("record") == "knowledge_effect":\n'
     '            buckets[str(r.get("created_at"))[:7]].append(r)\n'
     '    return [buckets[k] for k in sorted(buckets)]',
     f"{LA}::test_windows_come_from_append_order_never_from_created_at"),

    # --- 14. the bottleneck is declared rather than computed -----------
    ("14. the bottleneck is hardcoded instead of ranked from status",
     S / "learning_acceleration.py",
     "    name, channel = ranked[0]",
     '    name, channel = ("RETENTION", RETENTION)',
     f"{LA}::test_the_bottleneck_is_computed_not_declared"),

    # --- 15. high activity / low learning is suppressed ----------------
    ("15. the low-learning condition never fires",
     S / "learning_acceleration.py",
     "    detected = (share < LOW_LEARNING_SHARE\n"
     "                and len(effects) >= MIN_DENOMINATOR_FOR_VERDICT)",
     "    detected = False",
     f"{LA}::test_high_activity_low_learning_is_named"),

    # --- 16. the channels are blended into one score -------------------
    ("16. the seven channels are averaged into a composite",
     S / "learning_acceleration.py",
     '        "channels_measurable": sorted(',
     '        "composite": 1.0,\n'
     '        "channels_measurable": sorted(',
     f"{LA}::test_report_carries_all_seven_channels_independently"),
]

# --- NOT_BUILT ------------------------------------------------------------
#
# Two attacks the node lists have no guard to break, and the honest record is
# to say so rather than to write a proof that cannot fail.
#
# "rate > 1 accepted" for the CHANNELS specifically: the channel rates are
# built as num/den from populations the same filter produced, so there is no
# separate clamp to disable — proof 5 breaks the shared `rate()` guard in the
# quality half, which is where that defect actually occurred and where the
# guard actually lives. A second proof pointed at the channels would be
# demonstrating the absence of a code path.
#
# "small sample gets a mature TREND": effect-based trends do not exist yet.
# 393 of 402 live effects were appended in one cycle, so every channel reports
# its level and INSUFFICIENT_HISTORY for direction. There is no trend
# computation to mutate until the write history spans cycles, and building one
# to break would be the test that cannot fail.
NOT_BUILT = 2

if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4h — I-ACC-001 learning channels: {len(PROOFS)} proofs, "
               f"{NOT_BUILT} recorded NOT_BUILT")))
