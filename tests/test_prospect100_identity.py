"""The 100-company prospect universe opens on the right company, or says why not.

MEASURED 2026-11-09, before this file, through the same functions the deployed
search box and /analyze call (docs/engineering/prospect100/
baseline_pass0_identity.json):

  - 1 of 100 resolved to an analysable identity (Workday);
  - 85 returned COMPANY_NOT_FOUND;
  - 4 resolved to a DIFFERENT company and opened a run on its SEC filings:
      "World Wide Technology" -> Wolverine World Wide
      "Soda"                  -> Jones Soda Co.
      "Torq"                  -> Torq Resources Inc.
      "Presidio"              -> Presidio Production Co
  - and the suggestion list offered only the wrong company for "Ramp"
    (LiveRamp), "Cube" (CubeSmart), "Tecton" (Tectonic Metals), "Securiti"
    (Securitize), "Plex" (Plexus), "IFS" (Intercorp Financial Services) and
    "WWT" (Watts Water Technologies).

Every expectation below is read from the catalog row that carries the
prospect id, so the test cannot drift from the data it guards -- and the
wrong-company cases are asserted by NAME, so a regression reads as the
failure it is.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from intent_engine.company_ingestion import name_entry as NE
from intent_engine.company_ingestion import suggest as SG
from intent_engine.company_ingestion.catalog_prospects import PROSPECT_CATALOG
from intent_engine.company_ingestion.entities import (AMBIGUOUS, REGISTRY,
                                                      RESOLVED,
                                                      resolve_entity)

ROOT = Path(__file__).resolve().parents[1]
LIST = yaml.safe_load(
    (ROOT / "docs/engineering/prospect100/PROSPECT_LIST.yaml").read_text())
PROSPECTS = {p["prospect_id"]: p for p in LIST["prospects"]}
BY_PID = {row["prospect_id"]: row for row in PROSPECT_CATALOG
          if "prospect_id" in row}

#: Carried by another register and mapped, not duplicated.
EXISTING = {58: "workday"}

#: Listed names that are a sentence rather than a name. The listed form is
#: still asserted NOT to reach the wrong company, below.
TYPED = {82: "eSentire"}

STOPS = {"ACQUIRED_ABSORBED", "CEASED_OPERATING"}


def test_the_universe_is_exactly_one_hundred_and_all_represented():
    assert sorted(PROSPECTS) == list(range(1, 101))
    covered = set(BY_PID) | set(EXISTING)
    assert covered == set(PROSPECTS), sorted(set(PROSPECTS) - covered)
    assert not set(BY_PID) & set(EXISTING), "a prospect is carried twice"


@pytest.mark.parametrize("pid", sorted(BY_PID))
def test_every_prospect_name_resolves_to_its_own_entry(pid):
    row = BY_PID[pid]
    typed = TYPED.get(pid, PROSPECTS[pid]["name_as_listed"])
    entry = NE.resolve(typed)
    status = (row.get("corporate_status") or {}).get("state", "")
    if row.get("disambiguation_group"):
        # A shared name is a CHOICE, and this prospect must be one of them --
        # asked BEFORE any status, because the reader may mean the other one.
        res = resolve_entity(company_name=typed)
        assert res.status == AMBIGUOUS, (typed, res.status)
        assert row["entity_id"] in [c.entity_id for c in res.choices]
        return
    if status in STOPS:
        assert entry.state == NE.NO_LONGER_INDEPENDENT, (typed, entry.state)
        assert entry.company_id == row["entity_id"]
        return
    assert entry.resolved, (typed, entry.state, entry.reason)
    assert entry.website == f"https://{row['primary_domain']}", typed


@pytest.mark.parametrize("pid", sorted(BY_PID))
def test_every_prospect_is_the_first_suggestion_for_its_listed_name(pid):
    row = BY_PID[pid]
    typed = TYPED.get(pid, PROSPECTS[pid]["name_as_listed"])
    rows = SG.suggest(typed, allow_registrant=False)
    assert rows and rows[0].entity_id == row["entity_id"], (
        typed, [r.entity_id for r in rows[:3]])


def test_the_workday_prospect_is_the_manifest_company():
    entry = NE.resolve("Workday")
    assert entry.resolved and entry.company_id == "workday"


def test_the_listed_esentire_sentence_never_reaches_arctic_wolf():
    """#82 is listed as "Arctic Wolf Networks' peer, eSentire". The subject is
    eSentire; Arctic Wolf is a catalog company and must not be what opens."""
    entry = NE.resolve(PROSPECTS[82]["name_as_listed"])
    assert "arctic" not in (entry.website or "").lower()
    assert entry.company_id != "arctic-wolf"
    assert NE.resolve("eSentire").website == "https://esentire.com"


# --- the measured wrong-company cases, with the SEC table switched ON -------

#: A slice of company_tickers.json holding every registrant that collided.
_TICKERS = {
    "0": {"cik_str": 110471, "ticker": "WWW", "title": "WOLVERINE WORLD WIDE INC /DE/"},
    "1": {"cik_str": 1083522, "ticker": "JSDA", "title": "JONES SODA CO."},
    "2": {"cik_str": 1819986, "ticker": "TRBMF", "title": "Torq Resources Inc."},
    "3": {"cik_str": 1937995, "ticker": "PRZ", "title": "PRESIDIO PRODUCTION Co"},
    "4": {"cik_str": 733269, "ticker": "RAMP", "title": "LiveRamp Holdings, Inc."},
    "5": {"cik_str": 1298675, "ticker": "CUBE", "title": "CubeSmart"},
    "6": {"cik_str": 1900000, "ticker": "TECTF", "title": "Tectonic Metals Inc."},
    "7": {"cik_str": 1950000, "ticker": "SCTZ", "title": "Securitize Corp."},
    "8": {"cik_str": 785786, "ticker": "PLXS", "title": "Plexus Corp"},
    "9": {"cik_str": 1615903, "ticker": "IFS", "title": "Intercorp Financial Services Inc."},
    "10": {"cik_str": 795403, "ticker": "WTS", "title": "WATTS WATER TECHNOLOGIES INC"},
    "11": {"cik_str": 1013237, "ticker": "FDS", "title": "FACTSET RESEARCH SYSTEMS INC"},
}


def _sec(url, timeout, max_bytes=None):
    if "company_tickers" in url:
        return (200, {"Content-Type": "application/json"},
                json.dumps(_TICKERS).encode(), False)
    return (404, {}, b"", False)


@pytest.fixture()
def sec_on(monkeypatch):
    monkeypatch.setattr(SG, "_TICKERS", None)
    monkeypatch.setattr(SG, "_PREFIX_INDEX", {})
    monkeypatch.setattr(SG, "_INDEXED_TABLE", [])
    monkeypatch.setattr(NE, "_REGISTRANT_CACHE", {})
    return _sec


@pytest.mark.parametrize("typed,ours,also", [
    ("Soda", "soda-data", "Jones Soda Co."),
    ("Torq", "torq", "Torq Resources Inc."),
    ("Presidio", "presidio", "Presidio Production Co"),
    ("Ramp", "ramp", "LiveRamp Holdings, Inc."),
    ("Securiti", "securiti", "Securitize Corp."),
    ("Plex", "plex-systems", "Plexus Corp"),
    ("IFS", "ifs", "Intercorp Financial Services Inc."),
    ("WWT", "world-wide-technology", "Watts Water Technologies Inc"),
])
def test_a_collision_puts_the_prospect_first_and_still_offers_the_other(
        sec_on, typed, ours, also):
    """The registrant is a real company someone may mean: it stays, second."""
    rows = SG.suggest(typed, allow_registrant=True, transport=sec_on)
    assert rows[0].entity_id == ours, [r.legal_name for r in rows]
    shown = [r.legal_name.lower() for r in rows]
    assert also.lower() in shown, shown


@pytest.mark.parametrize("typed,wrong", [
    ("World Wide Technology", "Wolverine"),
    ("Soda", "Jones Soda"),
    ("Torq", "Torq Resources"),
    ("Presidio", "Presidio Production"),
])
def test_a_prospect_name_never_opens_on_a_registrants_filings(
        sec_on, typed, wrong):
    entry = NE.resolve(typed, allow_registrant=True, transport=sec_on)
    assert entry.state != NE.IDENTIFIED_NO_DOMAIN, (typed, entry.company_name)
    assert wrong.lower() not in entry.company_name.lower()
    assert entry.resolved


# --- the shared rule, independent of the prospect rows ----------------------

@pytest.mark.parametrize("typed", ["World Wide", "Wide"])
def test_a_word_in_the_middle_of_a_filers_name_does_not_identify_it(
        sec_on, typed):
    """In no register, and CONTAINED in "WOLVERINE WORLD WIDE INC" -- the exact
    shape `resolve_cik` accepts. It must not become Wolverine. (A name the
    catalog already carries cannot test this: the registry answers first.)"""
    from intent_engine.company_ingestion.edgar import resolve_cik
    assert resolve_cik(typed, transport=sec_on)["title"].startswith(
        "WOLVERINE"), "fixture no longer exercises the containment match"
    entry = NE.resolve(typed, allow_registrant=True, transport=sec_on)
    assert entry.state == NE.COMPANY_NOT_FOUND, entry.company_name


def test_the_filers_own_name_and_its_leading_words_still_identify_it(sec_on):
    """POSITIVE CONTROL: the guard must not turn real filers into NOT_FOUND."""
    for typed in ("Wolverine World Wide", "Plexus"):
        entry = NE.resolve(typed, allow_registrant=True, transport=sec_on)
        assert entry.state == NE.IDENTIFIED_NO_DOMAIN, (typed, entry.state)


# --- ownership status -------------------------------------------------------

def test_every_ownership_change_carries_an_announcement():
    for row in PROSPECT_CATALOG:
        st = row.get("corporate_status")
        if not st:
            continue
        assert st["summary"].strip(), row["entity_id"]
        assert st["evidence"] and all(
            u.startswith("https://") for u in st["evidence"]), row["entity_id"]
        assert st["effective"][:4].isdigit(), row["entity_id"]


def test_an_absorbed_company_carries_nothing_a_run_would_read():
    for row in PROSPECT_CATALOG:
        st = (row.get("corporate_status") or {}).get("state")
        if st in STOPS:
            assert not row.get("sources"), row["entity_id"]
            assert not row.get("sec_cik"), row["entity_id"]


def test_the_acquirers_domain_does_not_open_the_acquired_company():
    """Red Canary's site redirects to zscaler.com. Zscaler is not Red Canary:
    typing its domain must not resolve to the acquired company."""
    for row in PROSPECT_CATALOG:
        st = row.get("corporate_status") or {}
        dom = st.get("counterparty_domain")
        if not dom:
            continue
        res = resolve_entity(website=f"https://{dom}")
        if res.status == RESOLVED:
            assert res.profile.entity_id != row["entity_id"], (dom, row["entity_id"])


def test_a_suggestion_says_whose_company_it_now_is():
    rows = SG.suggest("Red Canary", allow_registrant=False)
    assert rows[0].entity_id == "red-canary"
    assert "Zscaler" in rows[0].describe()
    rows = SG.suggest("Paycor", allow_registrant=False)
    assert "Paychex" in rows[0].describe()


def test_a_renamed_company_opens_on_its_successor():
    entry = NE.resolve("Converge Technology Solutions")
    assert entry.resolved and entry.website == "https://pellera.com"
    assert "Converge" in (entry.corporate_status or {}).get("summary", "")


def test_a_shared_name_is_a_choice_not_a_pick():
    for typed, ids in (("Observe", {"observe-inc", "observe-ai"}),
                       ("Cube", {"cube-planning", "cube-dev"})):
        res = resolve_entity(company_name=typed)
        assert res.status == AMBIGUOUS, typed
        assert {c.entity_id for c in res.choices} == ids


def test_no_prospect_entry_shares_a_domain_with_an_earlier_registry_entry():
    seen = {}
    for p in REGISTRY:
        host = p.primary_domain.lower().removeprefix("www.")
        assert host not in seen, (p.entity_id, seen.get(host))
        seen[host] = p.entity_id


# --- every route into a run stops at an absorbed company --------------------

from intent_engine.webapp.app import WebApp  # noqa: E402
from intent_engine.webapp.config import AppConfig  # noqa: E402

REMOTE = "198.51.100.9"


def _offline(url, timeout):
    import email as _email
    body = (b"<html><head><title>Offline fixture</title></head><body><p>"
            b"A fixture page so this suite never leaves the machine.</p>"
            b"</body></html>")
    return 200, body, _email.message_from_string("Content-Type: text/html"), url


@pytest.fixture()
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_offline, resolver=False)


def _analyze(app, **form):
    session = {"anonymous": True, "analyses": [], "user_id": "p100",
               "csrf": "c"}
    form.setdefault("consent", "on")
    out = app._analyze(session, form, remote=REMOTE)
    return out, session


def _spent(app):
    return len(app._demo_ip_hits.get(REMOTE, []))


@pytest.mark.parametrize("form", [
    {"company_name": "Red Canary"},                         # typed name
    {"company_name": "Red Canary", "entity_id": "red-canary"},  # picked row
    {"company_name": "", "website": "https://redcanary.com"},  # typed site
])
def test_every_route_to_an_absorbed_company_answers_without_a_run(app, form):
    (status, _h, body), session = _analyze(app, **form)
    assert "now part of Zscaler" in body, body[:400]
    assert "Analyse Zscaler" in body
    assert session["analyses"] == [], "a run was opened"
    assert _spent(app) == 0, "being told a company was acquired cost credit"


def test_a_closed_company_is_answered_without_offering_an_analysis(app):
    (status, _h, body), session = _analyze(app, company_name="Cervest")
    assert "no longer operates" in body
    assert "Analyse " not in body.replace("Analyse company", "")
    assert session["analyses"] == [] and _spent(app) == 0


def test_an_acquired_company_that_still_publishes_opens_a_run(app):
    """POSITIVE CONTROL: Chronosphere is owned by Palo Alto Networks and still
    publishes as itself, so it is analysed like any other company."""
    (status, headers, body), session = _analyze(app, company_name="Chronosphere")
    assert "now part of" not in body
    assert _spent(app) == 1
