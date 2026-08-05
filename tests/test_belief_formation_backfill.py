"""Evidence already on the ledger, made reachable by formation — once, deliberately.

THE DEFECT
----------
`learning_cycle.run` proposes beliefs from `fresh` evidence: rows whose id is
not already recorded. Correct for a nightly cycle, and it left evidence
ingested BEFORE belief formation existed permanently unreachable — every later
run dedupes those rows away before formation sees them.

Measured on the production ledger 2026-08-05: 9 evidence rows, 0 beliefs, and
`refused: {}` — no reason at all, because nothing survived to be refused. An
operator could not tell that from "the evidence was not good enough". The same
9 rows against a store that had not seen them declared 8 beliefs.

WHAT MUST STAY TRUE
-------------------
The repair must not become a way to relitigate evidence nightly, must not
count as learning, and must not let the evidence that opened a belief also
confirm it. Each of those is asserted below rather than assumed.
"""
from __future__ import annotations

import pytest

from intent_engine.market import evidence_translation as ET
from intent_engine.market import learning_cycle as LC
from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME


@pytest.fixture()
def store(tmp_path) -> LS.LearningStore:
    return LS.LearningStore(tmp_path / "learning.jsonl")


def ev(subject="caterpillar", kind=ME.EARNINGS_SURPRISE, n=0,
       role="independent_reporting"):
    """One item of the shape the research sweep actually files."""
    return ME.build(
        subject_company=subject, actor=subject, evidence_type=kind,
        observed_at="2026-07-20",
        source=f"https://reuters.com/{subject}-{n}",
        fact=f"{subject} beat consensus estimates for the quarter ({n}).",
        source_role=role, reliability=0.75, relevance=0.6)


def ingested(store, items):
    """Put evidence on the ledger the way an earlier cycle did: recorded, but
    never passed to formation."""
    for item in items:
        store.record_evidence(item)
    return store


# --- the store could not read its own evidence back -------------------------
def test_the_store_can_rehydrate_the_evidence_it_recorded(store):
    items = [ev(n=1), ev(subject="linde", kind=ME.CAPEX_SIGNAL, n=2)]
    ingested(store, items)
    back = store.evidence()
    assert [e.evidence_id for e in back] == [e.evidence_id for e in items]
    assert {e.subject_company for e in back} == {"caterpillar", "linde"}


def test_derived_fields_are_recomputed_not_read_back(store):
    """`as_dict` writes `independence` and `self_authored`, and both are
    properties of `source_role`. Trusting the stored value would let an old
    row keep a weighting the current rule no longer gives it."""
    ingested(store, [ev(role="company_owned")])
    item = store.evidence()[0]
    assert item.self_authored is True
    assert item.independence == ME.INDEPENDENCE["company_owned"]


def test_a_row_with_no_source_is_skipped_rather_than_defaulted(store):
    """Evidence with no source is what rule 5 in `beliefs.py` refuses; a
    reader that invented an empty one would smuggle it back in."""
    ingested(store, [ev(n=1)])
    store._append(LS.EVIDENCE, {"evidence_id": "ev_broken",
                                "subject_company": "acme"})
    assert [e.evidence_id for e in store.evidence()] != []
    assert "ev_broken" not in {e.evidence_id for e in store.evidence()}


def test_evidence_survives_a_round_trip_through_the_log(store):
    original = ev(n=7)
    ingested(store, [original])
    back = store.evidence()[0]
    for field in ("evidence_id", "subject_company", "actor", "evidence_type",
                  "observed_at", "available_at", "source", "fact",
                  "source_role", "reliability", "relevance",
                  "contradiction_role"):
        assert getattr(back, field) == getattr(original, field), field


# --- the defect itself ------------------------------------------------------
def test_already_ingested_evidence_forms_no_belief_without_the_backfill(store):
    """The production state, reproduced: rows present, beliefs zero, and the
    refusal counts empty because nothing reached the refusals."""
    items = [ev(n=i) for i in range(3)]
    ingested(store, items)
    result = LC.run(as_of="2026-08-05", store=store, evidence=items)
    assert result.as_dict()["belief_formation"]["candidates"] == 0
    assert result.as_dict()["belief_formation"]["refused"] == {}
    assert store.beliefs() == ()


def test_the_backfill_opens_beliefs_from_evidence_already_on_the_ledger(store):
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    summary = result.as_dict()["belief_formation_backfill"]
    assert summary["declared"] >= 1
    assert store.beliefs()


def test_the_backfill_is_off_unless_asked_for(store):
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[])
    assert result.as_dict()["belief_formation_backfill"] == {}
    assert store.beliefs() == ()


# --- it may not be mistaken for learning ------------------------------------
def test_a_backfilled_belief_is_not_counted_as_knowledge_gain(store):
    """The whole point of keeping it separate. `belief_knowledge_gain` feeds
    `learned_without_trading`, which is the claim this cycle exists to make
    honestly."""
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    trades_opened=0, backfill_evidence=True)
    d = result.as_dict()
    assert d["belief_formation_backfill"]["declared"] >= 1
    assert d["belief_knowledge_gain"] == 0
    assert d["learned_without_trading"] is False


def test_a_backfill_does_not_report_itself_as_new_knowledge(store):
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    assert result.outcome_class != LS.NEW_KNOWLEDGE


def test_organic_formation_is_reported_apart_from_the_backfill(store):
    """A session that both ingests new evidence AND backfills must not blend
    them: one is this session's work, the other is a repair."""
    old = [ev(subject="linde", n=i) for i in range(2)]
    ingested(store, old)
    new = [ev(subject="duolingo", n=i) for i in range(3)]
    result = LC.run(as_of="2026-08-05", store=store, evidence=new,
                    backfill_evidence=True)
    d = result.as_dict()
    organic = {s for s in d["belief_formation"]["subjects"]}
    repaired = {s for s in d["belief_formation_backfill"]["subjects"]}
    assert "duolingo" in organic
    assert "linde" in repaired
    assert not organic & repaired
    # and only the organic half is knowledge gained
    assert d["belief_knowledge_gain"] == d["belief_formation"]["candidates"]


def test_evidence_ingested_this_session_is_not_backfilled_twice(store):
    """Formation has already seen this session's rows; reconsidering them in
    the same run would count one belief as both organic and repaired."""
    new = [ev(n=i) for i in range(3)]
    result = LC.run(as_of="2026-08-05", store=store, evidence=new,
                    backfill_evidence=True)
    d = result.as_dict()
    assert d["belief_formation"]["candidates"] >= 1
    assert d["belief_formation_backfill"]["declared"] == 0
    assert d["belief_formation_backfill"]["examined"] == 0


# --- deduplication is untouched ---------------------------------------------
def test_the_backfill_does_not_re_ingest_anything(store):
    ingested(store, [ev(n=i) for i in range(3)])
    before = store.evidence_ids()
    LC.run(as_of="2026-08-05", store=store, evidence=[],
           backfill_evidence=True)
    assert store.evidence_ids() == before


def test_running_the_backfill_twice_declares_nothing_the_second_time(store):
    """Rule 1 holds: an unchanged ledger read again does nothing."""
    ingested(store, [ev(n=i) for i in range(3)])
    LC.run(as_of="2026-08-05", store=store, evidence=[],
           backfill_evidence=True)
    held = {b.belief_id for b in store.beliefs()}
    second = LC.run(as_of="2026-08-06", store=store, evidence=[],
                    backfill_evidence=True)
    summary = second.as_dict()["belief_formation_backfill"]
    assert summary["declared"] == 0
    assert summary["refused"].get("belief_already_declared")
    assert {b.belief_id for b in store.beliefs()} == held


def test_a_normal_cycle_is_unchanged_by_the_feature_existing(store):
    new = [ev(n=i) for i in range(3)]
    with_flag_off = LC.run(as_of="2026-08-05", store=store, evidence=new)
    assert with_flag_off.as_dict()["belief_formation"]["candidates"] >= 1
    assert with_flag_off.as_dict()["belief_formation_backfill"] == {}


# --- preregistration still holds --------------------------------------------
def test_a_backfilled_expectation_is_dated_today_not_when_evidence_arrived(
        store):
    """The subtle one. Reconciliation scores expectations where
    `preregistered_at < as_of`, so dating a July observation in July would
    produce a window that had already closed — and the very evidence that
    opened the belief could settle it."""
    ingested(store, [ev(n=i) for i in range(3)])
    LC.run(as_of="2026-08-05", store=store, evidence=[],
           backfill_evidence=True)
    open_now = store.open_expectations(as_of="2026-08-05")
    assert open_now
    assert {e.preregistered_at[:10] for e in open_now} == {"2026-08-05"}


def test_the_evidence_that_opened_a_backfilled_belief_cannot_confirm_it(store):
    ingested(store, [ev(n=i) for i in range(3)])
    LC.run(as_of="2026-08-05", store=store, evidence=[],
           backfill_evidence=True)
    # The same session cannot score them: reconciliation requires a window
    # that opened on an EARLIER day.
    scoreable = [e for e in store.open_expectations(as_of="2026-08-05")
                 if e.preregistered_at[:10] < "2026-08-05"]
    assert scoreable == []


def test_a_backfilled_expectation_keeps_the_evidence_it_rests_on(store):
    ingested(store, [ev(n=i) for i in range(3)])
    LC.run(as_of="2026-08-05", store=store, evidence=[],
           backfill_evidence=True)
    assert all(e.evidence_basis
               for e in store.open_expectations(as_of="2026-08-05"))


# --- the step contract ------------------------------------------------------
def test_the_backfill_is_not_one_of_the_declared_steps(store):
    """`steps_total` is len(STEPS) and operators read attempted-against-total
    to see whether a session ran completely. A step that only sometimes
    exists would make every ordinary cycle look like it skipped one."""
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    assert "belief_formation_backfill" not in LC.STEPS
    assert not any(s.name == "belief_formation_backfill"
                   for s in result.steps)
    d = result.as_dict()
    assert d["steps_attempted"] <= d["steps_total"]


def test_the_backfill_summary_says_what_it_is(store):
    ingested(store, [ev(n=i) for i in range(3)])
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    note = result.as_dict()["belief_formation_backfill"]["note"].lower()
    assert "repair" in note
    assert "not" in note and "learning" in note


# --- a repair may not resurrect a retired judgement --------------------------
#
# The production ledger was written at 7e6b21f, where `classify_type` matched
# keywords against the WHOLE observation. It typed
#
#   "Caterpillar Inc. stock underperforms Monday when compared to competitors
#    despite daily gains"
#
# as COMPETITOR_ACTION -- a share-price story read as a rival making a move --
# and opened "Caterpillar Inc. faces a rival competing on price or capability",
# which reached a founder. The current branch extracts candidate SENTENCES and
# refuses that text outright. Six of the nine production rows fail the same way.
#
# So the backfill reprocesses old JUDGEMENTS, not just old evidence, and has to
# put each one to the classifier that is running now.
CAT_PRICE_MOVE = ("Caterpillar Inc. stock underperforms Monday when compared "
                  "to competitors despite daily gains - MarketWatch")


def stored_with_type(store, fact, etype, subject="caterpillar"):
    """Write a row whose stored type an OLDER classifier produced."""
    item = ME.build(subject_company=subject, actor=subject, evidence_type=etype,
                    observed_at="2026-07-20",
                    source="https://marketwatch.com/x", fact=fact,
                    source_role="independent_reporting",
                    reliability=0.75, relevance=0.6)
    store.record_evidence(item)
    return item


def test_the_current_classifier_refuses_the_headline_that_became_a_belief():
    """The regression itself, pinned: a price-move story is not an event."""
    from intent_engine.market import event_patterns as EP
    assert EP.classify_sentence(CAT_PRICE_MOVE) is None


def test_a_row_whose_type_no_longer_holds_opens_no_belief(store):
    stored_with_type(store, CAT_PRICE_MOVE, ME.COMPETITOR_ACTION)
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    summary = result.as_dict()["belief_formation_backfill"]
    assert summary["declared"] == 0
    assert summary["refused_stale_type"] == 1
    assert summary["examined"] == 0
    assert store.beliefs() == ()


def test_a_stale_type_is_reported_not_silently_dropped(store):
    stored_with_type(store, CAT_PRICE_MOVE, ME.COMPETITOR_ACTION)
    ingested(store, [ev(subject="duolingo", n=1)])
    summary = LC.run(as_of="2026-08-05", store=store, evidence=[],
                     backfill_evidence=True
                     ).as_dict()["belief_formation_backfill"]
    assert summary["on_ledger"] == 2
    assert summary["refused_stale_type"] == 1
    assert summary["examined"] == 1


def test_a_row_whose_type_merely_changed_is_dropped_not_re_routed(store):
    """Re-typing old evidence would rewrite a judgement nobody recorded
    making, and `routes_for` would send the belief to a different family."""
    fact = "Duolingo beat consensus estimates for the quarter."
    stored_with_type(store, fact, ME.CAPEX_SIGNAL, subject="duolingo")
    summary = LC.run(as_of="2026-08-05", store=store, evidence=[],
                     backfill_evidence=True
                     ).as_dict()["belief_formation_backfill"]
    assert summary["refused_stale_type"] == 1
    assert summary["declared"] == 0


def test_a_row_the_current_classifier_still_agrees_with_is_kept(store):
    ingested(store, [ev(subject="duolingo", n=i) for i in range(2)])
    summary = LC.run(as_of="2026-08-05", store=store, evidence=[],
                     backfill_evidence=True
                     ).as_dict()["belief_formation_backfill"]
    assert summary["refused_stale_type"] == 0
    assert summary["declared"] >= 1


def test_a_backfill_will_not_open_a_belief_on_another_companys_results(store):
    """The second door into the same defect.

    The live path refuses "PayPal tops Q2 estimates and raises full-year
    forecast" as evidence about Stripe. A backfill that only re-checked the
    TYPE would walk the same belief in through the ledger, because the type
    is genuinely GUIDANCE_REVISION -- it is the attribution that is wrong.
    """
    stored_with_type(
        store,
        "PayPal tops Q2 estimates and raises full-year forecast amid Stripe "
        "takeover bid.",
        ME.GUIDANCE_REVISION, subject="stripe")
    summary = LC.run(as_of="2026-08-05", store=store, evidence=[],
                     backfill_evidence=True
                     ).as_dict()["belief_formation_backfill"]
    assert summary["declared"] == 0
    assert summary["refused_stale_type"] == 1
    assert store.beliefs() == ()


def test_a_backfill_still_opens_a_belief_on_the_subjects_own_results(store):
    """The control: the attribution check must not refuse everything."""
    stored_with_type(
        store,
        "Duolingo beat consensus estimates for the quarter and raised its "
        "full-year forecast.",
        ME.EARNINGS_SURPRISE, subject="duolingo")
    summary = LC.run(as_of="2026-08-05", store=store, evidence=[],
                     backfill_evidence=True
                     ).as_dict()["belief_formation_backfill"]
    assert summary["declared"] == 1
    assert summary["refused_stale_type"] == 0


def test_a_slug_that_cannot_be_matched_falls_back_to_the_type_check(store):
    """`america_movil` does not reproduce "América Móvil". A position test
    that cannot find the subject has learned nothing, so it must not refuse
    over a spelling."""
    assert LC._slug_names("hdfc_bank")[1] == "Hdfc Bank"
    assert ET.reports_own_results(
        "América Móvil raised its full-year capex plan.", "raised",
        LC._slug_names("america_movil"))


def test_a_backfill_with_an_empty_ledger_says_so_rather_than_failing(store):
    result = LC.run(as_of="2026-08-05", store=store, evidence=[],
                    backfill_evidence=True)
    summary = result.as_dict()["belief_formation_backfill"]
    assert summary["requested"] is True
    assert summary["declared"] == 0
    assert summary["examined"] == 0


def test_the_summary_has_one_shape_whether_or_not_it_found_anything(store):
    """A summary whose keys depend on what it found makes every reader write
    a `.get`, and the one that forgets reads "found nothing" as "never ran"."""
    empty = LC.run(as_of="2026-08-05", store=store, evidence=[],
                   backfill_evidence=True
                   ).as_dict()["belief_formation_backfill"]
    ingested(store, [ev(subject="duolingo", n=i) for i in range(2)])
    full = LC.run(as_of="2026-08-06", store=store, evidence=[],
                  backfill_evidence=True
                  ).as_dict()["belief_formation_backfill"]
    assert set(empty) == set(full)
