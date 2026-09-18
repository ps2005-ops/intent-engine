"""Whose demand, which direction, and is it an observation at all.

The labelled corpus lives in `demand_corpus.py` and was written BEFORE this
detector existed, because a detector justified by the sentences its author
imagined is a detector that measures its author. Baseline for the phrase list
it replaces, on that corpus: PRECISION 0.50.

The four mistakes it made are each a different question, so they get separate
tests rather than a single accuracy number:

    the company BUYING              "we placed orders for new equipment"
    somebody else's demand          "Komatsu reported strong bookings growth"
    an expectation, not a fact      "we expect bookings to improve"
    the same word, another domain   "the team reduced its ticket backlog"
"""
from __future__ import annotations

import pytest

import demand_corpus as C
from intent_engine.market import demand_chain as DC
from intent_engine.market import demand_extraction as DX
from intent_engine.market import evidence_translation as ET
from intent_engine.market import micro_evidence as ME


def read(text: str):
    return DX.read(text, aliases=C.ALIASES)


# --- the corpus, as one number and as its parts -----------------------------

def test_precision_and_recall_on_the_labelled_corpus():
    """The headline. Both halves, because either alone is gameable.

    A detector that refuses everything scores perfect precision and a
    detector that accepts everything scores perfect recall.
    """
    got = C.score(lambda t: read(t).state)
    assert got["precision"] == 1.0, got["false_positive_examples"]
    assert got["recall"] == 1.0, got["missed"]


@pytest.mark.parametrize("row", C.POSITIVES, ids=lambda r: r.text[:40])
def test_every_positive_is_admitted_with_the_right_state(row):
    got = read(row.text)
    assert got.state == row.state
    assert got.role == DX.SELLER
    if row.direction:
        assert got.direction == row.direction


@pytest.mark.parametrize("row", C.NEGATIVES, ids=lambda r: r.text[:40])
def test_every_negative_is_refused(row):
    assert read(row.text).state is None


# --- the four questions, one at a time --------------------------------------

def test_the_company_buying_is_not_customer_demand():
    """The one that would put capex into a demand thesis."""
    got = read("We placed orders for new manufacturing equipment.")
    assert got.state is None
    assert got.reason == DX.WRONG_ROLE
    assert got.role == DX.BUYER
    # And the mirror image is admitted.
    assert read("Customer orders increased 18% year over year.").state == \
        "ORDERS"


def test_a_rivals_demand_is_not_ours():
    got = read("Komatsu reported strong bookings growth in its mining "
               "segment.")
    assert got.state is None
    assert got.reason == DX.WRONG_SUBJECT


def test_an_expectation_is_not_an_observation():
    got = read("We expect bookings to improve in the second half.")
    assert got.state is None
    assert got.reason == DX.SPECULATIVE
    assert got.standing == DX.EXPECTATION


def test_a_risk_is_not_a_decline():
    got = read("Orders could decline if tariffs persist.")
    assert got.state is None
    assert got.standing == DX.RISK


def test_the_same_word_in_another_domain():
    for sentence in ("The engineering team reduced its ticket backlog by 40%.",
                     "The court order requires disclosure of the settlement.",
                     "The effect is an order of magnitude smaller.",
                     "In order to reduce costs, two plants were merged."):
        assert read(sentence).state is None, sentence


def test_guidance_is_allowed_to_be_forward_looking():
    """The one state whose whole nature is an expectation.

    Applying the speculation gate to guidance would refuse every guidance
    sentence ever written.
    """
    got = read("We now expect full-year guidance of $8.00 to $8.50.")
    assert got.state == "GUIDANCE"


# --- direction and quantity -------------------------------------------------

def test_a_stated_level_is_flat_not_unknown():
    got = read("Contract liabilities were $7,280 million.")
    assert got.state == "COMMITTED_DEMAND"
    assert got.direction == DX.FLAT
    assert got.quantitative is True


def test_a_qualitative_reading_carries_no_false_precision():
    got = read("Strong order rates and a growing backlog reflect broadening "
               "momentum across all three of our primary segments.")
    assert got.state == "BACKLOG"
    assert got.direction == DX.UP
    assert got.quantitative is False
    assert got.quantity == ""


def test_two_directions_in_one_sentence_refuses_to_pick():
    """The quantity matters. Without one the sentence is refused anyway for
    having no direction at all, so the guard proves nothing; with one, a
    missing guard reads the level as FLAT and admits it."""
    got = read("Backlog rose to $37.5 billion while bookings fell 9%.")
    assert got.state is None
    assert got.reason == DX.NO_DIRECTION


def test_raising_guidance_has_a_direction():
    """A live refusal: 'Raises 2026 Guidance' read as having no direction."""
    assert read("CN raises 2026 guidance.").direction == DX.UP


def test_beating_estimates_is_a_result_not_a_forecast():
    """Twelve live revenue sentences were refused as speculation for the
    word 'estimates', which was naming the thing that got beaten."""
    got = read("Second-quarter revenue topped estimates at $20.5 billion.")
    assert got.state == "REVENUE"
    assert got.standing == DX.OBSERVATION


# --- refusal reasons are findings, not shrugs -------------------------------

def test_each_refusal_reports_the_reason_that_applies():
    cases = {
        "We placed orders for new manufacturing equipment.": DX.WRONG_ROLE,
        "Komatsu reported strong bookings growth.": DX.WRONG_SUBJECT,
        "We expect bookings to improve.": DX.SPECULATIVE,
        "Customers love the new excavator line.": DX.GENERIC_LANGUAGE,
        "The court order requires disclosure.": DX.NO_COMMERCIAL_OBJECT,
    }
    for sentence, reason in cases.items():
        assert read(sentence).reason == reason, sentence


def test_summarise_breaks_refusals_out_by_reason():
    readings = DX.read_all([row.text for row in C.ALL_ROWS],
                           aliases=C.ALIASES)
    got = DX.summarise(readings)
    assert got["admitted"] == len(C.POSITIVES)
    assert got["refused"] == len(C.NEGATIVES)
    assert set(got["by_reason"]) <= set(DX.REFUSAL_REASONS)
    assert len(got["by_reason"]) > 1, "one bucket cannot be acted on"


# --- the seam into canonical evidence ---------------------------------------

def test_a_demand_sentence_becomes_evidence():
    """The admission path. The commercial-event families return None for
    this sentence and it is still a commercial fact."""
    obs = [{"evidence_text":
            "Strong order rates and a growing backlog reflect broadening "
            "momentum across all three of our primary segments.",
            "kind": "filing", "source": "https://sec.gov/x",
            "published_at": "2026-08-01", "summary": "x"}]
    rows, _dropped, stats = ET.translate_with_stats(
        obs, subject_company="caterpillar", as_of="2026-08-09",
        subject_aliases=("Caterpillar", "CAT"))
    assert stats.by_type.get(ME.DEMAND_SIGNAL) == 1
    assert rows and rows[0].evidence_type == ME.DEMAND_SIGNAL


def test_a_wrong_role_sentence_does_not_become_evidence():
    """Named in the third person on purpose.

    "We placed orders" is caught by the first-person rule whether or not the
    seam threads aliases through, so it cannot show that the seam does. With
    the company named instead, only the alias rule can see that the buyer is
    us — and without it the sentence is admitted as customer ORDERS.
    """
    obs = [{"evidence_text":
            "Caterpillar placed orders for new manufacturing equipment.",
            "kind": "filing", "source": "https://sec.gov/x",
            "published_at": "2026-08-01", "summary": "x"}]
    rows, _dropped, stats = ET.translate_with_stats(
        obs, subject_company="caterpillar", as_of="2026-08-09",
        subject_aliases=("Caterpillar", "CAT"))
    assert ME.DEMAND_SIGNAL not in stats.by_type
    assert "demand_wrong_role" in stats.by_reason


def test_demand_signal_is_a_constructible_type():
    assert ME.DEMAND_SIGNAL in ME.EVIDENCE_TYPES


# --- the read side ----------------------------------------------------------

def _row(fact: str) -> dict:
    return {"record": "evidence", "subject_company": "caterpillar",
            "source_role": "regulatory_filing", "evidence_id": "e1",
            "observed_at": "2026-08-01", "fact": fact}


def test_demand_chain_uses_the_same_reader():
    """The chain and the admission path must not disagree about a sentence."""
    states = DC.read_states(
        [_row("Strong order rates and a growing backlog reflect broadening "
              "momentum across all three of our primary segments.")],
        company_id="caterpillar", aliases=("Caterpillar", "CAT"))
    assert "BACKLOG" in states
    assert states["BACKLOG"].direction == "UP"


def test_demand_chain_refuses_the_procurement_sentence():
    states = DC.read_states(
        [_row("We placed orders for new manufacturing equipment.")],
        company_id="caterpillar", aliases=("Caterpillar", "CAT"))
    assert states == {}


def test_a_customer_case_study_is_not_our_demand():
    """A live refusal worth keeping: a vendor's own site describing what a
    CUSTOMER achieved. The revenue is the customer's."""
    states = DC.read_states(
        [_row("See how Russell Hendrix, Canada's largest food service "
              "equipment supplier, increased B2B online orders by 43% and "
              "revenue by 20%.")],
        company_id="shopify", aliases=("Shopify",))
    assert states == {}
