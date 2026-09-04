"""'What changed your mind?' is answered from records, or it is not answered."""
from __future__ import annotations

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import thesis_history as TH


def mech(statement="rates rose so capex was deferred",
         falsifier="capex guidance is raised"):
    return ET.Mechanism(description=statement, falsifier=falsifier)


def thesis(*, standing=ET.PROPOSED, supporting=(), contradicting=(),
           alternatives=None, claim="capex will fall", as_of="2026-08-01"):
    if alternatives is None:
        alternatives = (mech("the programme was precommitted",
                             "a new programme is announced"),)
    return ET.EconomicThesis(
        subject="acme", question="will capex fall?", claim=claim,
        leading_mechanism=mech(), alternatives=tuple(alternatives),
        supporting_evidence=tuple(supporting),
        contradicting_evidence=tuple(contradicting),
        standing=standing, as_of=as_of)


# --- a transition must name its cause ----------------------------------------

def test_a_transition_explained_only_by_prose_is_refused():
    with pytest.raises(TH.RevisionRejected) as err:
        TH.ThesisRevision(
            thesis_id="th_1", transition=TH.WEAKENED,
            previous_standing=ET.PROPOSED, new_standing=ET.WEAKENED,
            reason="it felt weaker", changed_at="2026-08-09")
    assert "narration of a change, not a record of one" in str(err.value)


def test_creation_needs_no_prior_cause():
    got = TH.ThesisRevision(
        thesis_id="th_1", transition=TH.CREATED,
        previous_standing="", new_standing=ET.PROPOSED,
        reason="stated from the transmission", changed_at="2026-08-01")
    assert got.revision_id.startswith("rev_")


def test_an_unexplained_revision_is_refused():
    with pytest.raises(TH.RevisionRejected) as err:
        TH.ThesisRevision(
            thesis_id="th_1", transition=TH.CREATED, previous_standing="",
            new_standing=ET.PROPOSED, reason="   ", changed_at="2026-08-01")
    assert "cannot answer the one question it exists for" in str(err.value)


def test_strengthening_on_evidence_alone_is_refused():
    """A claim may only become more believed on evidence that CHANGED something."""
    with pytest.raises(TH.RevisionRejected) as err:
        TH.ThesisRevision(
            thesis_id="th_1", transition=TH.STRENGTHENED,
            previous_standing=ET.PROPOSED, new_standing=ET.SUPPORTED,
            reason="another article said so", changed_at="2026-08-09",
            triggering_evidence=("ev_9",))
    assert "evidence that CHANGED something" in str(err.value)


def test_strengthening_backed_by_an_effect_is_allowed():
    got = TH.ThesisRevision(
        thesis_id="th_1", transition=TH.STRENGTHENED,
        previous_standing=ET.PROPOSED, new_standing=ET.SUPPORTED,
        reason="the filing moved the exposure", changed_at="2026-08-09",
        knowledge_effect_ids=("ke_1",))
    assert got.raises_standing is True


def test_weakening_may_rest_on_triggering_evidence():
    """Doubting a claim on thin grounds is not the failure mode guarded here."""
    got = TH.ThesisRevision(
        thesis_id="th_1", transition=TH.WEAKENED,
        previous_standing=ET.SUPPORTED, new_standing=ET.WEAKENED,
        reason="a contradicting account arrived", changed_at="2026-08-09",
        triggering_evidence=("ev_4",))
    assert got.transition == TH.WEAKENED


def test_an_alternative_may_not_vanish_without_a_named_cause():
    with pytest.raises(TH.RevisionRejected) as err:
        TH.ThesisRevision(
            thesis_id="th_1", transition=TH.CREATED, previous_standing="",
            new_standing=ET.PROPOSED, reason="tidied", changed_at="2026-08-09",
            alternatives_before=("the programme was precommitted",),
            alternatives_after=())
    assert "disappeared without evidence eliminating them" in str(err.value)


# --- the chain is append-only and contiguous ---------------------------------

def test_a_revision_whose_parent_is_not_the_head_is_refused():
    history = TH.ThesisHistory()
    first = history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.CREATED, previous_standing="",
        new_standing=ET.PROPOSED, reason="stated", changed_at="2026-08-01"))
    with pytest.raises(TH.RevisionRejected) as err:
        history.append(TH.ThesisRevision(
            thesis_id="th_1", transition=TH.WEAKENED,
            previous_standing=ET.PROPOSED, new_standing=ET.WEAKENED,
            reason="contradicted", changed_at="2026-08-09",
            previous_revision="", triggering_evidence=("ev_1",)))
    assert "fork silently" in str(err.value)
    assert history.head("th_1") == first.revision_id


def test_a_contiguous_chain_is_accepted_and_ordered():
    history = TH.ThesisHistory()
    first = history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.CREATED, previous_standing="",
        new_standing=ET.PROPOSED, reason="stated", changed_at="2026-08-01"))
    second = history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.WEAKENED,
        previous_standing=ET.PROPOSED, new_standing=ET.WEAKENED,
        reason="a contradicting account arrived", changed_at="2026-08-09",
        previous_revision=first.revision_id, triggering_evidence=("ev_1",)))
    assert [r.revision_id for r in history.chain("th_1")] == [
        first.revision_id, second.revision_id]


def test_two_theses_keep_independent_chains():
    history = TH.ThesisHistory()
    for tid in ("th_1", "th_2"):
        history.append(TH.ThesisRevision(
            thesis_id=tid, transition=TH.CREATED, previous_standing="",
            new_standing=ET.PROPOSED, reason="stated",
            changed_at="2026-08-01"))
    assert len(history.chain("th_1")) == 1
    assert len(history.chain("th_2")) == 1


# --- the diff is over data, not prose ----------------------------------------

def test_the_diff_names_the_fields_that_actually_differ():
    before = thesis()
    after = thesis(standing=ET.WEAKENED, contradicting=("ev_2",))
    got = TH.diff(before, after)
    assert set(got) == {"standing", "contradicting_evidence"}


def test_an_unchanged_thesis_diffs_to_nothing():
    assert TH.diff(thesis(), thesis()) == ()


def test_a_dropped_alternative_shows_in_the_diff():
    got = TH.diff(thesis(), thesis(alternatives=()))
    assert "alternatives" in got


# --- classification ----------------------------------------------------------

def test_a_refuted_thesis_classifies_as_falsified():
    assert TH.classify(thesis(), thesis(standing=ET.REFUTED)) == TH.FALSIFIED


def test_first_contradicting_evidence_classifies_as_contested():
    got = TH.classify(thesis(), thesis(contradicting=("ev_2",)))
    assert got == TH.CONTESTED


def test_more_supporting_evidence_classifies_as_strengthened():
    got = TH.classify(thesis(supporting=("ev_1",)),
                      thesis(supporting=("ev_1", "ev_2")))
    assert got == TH.STRENGTHENED


# --- the answer --------------------------------------------------------------

def test_an_unmoved_thesis_says_so_rather_than_inventing_a_reason():
    history = TH.ThesisHistory()
    history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.CREATED, previous_standing="",
        new_standing=ET.PROPOSED, reason="stated", changed_at="2026-08-01"))
    got = history.what_changed_your_mind("th_1")
    assert got["changed"] is False
    assert "stands where it started" in got["answer"]


def test_the_answer_names_the_effects_that_caused_the_change():
    history = TH.ThesisHistory()
    before, after = thesis(), thesis(standing=ET.WEAKENED,
                                     contradicting=("ev_2",))
    history.append(TH.ThesisRevision(
        thesis_id=before.thesis_id, transition=TH.CREATED,
        previous_standing="", new_standing=ET.PROPOSED, reason="stated",
        changed_at="2026-08-01"))
    history.record(before, after, changed_at="2026-08-09",
                   reason="a third party reported the programme continuing",
                   knowledge_effect_ids=("ke_7",),
                   triggering_evidence=("ev_2",))
    got = history.what_changed_your_mind(before.thesis_id)
    assert got["changed"] is True
    assert got["because_of_effects"] == ["ke_7"]
    assert got["answer"] == "a third party reported the programme continuing"
    assert "standing" in got["changed_fields"]
    assert got["weakened_by"] == ["ke_7"]


def test_the_summary_counts_moves_that_rest_on_no_effect():
    history = TH.ThesisHistory()
    history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.CREATED, previous_standing="",
        new_standing=ET.PROPOSED, reason="stated", changed_at="2026-08-01"))
    head = history.head("th_1")
    history.append(TH.ThesisRevision(
        thesis_id="th_1", transition=TH.WEAKENED,
        previous_standing=ET.PROPOSED, new_standing=ET.WEAKENED,
        reason="contradicted", changed_at="2026-08-09",
        previous_revision=head, triggering_evidence=("ev_1",)))
    got = history.summarise()
    assert got["revisions"] == 2
    assert got["theses_that_moved"] == 1
    assert got["moves_without_an_effect"] == 1


# --- the production seam (G-THE-002) -----------------------------------------

def effect(target_type, target_id, effect_id_seed="a"):
    from intent_engine.market import knowledge_effect as KE

    return KE.KnowledgeEffect(
        evidence_id=f"ev_{effect_id_seed}", target_type=target_type,
        target_id=target_id, effect_type=KE.SUPPORTED,
        before_state="one", after_state="two",
        reason="the filing moved it", created_at="2026-08-09")


def test_an_effect_on_another_object_does_not_evidence_this_thesis():
    """Sharing a subject is not bearing on a claim."""
    from intent_engine.market import knowledge_effect as KE

    t = thesis()
    t = ET.EconomicThesis(
        subject=t.subject, question=t.question, claim=t.claim,
        leading_mechanism=t.leading_mechanism, alternatives=t.alternatives,
        exposures=("acme:REFINANCING",), standing=t.standing, as_of=t.as_of)
    unrelated = effect(KE.COMPANY_EXPOSURE, "acme:DEMAND")
    related = effect(KE.COMPANY_EXPOSURE, "acme:REFINANCING", "b")
    got = TH.effects_bearing_on(t, [unrelated, related])
    assert got == (related.effect_id,), (
        "an effect on a different exposure of the same company must not "
        "evidence this thesis")


def _production_shaped_thesis(subject="acme"):
    """The shape `from_transmission` actually builds: a BARE dimension.

    Test fixtures had been writing `exposures=("acme:REFINANCING",)` while
    production wrote `exposures=("CAPITAL_INTENSITY",)`, so the attribution
    rule was only ever exercised on a shape production does not emit.
    """
    return ET.EconomicThesis(
        subject=subject, question=f"what does MARKET_RATE mean for {subject}?",
        claim="capex will fall", leading_mechanism=mech(),
        area="CA", macro_conditions=("MARKET_RATE",),
        exposures=("CAPITAL_INTENSITY",), as_of="2026-08-01")


def test_an_effect_on_this_companys_exposure_bears_on_its_thesis():
    """The live seam. Two cycles reported zero attributed effects.

    An exposure effect is written with `target_id = "acme:CAPITAL_INTENSITY"`
    and the basis was built from the bare dimension, so the two never matched
    and the attribution rule could not fire. A guard that cannot fire reads
    exactly like a strict guard that nothing tripped.
    """
    from intent_engine.market import knowledge_effect as KE

    t = _production_shaped_thesis()
    bearing = effect(KE.COMPANY_EXPOSURE, "acme:CAPITAL_INTENSITY")
    assert TH.effects_bearing_on(t, [bearing]) == (bearing.effect_id,)


def test_an_effect_on_this_economys_condition_bears_on_its_thesis():
    from intent_engine.market import knowledge_effect as KE

    t = _production_shaped_thesis()          # area CA, MARKET_RATE
    ours = effect(KE.ECONOMIC_STATE, "CA:MARKET_RATE")
    assert TH.effects_bearing_on(t, [ours]) == (ours.effect_id,)


def test_another_economys_condition_does_not_bear_on_this_thesis():
    """A US rate effect must not strengthen a thesis about Canadian rates.

    This is the identity collision one layer down: even with two distinct
    theses, an unqualified condition name would let either economy's evidence
    move either thesis.
    """
    from intent_engine.market import knowledge_effect as KE

    t = _production_shaped_thesis()          # area CA
    theirs = effect(KE.ECONOMIC_STATE, "US:MARKET_RATE")
    assert TH.effects_bearing_on(t, [theirs]) == ()


def test_another_companys_exposure_does_not_bear_on_this_thesis():
    """Qualifying by subject is what stops the bare dimension matching all."""
    from intent_engine.market import knowledge_effect as KE

    t = _production_shaped_thesis()
    theirs = effect(KE.COMPANY_EXPOSURE, "othercorp:CAPITAL_INTENSITY")
    assert TH.effects_bearing_on(t, [theirs]) == ()


def test_a_claim_that_moved_by_a_word_is_still_the_same_thesis():
    """The one event worth recording must not destroy the record of it.

    This test used to assert the opposite — that a reworded claim produced a
    different `thesis_id` — and worked around it with a separate, coarser
    identity. That workaround was `(subject, question)`, and it collapsed
    eleven live theses into seven.
    """
    one = thesis(claim="capex will fall")
    two = thesis(claim="capex will fall sharply")
    assert one.thesis_id == two.thesis_id
    assert TH.identity(one) == TH.identity(two)


def test_a_restatement_on_a_later_date_is_the_same_thesis():
    """Keyed on the date, every thesis was new every night."""
    assert (TH.identity(thesis(as_of="2026-08-01"))
            == TH.identity(thesis(as_of="2026-09-01")))


def test_believing_a_thesis_more_does_not_make_it_another_thesis():
    assert (TH.identity(thesis(standing=ET.PROPOSED))
            == TH.identity(thesis(standing=ET.SUPPORTED,
                                  supporting=("ev_1",))))


def test_rewording_a_catalogue_mechanism_does_not_restart_its_history():
    """The reason identity uses a key and not the sentence.

    `transmission._MECHANISM` holds prose that is expected to be edited. If
    identity read the description, the first improvement to that wording
    would silently give every thesis a new id and an empty history — the same
    failure as keying on the claim, arriving through a different door.
    """
    def with_description(text):
        return ET.EconomicThesis(
            subject="acme", question="will capex fall?",
            claim="capex will fall",
            leading_mechanism=ET.Mechanism(
                description=text, falsifier="capex guidance is raised",
                key="transmission:CAPITAL_INTENSITY"),
            exposures=("CAPITAL_INTENSITY",), as_of="2026-08-01")

    before = with_description("a higher cost of capital defers spending")
    after = with_description(
        "a higher cost of capital raises the hurdle a programme must clear")
    assert TH.identity(before) == TH.identity(after)


def test_two_mechanisms_answering_one_question_are_two_theses():
    """The live class: same subject, same question, different explanation."""
    rate = thesis()
    demand = thesis(alternatives=(mech("the programme was precommitted",
                                       "a new programme is announced"),))
    demand = ET.EconomicThesis(
        subject=demand.subject, question=demand.question, claim=demand.claim,
        leading_mechanism=mech("demand fell so capex was deferred",
                               "orders recover"),
        alternatives=demand.alternatives, standing=demand.standing,
        as_of=demand.as_of)
    assert rate.question_key == demand.question_key, (
        "rival explanations of one question must still meet in a Competition")
    assert TH.identity(rate) != TH.identity(demand)


def test_two_economies_moving_one_condition_are_two_theses():
    """CA:MARKET_RATE and US:MARKET_RATE are different states.

    The live cycle held both for one company, gave them one identity, and
    persisted one of them.
    """
    ca = ET.EconomicThesis(
        subject="acme", question="what does MARKET_RATE mean for acme?",
        claim="capex will fall", leading_mechanism=mech(),
        area="CA", macro_conditions=("MARKET_RATE",),
        exposures=("CAPITAL_INTENSITY",), as_of="2026-08-01")
    us = ET.EconomicThesis(
        subject="acme", question="what does MARKET_RATE mean for acme?",
        claim="capex will fall", leading_mechanism=mech(),
        area="US", macro_conditions=("MARKET_RATE",),
        exposures=("CAPITAL_INTENSITY",), as_of="2026-08-01")
    assert TH.identity(ca) != TH.identity(us)
    assert ca.question_key != us.question_key, (
        "two economies are two questions; grouping them manufactured a "
        "contest between theses that were not disagreeing")


def test_an_unchanged_thesis_records_no_revision():
    _, summary = TH.reconcile([thesis()], [thesis()], as_of="2026-08-09")
    assert summary["unchanged"] == 1
    assert summary["written"] == 0


def test_a_new_thesis_records_a_creation():
    _, summary = TH.reconcile([], [thesis()], as_of="2026-08-09")
    assert summary["created"] == 1 and summary["written"] == 1


def test_a_strengthening_with_no_bearing_effect_is_not_recorded_as_stronger():
    """It moved for a reason the ledger cannot name; that is not stronger."""
    before = thesis()
    after = thesis(standing=ET.SUPPORTED, supporting=("ev_1",))
    _, summary = TH.reconcile([before], [after], as_of="2026-08-09",
                              effects=[])
    assert summary["strengthened"] == 0
    assert summary["unattributed"] == 1


def test_a_strengthening_backed_by_a_bearing_effect_is_recorded():
    from intent_engine.market import knowledge_effect as KE

    base = dict(subject="acme", question="will capex fall?",
                claim="capex will fall", leading_mechanism=mech(),
                alternatives=(mech("precommitted", "new programme"),),
                exposures=("acme:REFINANCING",), as_of="2026-08-01")
    before = ET.EconomicThesis(standing=ET.PROPOSED, **base)
    after = ET.EconomicThesis(standing=ET.SUPPORTED,
                              supporting_evidence=("ev_1",), **base)
    history, summary = TH.reconcile(
        [before], [after], as_of="2026-08-09",
        effects=[effect(KE.COMPANY_EXPOSURE, "acme:REFINANCING")])
    assert summary["strengthened"] == 1 and summary["written"] == 1
    answer = history.what_changed_your_mind(before.thesis_id)
    assert answer["changed"] is True
    assert answer["because_of_effects"]


def test_the_cycle_persists_revisions_and_a_fresh_store_reads_them(tmp_path):
    from intent_engine.market import knowledge_effect as KE
    from intent_engine.market import learning_store as LS

    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    base = dict(subject="acme", question="will capex fall?",
                claim="capex will fall", leading_mechanism=mech(),
                alternatives=(mech("precommitted", "new programme"),),
                exposures=("acme:REFINANCING",), as_of="2026-08-01")
    before = ET.EconomicThesis(standing=ET.PROPOSED, **base)
    after = ET.EconomicThesis(standing=ET.SUPPORTED,
                              supporting_evidence=("ev_1",), **base)

    # cycle 1: snapshot only
    store.record_thesis_snapshot(before, as_of="2026-08-01")
    assert store.thesis_revisions() == ()

    # cycle 2: a real move
    history, summary = TH.reconcile(
        [before], [after], as_of="2026-08-09",
        effects=[effect(KE.COMPANY_EXPOSURE, "acme:REFINANCING")])
    for revision in history.chain_all():
        store.record_thesis_revision(revision)
    store.record_thesis_snapshot(after, as_of="2026-08-09")
    assert len(store.thesis_revisions()) == 1

    # cycle 3: identical, nothing appended
    history3, summary3 = TH.reconcile([after], [after], as_of="2026-08-10")
    for revision in history3.chain_all():
        store.record_thesis_revision(revision)
    assert summary3["unchanged"] == 1
    assert len(store.thesis_revisions()) == 1, "an unchanged cycle appended"

    # a store that did not write it reads it back
    fresh = LS.LearningStore(tmp_path / "ledger.jsonl")
    assert len(fresh.thesis_revisions()) == 1
    assert fresh.thesis_revisions()[0]["knowledge_effect_ids"]


# --- one persisted thesis, one current thesis --------------------------------

def _two_rivals(*, standing_a=ET.PROPOSED, standing_b=ET.PROPOSED,
                supporting_a=(), supporting_b=()):
    """Two theses answering ONE question by two different mechanisms.

    Exactly the shape a live cycle produced and could not persist: same
    subject, same question, different route.
    """
    shared = dict(subject="acme", question="will capex fall?",
                  exposures=("acme:REFINANCING",), as_of="2026-08-01",
                  alternatives=(mech("precommitted", "new programme"),))
    a = ET.EconomicThesis(
        claim="capex will fall because borrowing got dearer",
        leading_mechanism=mech("rates rose so capex was deferred",
                               "capex guidance is raised"),
        standing=standing_a, supporting_evidence=tuple(supporting_a), **shared)
    b = ET.EconomicThesis(
        claim="capex will fall because orders dried up",
        leading_mechanism=mech("demand fell so capex was deferred",
                               "orders recover"),
        standing=standing_b, supporting_evidence=tuple(supporting_b), **shared)
    return a, b


def test_two_theses_under_one_question_both_persist(tmp_path):
    from intent_engine.market import learning_store as LS

    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    a, b = _two_rivals()
    assert a.thesis_id != b.thesis_id
    assert store.record_thesis_snapshot(a, as_of="2026-08-01") is True
    assert store.record_thesis_snapshot(b, as_of="2026-08-01") is True, (
        "the second thesis was refused as a duplicate of the first; a live "
        "cycle built 11 theses and persisted 7 this way")
    assert len(store.thesis_snapshots()) == 2


def test_each_thesis_reconciles_against_its_own_prior():
    a, b = _two_rivals()
    _, summary = TH.reconcile([a, b], [a, b], as_of="2026-08-09")
    assert summary["loaded"] == 2
    assert summary["compared"] == 2
    assert summary["unchanged"] == 2
    assert summary["identity_collisions"] == 0
    assert summary["unmatched_prior"] == 0
    assert summary["unmatched_current"] == 0


def test_moving_one_rival_revises_only_that_rival():
    from intent_engine.market import knowledge_effect as KE

    a, b = _two_rivals()
    moved_a, _ = _two_rivals(standing_a=ET.SUPPORTED, supporting_a=("ev_1",))
    history, summary = TH.reconcile(
        [a, b], [moved_a, b], as_of="2026-08-09",
        effects=[effect(KE.COMPANY_EXPOSURE, "acme:REFINANCING")])
    assert summary["compared"] == 2
    assert summary["written"] == 1
    assert summary["unchanged"] == 1
    written = history.chain_all()
    assert len(written) == 1
    assert written[0].thesis_id == a.thesis_id, (
        "the revision names the thesis that moved, not its rival")
    assert written[0].thesis_id != b.thesis_id
    assert history.chain(b.thesis_id) == ()


def test_a_prior_is_never_compared_against_twice():
    """The live defect: `compared` exceeded `loaded`.

    Eleven current theses matched seven priors, so four were graded against
    another thesis's past. It returned `unchanged`, which was luck: under a
    real movement the revision would have named the wrong thesis and the
    strengthening guard would have passed, because the effect genuinely bore
    on the identity — just not on that thesis.
    """
    a, _ = _two_rivals()
    _, summary = TH.reconcile([a], [a, a], as_of="2026-08-09")
    assert summary["loaded"] == 1
    assert summary["current"] == 2
    assert summary["compared"] == 1
    assert summary["identity_collisions"] == 1
    assert summary["compared"] <= summary["loaded"]


def test_two_priors_sharing_an_identity_are_refused_not_silently_dropped():
    a, _ = _two_rivals()
    _, summary = TH.reconcile([a, a], [a], as_of="2026-08-09")
    assert summary["loaded"] == 2
    assert summary["identity_collisions"] == 1
    assert summary["compared"] == 1
    assert summary["unmatched_prior"] == 1


def test_a_prior_with_no_current_thesis_is_counted_unmatched():
    a, b = _two_rivals()
    _, summary = TH.reconcile([a, b], [a], as_of="2026-08-09")
    assert summary["compared"] == 1
    assert summary["unmatched_prior"] == 1
    assert summary["unmatched_current"] == 0


# --- the chain survives the process ------------------------------------------

def test_a_reloaded_history_chains_the_next_revision_to_the_last(tmp_path):
    """Built empty each cycle, every revision was a first link forever."""
    from intent_engine.market import knowledge_effect as KE
    from intent_engine.market import learning_store as LS

    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    a, _ = _two_rivals()
    moved, _ = _two_rivals(standing_a=ET.SUPPORTED, supporting_a=("ev_1",))

    first, _ = TH.reconcile([], [a], as_of="2026-08-01")
    for revision in first.chain_all():
        store.record_thesis_revision(revision)

    reloaded, dropped = TH.ThesisHistory.load(store.thesis_revisions())
    assert dropped == []
    assert len(reloaded.chain(a.thesis_id)) == 1

    second, _ = TH.reconcile(
        [a], [moved], as_of="2026-08-09", history=reloaded,
        effects=[effect(KE.COMPANY_EXPOSURE, "acme:REFINANCING")])
    chain = second.chain(a.thesis_id)
    assert len(chain) == 2
    assert chain[1].previous_revision == chain[0].revision_id, (
        "a revision that does not name its parent cannot be walked back")


def test_snapshots_return_only_the_latest_cycle(tmp_path):
    from intent_engine.market import learning_store as LS

    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    store.record_thesis_snapshot(thesis(claim="one"), as_of="2026-08-01")
    store.record_thesis_snapshot(thesis(claim="two"), as_of="2026-08-09")
    latest = store.thesis_snapshots()
    assert len(latest) == 1 and latest[0]["snapshot_as_of"] == "2026-08-09", (
        "comparing against every historical snapshot would diff a thesis "
        "against its own ancestors and re-report movement that already "
        "happened")
