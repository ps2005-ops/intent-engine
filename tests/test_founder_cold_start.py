"""At T0 a prior is a prior, and every kind of nothing says which kind it is.

Two tests carry this file.

`test_the_six_kinds_of_nothing_do_not_share_a_sentence` is the defect that was
measured before any of this was written: the CEO surface answered every
question about an unanalysed company with "No economic view is recorded for
this company yet", and said exactly the same thing about a company whose
sources had gone dark. Those call for opposite actions.

`test_a_sector_prior_cannot_be_spoken_as_a_company_fact` is the one that
matters commercially. The pressure at T0 is to say something useful, and the
useful-sounding thing is a claim about the sector delivered in the voice of a
claim about the company.
"""
from __future__ import annotations

import pytest

from intent_engine.external_intel import ceo_answers as CA
from intent_engine.external_intel import coverage_state as CV
from intent_engine.external_intel import standing_ceiling as SC


class Intel:
    """The consumer shape, with the fields the planner and classifier read."""

    def __init__(self, **kw):
        self.economic_theses = ()
        self.evidence_ids = ()
        self.beliefs = ()
        self.available = True
        self.thesis_revisions = ()
        self.thesis_history = None
        self.limitations = ()
        self.source_constraints = ()
        self.company_id = "NEWCO"
        self.hydrating = False
        self.degraded_sources = ()
        for key, value in kw.items():
            setattr(self, key, value)


def thesis(**kw):
    row = {"thesis_id": "th_1", "claim": "input costs are rising",
           "standing": "PROPOSED", "mechanism": "tariffs raise landed cost",
           "falsifier": "landed cost does not move in 90 days",
           "alternatives": ["the exposure was hedged"],
           "evidence_ids": ["ev1"], "macro_conditions": ["tariff"],
           "exposures": ["imports"], "decision_implication": "watch"}
    row.update(kw)
    return row


def observed(field="exposure", value="imports"):
    return CV.Attributed(field=field, value=value,
                         origin=CV.COMPANY_OBSERVATION,
                         evidence_ids=("ev1",))


def sector_prior(field="exposure", value="imports"):
    return CV.Attributed(field=field, value=value, origin=CV.SECTOR_PRIOR)


# --- the six kinds of nothing -----------------------------------------------

def test_the_six_kinds_of_nothing_do_not_share_a_sentence():
    """The measured defect. One sentence covered all of these."""
    assert len(set(CV.STATE_WORDS.values())) == len(CV.COVERAGE_STATES)
    assert len(set(CV.MUST_NOT_CONCLUDE.values())) == len(CV.COVERAGE_STATES)


@pytest.mark.parametrize("kw,expected", [
    ({}, CV.NEVER_ANALYSED),
    ({"hydrating": True}, CV.HYDRATING),
    ({"evidence_ids": ("ev1",)}, CV.PARTIALLY_OBSERVED),
    ({"beliefs": ({"id": "b"},)}, CV.PARTIALLY_OBSERVED),
    ({"economic_theses": (thesis(),)}, CV.OBSERVED),
    ({"evidence_ids": ("ev1",), "degraded_sources": ("bls",)}, CV.DEGRADED),
])
def test_each_state_is_reached_from_a_real_dossier_shape(kw, expected):
    intel = Intel(**kw)
    assert CV.classify(
        intel, hydrating=intel.hydrating,
        degraded_sources=intel.degraded_sources) == expected


def test_a_dark_source_outranks_a_surviving_thesis():
    """Checked before the positive states on purpose. A dossier still carrying
    yesterday's thesis while today's source is dark reads as OBSERVED and is
    not."""
    intel = Intel(economic_theses=(thesis(),), degraded_sources=("bls",))
    assert CV.classify(intel, degraded_sources=("bls",)) == CV.DEGRADED


def test_the_ceo_surface_says_which_kind_of_nothing():
    answers = set()
    for kw in ({}, {"hydrating": True}, {"evidence_ids": ("ev1",)},
               {"evidence_ids": ("ev1",), "degraded_sources": ("bls",)}):
        intel = Intel(**kw)
        answers.add(CA.plan("What is happening?", intel).direct_answer)
    assert len(answers) == 4


def test_lost_visibility_is_never_reported_as_a_quiet_company():
    intel = Intel(evidence_ids=("ev1",), degraded_sources=("bls",))
    got = CA.plan("What is happening?", intel)
    assert "gap in our sources" in got.direct_answer
    assert any("reduced visibility" in m for m in got.must_not_conclude)


def test_an_unanalysed_company_is_not_reported_as_uninteresting():
    got = CA.plan("What is happening?", Intel())
    assert any("not a finding" in m for m in got.must_not_conclude)


def test_no_state_short_of_observed_licenses_an_assertion():
    for state in CV.COVERAGE_STATES:
        if state == CV.OBSERVED:
            continue
        assert CV.ceiling_for(state) == SC.ASSERT_NONE


def test_an_unsupported_plan_carries_a_decided_ceiling():
    """It used to carry "" — an undecided value the certainty wall then had to
    interpret. "Nothing may be asserted" is a decision; "" is the absence.

    BOTH PATHS, because they decide it differently and only one of them was
    covered. The current-state path derives the ceiling from the coverage
    state; every other unsupported answer — an unrecognised question, most of
    all — falls to the default in `_unsupported`. A test that only exercised
    the first left the default unguarded, which a break proof found.
    """
    derived = CA.plan("What is happening?", Intel())
    assert derived.ceiling == SC.ASSERT_NONE

    defaulted = CA.plan("What is the airspeed of an unladen swallow?",
                        Intel())
    assert defaulted.question_class == CA.UNKNOWN_QUESTION
    assert defaulted.ceiling == SC.ASSERT_NONE


# --- a prior is a prior -----------------------------------------------------

def test_a_sector_prior_cannot_be_spoken_as_a_company_fact():
    with pytest.raises(CV.CoverageRejected):
        CV.refuse_prior_as_observation([sector_prior()], surface="brief")


def test_a_prior_that_says_it_is_one_may_travel():
    labelled = CV.Attributed(field="exposure", value="imports",
                             origin=CV.SECTOR_PRIOR,
                             note="for companies in this sector")
    CV.refuse_prior_as_observation([labelled], surface="brief")


def test_an_observation_must_cite_something():
    """An observation without an evidence id is indistinguishable from a
    prior somebody relabelled — the one substitution this contract prevents."""
    with pytest.raises(CV.CoverageRejected):
        CV.Attributed(field="exposure", value="imports",
                      origin=CV.COMPANY_OBSERVATION)


def test_a_prior_may_not_carry_evidence_ids():
    """If the company's documents establish it, it is an observation. If they
    do not, the ids belong to another company and must not travel."""
    with pytest.raises(CV.CoverageRejected):
        CV.Attributed(field="exposure", value="imports",
                      origin=CV.SECTOR_PRIOR, evidence_ids=("ev1",))


def test_an_inferred_value_is_not_a_measured_one():
    inferred = CV.Attributed(field="margin", value="falling",
                             origin=CV.INFERRED)
    assert not inferred.speakable
    with pytest.raises(CV.CoverageRejected):
        CV.refuse_prior_as_observation([inferred])


def test_an_unknown_origin_is_refused_rather_than_assumed():
    with pytest.raises(CV.CoverageRejected):
        CV.Attributed(field="x", value="y", origin="PROBABLY_TRUE")


def test_every_origin_has_a_distinct_voice():
    voices = [CV.ORIGIN_VOICE[o] for o in CV.ORIGINS]
    assert len(set(voices)) == len(voices)


# --- the baseline object ----------------------------------------------------

def test_observed_cannot_be_claimed_with_no_observed_field():
    """The state would claim exactly what the fields deny."""
    with pytest.raises(CV.CoverageRejected):
        CV.Coverage(company="ACME", state=CV.OBSERVED,
                    fields=(sector_prior(),))


def test_degraded_must_name_the_source_that_went_dark():
    """An unnamed degradation cannot be chased, recovered or aged out."""
    with pytest.raises(CV.CoverageRejected):
        CV.Coverage(company="ACME", state=CV.DEGRADED)


def test_the_baseline_reports_the_split_between_priors_and_observations():
    got = CV.baseline(Intel(economic_theses=(thesis(),)), company="ACME",
                      fields=(observed(), sector_prior(field="rates")))
    payload = got.as_dict()
    assert payload["observed_fields"] == 1
    assert payload["prior_fields"] == 1
    assert payload["state"] == CV.OBSERVED


def test_a_baseline_exists_even_with_nothing_known():
    got = CV.baseline(Intel(), company="NEWCO")
    assert got.state == CV.NEVER_ANALYSED
    assert got.ceiling == SC.ASSERT_NONE
    assert got.reading and got.must_not_conclude


# --- progressive hydration --------------------------------------------------

def test_a_prior_replaced_by_evidence_is_reported_rather_than_silent():
    """Hydration has to be visible, or it is indistinguishable from the
    engine having always known."""
    before = (sector_prior(value="rates, assumed"),)
    after = (observed(value="rates, stated in the 10-K"),)
    moves = CV.replacements(before, after)
    assert len(moves) == 1
    assert moves[0]["from_origin"] == CV.SECTOR_PRIOR
    assert moves[0]["to_origin"] == CV.COMPANY_OBSERVATION
    assert moves[0]["evidence_ids"] == ["ev1"]


def test_an_unchanged_field_is_not_reported_as_a_replacement():
    same = (observed(),)
    assert CV.replacements(same, same) == ()


def test_coverage_improving_is_ordered_but_degraded_is_not_on_the_ladder():
    assert CV.improved(CV.NEVER_ANALYSED, CV.PARTIALLY_OBSERVED)
    assert CV.improved(CV.PARTIALLY_OBSERVED, CV.OBSERVED)
    assert not CV.improved(CV.OBSERVED, CV.PARTIALLY_OBSERVED)
    # Coming back from DEGRADED is a source returning, not evidence arriving.
    assert not CV.improved(CV.DEGRADED, CV.OBSERVED)
    assert not CV.improved(CV.OBSERVED, CV.DEGRADED)


def test_hydration_failing_halfway_does_not_read_as_finished():
    """Retrieval that stops mid-flight leaves a partially filled dossier that
    looks exactly like one that finished and found little."""
    mid = Intel(evidence_ids=("ev1",), hydrating=True)
    finished = Intel(evidence_ids=("ev1",))
    assert CV.classify(mid, hydrating=True) != CV.classify(finished)


# --- the sparse company must not look like the covered one ------------------

def test_a_sparse_company_does_not_look_like_a_covered_one():
    """The proof the node asks for, on the surface an executive reads."""
    covered = CA.plan("What is happening?",
                      Intel(economic_theses=(thesis(),),
                            evidence_ids=("ev1", "ev2", "ev3")))
    sparse = CA.plan("What is happening?", Intel(evidence_ids=("ev1",)))
    withheld = CA.plan("What is happening?", Intel())

    assert covered.supported and not sparse.supported \
        and not withheld.supported
    assert covered.ceiling != sparse.ceiling
    assert len({covered.direct_answer, sparse.direct_answer,
                withheld.direct_answer}) == 3


def test_the_covered_company_is_the_only_one_that_may_assert():
    covered = CA.plan("What is happening?",
                      Intel(economic_theses=(thesis(),)))
    assert SC.may_assert(covered.ceiling)
    for empty in (Intel(), Intel(evidence_ids=("ev1",)),
                  Intel(hydrating=True)):
        assert not SC.may_assert(CA.plan("What is happening?", empty).ceiling)
