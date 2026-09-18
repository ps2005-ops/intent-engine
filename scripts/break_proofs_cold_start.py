"""Break proofs for L-CLD-001: a prior presented as a prior.

Proof A is the one to read. It restores the single sentence that covered six
different situations — including a company nobody has looked at and a company
whose sources have gone dark, which call for opposite actions.

Proof E is the commercial one: it lets a sector claim be spoken in the voice
of a company claim, which is the failure the whole T0 surface exists to
prevent.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

E = ROOT / "src/intent_engine/external_intel"
T = "tests"
CS = f"{T}/test_founder_cold_start.py"

PROOFS = [
    ("A. every kind of nothing shares one sentence again",
     E / "coverage_state.py",
     "    NEVER_ANALYSED:\n"
     '        "We have not analysed this company. Nothing here is a finding '
     'about "\n'
     '        "it — there is no record to have a finding in.",',
     "    NEVER_ANALYSED:\n"
     '        "We have some of this company\'s evidence and not enough to '
     'form a "\n'
     '        "view. What is missing is listed rather than filled in.",',
     f"{CS}::test_the_six_kinds_of_nothing_do_not_share_a_sentence"),

    ("B. a dark source stops outranking a surviving thesis",
     E / "coverage_state.py",
     "    if degraded_sources and (theses or evidence or beliefs):",
     "    if False:",
     f"{CS}::test_a_dark_source_outranks_a_surviving_thesis"),

    ("C. lost visibility reads as a quiet company",
     E / "coverage_state.py",
     "    DEGRADED:\n"
     '        "fewer observations is reduced visibility, never reduced '
     'activity; "\n'
     '        "this company has not been shown to have stopped doing '
     'anything",',
     "    DEGRADED:\n"
     '        "the company appears to have gone quiet",',
     f"{CS}::test_lost_visibility_is_never_reported_as_a_quiet_company"),

    ("D. a partial view licenses an assertion",
     E / "coverage_state.py",
     "    PARTIALLY_OBSERVED: SC.ASSERT_NONE,",
     "    PARTIALLY_OBSERVED: SC.ASSERT_LEADING,",
     f"{CS}::test_no_state_short_of_observed_licenses_an_assertion"),

    ("E. a sector prior may be spoken as a company fact",
     E / "coverage_state.py",
     "    if offenders:\n"
     "        raise CoverageRejected(",
     "    if False:\n"
     "        raise CoverageRejected(",
     f"{CS}::test_a_sector_prior_cannot_be_spoken_as_a_company_fact"),

    ("F. an observation need not cite anything",
     E / "coverage_state.py",
     "        if self.origin == COMPANY_OBSERVATION and not self.evidence_ids:\n"
     "            raise CoverageRejected(",
     "        if False:\n"
     "            raise CoverageRejected(",
     f"{CS}::test_an_observation_must_cite_something"),

    ("G. a prior may carry another company's evidence ids",
     E / "coverage_state.py",
     "        if self.origin in PRIORS and self.evidence_ids:\n"
     "            raise CoverageRejected(",
     "        if False:\n"
     "            raise CoverageRejected(",
     f"{CS}::test_a_prior_may_not_carry_evidence_ids"),

    ("H. an inferred value counts as an observation",
     E / "coverage_state.py",
     "OBSERVATIONS = frozenset({COMPANY_OBSERVATION})",
     "OBSERVATIONS = frozenset({COMPANY_OBSERVATION, INFERRED})",
     f"{CS}::test_an_inferred_value_is_not_a_measured_one"),

    ("I. an unknown origin is assumed rather than refused",
     E / "coverage_state.py",
     "        if self.origin not in ORIGINS:\n"
     "            raise CoverageRejected(f\"unknown origin {self.origin!r}\")",
     "        if False:\n"
     "            raise CoverageRejected(f\"unknown origin {self.origin!r}\")",
     f"{CS}::test_an_unknown_origin_is_refused_rather_than_assumed"),

    ("J. OBSERVED may be claimed with no observed field",
     E / "coverage_state.py",
     "        if self.state == OBSERVED and not any(\n"
     "                f.speakable for f in self.fields):\n"
     "            raise CoverageRejected(",
     "        if False:\n"
     "            raise CoverageRejected(",
     f"{CS}::test_observed_cannot_be_claimed_with_no_observed_field"),

    ("K. a degradation need not name its source",
     E / "coverage_state.py",
     "        if self.state == DEGRADED and not self.degraded_sources:\n"
     "            raise CoverageRejected(",
     "        if False:\n"
     "            raise CoverageRejected(",
     f"{CS}::test_degraded_must_name_the_source_that_went_dark"),

    ("L. a prior becoming an observation happens silently",
     E / "coverage_state.py",
     "        if old is None or old.origin == field.origin:\n"
     "            continue",
     "        if True:\n"
     "            continue",
     f"{CS}::test_a_prior_replaced_by_evidence_is_reported_rather_than_silent"),

    ("M. hydration in flight reads as finished",
     E / "coverage_state.py",
     "    if hydrating:\n        return HYDRATING",
     "    if False:\n        return HYDRATING",
     f"{CS}::test_hydration_failing_halfway_does_not_read_as_finished"),

    ("N. the unsupported plan goes back to an undecided ceiling",
     E / "ceo_answers.py",
     '    kwargs.setdefault("ceiling", SC.ASSERT_NONE)',
     '    kwargs.setdefault("ceiling", "")',
     f"{CS}::test_an_unsupported_plan_carries_a_decided_ceiling"),

    ("O. the CEO surface stops saying which kind of nothing",
     E / "ceo_answers.py",
     "        answer, forbids, ceiling_ = _no_view_answer(intel)\n"
     "        return _unsupported(\n"
     "            question, cls, answer, source_constraints=constraints,\n"
     "            must_not_conclude=forbids, ceiling=ceiling_)",
     "        return _unsupported(\n"
     "            question, cls,\n"
     '            "No economic view is recorded for this company yet.",\n'
     "            source_constraints=constraints)",
     f"{CS}::test_the_ceo_surface_says_which_kind_of_nothing"),

    ("P. a sparse company reads like a covered one",
     E / "coverage_state.py",
     "    if theses:\n        return OBSERVED\n"
     "    if evidence or beliefs:\n        return PARTIALLY_OBSERVED",
     "    if theses or evidence or beliefs:\n        return OBSERVED",
     f"{CS}::test_a_sparse_company_does_not_look_like_a_covered_one"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"cold-start — L-CLD-001, a prior presented as a prior: "
               f"{len(PROOFS)} proofs")))
