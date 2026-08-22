"""Three copies of one announcement are one observation, in weight and in prose.

Changing only the wording is theatre: the belief would still mature on three
copies while the sentence said otherwise.
"""
from __future__ import annotations

import types

from intent_engine.market import evidence_trust as ET


def corr(**kw):
    base = dict(event_id="evt_1", standing="DEPENDENT_ACCOUNTS", accounts=3,
                effective_accounts=1.0, independent_accounts=1,
                conflicting_fields=())
    base.update(kw)
    return types.SimpleNamespace(**base)


# --- weight, not just wording ---------------------------------------------

def test_three_same_origin_reports_weigh_the_same_as_one():
    """Not slightly more. One observation is one observation however many
    sites carried it."""
    dependent = ET.assess(corr(accounts=3, effective_accounts=1.0))
    single = ET.assess(corr(accounts=1, effective_accounts=1.0))
    assert dependent.standing == ET.DEPENDENT_REREPORTING
    assert dependent.weight == single.weight == 1.0


def test_genuine_corroboration_weighs_more():
    got = ET.assess(corr(standing="CORROBORATED", accounts=3,
                         effective_accounts=2.5, independent_accounts=2))
    assert got.standing == ET.INDEPENDENTLY_CORROBORATED
    assert got.weight > ET.WEIGHT[ET.DEPENDENT_REREPORTING]


def test_conflicting_accounts_weigh_less_than_one_source():
    got = ET.assess(corr(accounts=3, conflicting_fields=("revenue",)))
    assert got.standing == ET.CONFLICTED
    assert got.weight < ET.WEIGHT[ET.SINGLE_SOURCE]


def test_dependent_reporting_does_not_inflate_independent_support():
    """The number a belief is allowed to mature on."""
    trusts = [ET.assess(corr(accounts=5, effective_accounts=1.0))]
    assert ET.independent_support_count(trusts) == 1
    assert ET.total_weight(trusts) == 1.0


def test_five_separate_events_each_count_once():
    trusts = [ET.assess(corr(event_id=f"e{i}", accounts=1,
                             effective_accounts=1.0)) for i in range(5)]
    assert ET.independent_support_count(trusts) == 5


# --- the language ---------------------------------------------------------

def test_the_reader_is_told_it_is_one_observation():
    got = ET.assess(corr(accounts=3, effective_accounts=1.0))
    assert "same underlying announcement" in got.sentence
    assert "one observation" in got.sentence


def test_independent_support_reads_as_independent():
    got = ET.assess(corr(standing="CORROBORATED", accounts=3,
                         effective_accounts=2.5, independent_accounts=2))
    assert "independently support" in got.sentence


def test_conflict_is_said_plainly_and_bounds_the_conclusion():
    got = ET.assess(corr(accounts=3, conflicting_fields=("revenue",)))
    assert "disagree" in got.sentence and "bounded" in got.sentence


def test_no_internal_vocabulary_reaches_the_reader():
    """SAME_ORIGIN and effective-account counts are how the engine decides,
    not how a person is spoken to."""
    for standing in ET.STANDINGS:
        sentence = ET._SENTENCES[standing].lower()
        for term in ET.INTERNAL_TERMS:
            assert term not in sentence, (standing, term)


def test_the_rendered_line_names_the_weakest_thing_worth_naming():
    trusts = [
        ET.assess(corr(event_id="a", standing="CORROBORATED", accounts=3,
                       effective_accounts=2.5, independent_accounts=2)),
        ET.assess(corr(event_id="b", accounts=4, effective_accounts=1.0)),
    ]
    assert "same underlying announcement" in ET.render(trusts)


def test_no_events_render_nothing_rather_than_a_reassurance():
    assert ET.render([]) == ""


def test_the_summary_carries_weight_and_the_sentence_together():
    got = ET.summarise([ET.assess(corr(accounts=3, effective_accounts=1.0))])
    assert got["independent_support"] == 1
    assert got["total_weight"] == 1.0
    assert "one observation" in got["sentence"]
