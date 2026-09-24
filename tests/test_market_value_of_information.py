"""Value of information — and the confirmation wall.

Research is currently pulled by availability. This makes it pullable by what
would actually discriminate between explanations the engine cannot separate.

The most load-bearing tests here are the refusals: belief formation routes
evidence BY DIRECTION, so a query naming the conclusion it wants would return
exactly the evidence that opens that belief and nothing that opens its
opposite. The search would manufacture its own confirmation and every
downstream test would inherit it.
"""
import pytest
from intent_engine.market import value_of_information as VOI


class _Mat:
    def __init__(self, state, subject="acme", prop="demand is weakening"):
        self.state, self.subject, self.proposition = state, subject, prop
        self.belief_id, self.what_would_revalidate = "b1", "the next figure"


class _HS:
    def __init__(self, dist, subject="acme"):
        self.distribution, self.subject = dist, subject


# ===========================================================================
# THE CONFIRMATION WALL
# ===========================================================================
@pytest.mark.parametrize("bad", [
    "Find evidence that demand is strengthening.",
    "Show proof that the company remains strong.",
    "Confirm that enterprise demand continues to grow.",
    "Find evidence supporting our thesis.",
    "Verify that margins are expanding.",
])
def test_a_question_naming_its_answer_is_refused(bad):
    with pytest.raises(VOI.ConfirmationSeeking):
        VOI.neutral_question(bad)


@pytest.mark.parametrize("good", [
    "Find the next reported revenue, bookings or guidance observation.",
    "What was the backlog figure in the most recent quarter?",
    "Did enterprise renewal rates change after the pricing change?",
    "Which observation would separate demand weakness from normalisation?",
])
def test_a_neutral_question_is_allowed(good):
    assert VOI.neutral_question(good) == good


def test_a_research_priority_cannot_carry_a_loaded_question():
    item = VOI.from_state(maturities=[_Mat("WEAKENING")])[0]
    with pytest.raises(VOI.ConfirmationSeeking):
        VOI.research_priority(item, question="Find proof demand is strong.",
                              eligible_sources=("results",))


def test_an_empty_question_discriminates_nothing():
    with pytest.raises(VOI.ConfirmationSeeking):
        VOI.neutral_question("   ")


# ===========================================================================
# WHAT EARNS PRIORITY
# ===========================================================================
def test_a_contradicted_belief_outranks_an_untested_one():
    """The engine has already been shown wrong once; the next observation is
    worth more there than anywhere it has merely never looked."""
    items = VOI.from_state(maturities=[_Mat("WEAKENING"), _Mat("STALE")])
    by_state = {i.source_of_value: i.priority for i in items}
    assert by_state[VOI.CONTRADICTED_BELIEF] == VOI.HIGH
    assert by_state[VOI.STALE_BELIEF] == VOI.LOW


def test_a_settled_hidden_state_is_not_worth_looking_at():
    """If the evidence already separates the postures, nothing is uncertain."""
    settled = _HS([("EXPANDING", 0.80), ("WAITING", 0.05)])
    assert VOI.from_state(hidden_states=[settled]) == ()


def test_an_ambiguous_hidden_state_earns_an_item():
    tied = _HS([("EXPANDING", 0.34), ("CAPACITY_CONSTRAINED", 0.33)])
    items = VOI.from_state(hidden_states=[tied])
    assert len(items) == 1
    assert items[0].source_of_value == VOI.AMBIGUOUS_HIDDEN_STATE
    assert len(items[0].competing_explanations) == 2


def test_a_healthy_belief_generates_no_item():
    assert VOI.from_state(maturities=[_Mat("SUPPORTED")]) == ()


def test_every_item_names_what_would_settle_it():
    for item in VOI.from_state(maturities=[_Mat("WEAKENING")],
                               hidden_states=[_HS([("A", 0.3), ("B", 0.3)])]):
        assert item.discriminating_observation
        assert item.where_it_would_appear
        assert len(item.competing_explanations) >= 2


def test_priority_is_ordinal_never_a_score():
    items = VOI.from_state(maturities=[_Mat("WEAKENING")])
    assert items[0].priority in VOI.PRIORITIES
    assert not any(c.isdigit() for c in items[0].priority)
