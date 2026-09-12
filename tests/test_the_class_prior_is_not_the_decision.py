"""Seven companies may not share one central question (§9, §19, §21).

MEASURED across cohort A on 1b0d803c, reading the live X-Ray of each company:
SEVEN of nine were handed the identical central question --

    "what to charge, and for what, without losing more customer count than
     the price gains?"

-- with identical watch metrics, across four unrelated categories. Cohesity
and project44 shared 21 of 23 long sentences VERBATIM; the only differences
were the substituted company name. A freight-visibility platform, a
data-protection vendor, an integration platform and an event-intelligence
company were all told their decision was a seat-pricing decision.

THE CAUSE IS STRUCTURAL. `_score_archetypes` ranks the menu by the model
class's own ordering, adjusted by live economic channels and identified
posture. A private company has neither, so nothing company-specific reached
the ordering and the class prior WAS the answer. `select` already received the
company's own text and spent all of it on classification: its words decided
what KIND of business it is and then played no part in WHICH DECISION it
faces.

This is the second time a class prior has stood in for an answer in this
product, which under §21 makes it a systemic failure rather than an edge case:
the menu still comes from the model, and the ORDER may now be moved by the
subject's own record -- which is what this module's docstring already claimed.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import analysis_selection as A

SOFTWARE = "subscription software platform " * 40
FREIGHT = ("supply chain visibility. shipment tracking across carrier "
           "networks. tariff and customs delays. freight volumes. logistics. "
           "procurement and supplier data. ") * 8
#: A COMPANY FACING A REGULATOR, not a company with a trust page.
#:
#: The first version of this fixture read "regulation and compliance drive
#: demand. gdpr, hipaa and data residency. regulatory audit requirement.
#: sovereignty." Every one of those phrases is on the trust page of every
#: enterprise-software company alive, and cohort A proved it: Boomi, an
#: integration platform, was handed "how to respond to what the regulator has
#: done" on compliance, gdpr and hipaa. The fixture was demonstrating that
#: the evidence path works using text that cannot distinguish one company
#: from another, so it demonstrated the defect instead.
REGULATED = ("a new regulation takes effect next year and the regulatory "
             "deadline is fixed. we are preparing for the compliance "
             "obligation and the audit requirement. data residency and data "
             "sovereignty rules change what we may sell. an enforcement "
             "action against a peer set the precedent. ") * 8
#: A COMPANY DECIDING HOW IT SELLS, not a company that has a sales team.
#:
#: Same correction. "go-to-market motion. channel partner and reseller
#: programme. product-led growth and self-serve." is marketing copy, and on
#: cohort A two hits of it moved SALES_MOTION above the class prior for a
#: supply-chain planner, an event-intelligence firm and a storage vendor.
GTM = ("we are shifting to a partner-led route to market. channel conflict "
       "with our direct sales force is managed by quota capacity rules. "
       "reseller margin and partner concentration are reviewed each quarter, "
       "and customer acquisition cost and payback period both improved. ") * 8
PRICED = ("list price and discounting. our pricing model moved to consumption "
          "pricing. per-seat plans remain. price increase announced. ") * 8
PLAIN = "a software platform for teams to work better together. " * 20


@pytest.fixture()
def profile():
    p = A.profile_for("", name="X", domain="x.com", published_text=SOFTWARE)
    assert p.known and p.business_model_class == "SUBSCRIPTION_SOFTWARE"
    return p


def _top(profile, text):
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=text)
    return rows[0]["archetype"] if rows else "NONE"


# --- the collapse -----------------------------------------------------------

def test_two_companies_of_one_class_can_reach_different_decisions(profile):
    """THE DEFECT. Both are subscription software by class; their records are
    about different things, and the decision has to follow the record."""
    freight = _top(profile, FREIGHT)
    regulated = _top(profile, REGULATED)
    assert freight != regulated, (
        f"two companies sharing a business model received the same decision "
        f"({freight}) despite records about entirely different subjects")


@pytest.mark.parametrize("text,expected", [
    (FREIGHT, "SUPPLY_CHAIN"),
    (REGULATED, "REGULATORY_RESPONSE"),
    (GTM, "SALES_MOTION"),
    (PRICED, "PRICING"),
])
def test_the_decision_follows_the_company_s_own_record(profile, text,
                                                       expected):
    assert _top(profile, text) == expected


def test_an_off_menu_decision_can_outrank_the_class_prior(profile):
    """SUPPLY_CHAIN is not a standing decision for subscription software, so
    it starts at zero against a five-deep menu. A company whose entire record
    is about moving freight is not facing a seat-pricing decision, and an
    evidence path that cannot say so is decoration -- measured: with a flat
    bonus, seven distinct freight terms still lost to PRICING."""
    assert _top(profile, FREIGHT) == "SUPPLY_CHAIN"
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=FREIGHT)
    assert rows[0]["score"] > rows[1]["score"]


# --- and the limits on it ---------------------------------------------------

@pytest.mark.parametrize("mention", [
    # ON THE STANDING MENU, which is where the gate actually bites. A first
    # version used "regulation" -- an OFF-menu archetype that starts at zero
    # and loses to the class prior whatever the gate says, so the test passed
    # for the wrong reason and a break proof caught it: dropping the gate to
    # one hit left it green. RETENTION and SALES_MOTION sit second and third
    # on the software menu, close enough that one hit would flip them.
    "our churn was discussed at the board. ",
    # PHRASES THAT ARE STILL IN THE TABLE. The earlier list used "our
    # go-to-market is evolving" and "we have a channel partner", and once
    # those stopped being evidence at all this test passed without exercising
    # the gate -- a test that cannot fail. Both are replaced by single
    # mentions of phrases the repaired table DOES count, so one hit still has
    # to be refused on the gate rather than on the vocabulary.
    "we are reviewing our route to market. ",
    "channel conflict came up once. ",
    "a price increase was mentioned in passing. ",
])
def test_one_passing_mention_does_not_move_the_menu(profile, mention):
    """The applicability gate. Every company mentions churn somewhere, and a
    menu reordered by a coincidence is the same defect with more steps."""
    once = mention + PLAIN
    assert _top(profile, once) == "PRICING", (
        f"a single incidental phrase ({mention.strip()!r}) reordered the "
        f"decision menu")


def test_a_company_with_no_distinguishing_record_keeps_the_class_prior(
        profile):
    """NOT A FAILURE. When a company published nothing that shows which
    decision it faces, the business model is the best available answer and
    saying so is honest. Inventing a distinction would be worse."""
    assert _top(profile, PLAIN) == "PRICING"
    assert _top(profile, "") == "PRICING"


def test_a_pricing_company_still_gets_pricing_and_by_evidence(profile):
    """POSITIVE CONTROL. The repair must not push every company OFF pricing;
    a company genuinely deciding what to charge should have that reinforced by
    its own record rather than assumed from its class."""
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=PRICED)
    assert rows[0]["archetype"] == "PRICING"
    assert "own record discusses this decision" in rows[0]["why"], (
        "pricing was selected by the class prior even where the record "
        "evidences it")


def test_the_reason_names_the_terms_that_moved_it(profile):
    """A selection a reader cannot check is a selection they must trust."""
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=FREIGHT)
    why = rows[0]["why"]
    assert any(term in why for term in ("freight", "shipment", "carrier",
                                        "customs", "logistics")), why


def test_an_empty_record_yields_no_evidence_archetypes():
    assert A._evidence_archetypes("") == {}
    assert A._evidence_archetypes("too short") == {}


def test_a_measured_economic_channel_still_outweighs_a_bare_mention():
    """ORDER OF AUTHORITY. A measured condition reaching this business is
    stronger than the company having written about a subject twice."""
    assert A._evidence_bonus(2) < 4
    assert A._evidence_bonus(7) > 4


# --- the repair must be ON the path -----------------------------------------

def test_select_passes_the_company_s_own_text_to_the_ordering():
    """`own_text` DEFAULTS TO "". Every behavioural test above passes with a
    call site that never supplies it, and the live page would then order every
    company by its class forever."""
    import inspect
    src = inspect.getsource(A.select)
    assert "own_text=" in src, (
        "select() scores archetypes without the company's own record, so the "
        "class prior decides every company's question")
    assert "evidence_text" in src and "published_text" in src


# --- §7/§8: the cohort must be able to SEE which force won -------------------

def test_every_candidate_reports_what_moved_it(profile):
    """Without this a cohort cannot tell "these companies genuinely look
    alike" from "the class prior won again" -- the distinction it took seven
    identical X-Rays to notice."""
    rows = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                               own_text=FREIGHT)
    for row in rows:
        c = row["contributions"]
        for key in ("class_prior", "evidence", "econ", "posture",
                    "class_prior_only"):
            assert key in c, f"{row['archetype']} reports no {key}"
        assert c["class_prior_only"] is (
            not any(c[k] for k in ("evidence", "econ", "posture", "causal")))


def test_a_class_prior_only_decision_is_labelled_as_one(profile):
    top = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                              own_text=PLAIN)[0]
    assert top["archetype"] == "PRICING"
    assert top["contributions"]["class_prior_only"] is True, (
        "a decision reached purely by the model class's menu ordering was not "
        "marked as such, so a cohort-wide collapse would look like a finding")


def test_an_evidence_led_decision_names_the_terms(profile):
    top = A._score_archetypes(profile, A.RecordFacts(evidence=6),
                              own_text=FREIGHT)[0]
    c = top["contributions"]
    assert c["class_prior_only"] is False
    assert c["evidence"] > 0
    assert set(c.get("evidence_terms") or ()) & {
        "freight", "shipment", "carrier", "customs", "logistics"}, c
