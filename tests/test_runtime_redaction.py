"""Security regression: secrets must never reach a persisted error string.

A market-data fetcher passes the API token as a URL query param; a network
exception embeds that URL. Every boundary that persists an error string
(job.failed events, status files, dashboard, per-item error records) must
redact first.
"""
from intent_engine.events import CompanyEventBus
from intent_engine.runtime.jobs import run_job
from intent_engine.runtime.redaction import redact_secrets


def test_known_secret_value_redacted(monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "LIVESECRET_abc123")
    out = redact_secrets("url=...&token=LIVESECRET_abc123")
    assert "LIVESECRET_abc123" not in out
    assert "REDACTED" in out


def test_credential_shaped_param_redacted_even_if_unknown():
    for probe in ("token=SECRET999", "api_key=SECRET999", "apikey=SECRET999",
                  "key=SECRET999", "authorization: Bearer SECRET999",
                  "password=SECRET999"):
        assert "SECRET999" not in redact_secrets("x " + probe + " y")


def test_non_secret_text_is_unchanged():
    msg = "ConnectionError: could not reach api.tiingo.com (timeout)"
    assert redact_secrets(msg) == msg


def test_none_is_safe():
    assert redact_secrets(None) == ""


def test_secret_never_reaches_persisted_event_log(tmp_path, monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "LIVESECRET_abc123XYZ")
    bus = CompanyEventBus(tmp_path / "events")

    def boom():
        raise RuntimeError(
            "request failed: https://api.tiingo.com/x?token=LIVESECRET_abc123XYZ")

    run_job("resolve", boom, root=tmp_path, bus=bus, retries=0)
    persisted = (tmp_path / "events" / "events.jsonl").read_text()
    persisted += (tmp_path / "status" / "jobs.jsonl").read_text()
    persisted += (tmp_path / "status" / "resolve.json").read_text()
    assert "LIVESECRET_abc123XYZ" not in persisted
    failed = [e for e in bus.store.read_all() if e.event_type == "job.failed"]
    assert failed and "***REDACTED***" in failed[0].payload["error"]
