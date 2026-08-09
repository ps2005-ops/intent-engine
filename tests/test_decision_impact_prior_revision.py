"""A metric that cannot report the negative is not evidence.

THE DEFECT THESE PIN, MEASURED ON ALL 59 LIVE DOSSIERS
------------------------------------------------------
25 were available and every one graded MEANINGFUL or DECISION_CHANGING —
sixteen the latter, nine the former, and NOT ONE `NONE`.

The cause is not a threshold. The production call site builds its BEFORE as
`build_context(strategic=None)`, whose `semantic_state` is EMPTY on all five
fields. Every field therefore goes empty → populated, every field counts as
changed, and an available dossier is structurally incapable of grading NONE.

So the metric answered "was a dossier attached", which was already known, and
read 100% forever — the failure this module's own docstring predicted by
name. The founder question is whether the NEW learning changed anything, so
the BEFORE has to be the previous revision of the same dossier.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.external_intel import decision_impact as di

STRATEGIC = pathlib.Path("/Users/prathamsharma/intent-engine-market/reports/"
                         "market/strategic")


def state(**fields):
    base = {field: [] for field in di.IMPACT_TYPES}
    base.update(fields)
    return base


# --- the three outcomes -----------------------------------------------------

def test_no_prior_revision_is_not_an_impact(tmp_path):
    """FIRST_OBSERVATION is neither a change nor a non-change."""
    got = di.assess_against_prior(
        tmp_path, analysis_id="a1", company_id="acme",
        after=state(ASSUMPTION=["Market evidence supports rising demand"]),
        provenance=["ev_1"])
    assert got.materiality == di.FIRST_OBSERVATION
    assert "nothing for this learning to change" in got.reason


def test_an_identical_dossier_grades_none(tmp_path):
    """The reading the metric could not previously produce."""
    after = state(ASSUMPTION=["Market evidence supports rising demand"])
    di.record_revision(tmp_path, company_id="acme", state=after)
    got = di.assess_against_prior(tmp_path, analysis_id="a2",
                                  company_id="acme", after=after,
                                  provenance=["ev_1"])
    assert got.materiality == di.NONE
    assert got.changed is False


def test_a_changed_dossier_still_grades_an_impact(tmp_path):
    """The fix must not simply refuse everything."""
    di.record_revision(
        tmp_path, company_id="acme",
        state=state(ASSUMPTION=["Market evidence supports rising demand"]))
    got = di.assess_against_prior(
        tmp_path, analysis_id="a2", company_id="acme",
        after=state(ASSUMPTION=["Market evidence supports falling demand"],
                    BOUNDED_CONCLUSION=["one period is not a trend"]),
        provenance=["ev_2"])
    assert got.materiality in (di.MEANINGFUL, di.DECISION_CHANGING)
    assert got.changed is True


# --- the store --------------------------------------------------------------

def test_an_unchanged_revision_is_not_appended_twice(tmp_path):
    after = state(ASSUMPTION=["a"])
    assert di.record_revision(tmp_path, company_id="acme", state=after) is True
    assert di.record_revision(tmp_path, company_id="acme", state=after) is False


def test_a_changed_revision_is_appended(tmp_path):
    assert di.record_revision(tmp_path, company_id="acme",
                              state=state(ASSUMPTION=["a"])) is True
    assert di.record_revision(tmp_path, company_id="acme",
                              state=state(ASSUMPTION=["b"])) is True


def test_the_revision_key_is_content_addressed():
    assert di.revision_key(state(ASSUMPTION=["a"])) == \
        di.revision_key(state(ASSUMPTION=["a"]))
    assert di.revision_key(state(ASSUMPTION=["a"])) != \
        di.revision_key(state(ASSUMPTION=["b"]))


def test_a_revision_needs_the_company_it_belongs_to(tmp_path):
    with pytest.raises(ValueError, match="company"):
        di.record_revision(tmp_path, company_id="", state=state())


# --- non-impacts must be persisted, or the rate has no denominator ----------

def test_a_none_impact_is_recorded_too(tmp_path):
    """The production receipt records an impact only `if impact.changed`,
    which makes the file a success log a rate cannot be taken over."""
    after = state(ASSUMPTION=["a"])
    di.record_revision(tmp_path, company_id="acme", state=after)
    got = di.assess_against_prior(tmp_path, analysis_id="a2",
                                  company_id="acme", after=after,
                                  provenance=["ev_1"])
    assert got.materiality == di.NONE
    assert di.record_impact(tmp_path, impact=got) is True
    rows = di.load_impacts(tmp_path)
    assert len(rows) == 1
    assert rows[0]["materiality"] == di.NONE


def test_the_same_comparison_is_not_recorded_twice(tmp_path):
    after = state(ASSUMPTION=["a"])
    di.record_revision(tmp_path, company_id="acme", state=after)
    got = di.assess_against_prior(tmp_path, analysis_id="a2",
                                  company_id="acme", after=after)
    assert di.record_impact(tmp_path, impact=got) is True
    assert di.record_impact(tmp_path, impact=got) is False


# --- against the real corpus ------------------------------------------------

@pytest.mark.skipif(not STRATEGIC.exists(), reason="no live dossiers")
def test_the_live_corpus_grades_none_on_a_second_identical_pass(tmp_path):
    """The measured defect and its repair, on production's own dossiers.

    First pass: every available dossier is a FIRST_OBSERVATION. Second pass
    over the SAME files: every one grades NONE. Before this change the same
    two passes both graded MEANINGFUL or DECISION_CHANGING, 25 out of 25.
    """
    from intent_engine.external_intel import pack as ep
    from intent_engine.external_intel import strategic_contract as sc

    states = []
    for path in sorted(STRATEGIC.glob("*.json")):
        try:
            intel = sc.load(path, today="2026-08-09")
        except Exception:                                  # noqa: BLE001
            continue
        if not getattr(intel, "available", False):
            continue
        context = ep.build_context(strategic=intel, as_of="2026-08-09")
        states.append((path.stem, di.semantic_state(context),
                       di.evidence_of(context)))
    if not states:                                         # pragma: no cover
        pytest.skip("no available dossier in the live corpus")

    first = set()
    for company, after, provenance in states:
        first.add(di.assess_against_prior(
            tmp_path, analysis_id="p1", company_id=company, after=after,
            provenance=provenance).materiality)
        di.record_revision(tmp_path, company_id=company, state=after)
    assert first == {di.FIRST_OBSERVATION}

    second = set()
    for company, after, provenance in states:
        second.add(di.assess_against_prior(
            tmp_path, analysis_id="p2", company_id=company, after=after,
            provenance=provenance).materiality)
    assert second == {di.NONE}, (
        "an unchanged dossier must grade NONE; anything else means the "
        "comparison is measuring the dossier's presence again")
