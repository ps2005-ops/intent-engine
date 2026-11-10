"""Shipping published dossiers to a deployed founder service.

The bridge is a file handoff, correct on one machine and carrying nothing
between two. This sends the artifact `strategic_publish` already wrote, byte
for byte, and nothing else — canonical learning truth stays in the ledger.

What is asserted here is mostly restraint: it is silent unless configured, it
never raises into the cycle, it does not retry a refusal, and it cannot invent
or alter a dossier.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from intent_engine.market import dossier_transport as DT

ENV = {DT.URL_ENV: "https://preview.example/internal/strategic-dossier",
       DT.TOKEN_ENV: "a-token"}


def published(root, company_id="caterpillar-inc", as_of="2026-08-05"):
    directory = root / "reports" / "market" / "strategic"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{company_id}.json").write_text(json.dumps(
        {"export_version": "strategic_market_intel.v1",
         "company_id": company_id, "as_of": as_of}))
    return directory


class Recorder:
    """A stand-in for `urlopen` that records what was actually sent."""

    def __init__(self, status="accepted", fail_times=0, http_error=None):
        self.requests = []
        self.status = status
        self.fail_times = fail_times
        self.http_error = http_error

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.http_error is not None:
            raise urllib.error.HTTPError(
                request.full_url, self.http_error, "refused", {},
                io.BytesIO(b'{"error": "refused by the contract"}'))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise urllib.error.URLError("connection refused")
        return _Response(json.dumps(
            {"status": self.status, "revision": "abc123", "as_of": "2026-08-05"}))


class _Response:
    def __init__(self, text):
        self._text = text.encode()

    def read(self):
        return self._text

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- silent unless asked ----------------------------------------------------
def test_it_does_nothing_when_nothing_is_configured(tmp_path):
    published(tmp_path)
    result = DT.ship(root=tmp_path, env={})
    assert result["configured"] is False
    assert result["attempted"] == 0
    assert DT.URL_ENV in result["note"]


@pytest.mark.parametrize("env", [
    {DT.URL_ENV: "https://x/y"}, {DT.TOKEN_ENV: "t"}, {}])
def test_half_a_configuration_is_no_configuration(env):
    assert not DT.configured(env)


def test_a_missing_dossier_directory_is_not_an_error(tmp_path):
    result = DT.ship(root=tmp_path, env=ENV)
    assert result["attempted"] == 0
    assert result["failed"] == []


# --- what it sends ----------------------------------------------------------
def test_it_sends_the_published_bytes_unaltered(tmp_path):
    directory = published(tmp_path)
    original = (directory / "caterpillar-inc.json").read_bytes()
    recorder = Recorder()
    DT.ship(root=tmp_path, env=ENV, opener=recorder)
    assert len(recorder.requests) == 1
    assert recorder.requests[0].data == original


def test_it_carries_the_token_in_a_header_never_in_the_url(tmp_path):
    published(tmp_path)
    recorder = Recorder()
    DT.ship(root=tmp_path, env=ENV, opener=recorder)
    request = recorder.requests[0]
    assert request.get_header("X-dossier-token") == "a-token"
    assert "a-token" not in request.full_url


def test_the_token_does_not_appear_in_the_report(tmp_path):
    published(tmp_path)
    result = DT.ship(root=tmp_path, env=ENV, opener=Recorder())
    assert "a-token" not in json.dumps(result)


def test_every_published_dossier_is_shipped(tmp_path):
    published(tmp_path, "caterpillar-inc")
    published(tmp_path, "linde-plc")
    recorder = Recorder()
    result = DT.ship(root=tmp_path, env=ENV, opener=recorder)
    assert result["attempted"] == 2
    assert len(result["sent"]) == 2


def test_a_company_filter_ships_only_that_company(tmp_path):
    published(tmp_path, "caterpillar-inc")
    published(tmp_path, "linde-plc")
    result = DT.ship(root=tmp_path, env=ENV, opener=Recorder(),
                     companies=["linde-plc"])
    assert [s["company_id"] for s in result["sent"]] == ["linde-plc"]


def test_revisions_are_not_shipped_as_if_they_were_current(tmp_path):
    """The receiver keeps revisions in a subdirectory; the sender must not
    walk into it and republish history as the present."""
    directory = published(tmp_path)
    nested = directory / "revisions" / "caterpillar-inc"
    nested.mkdir(parents=True)
    (nested / "2026-08-01-old.json").write_text("{}")
    result = DT.ship(root=tmp_path, env=ENV, opener=Recorder())
    assert result["attempted"] == 1


# --- outcomes ---------------------------------------------------------------
def test_an_unchanged_reply_is_reported_apart_from_a_send(tmp_path):
    """A retry that changed nothing is not a publication."""
    published(tmp_path)
    result = DT.ship(root=tmp_path, env=ENV,
                     opener=Recorder(status="unchanged"))
    assert result["unchanged"] and not result["sent"]


def test_a_transport_failure_is_retried(tmp_path):
    published(tmp_path)
    recorder = Recorder(fail_times=2)
    result = DT.ship(root=tmp_path, env=ENV, opener=recorder)
    assert len(recorder.requests) == 3
    assert result["sent"] and not result["failed"]


def test_a_refusal_is_not_retried(tmp_path):
    """A 4xx means the contract said no. Retrying cannot change its mind and
    would turn one refusal into three."""
    published(tmp_path)
    recorder = Recorder(http_error=422)
    result = DT.ship(root=tmp_path, env=ENV, opener=recorder)
    assert len(recorder.requests) == 1
    assert result["failed"] and not result["sent"]
    assert "422" in result["failed"][0]["error"]


def test_a_server_error_is_retried_and_then_reported(tmp_path):
    published(tmp_path)
    recorder = Recorder(http_error=503)
    result = DT.ship(root=tmp_path, env=ENV, opener=recorder)
    assert len(recorder.requests) == DT.ATTEMPTS
    assert result["failed"]


def test_a_failure_never_raises_into_the_cycle(tmp_path):
    """Learning already happened by the time a dossier exists. A transport
    that took the cycle down would lose it."""
    published(tmp_path)
    result = DT.ship(root=tmp_path, env=ENV, opener=Recorder(fail_times=99))
    assert result["failed"]
    assert result["sent"] == []


def test_one_failure_does_not_stop_the_others(tmp_path):
    published(tmp_path, "caterpillar-inc")
    published(tmp_path, "linde-plc")

    class Selective(Recorder):
        def __call__(self, request, timeout=None):
            if b"linde" in request.data:
                raise urllib.error.URLError("down")
            return super().__call__(request, timeout)

    result = DT.ship(root=tmp_path, env=ENV, opener=Selective())
    assert [s["company_id"] for s in result["sent"]] == ["caterpillar-inc"]
    assert [f["company_id"] for f in result["failed"]] == ["linde-plc"]


def test_the_cycle_step_reports_transport_without_being_configured(tmp_path):
    """The step must run the transport and record its silence, so an operator
    can tell 'not configured' from 'never attempted'."""
    from intent_engine.market import steps
    import inspect
    source = inspect.getsource(steps.learning_step)
    assert "dossier_transport" in source
    assert "payload[\"dossier_transport\"]" in source
