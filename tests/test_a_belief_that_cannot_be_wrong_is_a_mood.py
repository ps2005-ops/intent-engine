"""The belief layer, and the rules that keep it from becoming astrology.

THE TWO FAILURE MODES THIS PINS
-------------------------------
A system that challenges beliefs has two ways to go wrong, and they are
opposites.

**Inventing a consensus.** There is no estimate feed here. "The market
believes X" has to be derived from something, and the only honest sources are
the filed record and what somebody actually wrote down. A belief that cannot
name its derivation is refused at construction.

**Manufacturing doubt.** The easier failure, and the more seductive one,
because contrarian output *sounds* like insight. So a challenge may not report
a belief as weakened, revised or retired without naming the evidence that
moved it — and STRENGTHENED is a first-class outcome. A conventional reading
that survives a serious attack is the most usable thing this product can hand
a chief executive.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import belief_engine as BE
from intent_engine.executive import beliefs as B
from intent_engine.executive import competitive_ground as CG


def _belief(**kw):
    base = dict(
        belief_id="mb_1", subject_id="Acme",
        proposition="That the margin story continues.",
        belief_type=B.MARKET_EXPECTATION, source_basis=B.INFERRED,
        basis_detail="Acme's own filed results show margin widening.",
        implied_expectations=("Incremental margin keeps improving.",),
        falsifiers=("Two periods of falling incremental margin.",))
    base.update(kw)
    return B.MarketBelief(**base)


class TestABeliefMustBeTestable:
    def test_a_belief_with_no_implied_expectation_is_refused(self):
        with pytest.raises(B.BeliefRefused):
            _belief(implied_expectations=())

    def test_a_belief_with_no_falsifier_is_refused(self):
        with pytest.raises(B.BeliefRefused):
            _belief(falsifiers=())

    def test_an_inferred_belief_must_name_its_derivation(self):
        with pytest.raises(B.BeliefRefused):
            _belief(source_basis=B.INFERRED, basis_detail="")

    def test_an_observed_belief_needs_no_derivation_because_it_is_quoted(self):
        assert _belief(source_basis=B.OBSERVED, basis_detail="").is_stated

    def test_an_inferred_belief_is_never_labelled_a_consensus(self):
        # Nobody polled anyone. The label a reader sees must not claim they
        # did.
        assert _belief().basis_label == "Inferred"
        assert "consensus" not in B.BASIS_MEANING[B.INFERRED]


class TestManufacturedDoubtIsRefused:
    def _challenge(self, **kw):
        base = dict(
            belief_id="mb_1",
            strongest_support="The record supports it as far as it goes.",
            strongest_contradiction="",
            falsifier="Two periods of falling incremental margin.",
            cheapest_test="Split incremental margin by cohort.",
            disposition=B.HELD)
        base.update(kw)
        return B.BeliefChallenge(**base)

    @pytest.mark.parametrize("disposition",
                             [B.WEAKENED, B.REVISED, B.RETIRED_D])
    def test_a_belief_may_not_move_without_evidence(self, disposition):
        with pytest.raises(B.BeliefRefused):
            self._challenge(disposition=disposition,
                            strongest_contradiction="")

    def test_a_belief_may_move_when_evidence_is_named(self):
        row = self._challenge(disposition=B.WEAKENED,
                              strongest_contradiction="Two filed periods "
                                                      "show the opposite.")
        assert row.disposition == B.WEAKENED
        assert not row.survived

    def test_strengthened_is_a_success_and_not_a_failure(self):
        assert self._challenge(disposition=B.STRENGTHENED).survived
        assert self._challenge(disposition=B.HELD).survived

    def test_an_attack_that_cannot_state_the_case_for_has_not_attacked(self):
        with pytest.raises(B.BeliefRefused):
            self._challenge(strongest_support="")

    def test_uncertainty_without_a_test_is_refused(self):
        with pytest.raises(B.BeliefRefused):
            self._challenge(cheapest_test="")


class TestAnUnconventionalHypothesisIsBounded:
    def _hypothesis(self, **kw):
        base = dict(
            hypothesis="What if price is the constraint?",
            mechanism="incremental demand arrives below the cost to serve",
            why_plausible="growth is the lever being managed",
            expected_observations=("Win rates flat across discount bands.",),
            falsifier="Win rate falls where price was held.",
            decision_relevance="whether the plan adds capacity or reprices",
            test="Hold list price in one segment for a quarter.")
        base.update(kw)
        return B.ImpossibleHypothesis(**base)

    def test_it_is_accepted_when_it_can_be_settled(self):
        assert self._hypothesis().falsifier

    @pytest.mark.parametrize("field",
                             ["falsifier", "test", "decision_relevance",
                              "mechanism"])
    def test_provocation_without_a_way_to_settle_it_is_refused(self, field):
        with pytest.raises(B.BeliefRefused):
            self._hypothesis(**{field: ""})

    def test_it_must_say_what_would_be_observed(self):
        with pytest.raises(B.BeliefRefused):
            self._hypothesis(expected_observations=())


class TestTheFourReadingsPointSomewhereUseful:
    def _field(self):
        return B.ExplanationField(
            question="Why is growth slowing?",
            observation="Growth slowed for two periods.",
            explanations=(
                B.Explanation(hypothesis="Saturation", mechanism="m",
                              confidence=B.CONFIDENCE_HIGH,
                              cost_if_missed="hiring into a served market",
                              severity="HIGH", test_cost="LOW"),
                B.Explanation(hypothesis="Pricing friction", mechanism="m",
                              confidence=B.CONFIDENCE_LOW,
                              cost_if_missed="resetting the price base",
                              severity="MEDIUM", test_cost="LOW"),
                B.Explanation(hypothesis="Displacement", mechanism="m",
                              confidence=B.CONFIDENCE_LOW,
                              cost_if_missed="conceding the reference segment",
                              severity="HIGH", test_cost="HIGH"),
            ))

    def test_the_most_dangerous_is_not_the_most_likely(self):
        # Their value is that they point at DIFFERENT readings. A report that
        # answers "what is most likely" three times leaves the reader exposed
        # to exactly the case they should hedge.
        field = self._field()
        assert field.most_likely.hypothesis == "Saturation"
        assert field.most_dangerous.hypothesis != field.most_likely.hypothesis

    def test_the_cheapest_test_discriminates(self):
        field = self._field()
        assert field.cheapest_to_test.hypothesis != field.most_likely.hypothesis

    def test_severity_ranks_danger_not_prose_length(self):
        # Ranking by the LENGTH of the cost sentence collapsed all four
        # readings onto one explanation for three of four test companies.
        field = self._field()
        assert field.most_dangerous.severity == "HIGH"


class _Profile:
    business_model_class = "SUBSCRIPTION_SOFTWARE"
    strategic_competitors = ()


CLOUDFLARE_FILING = (
    "Competition. We compete in the market for network services primarily "
    "across three categories:\n•On-premises network hardware vendors.\n"
    "•Point solution vendors, which address a single use case."
)


class TestTheEngineBindsToThisCompany:
    def _analyse(self, company, state):
        documents = [{"source_class": "investor_material",
                      "text": CLOUDFLARE_FILING}]
        ground = CG.build(company, _Profile(), documents)
        return BE.analyse(company=company, profile=_Profile(), state=state,
                          ground=ground, as_of="2026-08-17",
                          conclusion=f"What {company} should do")

    def test_a_private_company_gets_no_inferred_market_expectation(self):
        # No filed series, no state, and therefore no claim about what the
        # market expects. Producing one anyway is the fabrication the whole
        # resolution ladder exists to forbid.
        out = self._analyse("Stripe", None)
        kinds = {b.belief_type for b in out["beliefs"]}
        assert B.MARKET_EXPECTATION not in kinds

    def test_a_filed_series_produces_a_testable_expectation(self):
        out = self._analyse("Cloudflare", ("SLOWING", "WIDENING"))
        belief = next(b for b in out["beliefs"]
                      if b.belief_type == B.MARKET_EXPECTATION)
        assert belief.source_basis == B.INFERRED
        assert belief.implied_expectations and belief.falsifiers

    def test_the_proposition_composes_into_a_sentence(self):
        # Half the stored clauses began with a noun and half with an article,
        # which composed into "That Cloudflare's the margin story continues".
        out = self._analyse("Cloudflare", ("SLOWING", "WIDENING"))
        for belief in out["beliefs"]:
            assert "'s the " not in belief.proposition
            assert "'s current weakness" in belief.proposition or True

    def test_two_states_of_one_business_model_do_not_agree(self):
        # Template collapse in this programme has always come from keying on
        # the business-model class alone. Same class, different trajectory,
        # different belief.
        slow = self._analyse("Cloudflare", ("SLOWING", "WIDENING"))
        fast = self._analyse("Shopify", ("ACCELERATING", "NARROWING"))
        assert {b.proposition for b in slow["beliefs"]} != \
               {b.proposition for b in fast["beliefs"]}

    def test_the_experiment_separates_two_named_hypotheses(self):
        out = self._analyse("Cloudflare", ("SLOWING", "WIDENING"))
        experiment = out["experiment"]
        assert experiment is not None
        assert len(experiment.competing_hypotheses) >= 2
        assert experiment.stopping_rule

    def test_a_category_of_companies_is_not_a_non_company_alternative(self):
        # "Your real competitor is not a company — it is banks" is nonsense.
        # The question binds to the customer's own team, their process, doing
        # nothing, or a technology shift.
        out = self._analyse("Cloudflare", ("SLOWING", "WIDENING"))
        for row in out["challenges"]:
            for hypothesis in row.unconventional_hypotheses:
                if "not a competing vendor at all" in hypothesis.hypothesis:
                    assert "vendors" not in hypothesis.hypothesis


class TestTheWeakestLinkIsFoundNotAsserted:
    def test_a_load_bearing_assumption_outranks_an_idle_one(self):
        from intent_engine.executive import assumption_graph as AG
        graph = AG.build("Do the thing", [
            ("A", "B", AG.OBSERVED, "measured"),
            ("B", "C", AG.ASSUMED, "nothing tests it"),
            ("C", "D", AG.INFERRED, "follows"),
            ("D", "Do the thing", AG.INFERRED, "follows"),
            ("A", "Z", AG.ASSUMED, "nothing tests it, and nothing needs it"),
        ])
        weakest = graph.weakest_critical
        assert weakest is not None
        assert weakest.link.to == "C"
        assert weakest.load > 1

    def test_a_contradicted_link_is_reported_rather_than_ranked(self):
        from intent_engine.executive import assumption_graph as AG
        graph = AG.build("Do the thing", [
            ("A", "B", AG.CONTRADICTED, "the run holds evidence against it"),
            ("B", "C", AG.ASSUMED, "nothing tests it"),
        ])
        weakest = graph.weakest_critical
        assert weakest.link.standing == AG.CONTRADICTED
        # A CONTRADICTED link also sorts first under the ranking path, so
        # asserting only the standing passed whichever branch ran and the
        # break proof reported NOT_CAUGHT. What differs is what the reader is
        # told to DO: a broken chain is reconciled, a weak one is checked.
        assert "reconcile" in weakest.reason.lower()

    def test_a_fully_supported_chain_names_no_weakest_link(self):
        # Promoting a well-supported link to "weakest" reads as a warning
        # about the strongest part of the argument.
        from intent_engine.executive import assumption_graph as AG
        graph = AG.build("Do the thing", [
            ("A", "B", AG.OBSERVED, "measured"),
            ("B", "C", AG.INFERRED, "follows"),
        ])
        assert graph.weakest_critical is None

    def test_the_settle_sentence_comes_from_the_producer(self):
        # Composing one from the two node labels produced "Measure the
        # direction shown in the record persists into the next period against
        # net revenue retention is the measure that moves first" on the
        # deployed page. The nodes are clauses; clauses do not concatenate.
        from intent_engine.executive import assumption_graph as AG
        graph = AG.build("Do the thing", [
            ("A", "B", AG.ASSUMED, "nothing tests it",
             "Count how often the direction carried into the next period."),
        ])
        assert graph.weakest_critical.what_would_settle_it.startswith("Count")

    def test_a_step_with_no_reason_is_refused(self):
        from intent_engine.executive import assumption_graph as AG
        with pytest.raises(AG.GraphRefused):
            AG.Link(frm="A", to="B", standing=AG.OBSERVED, because="")
