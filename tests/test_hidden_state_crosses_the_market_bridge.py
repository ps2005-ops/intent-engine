"""Pre-100 Batch 3: the founder end of the hidden-state block.

The contract fails closed on unknown fields, and a previous batch lost all 22
dossiers to exactly two unrecognised names. So adding a block on the market
side is only half the wiring: if this side does not know it, the field is
dropped and the product shows nothing, which looks identical to the market
never having produced it.
"""
from intent_engine.demo_dossier import contracts as C


def _snapshot(**over):
    payload = {
        "contract_version": "market_demo_snapshot.v1",
        "snapshot_id": "ms-test", "company_id": "cloudflare-inc",
        "canonical_name": "Cloudflare, Inc.", "subject_names": ["Cloudflare"],
        "availability": "AVAILABLE", "unavailable_reason": "",
        "generated_at": "2026-08-14", "known_at": "2026-08-14",
        "evidence_cutoff": "2026-08-14", "market_population": "REAL_MARKET",
        "hidden_state_refs": {"state": "AVAILABLE",
                              "ids": ["PLATFORM_EXPANDING"], "count": 1,
                              "note": ""},
    }
    payload.update(over)
    return payload


def test_hidden_state_refs_is_not_an_unknown_field():
    """If this regresses, the block is silently dropped at the bridge."""
    read = C.read_market_snapshot(_snapshot(),
                                  expected_company="cloudflare-inc")
    assert "hidden_state_refs" not in list(read.unknown_fields or ())


def test_hidden_state_refs_arrives_with_its_posture_intact():
    read = C.read_market_snapshot(_snapshot(),
                                  expected_company="cloudflare-inc")
    block = (read.blocks or {}).get("hidden_state_refs")
    assert block is not None, "the block did not survive the contract"
    assert block.state == "AVAILABLE"
    assert block.count == 1
    assert list(block.ids) == ["PLATFORM_EXPANDING"]


def test_a_snapshot_without_hidden_state_still_reads_as_did_not_run():
    """Absent must stay distinguishable from present-and-empty."""
    payload = _snapshot()
    payload.pop("hidden_state_refs")
    read = C.read_market_snapshot(payload, expected_company="cloudflare-inc")
    block = (read.blocks or {}).get("hidden_state_refs")
    assert block is None or block.state != "AVAILABLE"


def test_the_dossier_view_lists_hidden_states_as_a_block():
    """A block the assembler does not name can never reach a surface."""
    from intent_engine.demo_dossier import assembler as A
    names = dict(A._MARKET_VIEW)
    assert names.get("hidden_states") == "hidden_state_refs"
