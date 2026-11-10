"""A 10-K's ordinary register is not a company deciding anything.

WHAT THIS PINS
--------------
MEASURED live on 2c8c071b. Rubrik — a LEVEL A filer with 32 filings — was
handed "what to buy or sell, and at what price, measured against building the
same customer count internally?" on the evidence

    acquired by, acquisition of, combination with

which is the wording of an ASC 805 business-combination note. Essentially
every 10-K contains it, whether or not the company is buying anything.

THE AUDIT THAT MISSED IT. The evidence table had already been rewritten once
to be decision-bearing rather than topical, and M&A was passed because its
phrases name TRANSACTIONS rather than subjects. They do. But that audit was
done against a software marketing page, and a filing is a different register:
its mandatory disclosures use transaction and metric language as a matter of
form. Measured against an ordinary 10-K paragraph, FOUR archetypes fired on
text in which nothing was decided — capital allocation, cost structure, M&A
and retention, three hits each.

AND THE ALPHABET DECIDED THE TIE. Rubrik's PRICING (class prior, base 5) tied
M&A (off-menu, evidence 5) and lost, because the sort key ended in the
archetype NAME and "M&A" sorts before "PRICING". The same tie went the other
way for HYCU, whose REGULATORY_RESPONSE tied PRICING at 5 and lost because
"P" < "R". A tie is not evidence outranking the prior.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import analysis_selection as A
from intent_engine.executive.analysis_selection import (
    _evidence_archetypes, _evidence_bonus,
)

#: An ordinary 10-K paragraph. Every sentence is a mandatory disclosure or an
#: accounting-policy note, and NOTHING in it is a decision.
FILING_REGISTER = (
    "The accompanying consolidated financial statements include the accounts "
    "of the Company and its wholly owned subsidiaries. The acquisition of "
    "Datos IO was accounted for as a business combination with the fair value "
    "of consideration transferred allocated to the assets acquired by the "
    "Company. Gross margin was 77% compared with 75%. Operating leverage "
    "improved. Free cash flow was negative. Capital expenditure totalled "
    "$12.4 million. We have never declared or paid any cash dividend on our "
    "capital stock. Net revenue retention was 133%. Churn remained low and "
    "expansion revenue grew. Research and development expense increased. "
    "Headcount grew to 3,000. ") * 6

#: The same subjects, but a company ACTING on them.
DECIDING = (
    "We announced the acquisition of Acme and signed a definitive agreement. "
    "We also completed the divestiture of our hardware line. The board "
    "approved a share repurchase programme and we initiated a dividend. A "
    "restructuring charge was recorded as part of a workforce reduction. Our "
    "customer retention programme and customer success investment were "
    "expanded after renewal risk rose. ") * 6


@pytest.fixture()
def profile():
    p = A.profile_for("", name="X", domain="x.com",
                      published_text="subscription software platform " * 40)
    assert p.business_model_class == "SUBSCRIPTION_SOFTWARE"
    return p


def _top(profile, text):
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=text)
    return rows[0]["archetype"] if rows else "NONE"


# --- the register -----------------------------------------------------------

def test_an_ordinary_filing_paragraph_decides_nothing():
    assert _evidence_archetypes(FILING_REGISTER) == {}


def test_the_filing_control_is_long_enough_and_really_contains_the_words():
    """A negative control that passes by being empty proves nothing."""
    assert len(" ".join(FILING_REGISTER.split())) > 200
    for phrase in ("acquisition of", "acquired by", "business combination",
                   "gross margin", "operating leverage", "free cash flow",
                   "capital expenditure", "dividend", "net revenue retention",
                   "churn", "expansion revenue", "headcount"):
        assert phrase in FILING_REGISTER.lower(), phrase


def test_a_filer_is_not_handed_an_acquisitions_decision(profile):
    assert _top(profile, FILING_REGISTER) == "PRICING"


@pytest.mark.parametrize("archetype", [
    "M&A", "CAPITAL_ALLOCATION", "COST_STRUCTURE", "RETENTION",
])
def test_each_repaired_entry_is_still_reachable(archetype):
    """The repair must narrow the path, not close it."""
    shown = _evidence_archetypes(DECIDING)
    assert archetype in shown, sorted(shown)
    hits, phrases = shown[archetype]
    assert hits >= 2, (archetype, phrases)


# --- the tie-break ----------------------------------------------------------

def _off_menu_text(n):
    terms = ["announced the acquisition", "definitive agreement",
             "we acquired", "divested", "tender offer", "merger agreement"]
    return (". ".join(terms[:n]) + ". we build software for teams. ") * 8


def test_an_off_menu_archetype_that_only_ties_does_not_displace_the_prior(
        profile):
    """THE DEFECT. Equal is not more, and the name is not a reason."""
    for n in (2, 3, 4):
        text = _off_menu_text(n)
        rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                                   own_text=text)
        winner = rows[0]
        pricing = [r for r in rows if r["archetype"] == "PRICING"][0]
        assert winner["score"] >= pricing["score"]
        assert winner["archetype"] == "PRICING", (
            f"{winner['archetype']} displaced the class prior on a score of "
            f"{winner['score']} against {pricing['score']} — a tie decided by "
            f"the archetype's name")


def test_an_off_menu_archetype_that_strictly_exceeds_still_wins(profile):
    """And the path is not closed: enough evidence still displaces."""
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=_off_menu_text(5))
    assert rows[0]["archetype"] == "M&A"
    pricing = [r for r in rows if r["archetype"] == "PRICING"][0]
    assert rows[0]["score"] > pricing["score"]


def test_the_sort_does_not_end_on_the_archetype_name_alone():
    """Read from the running code: the tie-break must be a REASON."""
    import inspect

    src = inspect.getsource(A._score_archetypes)
    assert 'rows.sort(key=lambda r: (-r["score"], r["archetype"]))' not in src, \
        "ties are decided by dictionary order of the enum name"
    assert "standing_set" in src, "the tie-break does not consult the menu"


def test_a_standing_archetype_keeps_the_menu_order_on_a_tie(profile):
    """Within the menu, the prior's own ordering decides, not the alphabet."""
    rows = A._score_archetypes(profile, A.RecordFacts(), own_text="")
    names = [r["archetype"] for r in rows[:len(profile.decision_archetypes)]]
    assert names == list(profile.decision_archetypes), names
