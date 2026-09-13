"""The producer's actual bytes, through the consumer's actual chain.

WHY THIS FILE EXISTS SEPARATELY FROM THE OTHER BRIDGE TESTS
------------------------------------------------------------
The two ends live on different branches of one repository and neither can
import the other. The founder branch has `external_intel/strategic_contract.py`
and no `market/` package; the market branch has `market/strategic_export.py`
and no `external_intel/`. There is no process in which both can be called.

So every other test on this side necessarily builds its own payload, and two
hand-written "equivalent" fixtures are precisely what drift apart while both
suites stay green. That is not hypothetical here: the bridge shipped with an
allowlist enforced at both ends, a producer, a consumer and a full test suite
on each side, and carried zero dossiers, because one end filed
`microsoft.json` and the other asked for `microsoft-corporation.json`.

`tests/fixtures/produced/` holds files the real publisher emitted from the real
production learning ledger. See its PROVENANCE.md. This module runs them
through the chain a founder is actually served:

  real dossier file -> validator -> identity resolver -> strategic context
  -> canonical projection -> graph provenance -> presenter block
"""
import json
import pathlib

import pytest

from intent_engine.external_intel import market_contract as MC
from intent_engine.external_intel import pack as PK
from intent_engine.external_intel import presenter as PS
from intent_engine.external_intel import projection as PJ
from intent_engine.external_intel import strategic_contract as SC

PRODUCED = pathlib.Path(__file__).parent / "fixtures" / "produced"
AS_OF = "2026-08-05"
SUBJECT = "Caterpillar Inc."


def _payload(name="caterpillar-inc"):
    return json.loads((PRODUCED / f"{name}.json").read_text())


def _resolved(names=("Caterpillar",), today=AS_OF):
    return SC.resolve(PRODUCED, names=list(names), today=today)


def _context(intel=None):
    return PK.ExternalContext(market=MC.absent("not under test"),
                              strategic=intel or _resolved(), as_of=AS_OF)


# --- schema and allowlist compatibility -------------------------------------
def test_the_producers_real_artifact_passes_the_consumers_allowlist():
    """The one assertion that cannot be made by a fixture either side wrote."""
    SC.validate(_payload())


def test_the_contract_versions_still_agree():
    assert _payload()["export_version"] == SC.SCHEMA_VERSION


def test_every_published_artifact_validates_not_only_the_convenient_one():
    for path in sorted(PRODUCED.glob("*.json")):
        SC.validate(json.loads(path.read_text()))


# --- identity compatibility -------------------------------------------------
def test_the_dossier_is_found_by_the_name_a_founder_would_type():
    intel = _resolved(["Caterpillar"])
    assert intel.available, intel.reason
    assert intel.company_id == "caterpillar-inc"
    assert intel.display_name == SUBJECT


@pytest.mark.parametrize("typed", ["Caterpillar", "Caterpillar Inc",
                                   "Caterpillar Inc.", "CAT", "caterpillar"])
def test_every_name_the_producer_declared_resolves(typed):
    assert _resolved([typed]).available


def test_the_producer_declared_the_identity_rather_than_implying_it():
    payload = _payload()
    assert payload["company_display_name"] == SUBJECT
    assert SUBJECT in payload["subject_names"]


def test_a_company_the_producer_named_no_founder_way_is_not_bound_by_proximity():
    """`stripe.json` was published under an internal id with no display name.

    The honest outcome is that a founder cannot find it -- not that the
    resolver attaches the nearest dossier to the company being analysed.
    """
    assert not _resolved(["Stripe, Inc."]).available


def test_a_company_with_no_dossier_is_a_clean_absence():
    intel = _resolved(["A Company Nobody Published"])
    assert not intel.available
    assert intel.reason


# --- evidence lineage -------------------------------------------------------
def test_the_belief_keeps_the_evidence_ids_the_producer_published():
    published = set(_payload()["strategic_beliefs"][0]["evidence_ids"])
    carried = set(_resolved().beliefs[0]["evidence_ids"])
    assert published == carried


def test_the_as_of_and_schema_survive_to_the_graph():
    nodes, _ = PJ.project(_context(), company=SUBJECT)
    strategic = [n for n in nodes
                 if n.attrs.get("role") in PJ.STRATEGIC_ROLES]
    assert strategic
    for node in strategic:
        assert node.attrs["schema_version"] == SC.SCHEMA_VERSION
        assert node.attrs["dossier_as_of"] == AS_OF


# --- the whole crossing -----------------------------------------------------
def test_the_real_artifact_reaches_a_founder_visible_block():
    blocks = PS.strategic_blocks(_context())
    assert blocks, "the real dossier produced no founder-visible block"
    assert SUBJECT in blocks[0].fact


def test_the_projection_is_reached_on_the_real_artifact():
    provenance = PJ.belief_provenance(_context(), company=SUBJECT)
    assert provenance
    entry = next(iter(provenance.values()))
    assert entry["supports"], "the belief reached the graph with its basis"
    assert entry["evidence_ids"] == list(
        _payload()["strategic_beliefs"][0]["evidence_ids"])


def test_the_block_speaks_the_maturity_the_producer_actually_published():
    """DECLARED upstream must not read as tested downstream."""
    assert _payload()["strategic_beliefs"][0]["update_method"] == "DECLARED"
    block = PS.strategic_blocks(_context())[0]
    assert "newly formed reading" in block.fact
    assert "not a tested conclusion" in block.fact


def test_no_percentage_is_printed_for_a_heuristic_confidence():
    published = _payload()["strategic_beliefs"][0]["confidence"]
    assert published == 0.586
    block = PS.strategic_blocks(_context())[0]
    for rendered in ("58%", "59%", "0.586", "58.6"):
        assert rendered not in block.fact
        assert rendered not in block.text_alternative


# --- refusals, on the real shape --------------------------------------------
def test_an_unknown_field_added_to_the_real_artifact_fails_closed():
    payload = _payload()
    payload["positions_opened"] = 3
    with pytest.raises(SC.StrategicLeak):
        SC.validate(payload)


def test_a_nested_trading_field_in_the_real_artifact_fails_closed():
    payload = _payload()
    payload["strategic_beliefs"][0]["sharpe"] = 1.8
    with pytest.raises(SC.StrategicLeak):
        SC.validate(payload)


def test_a_trading_internal_smuggled_into_real_prose_fails_closed():
    payload = _payload()
    payload["strategic_beliefs"][0]["basis"] = (
        "opened after the paper book showed a sharpe of 1.8 on this name")
    with pytest.raises(SC.StrategicLeak):
        SC.validate(payload)


def test_no_founder_facing_text_from_the_real_artifact_names_a_trading_internal():
    block = PS.strategic_blocks(_context())[0]
    text = " ".join([block.fact, block.so_what, block.decision,
                     block.limitation, block.text_alternative]).lower()
    # The contract's own list, not a second one written here. A bare
    # "position" would be a false positive -- "an opening position" is a
    # sentence about a belief -- and maintaining a rival list is how the two
    # would come to disagree about what is banned.
    for banned in SC._BANNED_SUBSTRINGS:
        assert banned not in text, banned


def test_the_founder_never_sees_the_internal_slug():
    block = PS.strategic_blocks(_context())[0]
    text = " ".join([block.fact, block.so_what, block.text_alternative])
    assert "caterpillar-inc" not in text


def test_the_founder_never_sees_a_raw_evidence_id():
    block = PS.strategic_blocks(_context())[0]
    text = " ".join([block.fact, block.so_what, block.limitation,
                     block.text_alternative])
    for evidence_id in _payload()["evidence_ids"]:
        assert evidence_id not in text


def test_a_stale_real_artifact_is_refused_however_well_it_resolves():
    intel = _resolved(["Caterpillar"], today="2027-01-01")
    assert not intel.available
    assert intel.reason
