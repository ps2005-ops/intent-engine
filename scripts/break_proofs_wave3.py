"""Break proofs for wave 3: world model, VOI, maturity, adversarial guards.

Each mutation makes a self-flattering behaviour true and demands that a guard
notices. Restore bumps mtime: a same-length restore leaves CPython running
cached bytecode whose size and hash still match.
"""
from __future__ import annotations
import os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = "/Users/prathamsharma/intent-engine/.venv/bin/python"
S = ROOT / "src/intent_engine/market"

PROOFS = [
    ("1. a category becomes a counterparty",
     S / "actor_relationships.py",
     "        if not is_named_actor(value):",
     "        if False:",
     "tests/test_market_actor_relationships.py::test_a_category_is_not_a_counterparty"),

    ("2. a relationship enters with no evidence",
     S / "actor_relationships.py",
     "    if not evidence_ids:",
     "    if False:",
     "tests/test_market_actor_relationships.py::test_a_relationship_with_no_evidence_is_model_knowledge"),

    ("3. an interaction exists without a named rival",
     S / "interaction_binding.py",
     "    if not competitors_of:",
     "    if False:",
     "tests/test_market_interaction_binding.py::test_without_competitor_relationships_nothing_is_produced"),

    ("4. an interaction asserts a motive",
     S / "strategic_interaction.py",
     "    if inferred_objective and not alternative_explanations:",
     "    if False:",
     "tests/test_market_interaction_binding.py::test_the_contract_refuses_a_motive_without_an_alternative"),

    ("5. a VOI query may ask to prove a conclusion",
     S / "value_of_information.py",
     "    if _CONFIRMATION_SEEKING.search(question) or _LOADED.search(question):",
     "    if False:",
     "tests/test_market_value_of_information.py::test_a_question_naming_its_answer_is_refused"),

    ("6. staleness is reported as contradiction",
     S / "belief_maturity.py",
     "    if tested:",
     "    if False:",
     "tests/test_market_belief_maturity.py::test_stale_and_weakening_are_never_merged"),

    # The age check is UNREACHABLE for a tested belief -- `if tested:`
    # returns first -- so mutating the threshold proves nothing. The
    # property is the ORDER, so the mutation lifts the age check above it.
    ("7. staleness is checked before the belief's test record",
     S / "belief_maturity.py",
     "    tested = confirmations + contradictions\n    if tested:",
     "    tested = confirmations + contradictions\n"
     "    if age is not None and age >= STALE_AFTER_DAYS:\n"
     "        return STALE, 'aged out'\n"
     "    if tested:",
     "tests/test_market_belief_maturity.py::test_a_tested_belief_is_never_stale_however_old"),

    ("8. one subject agreeing with itself earns repeated support",
     S / "belief_maturity.py",
     "        if independent >= MIN_INDEPENDENT_FOR_REPEATED:",
     "        if True:",
     "tests/test_market_belief_maturity.py::test_one_subject_agreeing_with_itself_is_not_repeated_support"),

    ("9. a duplicate fact tests the belief it opened",
     S / "observation_binding.py",
     "            if _fingerprint(item.fact) in basis_text:",
     "            if False:",
     "tests/test_market_causal_episodes.py::test_the_same_fact_under_a_new_id_cannot_test_its_own_belief"),

    ("10. a causal edge is born asserted",
     S / "causal_episodes.py",
     "            edge_status=proposed.status,",
     "            edge_status='SUPPORTED',",
     "tests/test_market_causal_episodes.py::test_one_test_never_promotes_an_edge"),

    ("11. an episode drops its alternative explanation",
     S / "causal_episodes.py",
     "            alternative_explanations=(COMMON_CAUSE, REPORTING_ARTEFACT),",
     "            alternative_explanations=(),",
     "tests/test_market_causal_episodes.py::test_every_episode_carries_the_common_cause_alternative"),

    ("12. a settled hidden state still asks for research",
     S / "value_of_information.py",
     "        if len(dist) < 2 or (dist[0][1] - dist[1][1]) > 0.10:",
     "        if False:",
     "tests/test_market_value_of_information.py::test_a_settled_hidden_state_is_not_worth_looking_at"),

    # Neither the arity guard nor the multiplication is what keeps a rival
    # alive: `_renormalise` clamps every state to a FLOOR, so a posture
    # the action explains badly is argued down and never to zero. Defence
    # in depth, and the floor is the load-bearing layer.
    ("13. the probability floor is removed, so a rival can reach zero",
     S / "hidden_state.py",
     "    capped = {s: min(max(p, _FLOOR), _CEIL) for s, p in dist.items()}",
     "    capped = {s: min(p, _CEIL) for s, p in dist.items()}",
     "tests/test_market_hidden_state_binding.py::test_no_posture_is_ever_eliminated_only_argued_down"),

    ("14. the whole-loop bottleneck ignores a starved stage",
     S / "learning_health.py",
     "    if not relationships:",
     "    if False:",
     "tests/test_market_learning_health.py::test_source_coverage_outranks_the_funnels_own_answer"),
]


def run(target: str) -> bool:
    p = subprocess.run([PY, "-m", "pytest", target, "-q", "--no-header"],
                       cwd=ROOT, capture_output=True, text=True,
                       env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
    return p.returncode == 0


def main() -> int:
    bad = []
    for label, path, find, repl, target in PROOFS:
        original = path.read_text(encoding="utf-8")
        if find not in original:
            print(f"  SKIP  {label}\n        anchor missing in {path.name}")
            bad.append(label); continue
        if not run(target):
            print(f"  FAIL  {label}\n        guard was already red")
            bad.append(label); continue
        path.write_text(original.replace(find, repl, 1), encoding="utf-8")
        try:
            caught = not run(target)
        finally:
            path.write_text(original, encoding="utf-8")
            now = time.time() + 1
            os.utime(path, (now, now))
        if not run(target):
            print(f"  FAIL  {label}\n        did not restore green"); bad.append(label)
        elif caught:
            print(f"  ok    {label}")
        else:
            print(f"  FAIL  {label}\n        mutation NOT caught"); bad.append(label)
    print()
    print(f"{len(PROOFS)-len(bad)}/{len(PROOFS)} break proofs held")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
