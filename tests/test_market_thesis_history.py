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


def test_identity_is_subject_and_question_not_the_hashed_claim():
    """A claim that moved by a word must still be the same thesis."""
    one = thesis(claim="capex will fall")
    two = thesis(claim="capex will fall sharply")
    assert one.thesis_id != two.thesis_id
    assert TH.identity(one) == TH.identity(two)


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
