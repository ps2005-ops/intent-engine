"""The product named the competitors, then denied having identified any.

MEASURED LIVE on the deployed 0420fb0, 3 of 3 companies. Step 1 said:

    JPMorgan  "Its position is contested directly by banks and brokerage firms"
    NVIDIA    "...by Huawei Technologies Co and Open-source AI"
    Walmart   "...by social commerce platforms and delivery services"

and one click later, in the SAME run, "Who's the real competitor?" answered:

    "No competitor has been selected for this company from the evidence."

Both sentences described the same state. The ladder returned nothing, so
`_position` fell through to the manifest's class-level peers and stated them
with an evidence-strength verb, while Q&A — reading `level4_competition`,
which is empty on exactly those runs — reported accurately that the evidence
had named nobody. Two surfaces, two objects, one question a chief executive
asks first.

§22: different surfaces may take different projections, but they must share
ONE underlying competitive state.
"""
import pytest

from intent_engine.executive.strategic_read import (
    COMPETITION_FROM_EVIDENCE, COMPETITION_FROM_MODEL, COMPETITION_FROM_SECTOR,
    COMPETITION_NONE, competitive_sentence, competitive_state,
)
from intent_engine.founder_brief.qa import _competition_answer, _route_answer


class Peer:
    def __init__(self, name, basis):
        self.name, self.basis = name, basis


class Profile:
    def __init__(self, peers=()):
        self.strategic_competitors = tuple(peers)
        self.operating_leverage = ""


class Rival:
    def __init__(self, name, rung="DIRECT"):
        self.name, self.rung = name, rung
        self.likely_response = "Defends price."
        self.signal_to_watch = "list price."


class Read:
    """Only the fields the surfaces actually consume."""

    def __init__(self, rows=(), rivals=(), basis=COMPETITION_NONE,
                 standing="READ_SUPPORTED"):
        self.level4_competition = tuple(rows)
        self.competitive_rivals = tuple(rivals)
        self.competitive_basis = basis
        self.standing = standing

    @property
    def puts_a_strategy_forward(self):
        return self.standing in ("READ_SUPPORTED", "READ_BOUNDED")


# --- the state itself ---------------------------------------------------

def test_the_ladder_wins_when_it_has_rows():
    state = competitive_state(Profile([Peer("Sector Mate", "SECTOR")]),
                              [Rival("Named Rival")])
    assert state["basis"] == COMPETITION_FROM_EVIDENCE
    assert state["rivals"] == ("Named Rival",)


def test_the_ladders_weakest_rung_is_not_evidence():
    """STRUCTURAL_PEER is defined as 'same business model; not a stated
    rival'. Rendering the ladder's own bottom rung as the strongest claim on
    the page is how Meta's opening named 37signals and Exxon's a gold miner."""
    state = competitive_state(Profile(),
                              [Rival("37signals LLC", rung="STRUCTURAL_PEER")])
    assert state["basis"] == COMPETITION_NONE
    assert state["rivals"] == ()


def test_a_same_model_peer_is_a_weaker_basis_than_evidence():
    state = competitive_state(
        Profile([Peer("Same Model Co", "SAME_MODEL_AND_SECTOR"),
                 Peer("Sector Mate", "SECTOR")]), ())
    assert state["basis"] == COMPETITION_FROM_MODEL
    assert state["rivals"] == ("Same Model Co",)


def test_a_sector_mate_is_weaker_still():
    state = competitive_state(Profile([Peer("Sector Mate", "SECTOR")]), ())
    assert state["basis"] == COMPETITION_FROM_SECTOR


def test_the_verb_matches_the_basis():
    """'Contested directly by' is an evidence claim and may not be said of a
    class-level peer list."""
    evidence = competitive_sentence(
        {"rivals": ("A",), "basis": COMPETITION_FROM_EVIDENCE})
    model = competitive_sentence(
        {"rivals": ("A",), "basis": COMPETITION_FROM_MODEL})
    sector = competitive_sentence(
        {"rivals": ("A",), "basis": COMPETITION_FROM_SECTOR})
    assert "contested directly by" in evidence
    assert "contested directly by" not in model
    assert "contested directly by" not in sector
    assert "named no rival" in model and "named no rival" in sector


# --- the contradiction, directly ----------------------------------------

@pytest.mark.parametrize("basis", [COMPETITION_FROM_MODEL,
                                   COMPETITION_FROM_SECTOR])
def test_qa_does_not_deny_what_step_one_asserts(basis):
    """THE DEFECT. level4_competition is empty and step 1 still names peers;
    Q&A must project the same state rather than reporting nothing."""
    read = Read(rows=(), rivals=("Banks", "Brokerage firms"), basis=basis)
    answer, intent = _route_answer("Who's the real competitor?", {}, read)
    assert intent == "competitor"
    assert "No competitor has been selected" not in answer
    assert "Banks" in answer


def test_named_rivals_are_still_described_in_full():
    read = Read(rows=(Rival("Named Rival"),), rivals=("Named Rival",),
                basis=COMPETITION_FROM_EVIDENCE)
    answer, _ = _route_answer("Who's the real competitor?", {}, read)
    assert "Named Rival" in answer and "Watch" in answer


def test_a_run_with_no_competitive_state_still_says_so():
    """Honest absence is not the defect; contradiction was."""
    read = Read()
    answer, _ = _route_answer("Who's the real competitor?", {}, read)
    assert "No competitor has been selected" in answer


def test_the_competitor_answer_is_not_gated_on_a_strategy():
    """A run may identify rivals and honestly withhold a recommendation.
    Whether a strategy was put forward says nothing about who the rivals
    are, and gating this on it is half the reason the two surfaces
    disagreed."""
    withheld = Read(rows=(Rival("Named Rival"),), rivals=("Named Rival",),
                    basis=COMPETITION_FROM_EVIDENCE, standing="READ_WITHHELD")
    assert withheld.puts_a_strategy_forward is False
    # Through the ROUTER, not the helper: the gate that caused half this
    # defect lives in `_from_read`, and calling `_competition_answer`
    # directly walks straight past it.
    answer, _ = _route_answer("Who's the real competitor?", {}, withheld)
    assert "Named Rival" in answer
    assert "No competitor has been selected" not in answer
    assert "Named Rival" in _competition_answer(withheld)


def test_both_surfaces_read_the_same_fields():
    """The seam, asserted structurally: if step 1 and Q&A ever stop sharing
    the state, this is the test that notices."""
    import inspect

    from intent_engine.executive import strategic_read as SR
    position = inspect.getsource(SR._position)
    assert "competitive_state(" in position
    qa = inspect.getsource(_competition_answer)
    assert "competitive_basis" in qa and "competitive_rivals" in qa


# =======================================================================
# The actual cause of the live 3-of-3: a populated list read as an absence
# =======================================================================
#
# MEASURED by executing the router against the real field name. The composed
# decision carried competitor ROWS, and `_route_answer` returned the absent
# copy for them — while SKIPPING the read fallback that would have answered
# correctly, precisely because `value` was truthy.
#
# It does not depend on the model class, the ladder, or the standing. All
# three live companies were "Our read: Bounded", so the strategy gate was
# open; all three had ladder rows, so step 1 was not overclaiming. It depends
# only on the SHAPE of the composed decision.

def test_a_populated_row_list_is_rendered_not_refused():
    read = Read(rows=(Rival("Named Rival"),), rivals=("Named Rival",),
                basis=COMPETITION_FROM_EVIDENCE)
    answer, _ = _route_answer(
        "Who's the real competitor?",
        {"competitors": [{"name": "Huawei Technologies Co",
                          "likely_response": "It matches on capability.",
                          "signal_to_watch": "accelerator pricing."}]},
        read)
    assert "No competitor has been selected" not in answer
    assert "Huawei Technologies Co" in answer
    assert "accelerator pricing" in answer
    # AND IT MUST BE A SENTENCE, NOT A REPR. Stringifying the row would
    # satisfy every assertion above while showing a chief executive
    # {'name': 'Huawei Technologies Co', 'likely_response': ...}.
    assert "{" not in answer and "'name'" not in answer


def test_a_plain_string_list_is_unchanged():
    read = Read()
    answer, _ = _route_answer(
        "Who's the real competitor?",
        {"competitors": ["Huawei", "Open-source AI"]}, read)
    assert answer == "Huawei; Open-source AI"


def test_an_unrenderable_row_asks_the_read_before_giving_up():
    """Refusing here is how a true statement came to look like a gap."""
    read = Read(rows=(Rival("Named Rival"),), rivals=("Named Rival",),
                basis=COMPETITION_FROM_EVIDENCE)
    answer, _ = _route_answer("Who's the real competitor?",
                              {"competitors": [{"unknown_key": ""}]}, read)
    assert "Named Rival" in answer


def test_an_empty_decision_still_reaches_the_read():
    read = Read(rows=(Rival("Named Rival"),), rivals=("Named Rival",),
                basis=COMPETITION_FROM_EVIDENCE)
    answer, _ = _route_answer("Who's the real competitor?",
                              {"competitors": []}, read)
    assert "Named Rival" in answer


def test_the_row_renderer_is_not_competitor_specific():
    """The same branch serves every intent whose field holds rows, so the
    repair is at the shape, not at one question."""
    from intent_engine.founder_brief.qa import _render_rows
    assert _render_rows([{"statement": "Watch deposit costs."}]) == \
        "Watch deposit costs."
    assert _render_rows([{"title": "Pricing", "why": "It moves margin."}]) == \
        "Pricing: It moves margin."
    assert _render_rows([]) == ""
    assert _render_rows([{"nothing_useful": ""}]) == ""
