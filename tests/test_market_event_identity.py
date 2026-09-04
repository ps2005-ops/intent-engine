"""One occurrence, many accounts — and only a LATER one may test a belief.

The fact fingerprint catches the same sentence twice. It cannot catch two
outlets writing the same event differently, and that is precisely the case
where a belief looks independently confirmed and is not.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.market import event_identity as EI
from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import observation_binding as OB

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def item(fact, source="https://a.example/x", role="independent_reporting",
         observed="2026-08-05", subject="cloudflare"):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=ME.EARNINGS_RESULT, observed_at=observed,
                    source=source, fact=fact, source_role=role,
                    reliability=0.8, relevance=0.9)


# --- the case the fingerprint cannot see ---------------------------------

def test_two_outlets_writing_one_event_differently_are_one_event():
    reuters = item("Cloudflare Q2 revenue rises 36% as restructuring widens "
                   "the GAAP loss.", source="https://reuters.example/a")
    bloomberg = item("Revenue rises 36% at Cloudflare, filing shows, with a "
                     "wider GAAP loss on restructuring.",
                     source="https://bloomberg.example/b")
    assert OB._fingerprint(reuters.fact) != OB._fingerprint(bloomberg.fact)
    events = EI.group([reuters, bloomberg])
    assert len(events) == 1
    assert len(events[0].evidence_ids) == 2


def test_no_evidence_row_is_merged_away():
    rows = [item("Cloudflare Q2 revenue rises 36% on strong demand.",
                 source=f"https://outlet{i}.example/x") for i in range(3)]
    (event,) = EI.group(rows)
    assert len(event.evidence_ids) == 3
    assert len(event.sources) == 3
    assert set(event.evidence_ids) == {r.evidence_id for r in rows}


def test_different_figures_are_different_events():
    """Numbers do most of the work: 36% and 4% are not one print."""
    events = EI.group([
        item("Cloudflare Q2 revenue rises 36% on demand."),
        item("Cloudflare Q2 revenue rises 4% on demand.")])
    assert len(events) == 2


def test_the_same_wording_a_quarter_apart_is_two_events():
    events = EI.group([
        item("Cloudflare reports quarterly revenue growth of 36%.",
             observed="2026-05-05"),
        item("Cloudflare reports quarterly revenue growth of 36%.",
             observed="2026-08-05")])
    assert len(events) == 2


def test_independent_accounts_counts_roles_not_outlets():
    """Six aggregator rewrites of one wire story are one account."""
    rewrites = [item("Cloudflare Q2 revenue rises 36% on demand.",
                     source=f"https://agg{i}.example/x",
                     role="independent_reporting") for i in range(6)]
    (event,) = EI.group(rewrites)
    assert len(event.evidence_ids) == 6
    assert event.independent_accounts == 1

    mixed = rewrites + [item("Cloudflare Q2 revenue rises 36% on demand.",
                             source="https://sec.example/f",
                             role="regulatory_filing")]
    (event,) = EI.group(mixed)
    assert event.independent_accounts == 2


# --- corroboration is not a test -----------------------------------------

def test_the_same_event_corroborates_and_cannot_test():
    opener = item("Cloudflare Q2 revenue rises 36% on strong demand.")
    other = item("Revenue rises 36% at Cloudflare, filing shows strong "
                 "demand.", source="https://other.example/b")
    events = EI.group([opener, other])
    lookup = EI.index(events)
    assert EI.role_of(lookup[other.evidence_id],
                      [lookup[opener.evidence_id]]) == EI.CORROBORATES


def test_a_later_event_may_test():
    opener = item("Cloudflare Q2 revenue rises 36% on demand.",
                  observed="2026-05-05")
    later = item("Cloudflare Q3 revenue rises 41% on demand.",
                 observed="2026-08-05")
    lookup = EI.index(EI.group([opener, later]))
    assert EI.role_of(lookup[later.evidence_id],
                      [lookup[opener.evidence_id]]) == EI.TESTS_EXPECTATION


def test_the_binder_counts_corroboration_rather_than_discarding_it():
    """Throwing it away would cost the source diversity that makes the
    opener worth anything."""
    opener = item("Cloudflare Q2 revenue rises 36% on strong demand.")
    other = item("Revenue rises 36% at Cloudflare, filing shows strong "
                 "demand.", source="https://other.example/b",
                 role="regulatory_filing")
    from intent_engine.market import expectation as EXP

    exp = EXP.preregister(
        hypothesis_id="b1", subject="cloudflare",
        metric="demand_strengthening",
        expected_event="the next reported revenue figure",
        expected_direction=EXP.UP, preregistered_at="2026-08-05",
        evaluation_window_ends="2026-12-05",
        falsifier="revenue is flat or lower",
        evidence_basis=(opener.evidence_id,))
    _, refused = OB.bind([exp], [opener, other], as_of="2026-08-06")
    # Counted, not discarded — and it never reaches the observation payload,
    # which is `reconcile`'s argument list.
    assert refused.get("corroborates_the_opening_event") == 1
    assert refused.get("corroborating_accounts") == 1


# --- the real ledger ------------------------------------------------------

def test_the_real_ledger_has_genuinely_corroborated_events():
    """249 evidence rows describe 155 occurrences.

    Five of them are corroborated by accounts from DIFFERENT source roles —
    a filing and an independent report of the same print. Those five are
    exactly the population the fact fingerprint cannot see and would have
    let through as later outcomes.
    """
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    store = LS.LearningStore(REAL_LEDGER)
    got = EI.summarise(EI.group(store.evidence()))
    # The production runtime appends to this ledger nightly, so a constant
    # pinned here has an expiry date: these assertions were written green
    # and went red when a cycle ran mid-session. What is durable is the
    # INVARIANT, not the snapshot.
    assert got["evidence_rows"] >= 249
    assert got["events"] < got["evidence_rows"], "grouping must reduce rows"
    assert got["events"] >= 155
    # `== 49` survived directly beneath the note above warning against exactly
    # this, and expired on the next cycle. The floor is the durable half; the
    # ceiling is that grouping cannot invent an event.
    assert got["events_with_several_accounts"] >= 49
    assert got["events_with_several_accounts"] <= got["events"]
    assert got["events_with_independent_accounts"] >= 5


def test_a_period_marker_is_not_a_figure():
    """"Q2" appears in one account of a print and not the other, and
    including it split accounts of one event."""
    assert EI._PERIOD.match("Q2") and EI._PERIOD.match("FY2027")
    assert EI._PERIOD.match("2026")
    assert not EI._PERIOD.match("36%")
    events = EI.group([
        item("Cloudflare Q2 revenue rises 36% on demand."),
        item("Revenue rises 36% at Cloudflare on demand.",
             source="https://other.example/b")])
    assert len(events) == 1


# --- the row shape must not change the answer -----------------------------

def test_a_mapping_row_groups_the_same_as_an_object_row():
    """The ledger on disk is JSONL and the store hands back objects.

    Reading only attributes made a list of dicts fold into ONE event with an
    empty subject: 249 rows in, 1 event out, no error. The two shapes must
    reach the same events or every measurement taken from the file disagrees
    with the same measurement taken from the store.
    """
    class Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    fields = [
        dict(evidence_id="ev_1", subject_company="cloudflare",
             evidence_type="EARNINGS_RESULT", fact="revenue rises 36%",
             observed_at="2026-08-01", source="reuters.com",
             source_role="news_report"),
        dict(evidence_id="ev_2", subject_company="cloudflare",
             evidence_type="EARNINGS_RESULT",
             fact="Revenue rises 36% at Cloudflare, filing shows",
             observed_at="2026-08-02", source="bloomberg.com",
             source_role="regulatory_filing"),
        dict(evidence_id="ev_3", subject_company="honda",
             evidence_type="GUIDANCE_REVISION", fact="operating profit up 12%",
             observed_at="2026-08-02", source="honda.com",
             source_role="regulatory_filing"),
    ]
    as_dicts = EI.group(fields)
    as_objects = EI.group([Row(**f) for f in fields])
    assert len(as_dicts) == len(as_objects) == 2
    assert {e.event_id for e in as_dicts} == {e.event_id for e in as_objects}
    assert {e.subject for e in as_dicts} == {"cloudflare", "honda"}


def test_a_row_that_identifies_no_occurrence_is_refused():
    """The failure that hid the bug: rows with none of the identity fields
    all hash to the same empty core and look like one well-corroborated
    event. Refusing is the only reading that is not a lie."""
    with pytest.raises(ValueError, match="cannot identify an occurrence"):
        EI.group([{"record": "cycle", "cycle_id": "c1"}])
