"""The deployed transport: what it accepts, and everything it refuses.

The bridge is a file handoff, which is correct on one machine and carries
nothing between two. Measured 2026-08-05: no Render service in this account
has a persistent disk (production included), the market engine does not run
inside the founder service, and the founder branch has no `market` package —
so a locally published dossier could never reach a deployed founder, and every
"live crossing" was a local one.

This moves the artifact and does nothing else. The payload is put through
`strategic_contract.validate`, the same allowlist the local file path uses, so
the deployed route trusts exactly what the file route trusts.

The refusals are the substance of the file. An authenticated write endpoint on
a deployed service earns its place only if it fails closed on absence, on
authorisation, on size, on shape, on schema, on content and on identity.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.external_intel import dossier_ingest as DI
from intent_engine.external_intel import strategic_contract as SC

PRODUCED = pathlib.Path(__file__).parent / "fixtures" / "produced"
TOKEN = "a-preview-token"
HOST = "preview.example"
ENV = {DI.TOKEN_ENV: TOKEN, DI.HOST_ENV: HOST}


def payload(**over):
    p = json.loads((PRODUCED / "caterpillar-inc.json").read_text())
    p.update(over)
    return p


def body(**over) -> bytes:
    return json.dumps(payload(**over)).encode("utf-8")


def ingest(raw=None, *, root, token=TOKEN, host=HOST, env=ENV):
    return DI.ingest(raw if raw is not None else body(), runtime_root=root,
                     provided_token=token, request_host=host, env=env)


# --- it does not exist unless configured ------------------------------------
def test_with_no_token_configured_there_is_no_endpoint(tmp_path):
    """Absence, not a disabled route: production has no variable and so has
    nothing to attack rather than something switched off."""
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(root=tmp_path, env={})
    assert exc.value.status == 404


def test_the_token_does_not_work_on_a_host_it_was_not_issued_for(tmp_path):
    """The second condition, and it exists because of the exact mistake that
    produced it: this preview was created by COPYING another service's env
    vars. A check that a copied variable satisfies is not a second condition.
    """
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(root=tmp_path, host="intent-engine-oatc.onrender.com")
    assert exc.value.status == 404


def test_enabled_only_when_both_conditions_hold():
    assert DI.enabled_for(HOST, ENV)
    assert DI.enabled_for(HOST + ":443", ENV)
    assert not DI.enabled_for("somewhere.else", ENV)
    assert not DI.enabled_for(HOST, {DI.TOKEN_ENV: TOKEN})
    assert not DI.enabled_for(HOST, {DI.HOST_ENV: HOST})


def test_a_hardened_preview_is_not_mistaken_for_production():
    """The bug this replaced: keying on WEBAPP_ENV refused the very service
    it was meant to enable, because a preview should run hardened too."""
    assert DI.enabled_for(HOST, ENV)


# --- authorisation ----------------------------------------------------------
def test_a_wrong_token_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(root=tmp_path, token="not-the-token")
    assert exc.value.status == 401


def test_an_absent_token_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(root=tmp_path, token="")
    assert exc.value.status == 401


def test_nothing_is_written_when_authorisation_fails(tmp_path):
    with pytest.raises(DI.IngestRefused):
        ingest(root=tmp_path, token="wrong")
    assert not DI.strategic_dir(tmp_path).exists()


# --- shape and size ---------------------------------------------------------
def test_an_empty_body_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(b"", root=tmp_path)
    assert exc.value.status == 400


def test_an_oversized_body_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(b"x" * (DI.MAX_BYTES + 1), root=tmp_path)
    assert exc.value.status == 413


def test_unreadable_json_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(b"{not json", root=tmp_path)
    assert exc.value.status == 400


def test_a_json_array_is_not_a_dossier(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(b"[]", root=tmp_path)
    assert exc.value.status == 400


# --- the contract, unchanged ------------------------------------------------
def test_an_unsupported_schema_version_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(body(export_version="strategic_market_intel.v99"),
               root=tmp_path)
    assert exc.value.status == 409


def test_an_unknown_field_is_refused_by_the_same_allowlist(tmp_path):
    raw = json.dumps(dict(payload(), positions_opened=3)).encode()
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(raw, root=tmp_path)
    assert exc.value.status == 422


def test_a_trading_internal_in_prose_is_refused(tmp_path):
    p = payload()
    p["strategic_beliefs"][0]["basis"] = "opened after a sharpe of 1.8"
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(json.dumps(p).encode(), root=tmp_path)
    assert exc.value.status == 422


def test_the_route_cannot_be_a_weaker_way_in(tmp_path):
    """Anything the local file path would refuse, this refuses too."""
    p = payload()
    p["strategic_beliefs"][0]["proposition"] = "the paper book shows a sharpe"
    with pytest.raises(SC.StrategicLeak):
        SC.validate(p)
    with pytest.raises(DI.IngestRefused):
        ingest(json.dumps(p).encode(), root=tmp_path)


# --- identity ---------------------------------------------------------------
def test_a_dossier_with_no_company_id_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(body(company_id=""), root=tmp_path)
    assert exc.value.status == 422


def test_a_non_canonical_company_id_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(body(company_id="Caterpillar Inc."), root=tmp_path)
    assert exc.value.status == 422


@pytest.mark.parametrize("hostile", [
    "../../../etc/passwd", "..", "a/b", "/absolute", "x\x00y"])
def test_a_path_traversal_in_the_company_id_cannot_reach_a_filename(
        tmp_path, hostile):
    """The filename comes from the VALIDATED payload through the resolver's
    own slug function, never from anything a caller chose."""
    with pytest.raises(DI.IngestRefused):
        ingest(body(company_id=hostile), root=tmp_path)
    written = list(tmp_path.rglob("*.json"))
    assert written == []


def test_a_dossier_with_no_as_of_is_refused(tmp_path):
    with pytest.raises(DI.IngestRefused) as exc:
        ingest(body(as_of=""), root=tmp_path)
    assert exc.value.status == 422


# --- what a successful crossing does ----------------------------------------
def test_an_accepted_dossier_lands_where_the_resolver_looks(tmp_path):
    result = ingest(root=tmp_path)
    assert result["status"] == DI.ACCEPTED
    assert (DI.strategic_dir(tmp_path) / "caterpillar-inc.json").exists()


def test_the_resolver_then_finds_it_by_the_name_a_founder_types(tmp_path):
    ingest(root=tmp_path)
    intel = SC.resolve(DI.strategic_dir(tmp_path), names=["Caterpillar"],
                       today="2026-08-05")
    assert intel.available, intel.reason
    assert intel.display_name == "Caterpillar Inc."


def test_republishing_the_same_dossier_is_idempotent(tmp_path):
    """What a transport retry looks like. It must not create a revision."""
    first = ingest(root=tmp_path)
    second = ingest(root=tmp_path)
    assert first["status"] == DI.ACCEPTED
    assert second["status"] == DI.UNCHANGED
    assert second["revision"] == first["revision"]
    assert second["revisions_kept"] == first["revisions_kept"] == 1


def test_a_new_revision_supersedes_without_destroying_the_old_one(tmp_path):
    """Append-only: a later publication changes what is READ, not what
    happened. An earlier founder analysis was shown the earlier dossier."""
    ingest(root=tmp_path)
    second = ingest(body(as_of="2026-08-06",
                         generated_at="2026-08-06T00:00:00+00:00"),
                    root=tmp_path)
    assert second["status"] == DI.SUPERSEDED
    assert second["revisions_kept"] == 2
    current = json.loads(
        (DI.strategic_dir(tmp_path) / "caterpillar-inc.json").read_text())
    assert current["as_of"] == "2026-08-06"


def test_revisions_are_invisible_to_the_resolver_scan(tmp_path):
    """`resolve` globs `*.json` non-recursively. If revisions were siblings,
    two dossiers would claim one company and BOTH would be refused."""
    ingest(root=tmp_path)
    ingest(body(as_of="2026-08-06"), root=tmp_path)
    siblings = sorted(p.name for p in DI.strategic_dir(tmp_path).glob("*.json"))
    assert siblings == ["caterpillar-inc.json"]
    assert SC.resolve(DI.strategic_dir(tmp_path), names=["Caterpillar"],
                      today="2026-08-06").available


def test_a_refused_dossier_never_replaces_a_good_one(tmp_path):
    """Fail closed: a bad publication must not leave the consumer worse off
    than before it arrived."""
    ingest(root=tmp_path)
    good = (DI.strategic_dir(tmp_path) / "caterpillar-inc.json").read_bytes()
    with pytest.raises(DI.IngestRefused):
        ingest(json.dumps(dict(payload(), win_rate=0.62)).encode(),
               root=tmp_path)
    assert (DI.strategic_dir(tmp_path)
            / "caterpillar-inc.json").read_bytes() == good


def test_the_stored_bytes_are_the_bytes_the_resolver_validates(tmp_path):
    ingest(root=tmp_path)
    stored = json.loads(
        (DI.strategic_dir(tmp_path) / "caterpillar-inc.json").read_text())
    SC.validate(stored)
