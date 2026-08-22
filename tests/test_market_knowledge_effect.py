"""Evidence must know what it changed — or say plainly that it changed nothing."""
from __future__ import annotations

import pytest

from intent_engine.market import company_exposure as CX
from intent_engine.market import knowledge_effect as KE
from intent_engine.market import research_policy as RP


def effect(**kw):
    base = dict(evidence_id="e1", target_type=KE.BELIEF, target_id="b1",
                effect_type=KE.CREATED, before_state="absent",
                after_state="prior=0.3", reason="opened")
    base.update(kw)
    return KE.KnowledgeEffect(**base)


# --- marked affected is not affected ------------------------------------------

def test_a_change_that_changed_nothing_is_refused():
    """The easiest way to fake this layer is to attribute everything."""
    with pytest.raises(KE.NotAChange) as err:
        effect(before_state="prior=0.3", after_state="prior=0.3")
    assert "merely ABOUT" in str(err.value)


def test_every_changing_type_must_show_a_change():
    for kind in sorted(KE.CHANGING):
        with pytest.raises(KE.NotAChange):
            effect(effect_type=kind, before_state="same", after_state="same")


def test_a_change_needs_the_object_it_changed():
    with pytest.raises(KE.EffectRejected):
        effect(target_id="")


def test_an_effect_needs_the_evidence_that_caused_it():
    with pytest.raises(KE.EffectRejected) as err:
        effect(evidence_id="")
    assert "price a research action" in str(err.value)


def test_an_unexplained_attribution_is_refused():
    with pytest.raises(KE.EffectRejected) as err:
        effect(reason="  ")
    assert "cannot be audited" in str(err.value)


def test_no_change_may_not_report_two_states():
    with pytest.raises(KE.EffectRejected):
        KE.KnowledgeEffect(evidence_id="e1", target_type=KE.BELIEF,
                           target_id="", effect_type=KE.NO_CHANGE,
                           before_state="a", after_state="b", reason="r")


# --- NO_CHANGE is as cheap to write as a change ---------------------------------

def test_recording_nothing_happened_takes_one_call():
    got = KE.no_change("e1", reason="no family routes this evidence type")
    assert got.effect_type == KE.NO_CHANGE
    assert got.changed is False
    assert got.discriminating is False


def test_the_summary_separates_unexamined_from_unmoved():
    """Nobody looked, and somebody looked and nothing moved, are different."""
    got = KE.summarise([KE.no_change("e1", reason="r")], evidence_total=10)
    assert got["evidence_attributed"] == 1
    assert got["evidence_that_changed_nothing"] == 1
    assert got["evidence_unattributed"] == 9
    assert "must not be added together" in got["note"]


def test_an_unknown_denominator_is_none_not_zero():
    got = KE.summarise([KE.no_change("e1", reason="r")])
    assert got["evidence_total"] is None
    assert got["evidence_unattributed"] is None


# --- only a direct attribution may price an action --------------------------------

def test_a_reconstructed_attribution_cannot_price_an_action():
    assert effect(standing=KE.RECONSTRUCTED).priceable is False
    assert effect(standing=KE.UNKNOWN).priceable is False
    assert effect(standing=KE.DIRECT).priceable is True


# --- discrimination comes from resolution, not from creation ------------------------

def test_creating_a_belief_does_not_discriminate():
    assert effect(effect_type=KE.CREATED).discriminating is False


def test_resolving_and_contradicting_discriminate():
    assert effect(effect_type=KE.RESOLVED, before_state="open",
                  after_state="CONFIRMED").discriminating is True
    assert effect(effect_type=KE.CONTRADICTED, before_state="untested",
                  after_state="CONTRADICTED").discriminating is True


class _Rec:
    def __init__(self, outcome, ids=("e1",)):
        self.outcome = outcome
        self.evidence_ids = ids
        self.expectation_id = "x1"
        self.hypothesis_id = "b1"
        self.evaluated_at = "2026-08-08"
        self.rationale = "the observation went the other way"


def test_a_resolved_expectation_attributes_two_different_facts():
    got = KE.from_reconciliation(_Rec("CONTRADICTED"))
    kinds = {(e.target_type, e.effect_type) for e in got}
    assert (KE.EXPECTATION, KE.RESOLVED) in kinds
    assert (KE.BELIEF, KE.CONTRADICTED) in kinds


def test_an_open_window_attributes_no_change_rather_than_nothing():
    got = KE.from_reconciliation(_Rec("TOO_EARLY"))
    assert got and all(e.effect_type == KE.NO_CHANGE for e in got)


def test_a_confirmation_supports_without_discriminating_the_belief():
    got = KE.from_reconciliation(_Rec("CONFIRMED"))
    belief = [e for e in got if e.target_type == KE.BELIEF][0]
    assert belief.effect_type == KE.SUPPORTED
    assert belief.discriminating is False


# --- the change history a thesis reads ------------------------------------------------

def test_a_targets_history_comes_back_in_order():
    a = effect(evidence_id="e1", occurred_at="2026-01-01")
    b = effect(evidence_id="e2", effect_type=KE.SUPPORTED,
               before_state="prior=0.3", after_state="prior=0.5",
               occurred_at="2026-03-01")
    got = KE.by_target([b, a], target_type=KE.BELIEF, target_id="b1")
    assert [e.evidence_id for e in got] == ["e1", "e2"]


# --- written at the exposure seam --------------------------------------------------------

def _row(fact, role="regulatory_filing", eid="e1"):
    return {"record": "evidence", "subject_company": "acme",
            "evidence_id": eid, "fact": fact, "source_role": role,
            "observed_at": "2026-05-01"}


def test_an_exposure_sentence_attributes_a_creation():
    effects: list = []
    CX.read_exposures([_row("we are exposed to interest rates on our "
                              "floating rate borrowings")],
                      company_id="acme", effects=effects)
    created = [e for e in effects if e.effect_type == KE.CREATED]
    assert created and created[0].target_type == KE.COMPANY_EXPOSURE
    assert created[0].before_state == CX.UNKNOWN


def test_evidence_that_names_no_exposure_attributes_no_change():
    effects: list = []
    CX.read_exposures([_row("the chief executive visited a trade show")],
                      company_id="acme", effects=effects)
    assert effects and all(e.effect_type == KE.NO_CHANGE for e in effects)
    assert "names an exposure" in effects[0].reason


def test_a_filing_upgrading_a_headline_is_a_revision_not_a_creation():
    effects: list = []
    CX.read_exposures(
        [_row("we are exposed to interest rates on our borrowings",
              role="independent_reporting", eid="e1"),
         _row("we are exposed to interest rates on our borrowings",
              role="regulatory_filing", eid="e2")],
        company_id="acme", effects=effects)
    revised = [e for e in effects if e.effect_type == KE.REVISED]
    assert revised
    assert revised[0].before_state == CX.INFERRED
    assert revised[0].after_state == CX.OBSERVED


def test_attribution_is_opt_in_and_changes_nothing_when_absent():
    sentence = "we are exposed to interest rates on our borrowings"
    plain = CX.read_exposures([_row(sentence)], company_id="acme")
    with_effects = CX.read_exposures([_row(sentence)], company_id="acme",
                                     effects=[])
    assert [e.as_dict() for e in plain] == [e.as_dict() for e in with_effects]


# --- the reward, now that the terms are measurable ------------------------------------------

def test_the_effect_priced_log_measures_what_the_reconstructed_one_could_not():
    rows = [{"record": "evidence", "evidence_id": "e1",
             "subject_company": "acme", "source_role": "regulatory_filing",
             "fact": "f", "independence": 0.85, "self_authored": False,
             "evidence_type": "EARNINGS_RESULT", "observed_at": "2026-05-01"}]
    effects = [effect(evidence_id="e1", target_type=KE.COMPANY_EXPOSURE,
                      target_id="acme:RATE_EXPOSURE",
                      effect_type=KE.CREATED, before_state="UNKNOWN",
                      after_state="OBSERVED")]
    log = RP.log_from_effects(rows, effects)
    assert len(log) == 1
    assert log[0].outcome.decision_relevant is True
    assert log[0].outcome.discriminating is False   # measured, not None
    assert RP.reconstruct_log(rows)[0].outcome.discriminating is None


def test_evidence_with_no_effect_record_is_not_priced():
    """An unexamined action must not be given a result."""
    rows = [{"record": "evidence", "evidence_id": "e1",
             "subject_company": "acme", "source_role": "company_owned",
             "fact": "f", "independence": 0.25, "self_authored": True}]
    assert RP.log_from_effects(rows, []) == []


def test_an_attack_that_changes_more_than_the_honest_policy_is_not_a_hack():
    """The correction: winning is not hacking.

    The first audit reported HACKABLE because a volume attack topped the
    table. On the live corpus that attack picks independent reporting, which
    has the HIGHEST knowledge-change rate and the LOWEST duplication — the
    volume arm and the value arm are the same arm. An alarm that fires
    whenever the best source is also the most prolific one is always on.
    """
    def rec(family, changed):
        return RP.ResearchRecord(
            action=RP.ResearchAction(source_family=family, subject="acme"),
            outcome=RP.ResearchOutcome(
                outcome=RP.USED, independent=True,
                resolved_open_question=changed, decision_relevant=changed,
                discriminating=changed))
    log = ([rec(RP.INDEPENDENT_REPORTING, True) for _ in range(60)]
           + [rec(RP.REGULATORY_FILING, False) for _ in range(40)])
    got = RP.audit_reward(log)
    assert got["hackable"] is False
    assert got["change_rate"]["ATTACK_VOLUME"] >= \
        got["change_rate"][got["best_honest"]]


def test_an_attack_that_wins_while_changing_less_is_flagged():
    """The direction that must FAIL when the comparison is removed.

    The companion test asserts the safe outcome, so deleting the change-rate
    comparison leaves it passing. This one asserts the alarm.
    """
    def volume(_):
        # Clean, independent, and it moves nothing.
        return RP.ResearchRecord(
            action=RP.ResearchAction(source_family=RP.INDEPENDENT_REPORTING,
                                     subject="acme"),
            outcome=RP.ResearchOutcome(outcome=RP.USED, independent=True))

    def valuable(_):
        # Duplicative and self-authored, so it scores badly per action — and
        # it resolves an open question every single time.
        return RP.ResearchRecord(
            action=RP.ResearchAction(source_family=RP.REGULATORY_FILING,
                                     subject="acme"),
            outcome=RP.ResearchOutcome(
                outcome=RP.USED, independent=False, duplicate=True,
                resolved_open_question=True))

    # The attack tops the table WHILE changing nothing, and the policy that
    # changes something every time scores below it. Invisible to a score
    # alone, which is why the audit compares change rates.
    log = [volume(i) for i in range(90)] + [valuable(i) for i in range(40)]
    got = RP.audit_reward(log)
    assert got["top"] == "ATTACK_VOLUME", got["scores"]
    assert got["hackable"] is True
    assert "ATTACK_VOLUME" in got["hacking_policies"]
    assert got["change_rate"]["ATTACK_VOLUME"] < \
        got["change_rate"][got["best_honest"]]


def test_an_attack_that_wins_while_changing_less_is_a_hack():
    def rec(family, changed, dupe=False):
        return RP.ResearchRecord(
            action=RP.ResearchAction(source_family=family, subject="acme"),
            outcome=RP.ResearchOutcome(
                outcome=RP.USED, independent=True, duplicate=dupe,
                resolved_open_question=changed, decision_relevant=changed,
                discriminating=changed))
    # The prolific family answers constantly and moves nothing; the VOI
    # heuristic's preferred family moves something every time.
    log = ([rec(RP.INDEPENDENT_REPORTING, False) for _ in range(90)]
           + [rec(RP.REGULATORY_FILING, True) for _ in range(40)])
    got = RP.audit_reward(log)
    assert got["change_rate"]["ATTACK_VOLUME"] < \
        got["change_rate"][got["best_honest"]]
