"""Actor relationships — and the measured reason the graph is still empty.

interaction_binding is built and returns zero because nothing records that two
companies are rivals. This is the prerequisite. The refusals are the valuable
part: a relationship graph that admits "our competitors include other large
technology companies" connects nothing while looking exactly like one that
connects something.
"""
import pytest

from intent_engine.market import actor_relationships as AR


def _rel(**kw):
    base = dict(subject_actor="Acme Corp", predicate=AR.COMPETES_WITH,
                object_actor="Wayne Industries", evidence_ids=("ev_1",),
                source_document="doc:10-K", subject_span="Acme Corp",
                object_span="Wayne Industries",
                relationship_span="Acme Corp competes with Wayne Industries.")
    base.update(kw)
    return AR.relationship(**base)


# ===========================================================================
# WHAT MAY NOT ENTER THE GRAPH
# ===========================================================================
@pytest.mark.parametrize("category", [
    "other large technology companies", "various competitors",
    "certain suppliers", "third parties", "our top ten customers",
    "numerous firms", "many providers", "several players",
])
def test_a_category_is_not_a_counterparty(category):
    """These are the exact phrases real filings use.

    Measured across five large-cap filings and 3959 sentences: every single
    relationship-shaped sentence named a category rather than a party.
    """
    with pytest.raises(AR.RelationshipRejected):
        _rel(object_actor=category)


def test_a_relationship_with_no_evidence_is_model_knowledge():
    """"Microsoft competes with AWS" is common knowledge and still refused.

    A graph that mixes what was read with what was already believed cannot be
    audited afterwards.
    """
    with pytest.raises(AR.RelationshipRejected):
        _rel(evidence_ids=())


def test_a_relationship_needs_the_span_that_states_it():
    with pytest.raises(AR.RelationshipRejected):
        _rel(relationship_span="   ")


def test_an_actor_cannot_relate_to_itself():
    with pytest.raises(AR.RelationshipRejected):
        _rel(object_actor="Acme Corp")


def test_unknown_predicates_and_statuses_are_refused():
    with pytest.raises(AR.RelationshipRejected):
        _rel(predicate="VIBES_WITH")
    with pytest.raises(AR.RelationshipRejected):
        _rel(epistemic_status="PROBABLY")


def test_same_sector_alone_creates_nothing():
    """No API path exists from 'same industry' to an edge. Sector adjacency
    is what produced the fabricated ASML/Infosys interaction."""
    assert not hasattr(AR, "from_sector")
    assert not hasattr(AR, "infer_competitors")


# ===========================================================================
# WHAT MAY
# ===========================================================================
def test_a_stated_relationship_with_two_named_parties_is_observed():
    row = _rel()
    assert row.epistemic_status == AR.OBSERVED
    assert row.subject_span and row.object_span and row.relationship_span


def test_extraction_requires_a_named_counterparty_after_the_predicate():
    rows, refused = AR.extract(
        [("Acme Corp competes with Wayne Industries in North America.",
          "doc:1")], subject_actor="Acme Corp")
    assert len(rows) == 1 and rows[0].object_actor.startswith("Wayne")

    # Refused either as an unnamed counterparty or as a category,
    # depending on capitalisation. WHICH guard fires is an implementation
    # detail; that nothing enters the graph is the property.
    rows, refused = AR.extract(
        [("Acme Corp competes with other large technology companies.",
          "doc:1")], subject_actor="Acme Corp")
    assert rows == ()
    assert sum(refused.values()) == 1

    rows, refused = AR.extract(
        [("Acme Corp competes with Other large technology companies.",
          "doc:1")], subject_actor="Acme Corp")
    assert rows == ()
    assert refused["counterparty_is_a_category"] == 1


def test_regulated_by_reverses_the_direction():
    rows, _ = AR.extract(
        [("Acme Corp is regulated by the Federal Reserve.", "doc:1")],
        subject_actor="Acme Corp")
    assert rows and rows[0].predicate == AR.REGULATES
    assert rows[0].object_actor == "Acme Corp"


def test_the_competitor_map_is_symmetric():
    """If A's filing names B a rival, either may respond to the other."""
    mapping = AR.competitor_map([_rel()])
    assert "wayne industries" in mapping["acme corp"]
    assert "acme corp" in mapping["wayne industries"]


def test_the_competitor_map_ignores_non_rival_predicates():
    assert AR.competitor_map([_rel(predicate=AR.PARTNERS_WITH)]) == {}
