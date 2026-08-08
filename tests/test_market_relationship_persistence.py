"""A learning system that forgets on restart is not learning.

Three valid COMPETES_WITH edges were discovered in wave 5, reported, and
measured as ZERO in wave 10. Nothing had gone wrong at extraction: the store
had `record_evidence`, `record_expectation`, `record_cycle`,
`record_reconciliation` and `record_lifecycle`, and no way to record a
relationship at all. The seam was not broken; it did not exist.
"""
from __future__ import annotations

import pytest

from intent_engine.market import actor_relationships as AR
from intent_engine.market import learning_store as LS


def edge(**kw):
    base = dict(relationship_id="rel_1", subject_actor_id="Shopify",
                object_actor_id="Magento", predicate=AR.COMPETES_WITH,
                competitive_object="E-commerce platform",
                buyer_or_market="VIA VAI", subject_kind=AR.LEGAL_ENTITY,
                object_kind=AR.LEGAL_ENTITY, epistemic_status=AR.OBSERVED,
                evidence_ids=["ev_1"], source_document_ids=["https://x/1"],
                relationship_span="VIA VAI migrated from Magento to Shopify",
                created_at="2026-08-08")
    base.update(kw)
    return base


@pytest.fixture()
def store(tmp_path):
    return LS.LearningStore(tmp_path / "ledger.jsonl")


# --- it survives a different process --------------------------------------

def test_a_relationship_survives_a_fresh_store(tmp_path):
    """The whole point. A second LearningStore over the same file has
    nothing in memory — only what was written down."""
    path = tmp_path / "ledger.jsonl"
    assert LS.LearningStore(path).record_relationship(edge()) is True
    reloaded = LS.LearningStore(path).relationships()
    assert len(reloaded) == 1
    assert reloaded[0]["predicate"] == AR.COMPETES_WITH
    assert reloaded[0]["competitive_object"] == "E-commerce platform"
    assert reloaded[0]["buyer_or_market"] == "VIA VAI"


def test_the_scope_is_persisted_not_just_the_pair():
    """"Shopify competes with Magento" is not the claim. WHAT they contest
    and FOR WHOM is what makes a rivalry actionable."""
    key = LS.relationship_scope(edge())
    assert "e-commerce platform" in key
    assert "competes_with" in key.lower()


# --- idempotency ----------------------------------------------------------

def test_the_same_relationship_twice_is_one_edge(store):
    assert store.record_relationship(edge()) is True
    assert store.record_relationship(edge()) is False
    assert len(store.relationships()) == 1


def test_re_deriving_after_an_extractor_change_is_still_one_edge(store):
    """Ids are content hashes and move when patterns change. Keying identity
    on the id would create a second edge for the same rivalry."""
    store.record_relationship(edge(relationship_id="rel_1"))
    store.record_relationship(edge(relationship_id="rel_MOVED"))
    assert len(store.relationships()) == 1


def test_a_symmetric_predicate_ignores_direction(store):
    """The same rivalry read off Shopify's page and off Magento's page is
    one edge; rivalry is mutual."""
    store.record_relationship(edge())
    store.record_relationship(edge(subject_actor_id="Magento",
                                   object_actor_id="Shopify"))
    assert len(store.relationships()) == 1


def test_an_asymmetric_predicate_keeps_its_direction(store):
    """Supplying is not being supplied."""
    store.record_relationship(edge(predicate=AR.SUPPLIES,
                                   competitive_object=""))
    store.record_relationship(edge(predicate=AR.SUPPLIES,
                                   competitive_object="",
                                   subject_actor_id="Magento",
                                   object_actor_id="Shopify"))
    assert len(store.relationships()) == 2


def test_a_different_contested_object_is_a_different_claim(store):
    """The same two companies may contest more than one thing, and
    collapsing them would lose the scope."""
    store.record_relationship(edge())
    store.record_relationship(edge(competitive_object="Field service"))
    assert len(store.relationships()) == 2


# --- history is append-only -----------------------------------------------

def test_new_evidence_appends_support_rather_than_a_second_edge(store):
    store.record_relationship(edge())
    store.record_relationship(edge(evidence_ids=["ev_2"]))
    assert len(store.relationships()) == 1
    support = [r for r in store._rows()
               if r.get("record") == LS.RELATIONSHIP_SUPPORT]
    assert support and support[0]["evidence_ids"] == ["ev_2"]


def test_retiring_a_relationship_never_deletes_the_claim(store):
    store.record_relationship(edge())
    assert store.retire_relationship("rel_1", reason="the merchant moved back",
                                     as_of="2026-09-01") is True
    assert store.relationships() == ()
    # The row that asserted it is still there.
    assert len(store.relationships(include_retired=True)) == 1


def test_a_retirement_with_no_reason_is_refused(store):
    store.record_relationship(edge())
    with pytest.raises(ValueError, match="cannot be audited"):
        store.retire_relationship("rel_1", reason="  ", as_of="2026-09-01")


# --- a preregistration that does not survive is not a preregistration -----

def expectation(**kw):
    base = dict(expectation_id="cax_1", interaction_id="int_1",
                trigger_actor="Shopify", counterparty="Salesforce",
                competitive_object="E-commerce platform",
                mechanism="the same enterprise buyer is being contested",
                expected_response_class="PRICE_CHANGE",
                resolution_window="2026-11-08", created_at="2026-08-08")
    base.update(kw)
    return base


def test_a_preregistration_survives_a_fresh_store(tmp_path):
    """Its entire claim is that it existed BEFORE the evidence, and an
    in-memory object cannot make that claim to anybody."""
    path = tmp_path / "ledger.jsonl"
    assert LS.LearningStore(path).record_cross_actor_expectation(
        expectation()) is True
    reloaded = LS.LearningStore(path).cross_actor_expectations()
    assert len(reloaded) == 1
    assert reloaded[0]["created_at"] == "2026-08-08"


def test_registering_the_same_expectation_twice_is_one_test(store):
    store.record_cross_actor_expectation(expectation())
    assert store.record_cross_actor_expectation(expectation()) is False
    assert len(store.cross_actor_expectations()) == 1


def test_an_outcome_needs_a_preregistered_expectation(store):
    """An outcome for an expectation nobody wrote down is exactly the
    retroactive story preregistration exists to prevent."""
    with pytest.raises(ValueError, match="never written down"):
        store.record_cross_actor_outcome(
            expectation_id="cax_never", outcome="CONFIRMED",
            observed_at="2026-09-01")


def test_the_outcome_is_a_separate_row_from_the_expectation(store):
    """Editing the expectation to carry its own outcome would destroy the
    evidence that it was written before the answer."""
    store.record_cross_actor_expectation(expectation())
    store.record_cross_actor_outcome(expectation_id="cax_1",
                                     outcome="CONFIRMED",
                                     observed_at="2026-09-01",
                                     evidence_ids=["ev_9"])
    (written,) = store.cross_actor_expectations()
    assert "outcome" not in written
    outcomes = [r for r in store._rows()
                if r.get("record") == LS.CROSS_ACTOR_OUTCOME]
    assert outcomes[0]["outcome"] == "CONFIRMED"


# --- the NIGHTLY CYCLE, not just the API ----------------------------------

def test_the_acquisition_step_persists_what_it_accepts(tmp_path, monkeypatch):
    """The line that was missing for six waves.

    Wave 5 discovered three valid rivalries, the run report carried them, and
    the next process saw none of it — `accepted` went into a payload and
    nowhere else. This asserts the step itself writes.
    """
    from intent_engine.market import steps as ST
    from intent_engine.market import counterparty_sources as CS
    from intent_engine.market import cycle as C

    made = AR.relationship(
        subject_actor="Cloudflare, Inc.", predicate=AR.SELLS_TO,
        object_actor="Federal Acquisition Service",
        subject_kind=AR.LEGAL_ENTITY, object_kind=AR.GOVERNMENT,
        evidence_ids=("usaspending:1",), source_document="https://x/1",
        subject_span="Cloudflare, Inc.",
        object_span="Federal Acquisition Service",
        relationship_span="Cloudflare received award 1",
        created_at="2026-08-08")

    class _Report:
        def as_dict(self):
            return {"family": "government_award"}

        def verdict(self):
            return (CS.INTEGRATE, "measured")

    monkeypatch.setattr(CS, "measure",
                        lambda *a, **k: ((made,), _Report()))
    (tmp_path / "reports" / "market").mkdir(parents=True)
    ctx = C.CycleContext(cycle="market", as_of="2026-08-08", root=tmp_path,
                         session=None, run_id="r1")
    payload = ST.source_acquisition_step(ctx)

    assert payload["summary"]["relationships_accepted"] >= 1
    assert payload["summary"]["relationships_persisted"] >= 1
    assert payload["summary"]["persistence_gap"] == 0
    # And a FRESH store over the same file sees it.
    assert LS.LearningStore(tmp_path / LS.DEFAULT_PATH).relationships()


def test_a_second_identical_cycle_adds_no_second_edge(store):
    """Re-running the same night must not double the graph."""
    assert store.record_relationship(edge()) is True
    assert store.record_relationship(edge()) is False
    assert len(store.relationships()) == 1


def test_a_rivalry_with_no_contested_object_is_refused(store):
    """Its scope key would be empty, so every future claim about these two
    companies would collapse into this one edge."""
    with pytest.raises(ValueError, match="no competitive object"):
        store.record_relationship(edge(competitive_object=""))
