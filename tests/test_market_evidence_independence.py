"""Origin independence, and what a re-observation is actually worth.

The metamorphic cases are the point: ten syndicated copies of one claim must
not read like ten outlets checking it, and a high repeat rate must not be
reported as a defect when the repeats are testing something.
"""
import pytest

from intent_engine.market import evidence_independence as EI


def ev(source, fact, subject="acme", role="independent_reporting", **kw):
    """The shape the producer actually writes.

    `micro_evidence` always emits `source_role` and the derived
    `independence` weight, so a fixture omitting them is not a realistic row.
    A row with NO vantage signal falls to 0.5 and is correctly refused
    independence — see the unknown-vantage test below.
    """
    from intent_engine.market.micro_evidence import INDEPENDENCE, SELF_AUTHORED
    row = {"record": "evidence", "evidence_id": f"e{abs(hash((source, fact)))}",
           "source": source, "fact": fact, "subject_company": subject,
           "source_role": role,
           "independence": INDEPENDENCE.get(role, 0.5),
           "self_authored": role in SELF_AUTHORED}
    row.update(kw)
    return row


def test_a_row_with_no_vantage_signal_is_not_independent():
    """Conservative by construction: unknown vantage never earns independence."""
    out = EI.assess([{"record": "evidence", "evidence_id": "a",
                      "source": "https://somewhere.example/x",
                      "fact": "A claim with no recorded source role at all",
                      "subject_company": "acme"}])
    assert out["independent_groups"] == 0


CLAIM = ("Acme raised enterprise prices by eighteen percent across all "
         "regions effective the first of next quarter")


# --- the origin axis ---------------------------------------------------------
def test_two_unrelated_outside_sources_are_independent():
    out = EI.assess([ev("https://reuters.com/a", "Distributors report a "
                        "shortage of qualified integrators this quarter"),
                     ev("https://ft.com/b", "Industrial buyers delayed "
                        "orders after the rate move last month")])
    assert out["independent_groups"] == 2
    assert out["corroboration_state"] == EI.INDEPENDENT


def test_a_syndicated_claim_is_derived_not_a_second_source():
    """The gap the scalar vantage weight cannot see.

    Both rows are independent_reporting at 0.90. Only the relation between
    them reveals that one is a copy.
    """
    out = EI.assess([ev("https://reuters.com/a", CLAIM),
                     ev("https://finance.yahoo.com/b", CLAIM)])
    assert out["derived_rows"] == 1
    assert out["independent_groups"] == 1
    assert out["corroboration_state"] == EI.PARTIALLY_INDEPENDENT


def test_ten_syndicated_copies_do_not_become_ten_confirmations():
    """§11 metamorphic property."""
    rows = [ev("https://reuters.com/a", CLAIM)]
    rows += [ev(f"https://outlet{i}.com/x", CLAIM) for i in range(10)]
    out = EI.assess(rows)
    assert out["evidence_rows"] == 11
    assert out["independent_groups"] == 1
    assert out["derived_rows"] == 10


def test_company_owned_material_is_never_an_outside_vantage_point():
    out = EI.assess([ev("company_owned", "We are the market leader",
                        role="company_owned"),
                     ev("executive_statement", "Our pricing is competitive",
                        role="executive_statement")])
    assert out["independent_groups"] == 0
    assert out["corroboration_state"] != EI.INDEPENDENT


def test_many_pages_from_one_company_are_one_origin():
    rows = [ev("company_owned", f"Company page number {i} about products",
               role="company_owned") for i in range(8)]
    out = EI.assess(rows)
    assert out["unique_origins"] == 1


def test_many_urls_on_one_host_are_one_origin():
    """Exercises the URL-host collapse specifically.

    Written after a break proof that replaced host collapsing with the raw
    source string went NOT_CAUGHT: every existing origin test used role-style
    sources (`company_owned`), so the URL branch was never executed.
    """
    rows = [ev(f"https://news.reuters.com/story-{i}",
               f"A distinct report number {i} about the sector outlook")
            for i in range(5)]
    out = EI.assess(rows)
    assert out["unique_origins"] == 1
    assert out["independent_groups"] == 1


def test_unknown_origin_never_counts_as_independent():
    out = EI.assess([{"record": "evidence", "fact": "x", "evidence_id": "a"}])
    assert out["unknown_rows"] == 1
    assert out["independent_groups"] == 0
    assert out["corroboration_state"] == EI.UNAVAILABLE


def test_an_empty_set_is_unavailable_not_uncorroborated():
    out = EI.assess([])
    assert out["corroboration_state"] == EI.UNAVAILABLE
    assert out["state"] == "MEASURED"


# --- re-observation value ----------------------------------------------------
def expectation(subject, ends):
    return {"record": "expectation", "subject": subject,
            "evaluation_window_ends": ends, "expectation_id": f"x{subject}"}


def sighting(subject, first="2026-08-05", again="2026-08-13"):
    return {"record": "evidence_seen", "subject_company": subject,
            "evidence_id": f"e{subject}{again}",
            "occurrence_first_seen": first, "seen_at": again}


def test_no_testable_expectation_makes_the_value_unmeasurable():
    """The live finding, pinned.

    301 sightings, every expectation window 4-12 months out. Nothing could
    have been resolved by re-reading today, so no re-observation can be
    called valuable — and the honest answer is UNMEASURABLE, not 100% useful.
    """
    out = EI.classify_reobservations(
        [sighting("acme")], as_of="2026-08-13",
        open_expectations=[expectation("acme", "2027-06-01")])
    assert out["state"] == "UNMEASURABLE"
    assert out["testable_subjects"] == 0


def test_a_closing_window_makes_a_re_read_required_monitoring():
    out = EI.classify_reobservations(
        [sighting("acme")], as_of="2026-08-13",
        open_expectations=[expectation("acme", "2026-08-20")])
    assert out["state"] == "MEASURED"
    assert out["by_class"][EI.REQUIRED_MONITORING] == 1
    assert out["low_value_repeat_rate"] == 0.0


def test_a_re_read_of_an_untested_subject_is_not_valuable():
    """The property is VALUE, not which non-valuable bucket it lands in.

    A dated refetch of an untested subject classifies as
    SAME_DOCUMENT_NEW_FETCH rather than LOW_VALUE_REPEAT — the latter is
    reserved for a repeat with no date movement at all. Neither earns its
    retrieval, and that is what the rate must show.
    """
    out = EI.classify_reobservations(
        [sighting("acme"), sighting("other")], as_of="2026-08-13",
        open_expectations=[expectation("acme", "2026-08-20")])
    assert out["by_class"][EI.REQUIRED_MONITORING] == 1
    assert out["valuable"] == 1
    assert out["useful_reobservation_rate"] == 0.5
    untested = out["by_class"][EI.SAME_DOCUMENT_NEW_FETCH] + \
        out["by_class"][EI.LOW_VALUE_REPEAT]
    assert untested == 1


def test_a_belief_due_for_review_makes_a_re_read_useful_revalidation():
    out = EI.classify_reobservations(
        [sighting("acme")], as_of="2026-08-13", beliefs_due_subjects={"acme"})
    assert out["by_class"][EI.USEFUL_REVALIDATION] == 1


def test_repeat_rate_alone_is_never_the_defect():
    """§13: a high repeat share is fine when the repeats are testing.

    Ten monitored re-reads must report a 0% low-value rate, so an operator
    optimising the raw repeat number cannot use this report to justify it.
    """
    out = EI.classify_reobservations(
        [sighting("acme", again=f"2026-08-{d:02d}") for d in range(1, 11)],
        as_of="2026-08-13",
        open_expectations=[expectation("acme", "2026-08-20")])
    assert out["sightings"] == 10
    assert out["useful_reobservation_rate"] == 1.0
    assert out["low_value_repeat_rate"] == 0.0


@pytest.mark.parametrize("state", EI.STATES)
def test_every_independence_state_is_closed(state):
    assert state in EI.STATES
