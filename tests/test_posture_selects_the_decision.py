"""The identified operating posture must select the decision.

WHAT WENT WRONG. The market engine identifies which of seventeen operating
postures a company is in. The founder's selection layer collapsed all
seventeen into one rule -- "+3 to pricing and competitive response" -- so a
company cutting cost and a company preparing an acquisition were steered to
the same decision. The engine's most company-specific output was discarded
at the exact point it should have decided the analysis.

WHY IT WAS INVISIBLE. The decision question is a function of (business
model, archetype). The measurement that closed the FIRST template collapse
compared Cloudflare, Caterpillar and Johnson & Johnson -- three different
business models -- and read 0.000 overlap. Within a model class nothing was
measured, and 21 of the 100 manifest companies are subscription software.
All 21 got the pricing question.

These tests measure WITHIN a business model class, which is the measurement
that was missing.
"""
import pytest

from intent_engine.executive import analysis_selection as AS

F = AS.RecordFacts

#: All subscription software, so the business model cannot be what separates
#: them. Anything that differs here differs because of the record.
SAME_MODEL = [
    ("cloudflare", "Cloudflare, Inc.", "COST_CUTTING", "COST_STRUCTURE"),
    ("shopify", "Shopify Inc.", "GROWING", "SALES_MOTION"),
    ("palantir-technologies", "Palantir Technologies Inc.",
     "PREPARING_ACQUISITION", "M&A"),
    ("datadog", "Datadog, Inc.", "DEFENDING", "RETENTION"),
    ("snowflake", "Snowflake Inc.", "REGULATORY_DEFENSIVE",
     "REGULATORY_RESPONSE"),
    ("salesforce", "Salesforce, Inc.", "CAPITAL_CONSTRAINED",
     "CAPITAL_ALLOCATION"),
    ("workday", "Workday, Inc.", "EXPANDING", "CAPACITY"),
]


@pytest.mark.parametrize("cid,name,posture,expected", SAME_MODEL)
def test_the_posture_selects_the_archetype(cid, name, posture, expected):
    sel = AS.select(cid, name=name,
                    facts=F(evidence=20, beliefs=3, hidden_state=posture))
    assert sel.archetype == expected


def test_one_business_model_does_not_produce_one_question():
    """The regression that matters: seven subscription-software companies in
    seven different observed postures must face seven different decisions."""
    bodies = set()
    for cid, name, posture, _ in SAME_MODEL:
        sel = AS.select(cid, name=name,
                        facts=F(evidence=20, beliefs=3, hidden_state=posture))
        # Strip the company name, which differs trivially. What must differ
        # is the QUESTION, not the label on it.
        bodies.add(sel.decision_question.split(":", 1)[-1].strip())
    assert len(bodies) == len(SAME_MODEL), (
        f"{len(bodies)} distinct questions for {len(SAME_MODEL)} companies "
        f"of the same business model")


def test_an_observation_outranks_the_business_model_prior():
    """A company observed cutting cost faces a cost decision even though
    pricing leads the subscription-software menu."""
    generic = AS.select("cloudflare", name="Cloudflare, Inc.",
                        facts=F(evidence=20))
    observed = AS.select("cloudflare", name="Cloudflare, Inc.",
                         facts=F(evidence=20, hidden_state="COST_CUTTING"))
    assert generic.archetype == "PRICING"           # the model's own prior
    assert observed.archetype == "COST_STRUCTURE"   # the observation wins


def test_a_posture_added_archetype_declares_it_is_not_standing():
    """It must be visible that this decision is on the list because of the
    record and not because the business model implies it."""
    sel = AS.select("cloudflare", name="Cloudflare, Inc.",
                    facts=F(evidence=20, hidden_state="COST_CUTTING"))
    why = sel.why_this_question.lower()
    assert "not a standing decision" in why
    assert "cutting cost" in why


# --- the refusals ----------------------------------------------------------

def test_no_identified_posture_changes_nothing():
    """A run STATUS is not a posture and must never select a decision."""
    baseline = AS.select("cloudflare", name="Cloudflare, Inc.",
                         facts=F(evidence=20))
    for status in ("TRACKED_NO_IDENTIFIED_STATE", "HIDDEN_STATE_NOT_RUN",
                   "HIDDEN_STATE_NONE_TRACKED", "", "UNKNOWN"):
        sel = AS.select("cloudflare", name="Cloudflare, Inc.",
                        facts=F(evidence=20, hidden_state=status))
        assert sel.archetype == baseline.archetype
        assert sel.decision_question == baseline.decision_question


def test_waiting_selects_nothing():
    """A company that is waiting has not committed to a decision, so nothing
    may be inferred about which one it faces."""
    baseline = AS.select("cloudflare", name="Cloudflare, Inc.",
                         facts=F(evidence=20))
    waiting = AS.select("cloudflare", name="Cloudflare, Inc.",
                        facts=F(evidence=20, hidden_state="WAITING"))
    assert waiting.archetype == baseline.archetype


def test_an_unrecognised_posture_does_not_invent_a_decision():
    """A posture this build has no mapping for must fall back to the standing
    menu, not to an arbitrary archetype."""
    sel = AS.select("cloudflare", name="Cloudflare, Inc.",
                    facts=F(evidence=20, hidden_state="SOME_NEW_STATE"))
    assert sel.archetype in AS.profile_for(
        "cloudflare", name="Cloudflare, Inc.").decision_archetypes


def test_posture_cannot_specialise_an_unclassified_company():
    """The posture extends a menu; a company with no menu still has none.
    Otherwise an unknown company would get a confident decision from a
    single observation."""
    sel = AS.select("nowhere-ltd", name="Nowhere Ltd",
                    facts=F(evidence=20, hidden_state="COST_CUTTING"))
    assert sel.archetype == "UNKNOWN"
    assert sel.signals == ()


# --- the question must be grammatical for every driver it names ------------

def test_the_question_agrees_with_a_plural_driver():
    """The driver and cost slots hold noun phrases that may be singular
    ("customer count") or plural ("orders and backlog"), and no single
    conjugation is correct for both. "supply chain and component availability
    IS committed before the orders and backlog it is meant to serve ARRIVES"
    reached a customer, so the tails put the slot where it governs no verb.
    """
    from intent_engine.validation import load as load_manifest
    manifest = load_manifest()
    bad = ("serve arrives", "availability is committed", "backlog is known",
           "availability sets")
    for company in manifest.companies:
        for posture in ("", "CAPACITY_CONSTRAINED", "GROWING", "COST_CUTTING"):
            question = AS.select(
                company.company_id, name=company.canonical_name,
                manifest=manifest,
                facts=F(evidence=20, hidden_state=posture)).decision_question
            for phrase in bad:
                assert phrase not in question, (
                    f"{company.company_id}/{posture or 'no posture'}: "
                    f"{question}")
