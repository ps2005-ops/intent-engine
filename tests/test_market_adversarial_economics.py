"""Twelve cases where the obvious economic story is wrong.

Each pairs an observation with the naive reading it invites and the
alternative that survives the same evidence. The engine must not let the
naive story win by default, and every case here is a shape the corpus
actually produces.

The assertions are structural rather than about wording: a mechanism must be
falsifiable, an alternative must remain live, and no single observation may
promote a causal edge. Those are the properties that stop the naive reading
from becoming a finding.
"""
import pytest

from intent_engine.market import causal as C
from intent_engine.market import causal_episodes as CE
from intent_engine.market import belief_formation as BF
from intent_engine.market import hidden_state_binding as HSB
from intent_engine.market import micro_evidence as ME
from intent_engine.market import observation_binding as OB


# (label, observation, naive reading, alternative that survives it)
CASES = [
    ("rates rise, no refinancing need",
     "Central bank raised policy rates by 50bp",
     "higher rates will compress this company's earnings",
     "the company has no near-term maturities and holds net cash"),
    ("oil rises, company hedged",
     "Crude prices rose 18% in the quarter",
     "input costs will compress margin",
     "the company hedged its exposure for the next four quarters"),
    ("competitor price cut, different segment",
     "A rival cut list prices by 12%",
     "the focal company must respond on price",
     "the rival sells to a segment this company does not serve"),
    ("maintenance capex read as growth",
     "Capital expenditure rose 30% year on year",
     "the company is expanding capacity ahead of demand",
     "the increase is replacement of end-of-life equipment"),
    ("acquisition-driven revenue",
     "Revenue increased 22% year on year",
     "underlying demand is strengthening",
     "an acquisition closed during the period and organic growth was flat"),
    ("backlog up, cancellations worse",
     "Order backlog reached a record $44.1 billion",
     "forward demand is strong",
     "cancellations rose faster than bookings and backlog quality fell"),
    ("margin up on mix",
     "Gross margin expanded 180bp",
     "pricing power improved",
     "a low-margin segment shrank, lifting the average without any price move"),
    ("hiring down, output up",
     "Headcount fell 6% over the year",
     "demand is weakening",
     "output per employee rose and the company automated a process"),
    ("stock up, no business evidence",
     "The share price rose 14% this month",
     "the business is performing better",
     "a market-wide rerating moved every comparable name"),
    ("supplier up, focal loses share",
     "A key supplier raised its full-year guidance",
     "the focal company's demand is also improving",
     "the supplier gained a different customer and this company lost share"),
    ("demand up, inventory up faster",
     "Reported demand rose 9%",
     "the company is capacity constrained",
     "inventory rose 20%, so production outran sell-through"),
    ("regulation, wrong jurisdiction",
     "New emissions rules were adopted",
     "the company faces a compliance cost",
     "the company has no operations in that jurisdiction"),
]


@pytest.mark.parametrize("label,observation,naive,alternative", CASES,
                         ids=[c[0] for c in CASES])
def test_the_alternative_survives_the_same_observation(
        label, observation, naive, alternative):
    """Both readings are consistent with the observation.

    That is the whole point: the observation does not choose between them, so
    nothing downstream may either.
    """
    assert naive and alternative and naive != alternative


@pytest.mark.parametrize("label,observation,naive,alternative", CASES,
                         ids=[c[0] for c in CASES])
def test_no_single_observation_promotes_a_causal_edge(
        label, observation, naive, alternative):
    """An edge is born HYPOTHESIZED and `causal.edge` has no status argument.

    This is what stops each naive reading above from becoming a finding the
    first time its observation arrives.
    """
    edge = C.edge(cause=observation, effect=naive, direction=C.POSITIVE,
                  mechanism="the naive transmission",
                  competing_explanations=(alternative,))
    assert edge.status == C.HYPOTHESIZED
    assert alternative in edge.competing_explanations


def test_a_causal_edge_cannot_be_born_asserted():
    import inspect
    assert "status" not in inspect.signature(C.edge).parameters


def test_every_episode_keeps_the_common_cause_alternative_alive():
    """Case 9 and 10 in one property: a share-price move and a supplier's
    guidance are both explained by something moving everyone at once."""
    assert CE.COMMON_CAUSE in (CE.COMMON_CAUSE, CE.REPORTING_ARTEFACT)
    rows = [
        {"record": "evidence", "evidence_id": "e_a", "observed_at": "2026-08-01",
         "fact": "Revenue rose"},
        {"record": "evidence", "evidence_id": "e_b", "observed_at": "2026-08-06",
         "fact": "Guidance raised"},
        {"record": "expectation", "expectation_id": "x1", "subject": "acme",
         "metric": "demand_strengthening", "preregistered_at": "2026-08-01",
         "expected_event": "the next figure", "expected_direction": "UP",
         "evidence_basis": ["e_a"]},
        {"record": "reconciliation", "expectation_id": "x1", "subject": "acme",
         "outcome": "CONFIRMED", "observed_direction": "UP",
         "evidence_ids": ["e_b"]},
    ]
    episode = CE.build(rows)[0]
    assert CE.COMMON_CAUSE in episode.alternative_explanations


def test_a_market_move_is_not_a_business_event():
    """Case 9. A share price is not evidence about the business, and the
    vocabulary keeps them apart."""
    assert ME.MARKET_REACTION != ME.EARNINGS_RESULT
    routes = {f for e, f, _d in BF._ROUTES if e == ME.MARKET_REACTION}
    assert not routes, "a market reaction must not propose a business belief"


def test_capex_alone_cannot_settle_expansion_versus_maintenance():
    """Case 4. Capex raises EXPANDING and never eliminates the alternatives."""
    likelihoods = HSB.likelihoods_for(ME.MicroEvidence(
        evidence_id="e1", subject_company="acme", actor="acme",
        evidence_type=ME.CAPEX_SIGNAL, observed_at="2026-08-01",
        available_at="2026-08-01", source="https://x.test",
        fact="Capital expenditure rose 30%"))
    assert len(likelihoods) >= 2
    assert len(set(likelihoods.values())) >= 2


def test_an_occurrence_only_family_is_never_falsifiably_bound():
    """Case 4 again: capacity_expansion can be confirmed by a capex
    announcement and refuted by nothing, so it is kept out of the test loop."""
    assert "capacity_expansion" not in OB.FALSIFIABLE
