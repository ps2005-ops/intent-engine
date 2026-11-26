"""Round 9: past stops placed by statistics as released then; BLS reliability."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from intent_engine.econ import store as EST
from intent_engine.executive import history_rewind as HR
from intent_engine.external_intel import econ_history as EH
from intent_engine.external_intel import macro_provider as MP


def _node(tmp, kind, occurred, available, value):
    EST.append(tmp, "node", {"kind": kind, "occurred_at": occurred,
                             "available_at": available, "value": value,
                             "unit": "%"}, written_at=available)


def _store(tmp):
    _node(tmp, "labour", "2025-05-01", "2025-06-06", 4.2)
    _node(tmp, "labour", "2025-06-01", "2025-07-03", 4.1)
    _node(tmp, "labour", "2025-07-01", "2025-08-01", 4.3)   # after the stop
    return tmp


def test_only_what_was_released_by_the_stop_is_used(tmp_path):
    c = EH.reconstruct_at(_store(tmp_path), "2025-07-28")
    reading = c.conditions["labour"]
    assert reading["value"] == 4.1 and reading["direction"] == "DOWN"
    assert c.as_of == "2025-07-03" and c.reconstructed


def test_the_day_before_a_release_does_not_see_it(tmp_path):
    """THE WALL, one day either side of a release."""
    root = _store(tmp_path)
    assert EH.reconstruct_at(root, "2025-07-02").conditions["labour"]["value"] == 4.2
    assert EH.reconstruct_at(root, "2025-07-03").conditions["labour"]["value"] == 4.1


def test_before_any_release_there_is_no_reading(tmp_path):
    assert EH.reconstruct_at(_store(tmp_path), "2024-01-01") is None


def test_a_reconstructed_stop_is_never_called_a_published_state(tmp_path):
    root = _store(tmp_path)
    text, state = HR._economic_then(lambda iso: EH.reconstruct_at(root, iso),
                                    datetime.date(2025, 7, 28), "Acme")
    assert state == HR.ECON_RECONSTRUCTED != HR.ECON_LINKED
    assert "reconstructed today" in text and "revisions" in text
    assert "the unemployment rate" in text
    assert "2025-08-01" not in text                       # nothing after


# The app's reader (published state first, reconstruction only where none
# exists) is verified on the real pages of the round that runs it: every
# reconstructed stop carries data-econ-state="ECONOMIC_CONTEXT_RECONSTRUCTED"
# and the round's history_expanded report counts them separately. A unit
# test that re-implements the closure could not fail, so there is none.


# --- BLS --------------------------------------------------------------------
def test_the_registration_key_rides_only_on_the_request(monkeypatch):
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    assert MP._bls_key() == ""
    monkeypatch.setenv("BLS_API_KEY", "k123")
    assert MP._bls_key() == "&registrationkey=k123"


def test_a_bls_success_without_data_is_not_data(tmp_path):
    empty = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": []}]}}
    assert MP._cached_get(tmp_path, "b", "u", now=1.0,
                          fetcher=lambda u: empty) is None


def test_a_non_json_body_is_not_data(tmp_path):
    assert MP._cached_get(tmp_path, "h", "u", now=1.0,
                          fetcher=lambda u: "<html>error</html>") is None


def test_real_series_data_is_kept(tmp_path):
    """POSITIVE CONTROL."""
    good = {"status": "REQUEST_SUCCEEDED",
            "Results": {"series": [{"data": [{"value": "4.1"}]}]}}
    assert MP._cached_get(tmp_path, "g", "u", now=1.0,
                          fetcher=lambda u: good) == good
    treasury = {"data": [{"record_date": "2026-10-31"}]}
    assert MP._cached_get(tmp_path, "t", "u", now=1.0,
                          fetcher=lambda u: treasury) == treasury
