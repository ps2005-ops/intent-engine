"""Research as a decision problem: the log, the reward, and the wall."""
from __future__ import annotations

import pytest

from intent_engine.market import research_policy as RP


def record(family=RP.INDEPENDENT_REPORTING, *, subject="acme", outcome=RP.USED,
           independent=True, duplicate=False, resolved=False,
           discriminating=None, decision=False, cost=1.0, qtype="EARNINGS"):
    return RP.ResearchRecord(
        action=RP.ResearchAction(source_family=family, subject=subject,
                                 question=qtype, cost=cost),
        outcome=RP.ResearchOutcome(
            outcome=outcome, independent=independent, duplicate=duplicate,
            resolved_open_question=resolved, discriminating=discriminating,
            decision_relevant=decision),
        context={"subject": subject, "question_type": qtype})


# --- the wall ------------------------------------------------------------------

def test_a_research_policy_cannot_reach_a_trade():
    with pytest.raises(RP.OutsideResearch) as err:
        RP.guard_action("place_trade")
    assert "no term that prices being wrong" in str(err.value)


def test_every_restricted_action_is_refused():
    for action in RP.RESTRICTED_ACTIONS:
        with pytest.raises(RP.OutsideResearch):
            RP.guard_action(action)


def test_a_research_action_is_allowed_through():
    assert RP.guard_action(RP.REGULATORY_FILING) == RP.REGULATORY_FILING


def test_a_free_action_is_refused():
    with pytest.raises(RP.PolicyRejected):
        RP.ResearchAction(source_family=RP.COMPANY_OWNED, subject="a",
                          cost=0.0)


# --- the reward ------------------------------------------------------------------

def test_nothing_in_the_reward_counts_documents():
    """Ten duplicates must be worth less than one independent fact."""
    one_good = RP.reward(record(independent=True))
    ten_dupes = sum(RP.reward(record(independent=True, duplicate=True))
                    for _ in range(10))
    assert one_good > ten_dupes


def test_a_source_confirming_itself_earns_a_negative_reward():
    assert RP.reward(record(RP.COMPANY_OWNED, independent=False,
                            duplicate=True)) < 0


def test_an_unmeasured_discriminating_term_earns_nothing_and_costs_nothing():
    """None is not False and must not be coerced into one."""
    unmeasured = RP.reward(record(discriminating=None))
    negative = RP.reward(record(discriminating=False))
    positive = RP.reward(record(discriminating=True))
    assert unmeasured == negative < positive


def test_a_failed_source_costs_less_than_a_refused_one():
    assert RP.reward(record(outcome=RP.FAILED)) > \
        RP.reward(record(outcome=RP.REFUSED))


def test_the_best_possible_action_does_not_scale_with_volume():
    best = RP.reward(record(independent=True, resolved=True,
                            discriminating=True, decision=True, cost=1.0))
    assert best <= RP.MAX_ACTION_REWARD


# --- policies ----------------------------------------------------------------------

def test_the_random_policy_is_reproducible():
    a, b = RP.RandomPolicy(seed=7), RP.RandomPolicy(seed=7)
    ctx = {"subject": "acme"}
    assert [a.choose(ctx, list(RP.SOURCE_FAMILIES)) for _ in range(10)] == \
           [b.choose(ctx, list(RP.SOURCE_FAMILIES)) for _ in range(10)]


def test_an_untried_family_is_optimistic_not_zero():
    """Otherwise a policy can never learn that an unexplored source was good."""
    policy = RP.HistoricalYieldPolicy()
    policy.learn({}, RP.COMPANY_OWNED, 0.5)
    assert policy.choose({}, [RP.COMPANY_OWNED, RP.REGULATORY_FILING]) == \
        RP.REGULATORY_FILING


def test_the_bandit_separates_contexts():
    policy = RP.ContextualBanditPolicy(confidence=0.0)
    for _ in range(20):
        policy.learn({"question_type": "A"}, RP.REGULATORY_FILING, 3.0)
        policy.learn({"question_type": "A"}, RP.COMPANY_OWNED, -1.0)
        policy.learn({"question_type": "B"}, RP.REGULATORY_FILING, -1.0)
        policy.learn({"question_type": "B"}, RP.COMPANY_OWNED, 3.0)
    options = [RP.REGULATORY_FILING, RP.COMPANY_OWNED]
    assert policy.choose({"question_type": "A"}, options) == \
        RP.REGULATORY_FILING
    assert policy.choose({"question_type": "B"}, options) == RP.COMPANY_OWNED


# --- offline evaluation --------------------------------------------------------------

def test_a_policy_that_never_agrees_is_reported_as_unmeasured():
    log = [record(RP.INDEPENDENT_REPORTING) for _ in range(50)]
    got = RP.evaluate_offline(log, RP.FixedPolicy(RP.GOVERNMENT_DATA))
    assert got.matched == 0 and got.mean_reward is None
    assert got.trustworthy is False
    assert "says nothing about it" in got.note


def test_a_thin_overlap_is_never_trustworthy():
    log = ([record(RP.INDEPENDENT_REPORTING) for _ in range(95)]
           + [record(RP.GOVERNMENT_DATA) for _ in range(5)])
    got = RP.evaluate_offline(log, RP.FixedPolicy(RP.GOVERNMENT_DATA))
    assert got.matched == 5 and got.overlap == 0.05
    assert got.trustworthy is False


def test_the_comparison_never_declares_a_policy_deployable():
    log = [record() for _ in range(60)]
    got = RP.compare(log, [RP.VOIPolicy(), RP.RandomPolicy()])
    assert got["deployable"] is False
    assert "no exploration" in got["why_not_deployable"]


def test_the_comparison_reports_how_much_of_the_log_was_reconstructed():
    log = [record() for _ in range(3)]
    got = RP.compare(log, [RP.RandomPolicy()])
    assert got["reconstructed"] == 0


# --- reward hacking --------------------------------------------------------------------

def test_an_attack_tying_at_the_top_counts_as_hackable():
    """A tie is not a pass. The live audit is decided by exactly this."""
    log = [record(RP.INDEPENDENT_REPORTING) for _ in range(80)]
    got = RP.audit_reward(log)
    assert got["hackable"] is True


def test_a_reward_that_prices_discrimination_resists_the_volume_attack():
    """The same log, with the term the live ledger cannot fill.

    Volume comes from a family that answers often; value comes from a family
    that separates explanations. When the discriminating term is measurable
    the two come apart, and the attack stops winning.
    """
    log = ([record(RP.INDEPENDENT_REPORTING, discriminating=False,
                   duplicate=True) for _ in range(80)]
           + [record(RP.REGULATORY_FILING, discriminating=True, resolved=True,
                     decision=True) for _ in range(60)])
    got = RP.audit_reward(log)
    assert got["hackable"] is False, got["scores"]


def test_an_untrustworthy_estimate_cannot_exonerate_the_reward():
    """A policy matching a handful of rows must not outrank an attack.

    The log is built so the thin slice is the GOOD one: five excellent
    filings among eighty duplicated press releases. The VOI heuristic prefers
    filings, so it matches those five and posts by far the highest mean in the
    table — and on five matches that mean is noise. Counted, it would put an
    honest policy on top and the audit would report the reward as safe while
    the volume attack still beats every policy that is actually measurable.
    """
    log = ([record(RP.COMPANY_OWNED, independent=False, duplicate=True)
            for _ in range(80)]
           + [record(RP.REGULATORY_FILING, independent=True, resolved=True,
                     discriminating=True, decision=True) for _ in range(5)])
    got = RP.audit_reward(log)
    assert "VOI_HEURISTIC" in got["not_trustworthy"]
    assert "VOI_HEURISTIC" not in got["scores"]
    for name in got["scores"]:
        assert name not in got["not_trustworthy"]
    assert got["hackable"] is True


# --- reconstruction --------------------------------------------------------------------

def test_a_reconstructed_record_says_so():
    rows = [{"record": "evidence", "source_role": "independent_reporting",
             "subject_company": "acme", "fact": "f", "independence": 0.9,
             "self_authored": False, "evidence_type": "EARNINGS_RESULT"}]
    log = RP.reconstruct_log(rows)
    assert len(log) == 1 and log[0].reconstructed is True


def test_independence_is_read_as_a_score_not_a_label():
    """The ledger stores 0.9, not the word INDEPENDENT."""
    high = RP.reconstruct_log([{"record": "evidence", "source_role":
                                "independent_reporting",
                                "subject_company": "a", "fact": "f",
                                "independence": 0.9, "self_authored": False}])
    # SELF-AUTHORED IS DELIBERATELY FALSE HERE. With it set the record fails
    # on the second condition too, and a break proof against the threshold
    # passed on the flag; only a low score with no flag isolates the number.
    low = RP.reconstruct_log([{"record": "evidence", "source_role":
                               "company_owned", "subject_company": "a",
                               "fact": "f", "independence": 0.25,
                               "self_authored": False}])
    assert high[0].outcome.independent is True
    assert low[0].outcome.independent is False


def test_a_repeated_fact_from_one_family_is_a_duplicate():
    row = {"record": "evidence", "source_role": "regulatory_filing",
           "subject_company": "acme", "fact": "same", "independence": 0.85,
           "self_authored": False}
    log = RP.reconstruct_log([dict(row), dict(row)])
    assert log[0].outcome.duplicate is False
    assert log[1].outcome.duplicate is True


def test_a_reconstructed_log_cannot_measure_discrimination():
    log = RP.reconstruct_log([{"record": "evidence", "source_role":
                               "regulatory_filing", "subject_company": "a",
                               "fact": "f", "independence": 0.85,
                               "self_authored": False}])
    assert log[0].outcome.discriminating is None


def test_non_evidence_rows_are_ignored():
    assert RP.reconstruct_log([{"record": "belief"}, {"record": "cycle"}]) == []
