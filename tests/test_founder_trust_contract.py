"""The trust block crosses because it is declared, and telemetry counts use.

Two separate failure modes live here. The first is a consumer that accepts
whatever the file happens to contain — the allowlist must walk INTO the trust
block, not merely permit it. The second is telemetry that counts a dossier as
"reasoned from normalized evidence" because a normalized dossier existed,
which is the failure that looks most like success.
"""
from __future__ import annotations

import copy
import json

import pytest

from intent_engine.external_intel import consumption_receipt as cr
from intent_engine.external_intel import evidence_trust as et
from intent_engine.external_intel import founder_learning_health as flh
from intent_engine.external_intel import strategic_contract as sc

TRUST = {
    "contract": "evidence_trust.v1", "standing": "DEPENDENT_REREPORTING",
    "raw_accounts": 3, "distinct_events": 1, "independent_support": 1,
    "weight": 1.0,
    "sentence": "Several reports repeat the same underlying announcement.",
    "events": [{"event_id": "evt_0", "standing": "DEPENDENT_REREPORTING",
                "accounts": 3, "weight": 1.0,
                "evidence_ids": ["ev_0", "ev_1", "ev_2"]}],
}


def _dossier(trust=TRUST):
    # Deep-copied: the refusal tests below mutate the payload they are given,
    # and a shared nested dict would carry that mutation into every later
    # test — which is how a fixture starts asserting a state no production
    # code can produce.
    trust = copy.deepcopy(trust) if trust is not None else None
    belief = {
        "proposition": "Acme is moving upmarket", "subject": "Acme Corp",
        "confidence": 0.586, "direction_of_last_change": "UP",
        "last_updated": "2026-08-05", "basis": "b",
        "update_method": "CORROBORATED",
        "evidence_ids": ["ev_0", "ev_1", "ev_2"], "limitations": [],
    }
    if trust is not None:
        belief["evidence_trust"] = trust
    return {
        "export_version": sc.SCHEMA_VERSION, "generated_at": "2026-08-05",
        "company_id": "acme", "company_display_name": "Acme Corp",
        "subject_names": ["Acme Corp"], "as_of": "2026-08-05",
        "strategic_beliefs": [belief], "limitations": [],
        "evidence_ids": ["ev_0", "ev_1", "ev_2"],
        "disclaimer": sc.DISCLAIMER,
    }


# --- the contract ---------------------------------------------------------

def test_a_normalized_dossier_validates():
    intel = sc.consume(_dossier(), today="2026-08-06")
    assert intel.available, intel.reason
    assert intel.beliefs[0]["evidence_trust"]["distinct_events"] == 1


def test_an_undeclared_field_in_the_trust_block_is_refused():
    """The allowlist must walk INTO the block. A schema that permits the
    block but not its contents is a schema that renders anything."""
    payload = _dossier()
    payload["strategic_beliefs"][0]["evidence_trust"]["sharpe"] = 1.4
    intel = sc.consume(payload, today="2026-08-06")
    assert not intel.available
    assert "refused" in intel.reason


def test_an_undeclared_field_inside_the_events_list_is_refused():
    payload = _dossier()
    payload["strategic_beliefs"][0]["evidence_trust"]["events"][0][
        "position_size"] = 3
    intel = sc.consume(payload, today="2026-08-06")
    assert not intel.available


def test_a_dossier_without_trust_still_validates():
    """Older producers must keep working. Their beliefs are simply unrated."""
    intel = sc.consume(_dossier(trust=None), today="2026-08-06")
    assert intel.available, intel.reason
    assert et.of_belief(intel.beliefs[0]).standing == et.UNKNOWN


# --- telemetry: availability is not use -----------------------------------

def _emit(tmp_path, payload):
    intel = sc.consume(payload, today="2026-08-06")
    cr.acknowledge_context(
        tmp_path, company_id="acme", analysis_id="run1", strategic=intel,
        has_strategic=True, analysis_as_of="2026-08-06", rendered_blocks=1,
        surface="analysis")
    return [json.loads(line) for line in
            (tmp_path / cr.LEDGER_PATH).read_text().splitlines() if line]


def test_a_normalized_dossier_emits_the_trust_stage(tmp_path):
    stages = {r["stage"] for r in _emit(tmp_path, _dossier())}
    assert cr.TRUST_NORMALIZED in stages


def test_an_unnormalized_dossier_emits_no_trust_stage(tmp_path):
    """The gap between available and used has to be readable. A dossier the
    producer never normalized must not be credited with normalization."""
    stages = {r["stage"] for r in _emit(tmp_path, _dossier(trust=None))}
    assert cr.TRUST_NORMALIZED not in stages


def test_health_reads_the_new_stage(tmp_path):
    """The ladder is declared once. A stage the health reader has not heard
    of ranks below every other and silently vanishes."""
    _emit(tmp_path, _dossier())
    health = flh.assess(tmp_path)
    assert health["trust_normalized_consumptions"] == 1
    # One analysis is not a rate. The module refuses to divide below three,
    # deliberately and by the same threshold as the market side, so the two
    # reports cannot disagree about what counts as measurable.
    assert health["normalized_rate"] == flh.UNMEASURABLE


def test_the_normalized_rate_becomes_measurable_with_enough_analyses(tmp_path):
    for n in range(3):
        intel = sc.consume(_dossier(), today="2026-08-06")
        cr.acknowledge_context(
            tmp_path, company_id="acme", analysis_id=f"run{n}",
            strategic=intel, has_strategic=True, analysis_as_of="2026-08-06",
            rendered_blocks=1, surface="analysis")
    health = flh.assess(tmp_path)
    assert health["trust_normalized_consumptions"] == 3
    assert health["normalized_rate"] == 1.0


def test_the_ladder_is_declared_once():
    assert cr.TRUST_NORMALIZED in cr.LADDER
    assert flh._ORDER == {n: i for i, n in enumerate(cr.LADDER)}


def test_the_trust_stage_sits_between_use_and_rendering():
    """It qualifies what was used: a dossier can be fully consumed and still
    have been consumed by counting rows."""
    assert (cr.LADDER.index(cr.USED_IN_REASONING)
            < cr.LADDER.index(cr.TRUST_NORMALIZED)
            < cr.LADDER.index(cr.RENDERED_TO_FOUNDER))


# --- historical stability -------------------------------------------------

def test_reading_a_dossier_twice_produces_the_same_standing():
    """A newly deployed trust model must not silently rewrite what a founder
    was previously shown. The projection is pure, so the same dossier gives
    the same standing however many times it is read."""
    first = sc.consume(_dossier(), today="2026-08-06")
    second = sc.consume(_dossier(), today="2026-08-06")
    assert et.of_belief(first.beliefs[0]) == et.of_belief(second.beliefs[0])


def test_an_old_dossier_is_not_retroactively_rated(tmp_path):
    """An analysis generated under the old semantics stays what it was. The
    absence of a standing is preserved rather than filled in."""
    intel = sc.consume(_dossier(trust=None), today="2026-08-06")
    assert intel.evidence_trust is None
    assert et.of_belief(intel.beliefs[0]).standing == et.UNKNOWN
