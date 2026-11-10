"""The economy as a dated state, and the three ways it lies if you let it.

1. A statistic pretending to be a conclusion about a company.
2. A reference period pretending to be a publication date.
3. A revision pretending it was always known.
"""
from __future__ import annotations

import pytest

from intent_engine.market import macro_state as MS


def obs(**kw):
    base = dict(state_kind=MS.POLICY_RATE, series_id="DGS10",
                label="10-year Treasury", value=4.2, unit="%",
                reference_period="2026-06-30", published_at="2026-07-15",
                retrieved_at="2026-08-08", source="treasury")
    base.update(kw)
    return MS.MacroObservation(**base)


# --- a statistic is not a conclusion ---------------------------------------

def test_a_macro_state_refuses_to_say_what_it_means_for_a_company():
    """THE FUNCTION THAT MUST NOT EXIST. A plausible sentence is always
    available here, and producing one would turn a national figure into a
    claim about a specific company without touching its exposure."""
    state = MS.state_of(MS.POLICY_RATE, [obs()], as_of="2026-08-08")
    with pytest.raises(MS.CausalOverreach):
        MS.consequence_of(state, "shopify")


def test_a_macro_observation_carries_no_company():
    """The moment it knows whose it is, it will be read as a claim about
    them."""
    assert not hasattr(obs(), "company")
    assert not hasattr(obs(), "subject")


# --- three times, never conflated ------------------------------------------

def test_a_figure_cannot_describe_a_period_that_had_not_finished():
    with pytest.raises(MS.MacroRejected, match="had not finished"):
        obs(reference_period="2026-09-30", published_at="2026-07-15")


def test_a_reference_period_is_required():
    """Falling back to the retrieval date is how a June figure becomes an
    August one."""
    with pytest.raises(MS.MacroRejected, match="period it describes"):
        obs(reference_period="")


def test_availability_is_decided_by_publication_not_by_reference_period():
    o = obs(reference_period="2026-06-30", published_at="2026-07-15")
    assert not o.known_at("2026-07-01"), "the June figure did not exist in June"
    assert o.known_at("2026-07-15")
    assert o.known_at("2026-08-01")


def test_an_unpublished_figure_is_never_known():
    assert not obs(published_at="").known_at("2030-01-01")


# --- revisions append -------------------------------------------------------

def test_a_revision_supersedes_rather_than_overwrites():
    first = obs(value=2.1, published_at="2026-07-15")
    second = MS.revise(first, value=1.4, published_at="2026-08-27")
    assert second.supersedes == first.observation_id
    assert second.observation_id != first.observation_id
    assert first.value == 2.1, "the original figure must survive the revision"


def test_a_revision_cannot_predate_what_it_revises():
    first = obs(published_at="2026-07-15")
    with pytest.raises(MS.MacroRejected, match="cannot predate"):
        MS.revise(first, value=1.0, published_at="2026-06-01")


def test_a_decision_is_scored_against_the_vintage_it_could_have_seen():
    """THE LEAK. Revisions move toward the truth, so grading a July call
    against the August revision flatters the engine every time."""
    first = obs(value=2.1, published_at="2026-07-15")
    revised = MS.revise(first, value=1.4, published_at="2026-08-27")
    both = [first, revised]

    in_july = MS.as_known_at(both, "2026-08-01")
    assert [o.value for o in in_july] == [2.1]

    in_september = MS.as_known_at(both, "2026-09-01")
    assert [o.value for o in in_september] == [1.4]


def test_a_state_built_for_a_past_date_cannot_see_a_later_revision():
    first = obs(value=2.1, published_at="2026-07-15")
    revised = MS.revise(first, value=1.4, published_at="2026-08-27")
    state = MS.state_of(MS.POLICY_RATE, [first, revised], as_of="2026-08-01")
    assert state.observation.value == 2.1


# --- unknown is not flat ----------------------------------------------------

def test_an_unmeasured_condition_is_unknown_and_never_flat():
    """"we did not measure this" and "this did not move" support completely
    different decisions."""
    state = MS.state_of(MS.HOUSING, [obs()], as_of="2026-08-08")
    assert state.standing == MS.UNKNOWN
    assert not state.known
    assert not state.anchors
    assert state.observation is None


def test_an_unknown_condition_cannot_anchor_a_chain():
    assert not MS.unknown(MS.GROWTH).anchors


def test_a_hypothesized_state_does_not_anchor_a_chain():
    """Somebody's opinion about the economy is not a measurement of it."""
    state = MS.state_of(MS.POLICY_RATE,
                        [obs(standing=MS.HYPOTHESIZED)], as_of="2026-08-08")
    assert state.known
    assert not state.anchors


def test_observed_and_inferred_both_anchor():
    for standing in (MS.OBSERVED, MS.INFERRED):
        state = MS.state_of(MS.POLICY_RATE, [obs(standing=standing)],
                            as_of="2026-08-08")
        assert state.anchors, standing


# --- direction --------------------------------------------------------------

def test_direction_reads_the_move_not_the_level():
    older = obs(value=3.9, reference_period="2026-05-31",
                published_at="2026-06-15")
    newer = obs(value=4.2, reference_period="2026-06-30",
                published_at="2026-07-15")
    state = MS.state_of(MS.POLICY_RATE, [older, newer], as_of="2026-08-08")
    assert state.moved == MS.UP
    assert state.prior.value == 3.9


def test_two_different_series_are_not_a_direction():
    a = obs(series_id="DGS10", value=4.2)
    b = obs(series_id="DGS02", value=3.1)
    with pytest.raises(MS.MacroRejected, match="different things"):
        MS.direction(a, b)


def test_a_level_is_not_differenced_against_a_change():
    a = obs(measure=MS.LEVEL, value=4.2)
    b = obs(measure=MS.CHANGE, value=0.3)
    with pytest.raises(MS.MacroRejected, match="level against a change"):
        MS.direction(b, a)


def test_a_first_observation_has_no_direction():
    state = MS.state_of(MS.POLICY_RATE, [obs()], as_of="2026-08-08")
    assert state.moved == MS.FLAT
    assert state.prior is None


# --- identity and summary ---------------------------------------------------

def test_identity_is_content_keyed_so_a_refetch_is_not_a_new_fact():
    assert obs().observation_id == obs().observation_id
    assert obs(retrieved_at="2027-01-01").observation_id == \
        obs().observation_id, "re-reading a figure does not make a new one"


def test_a_revised_value_is_a_different_observation():
    assert obs(value=4.2).observation_id != obs(value=4.3).observation_id


def test_the_summary_counts_standings_rather_than_averaging_them():
    states = [MS.state_of(MS.POLICY_RATE, [obs()], as_of="2026-08-08"),
              MS.unknown(MS.HOUSING), MS.unknown(MS.WAGES)]
    got = MS.summarise(states)
    assert got["conditions"] == 3
    assert got["anchoring"] == 1
    assert got["by_standing"] == {MS.OBSERVED: 1, MS.UNKNOWN: 2}
    assert got["unknown_kinds"] == [MS.HOUSING, MS.WAGES]
    assert "averaged" in got["note"]


def test_an_unknown_series_id_is_refused():
    with pytest.raises(MS.MacroRejected, match="series id"):
        obs(series_id="")


def test_an_unknown_state_kind_is_refused():
    with pytest.raises(MS.MacroRejected):
        obs(state_kind="VIBES")


# --- the chain anchor: what this module exists for -------------------------

def _ledger_rows():
    import json
    import pathlib
    p = pathlib.Path("/Users/prathamsharma/intent-engine-market/reports/"
                     "market/learning_ledger.jsonl")
    if not p.exists():                                   # pragma: no cover
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_a_measured_economy_makes_the_top_of_the_chain_knowable():
    """THE BOTTLENECK THIS CLOSES. Every chain was decapitated: the ledger
    holds only company-scoped evidence, so MACRO_STATE had no possible source
    and stood UNKNOWN on every subject."""
    from intent_engine.market import economic_chain as EC

    rows = _ledger_rows()
    if not rows:                                         # pragma: no cover
        return
    subject = EC.score_candidates(rows)[0]["subject"]
    macro = MS.state_of(MS.POLICY_RATE, [obs()], as_of="2026-08-08")

    before = EC.build(rows, subject=subject).as_dict()
    after = EC.build(rows, subject=subject, macro=macro).as_dict()

    node_before = [n for n in before["nodes"]
                   if n["node_type"] == "MACRO_STATE"][0]
    node_after = [n for n in after["nodes"]
                  if n["node_type"] == "MACRO_STATE"][0]
    assert node_before["status"] == "UNKNOWN"
    assert node_after["status"] == "KNOWN"
    assert after["known_nodes"] == before["known_nodes"] + 1
    # Provenance walks back to the series, not to a company row.
    assert node_after["evidence_ids"][0].startswith("macro_")


def test_an_opinion_about_the_economy_does_not_anchor_the_chain():
    """A HYPOTHESIZED macro state is somebody's view, not a measurement, and
    a chain resting on a view must not read as a measured one."""
    from intent_engine.market import economic_chain as EC

    rows = _ledger_rows()
    if not rows:                                         # pragma: no cover
        return
    subject = EC.score_candidates(rows)[0]["subject"]
    opinion = MS.state_of(MS.POLICY_RATE, [obs(standing=MS.HYPOTHESIZED)],
                          as_of="2026-08-08")
    built = EC.build(rows, subject=subject, macro=opinion).as_dict()
    node = [n for n in built["nodes"] if n["node_type"] == "MACRO_STATE"][0]
    assert node["status"] == "UNKNOWN"


def test_an_unknown_macro_state_leaves_the_chain_as_it_was():
    from intent_engine.market import economic_chain as EC

    rows = _ledger_rows()
    if not rows:                                         # pragma: no cover
        return
    subject = EC.score_candidates(rows)[0]["subject"]
    plain = EC.build(rows, subject=subject).as_dict()
    unmeasured = EC.build(rows, subject=subject,
                          macro=MS.unknown(MS.POLICY_RATE)).as_dict()
    assert unmeasured["known_nodes"] == plain["known_nodes"]


def test_filling_one_end_does_not_promote_the_link():
    """HONEST BOUNDS. A link needs evidence at BOTH ends, so anchoring the
    top of the chain must not silently upgrade the first link — the customer
    state below it is still unmeasured."""
    from intent_engine.market import economic_chain as EC

    rows = _ledger_rows()
    if not rows:                                         # pragma: no cover
        return
    subject = EC.score_candidates(rows)[0]["subject"]
    macro = MS.state_of(MS.POLICY_RATE, [obs()], as_of="2026-08-08")
    before = EC.build(rows, subject=subject).as_dict()
    after = EC.build(rows, subject=subject, macro=macro).as_dict()
    assert after["by_link_status"] == before["by_link_status"]
