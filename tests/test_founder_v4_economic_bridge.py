"""The economy crosses the bridge, and arrives no more confident than it left."""
from __future__ import annotations

from datetime import date

from intent_engine.external_intel import strategic_contract as SC


def dossier(**overrides):
    payload = {
        "export_version": SC.SCHEMA_VERSION,
        "generated_at": "2026-08-08T00:00:00+00:00",
        "company_id": "acme", "company_display_name": "Acme",
        "subject_names": ["Acme"], "as_of": date.today().isoformat(),
        "economic_context": {
            "conditions": [{"area": "CA", "state_kind": "POLICY_RATE",
                            "standing": "OBSERVED", "moved": "FLAT",
                            "reason": "target for the overnight rate 2.25%"}],
            "conditions_tracked": 30, "conditions_known": 13,
            "note": "an unmeasured condition is absent from this list"},
        "economic_theses": [{
            "thesis_id": "th_1",
            "claim": "the move in MARKET_RATE is expected to lower capex",
            "standing": "PROPOSED", "question": "what does the rate mean?",
            "horizon_days": 270, "macro_conditions": ["MARKET_RATE"],
            "exposures": ["CAPITAL_INTENSITY"],
            "mechanism": "a higher cost of capital raises the hurdle",
            "falsifier": "capital spending is raised anyway",
            "alternatives": ["the programme was already committed"],
            "unknowns": ["no outcome observed yet"],
            "decision_implication": "do not act on this yet",
            "confidence_in_words": "we have not tested this",
            "evidence_ids": ["e1"]}],
        "disclaimer": SC.DISCLAIMER,
    }
    payload.update(overrides)
    return payload


def test_the_economic_block_crosses():
    got = SC.consume(dossier(), expected_company="acme")
    assert got.available is True
    assert got.economic_context["conditions_known"] == 13
    assert len(got.economic_theses) == 1


def test_an_absent_economic_block_is_none_not_an_empty_economy():
    payload = dossier()
    payload.pop("economic_context")
    payload.pop("economic_theses")
    got = SC.consume(payload, expected_company="acme")
    assert got.available is True
    assert got.economic_context is None
    assert got.economic_theses == ()


def test_a_thesis_arriving_without_rivals_is_downgraded_not_rendered():
    payload = dossier()
    payload["economic_theses"][0]["standing"] = "TESTED"
    payload["economic_theses"][0]["alternatives"] = []
    got = SC.consume(payload, expected_company="acme")
    assert got.economic_theses[0]["standing"] == "PROPOSED"
    assert "renders as the only one" in \
        got.economic_theses[0]["downgraded_because"]


def test_a_thesis_with_rivals_keeps_its_standing():
    payload = dossier()
    payload["economic_theses"][0]["standing"] = "SUPPORTED"
    got = SC.consume(payload, expected_company="acme")
    assert got.economic_theses[0]["standing"] == "SUPPORTED"
    assert "downgraded_because" not in got.economic_theses[0]


def test_an_unlisted_economic_field_still_fails_the_whole_dossier():
    """The allowlist is declared twice; a producer-only field must be refused."""
    payload = dossier()
    payload["economic_theses"][0]["price_target"] = 42
    got = SC.consume(payload, expected_company="acme")
    assert got.available is False
    assert "refused by the founder-side contract" in got.reason


def test_the_economic_block_cannot_smuggle_trading_language():
    payload = dossier()
    payload["economic_theses"][0]["claim"] = "a clear buy signal on rates"
    got = SC.consume(payload, expected_company="acme")
    assert got.available is False
