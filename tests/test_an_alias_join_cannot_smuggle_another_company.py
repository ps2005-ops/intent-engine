"""The two sides key a company differently, and that must not open a door.

Found live on Render: Cloudflare's dossier joined both sides correctly and
came back QUARANTINED with WRONG_COMPANY_EVIDENCE, because the founder files
under the manifest id (`cloudflare`) and the market publishes under the key
from the legal name (`cloudflare-inc`), and the assembler compared the two
as strings. That is the third door this one collision has come through --
see the bridge's own docstring for the first two.

The repair widens what counts as the same company. So the test that matters
is not "does the legitimate join now pass" -- it is "can a WIDER rule be
made to attribute one company's intelligence to another". Both are here, and
the second is the one that would fail if this were done carelessly.
"""
import pytest

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.assembler import _quarantine, assemble
from intent_engine.demo_dossier.contracts import (FOUNDER_CONTRACT,
                                                  MARKET_CONTRACT,
                                                  read_founder_snapshot,
                                                  read_market_snapshot)


def _market(company_id: str):
    return read_market_snapshot({
        "contract_version": MARKET_CONTRACT, "snapshot_id": "ms-1",
        "company_id": company_id, "canonical_name": company_id,
        "market_run_id": "r1", "analysis_id": "a1", "runtime_sha": "s" * 40,
        "generated_at": "2026-08-14", "known_at": "2026-08-14",
        "evidence_cutoff": "2026-08-14", "availability": "AVAILABLE",
        "market_population": "REAL_MARKET",
        "evidence_reference_ids": {"state": "AVAILABLE", "count": 2,
                                   "ids": ["e1", "e2"], "note": ""},
    })


def _founder(company_id: str):
    return read_founder_snapshot({
        "contract_version": FOUNDER_CONTRACT, "snapshot_id": "fs-1",
        "company_id": company_id, "canonical_name": company_id,
        "run_id": "r1", "generated_at": "2026-08-14",
        "known_at": "2026-08-14", "evidence_cutoff": "2026-08-14",
        "availability": "AVAILABLE", "data_population": "REAL_ENTERPRISE",
    })


def test_the_same_company_under_two_legitimate_keys_is_not_quarantined():
    """The live defect."""
    reasons = _quarantine(_market("cloudflare-inc"), _founder("cloudflare"),
                          V.SAME_WINDOW, V.POPULATION_COHERENT_REAL,
                          known_as=("cloudflare", "cloudflare-inc"))
    assert V.WRONG_COMPANY_EVIDENCE not in reasons


def test_a_different_company_is_still_refused_however_it_is_keyed():
    """The negative control. This is the test that must be able to fail.

    A snapshot for a DIFFERENT company, offered to a join whose alias set
    was built by resolving our own company, must still be refused -- the
    alias set can never contain it, because membership is established by
    resolving us and not by comparing us to the snapshot.
    """
    reasons = _quarantine(_market("globex-corporation"), _founder("acme-inc"),
                          V.SAME_WINDOW, V.POPULATION_COHERENT_REAL,
                          known_as=("acme-inc", "acme", "acme-corp"))
    assert V.WRONG_COMPANY_EVIDENCE in reasons


def test_an_empty_alias_set_is_exactly_the_old_strict_rule():
    """Nothing gets looser by default."""
    assert V.WRONG_COMPANY_EVIDENCE in _quarantine(
        _market("cloudflare-inc"), _founder("cloudflare"),
        V.SAME_WINDOW, V.POPULATION_COHERENT_REAL)
    assert V.WRONG_COMPANY_EVIDENCE not in _quarantine(
        _market("cloudflare"), _founder("cloudflare"),
        V.SAME_WINDOW, V.POPULATION_COHERENT_REAL)


def test_an_alias_set_cannot_authorise_a_key_it_does_not_contain():
    """Widening is bounded by the caller's own resolution, not by shape.

    `cloudflare-incorporated` LOOKS like a Cloudflare key and is not one the
    caller resolved. A rule matching on prefix or similarity would accept it;
    membership is exact, so it does not.
    """
    reasons = _quarantine(_market("cloudflare-incorporated"),
                          _founder("cloudflare"), V.SAME_WINDOW,
                          V.POPULATION_COHERENT_REAL,
                          known_as=("cloudflare", "cloudflare-inc"))
    assert V.WRONG_COMPANY_EVIDENCE in reasons


def test_assemble_carries_the_alias_set_through_to_readiness():
    """The parameter has to reach the join, not just exist on the signature.

    A `known_as` accepted by `assemble` and dropped before `_quarantine`
    would leave every live dossier quarantined while every unit test above
    passed -- which is the shape of the defect this whole file is about.
    """
    joined = assemble(_market("cloudflare-inc"), _founder("cloudflare"),
                      now="2026-08-14",
                      known_as=("cloudflare", "cloudflare-inc"))
    assert not joined.quarantined, joined.quarantine_reasons
    assert joined.readiness != "QUARANTINED"

    still_refused = assemble(_market("globex-corporation"),
                             _founder("acme-inc"), now="2026-08-14",
                             known_as=("acme-inc", "acme"))
    assert still_refused.quarantined
    assert V.WRONG_COMPANY_EVIDENCE in still_refused.quarantine_reasons


@pytest.mark.parametrize("stored", ["", None])
def test_a_founder_id_is_always_its_own_identity(stored):
    """Whatever the caller passes, a company is itself."""
    reasons = _quarantine(_market("acme-inc"), _founder("acme-inc"),
                          V.SAME_WINDOW, V.POPULATION_COHERENT_REAL,
                          known_as=(stored,) if stored is not None else ())
    assert V.WRONG_COMPANY_EVIDENCE not in reasons
