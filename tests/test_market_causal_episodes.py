"""Causal episodes built from real preregistered tests — and the self-test bug.

`causal.py` shipped a complete CausalEdge long ago and held zero edges. The
missing piece was never the model; it was a source of episodes good enough to
justify one. Informative reconciliations are that source.

Building the episodes immediately exposed a defect nothing else had: three of
ten "independent" tests scored a belief against the sentence that opened it,
arriving with a different evidence id. All three came back CONFIRMED.
"""
import pytest

from intent_engine.market import causal as C
from intent_engine.market import causal_episodes as CE
from intent_engine.market import observation_binding as OB
from intent_engine.market import micro_evidence as ME
from intent_engine.market import expectation as EXP


def _rows(outcome="CONFIRMED", family="demand_strengthening"):
    return [
        {"record": "evidence", "evidence_id": "ev_open",
         "observed_at": "2026-08-01", "fact": "Revenue rose 12% in Q2"},
        {"record": "evidence", "evidence_id": "ev_test",
         "observed_at": "2026-08-06", "fact": "Guidance raised for the year"},
        {"record": "expectation", "expectation_id": "e1", "subject": "acme",
         "metric": family, "preregistered_at": "2026-08-01",
         "expected_event": "the next reported revenue or guidance figure",
         "expected_direction": "UP", "evidence_basis": ["ev_open"]},
        {"record": "reconciliation", "expectation_id": "e1", "subject": "acme",
         "outcome": outcome, "observed_direction": "UP",
         "evidence_ids": ["ev_test"]},
    ]


# ===========================================================================
# EPISODES COME FROM REAL TESTS, NOT FROM ORDERING
# ===========================================================================
def test_an_episode_needs_a_preregistered_expectation_and_an_outcome():
    assert len(CE.build(_rows())) == 1
    # a reconciliation that settled nothing is not an episode
    assert CE.build(_rows(outcome="TOO_EARLY")) == ()


def test_a_family_with_no_separately_observable_effect_makes_no_episode():
    """Otherwise the "effect" is a paraphrase of the cause."""
    assert CE.build(_rows(family="capacity_expansion")) == ()


def test_the_timeline_orders_opener_expectation_and_test():
    episode = CE.build(_rows())[0]
    roles = [t["role"] for t in episode.timeline]
    assert roles == ["opened the belief", "expectation preregistered",
                     "tested the expectation"]


# ===========================================================================
# WHAT IT REFUSES TO CLAIM
# ===========================================================================
def test_no_edge_is_ever_observed():
    """Causation is not observed. Events are; the link is inferred."""
    summary = CE.summarise(CE.build(_rows()))
    assert summary["observed_edges"] == 0
    assert summary["hypothesized_edges"] == 1


def test_one_test_never_promotes_an_edge():
    episode = CE.build(_rows())[0]
    assert episode.edge_status == C.HYPOTHESIZED


def test_every_episode_carries_the_common_cause_alternative():
    """Always live: a sector-wide shift moves both observations without
    either causing the other, and no within-company evidence rules it out."""
    episode = CE.build(_rows())[0]
    assert CE.COMMON_CAUSE in episode.alternative_explanations
    assert CE.REPORTING_ARTEFACT in episode.alternative_explanations


def test_a_contradicted_episode_weakens_rather_than_refutes():
    episode = CE.build(_rows(outcome="CONTRADICTED"))[0]
    assert "weakened, not refuted" in episode.what_was_learned


def test_an_edge_cannot_be_built_without_a_mechanism():
    with pytest.raises(C.CausalError):
        C.edge(cause="a", effect="b", direction=C.POSITIVE, mechanism="")


# ===========================================================================
# THE SELF-TEST BUG
# ===========================================================================
def test_the_same_fact_under_a_new_id_cannot_test_its_own_belief():
    """Measured on the real ledger: 3 of 10 informative results did this.

    The same wire story arrives twice, from two outlets, with two ids and
    near-identical text. Holding out the basis by id let it straight through,
    and every one of those self-tests came back CONFIRMED — which is exactly
    how a channel that cannot fail looks from outside.
    """
    fact = "Acme Corp revenue rose 12% in the second quarter"
    opener = ME.MicroEvidence(
        evidence_id="ev_open", subject_company="acme", actor="acme",
        evidence_type="EARNINGS_RESULT", observed_at="2026-08-01",
        available_at="2026-08-01", source="https://a.test", fact=fact)
    restated = ME.MicroEvidence(
        evidence_id="ev_other", subject_company="acme", actor="acme",
        evidence_type="EARNINGS_RESULT", observed_at="2026-08-06",
        available_at="2026-08-06", source="https://b.test",
        fact=fact + " - Reuters")
    exp = EXP.ExpectedObservation(
        expectation_id="e1", hypothesis_id="b1", subject="acme",
        expected_event="the next reported figure", expected_direction=EXP.UP,
        preregistered_at="2026-08-01", evaluation_window_ends="2026-12-01",
        falsifier="a lower figure", metric="demand_strengthening",
        evidence_basis=("ev_open",))

    bound, refused = OB.bind([exp], [opener, restated], as_of="2026-08-07")
    assert bound == {}
    assert refused["restates_the_evidence_that_opened_it"] == 1


def test_a_genuinely_different_later_fact_still_binds():
    """The guard must not have bought silence."""
    opener = ME.MicroEvidence(
        evidence_id="ev_open", subject_company="acme", actor="acme",
        evidence_type="EARNINGS_RESULT", observed_at="2026-08-01",
        available_at="2026-08-01", source="https://a.test",
        fact="Acme Corp revenue rose 12% in the second quarter")
    later = ME.MicroEvidence(
        evidence_id="ev_new", subject_company="acme", actor="acme",
        evidence_type="GUIDANCE_REVISION", observed_at="2026-08-06",
        available_at="2026-08-06", source="https://b.test",
        fact="Acme Corp raised full-year guidance after strong bookings")
    exp = EXP.ExpectedObservation(
        expectation_id="e1", hypothesis_id="b1", subject="acme",
        expected_event="the next reported figure", expected_direction=EXP.UP,
        preregistered_at="2026-08-01", evaluation_window_ends="2026-12-01",
        falsifier="a lower figure", metric="demand_strengthening",
        evidence_basis=("ev_open",))
    bound, _ = OB.bind([exp], [opener, later], as_of="2026-08-07")
    assert bound["e1"]["evidence_ids"] == ("ev_new",)


def test_the_fingerprint_ignores_the_outlet_attribution():
    assert OB._fingerprint("Revenue rose 12% - Reuters") == \
        OB._fingerprint("Revenue rose 12% - Yahoo Finance")
