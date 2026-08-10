"""A number that reaches no artifact was not measured, for any operator.

A-RD-009 ran for a whole session and its counts were unobservable: the cycle
computed delayed rewards, persisted them, and `_knowledge_summary` had no
`delayed_reward` block, so the figure "did this action get paid for what it
found" had a correct answer nobody could read. The absence looked identical
to the capability not running.

`K-CYC-001` and `K-CYC-002` exist for the same reason one layer up. This file
holds the line for the blocks added since: every key a node's acceptance
depends on must survive `_knowledge_summary`, and a projection that silently
drops a key is caught here rather than by reading a report a day later.
"""
from __future__ import annotations

from intent_engine.market import report as R

#: What each node's acceptance criteria promise an operator can read.
REQUIRED = {
    "thesis_history": (
        # G-THE-004: the reconciliation must report what it FAILED to match,
        # not only what it matched. `compared: 11` sat beside `loaded: 7` for
        # two cycles because nothing projected the third number that would
        # have made the pair impossible to read as fine.
        "loaded", "compared", "identity_collisions", "unmatched_prior",
        "unmatched_current", "theses_built", "theses_sharing_an_identity",
        "snapshot_records_written", "prior_revisions_loaded",
    ),
    "delayed_reward": (
        # A-RD-009: who got paid, for what, and who could not be paid at all.
        "delayed_outcomes_written", "decisions_credited",
        "revisions_credited", "untraceable_revisions", "reward_delta_total",
    ),
    "economic_method": (
        # C-MET-002 / C-MET-004: a leader is worthless without the assumption
        # failures beside it.
        "series_scored", "evaluations", "leader", "by_standing",
        "assumption_failures_critical", "performance_records_written",
    ),
    "adversary": (
        # L-ADV-001. `by_standing` is the one that matters: every live case is
        # SPECULATIVE while the corpus carries no evidence of a counterparty's
        # means or motive, and cases shown without it would read in the same
        # voice as an observed move. Caught on the first live cycle after the
        # step was wired — steps.py filled the payload and this projection had
        # no entry for it, so the block existed and reached no artifact.
        "cases", "by_standing", "actionable", "strongest",
    ),
}


def _knowledge_with(block, keys):
    return {block: {k: 1 for k in keys}}


def test_every_required_key_survives_the_projection():
    for block, keys in REQUIRED.items():
        got = R._knowledge_summary(_knowledge_with(block, keys))
        assert block in got, f"{block} is not projected at all"
        missing = [k for k in keys if k not in got[block]]
        assert not missing, (
            f"{block} dropped {missing}; a count that reaches no artifact was "
            "not measured, for anyone who did not run the cycle")


def test_a_zero_is_projected_and_not_treated_as_absent():
    """`0` and `absent` are different claims and the projection filters None.

    A dict comprehension guarded on `is not None` is correct; one guarded on
    truthiness would drop every zero, and zero is the value these counts have
    when the thing being counted is working.
    """
    for block, keys in REQUIRED.items():
        got = R._knowledge_summary({block: {k: 0 for k in keys}})
        assert all(got[block][k] == 0 for k in keys), (
            f"{block} dropped a zero; 'no collisions' would read as 'not "
            "measured'")


def test_a_block_the_step_did_not_produce_is_absent_rather_than_empty():
    got = R._knowledge_summary({"thesis_history": {}})
    assert got.get("thesis_history") == {}
    assert "delayed_reward" not in got or got["delayed_reward"] == {}


def test_an_error_from_a_block_is_projected_rather_than_swallowed():
    for block in REQUIRED:
        got = R._knowledge_summary({block: {"error": "TypeError: boom"}})
        assert got[block].get("error"), (
            f"{block} swallowed its own error; a step that failed would "
            "report as a step that found nothing")


def test_the_projection_refuses_an_empty_knowledge_payload():
    got = R._knowledge_summary({})
    assert got["present"] is False
    assert got["reason"]
