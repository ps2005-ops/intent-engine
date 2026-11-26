"""An app given a transport reaches the world through it and nothing else.

MEASURED 2026-11-26: test_async_analysis::test_work_beyond_capacity_is_
refused_not_silently_dropped held open sockets to the Treasury's CDN and a
publisher host, and the full guarded suite stalled for minutes at ~8%. The
analysis worker's external-context step called `macro_provider.build_factors`
with no fetcher, so it dialled BLS and the Treasury live even though the app
was built with an injected transport (a test or a replay) -- and even on a
page render, which `_external_context` promises never fetches.

The property is asserted on the WHOLE analysis path, by recording every
outbound connection the process attempts, not by mocking the one call that
happened to leak.
"""
from __future__ import annotations

import socket

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


def _offline(url, timeout):
    body = (b"<html><head><title>Acme</title></head><body><p>Acme sells "
            b"planning software to finance teams, priced per seat, and its "
            b"customers' borrowing costs and interest rates shape their "
            b"budgets for new software.</p></body></html>")
    return 200, {"content-type": "text/html"}, body, False


def _outbound(monkeypatch):
    attempts = []
    real = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            attempts.append(address)
            raise OSError("outbound connection refused by the test")
        return real(self, address)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection",
                        lambda addr, *a, **k: (_ for _ in ()).throw(
                            attempts.append(addr) or OSError("refused")))
    return attempts


def _app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_offline, resolver=False)
    app._analysis_async = True
    return app


def test_a_full_analysis_with_an_injected_transport_dials_nothing(
        tmp_path, monkeypatch):
    attempts = _outbound(monkeypatch)
    app = _app(tmp_path)
    run = app.ci.create_run(company_name="Acme", website="https://acme.example",
                            user_id="u", as_of="2026-11-26T00:00:00+00:00")
    assert app._schedule_analysis("u", run["run_id"])
    assert app.wait_for_analysis(run["run_id"], timeout=60)
    assert attempts == [], f"dialled the live network: {attempts[:3]}"


def test_the_external_context_never_fetches_macro_with_a_transport(
        tmp_path, monkeypatch):
    """THE CALLER, directly: even allow_fetch=True (the analysis path) may not
    hand the macro provider a live fetcher when a transport was injected."""
    from intent_engine.external_intel import macro_provider as mp
    seen = []
    real = mp.build_factors

    def spy(*a, **k):
        seen.append(k.get("fetcher"))
        return real(*a, **k)
    monkeypatch.setattr(mp, "build_factors", spy)
    app = _app(tmp_path)
    run = app.ci.create_run(company_name="Acme", website="https://acme.example",
                            user_id="u", as_of="2026-11-26T00:00:00+00:00")
    app._external_context(run["run_id"], allow_fetch=True)
    assert seen and seen[-1] is not None
    assert seen[-1]("https://api.bls.gov/x") is None
