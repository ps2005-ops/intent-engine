"""The limited page names a company the way every other surface does."""
from __future__ import annotations

import email
import re
import urllib.error

from tests.test_insufficient_evidence_page import Client
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


def _refuse(url, timeout):
    """Only one thin page answers -- the live bounded condition."""
    if url.rstrip("/").endswith("/about"):
        body = (b"<html><head><title>Form 6-K (2026-05-14)</title></head>"
                b"<body><p>Report furnished pursuant to the rules of the "
                b"Exchange Act. This report is incorporated by reference "
                b"into the registration statements of the registrant.</p>"
                b"</body></html>")
        return (200, {"content-type": "text/html"}, body, False)
    raise urllib.error.HTTPError(url, 403, "forbidden",
                                 email.message_from_string(""), None)


def _limited(tmp_path, typed, website):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_refuse, resolver=False)
    client = Client(app)
    client.request("POST", "/demo")
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={typed}"
        f"&website={website}")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app._results[run_id]["strategic_report"] is None
    _, _, html = client.request("GET", f"/runs/{run_id}")
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def test_a_legal_name_carries_the_name_a_reader_knows(tmp_path):
    text = _limited(tmp_path, "Themis Solutions Inc.", "https://clio.com")
    assert "Limited analysis of Themis Solutions Inc. (Clio)" in text


def test_a_name_with_no_registry_entry_is_unchanged(tmp_path):
    """CONTROL: nothing is appended to a company the registry does not know."""
    text = _limited(tmp_path, "Brimsdale", "https://brimsdale.example")
    assert "Limited analysis of Brimsdale" in text
    assert "Brimsdale (" not in text
