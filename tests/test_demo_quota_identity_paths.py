"""A question is not an analysis, and rejoining your own run is not a new one.

MEASURED LIVE 2026-09-11 on b88df2bb, then reproduced offline. Typing
"Highspot" -- a real company the register did not carry -- returned the
"We could not identify" page in under a second AND consumed one of the
visitor's ten analyses for the hour. No run was opened, nothing was fetched,
nothing was shown. Ten attempts at companies we could not name and the demo
was closed to that visitor for an hour, having produced nothing at all.

That is how the reported "Too many analyses for now" was reached without a
single analysis having run.

`_analyze` reserves quota at the top and refunds it on the paths that fail to
open a run. Three paths that return a QUESTION rather than a result were
missing from that list:

    AMBIGUOUS_COMPANY  -> `_name_choice_page`      ("which of these?")
    COMPANY_NOT_FOUND  -> `_company_not_found_page` (the Highspot case)
    AMBIGUOUS entity   -> `_disambiguation_page`    (the Sony case)

and a fourth path charged for work that did not happen: re-requesting a
company the visitor is ALREADY analysing returns the same run id, because
`create_run` keys a run on (subject, user, as_of) -- so the second request
queued nothing and billed for it anyway.

WHY THESE ARE BEHAVIOURAL TESTS. The file that shipped before this one
guarded the same property structurally, by counting `_release_demo_quota`
occurrences in the source and requiring three or more. Three were present
throughout, so the count was satisfied while the three paths above leaked.
A guard that cannot fail is not a guard; each path is driven here instead.
"""
import urllib.error

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

REMOTE = "198.51.100.4"


def _offline_transport(url, timeout):
    """Every fetch answered from memory. A TEST MUST NOT REACH THE NETWORK.

    Written after the first version of this file was handed `transport=None`,
    which is the PRODUCTION transport: the analyses these tests start went
    out to highspot.com and bigid.com for real, from inside the suite. It
    passed, and it made the guard slower and dependent on two companies'
    websites being up.
    """
    import email as _email
    body = ("<html><head><title>Offline fixture</title></head><body>"
            "<p>A fixture page. It exists so this suite never leaves the "
            "machine it runs on.</p></body></html>")
    headers = _email.message_from_string("Content-Type: text/html")
    return 200, body.encode(), headers, url


@pytest.fixture()
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_offline_transport, resolver=False)


def _session(name="anon-q1"):
    return {"anonymous": True, "analyses": [], "user_id": name, "csrf": "c"}


def _spent(app, remote=REMOTE):
    return len(app._demo_ip_hits.get(remote, []))


def _analyze(app, session, **form):
    form.setdefault("consent", "on")
    return app._analyze(session, form, remote=REMOTE)


# --- the three questions ----------------------------------------------------

def test_a_company_we_cannot_name_is_free(app):
    """The Highspot case, as the visitor met it."""
    s = _session()
    status, _h, body = _analyze(app, s, company_name="Zzzqqxnotacompany")
    assert "could not identify" in body.lower()
    assert _spent(app) == 0, "being told we cannot name a company cost an analysis"
    assert s["analyses"] == []


def test_being_asked_which_company_is_free(app):
    """AMBIGUOUS_COMPANY: two real companies share the typed name."""
    s = _session()
    _analyze(app, s, company_name="Sony")
    assert _spent(app) == 0, "being asked which company cost an analysis"


def test_being_asked_which_entity_is_free(app):
    """AMBIGUOUS: the name plus a website still denote more than one entity."""
    s = _session()
    _analyze(app, s, company_name="Sony", website="https://sony.net")
    assert _spent(app) == 0, "the disambiguation question cost an analysis"


def test_answering_the_question_costs_exactly_one(app):
    """The refunds must not make analysis free -- only the QUESTION is."""
    s = _session()
    _analyze(app, s, company_name="Sony")
    assert _spent(app) == 0
    _analyze(app, s, company_name="Sony", website="https://sony.com")
    assert _spent(app) == 1, "answering the question did not consume a slot"


# --- rejoining your own run -------------------------------------------------

def test_re_requesting_a_running_company_is_free(app):
    """A reload, a second tab, an impatient re-submit. Same run, no charge."""
    s = _session()
    first = _analyze(app, s, company_name="Highspot")
    assert _spent(app) == 1, "the first analysis should cost one"
    second = _analyze(app, s, company_name="Highspot")
    assert _spent(app) == 1, (
        "re-requesting a run the visitor already owns charged them again")
    # and it is the SAME run, not a second one queued behind the first
    assert dict(first[1]).get("Location") == dict(second[1]).get("Location")


# --- the boundary the refunds must not cross --------------------------------

def test_a_different_company_still_costs(app):
    s = _session()
    _analyze(app, s, company_name="Highspot")
    _analyze(app, s, company_name="BigID")
    assert _spent(app) == 2, "two different companies must cost two analyses"
