"""A company the market engine does not follow still receives its economics.

Measured on prospect-100 round 7 (2026-11-26): the published economic state
was readable (US, 5 measured conditions, 67 beliefs) and none of it reached
any of the 95 private or unlisted companies -- every X-Ray said "the economic
layer did not run" -- because company-level economics arrived ONLY through a
market-engine snapshot, published for its own 28 subjects.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intent_engine.executive import decision_synthesis as DS
from intent_engine.executive.analysis_selection import RecordFacts, select
from intent_engine.external_intel import founder_economy as FE


def _economy(**known):
    """A published state. `known` maps condition kind -> direction."""
    return SimpleNamespace(
        available=True, area="US", as_of="2026-11-25",
        conditions={k: {"known": True, "direction": d}
                    for k, d in known.items()} | {
            "commodity_oil": {"known": False}})


STATE = _economy(inflation="UP", wages="UP", labour="DOWN",
                 treasury_10y="UP", fiscal="DOWN")


# --- the block --------------------------------------------------------------
def test_an_evidenced_exposure_met_by_a_measured_condition_is_a_channel():
    b = FE.block(STATE, ("wages",))
    assert b["state"] == "AVAILABLE" and b["ids"] == ["US:LABOR"]
    assert b["source"] == FE.SOURCE          # provenance travels with it


def test_an_interest_rate_exposure_is_met_by_whichever_rate_is_measured():
    """The company says "interest rates"; the state measures the 10-year."""
    assert FE.block(STATE, ("policy_rate",))["ids"] == ["US:MARKET_RATE"]


def test_an_exposure_the_state_does_not_measure_is_not_a_channel():
    """POSITIVE CONTROL: oil is unmeasured here, so nothing is claimed."""
    b = FE.block(STATE, ("commodity_oil",))
    assert b["state"] == "AVAILABLE" and b["ids"] == []


def test_no_evidenced_exposure_is_a_finding_not_did_not_run():
    """A sector never supplies an exposure: none established means none."""
    b = FE.block(STATE, ())
    assert b["state"] == "AVAILABLE" and b["ids"] == []


def test_no_readable_state_is_no_block():
    assert FE.block(None, ("wages",)) == {}
    assert FE.block(SimpleNamespace(available=False), ("wages",)) == {}


# --- the dossier seam -------------------------------------------------------
class _Dossier:
    def __init__(self, econ=None):
        blocks = {"evidence": {"state": "AVAILABLE", "count": 3}}
        if econ is not None:
            blocks["economic_state"] = econ
        self.market_block = {"availability": "UNAVAILABLE", "blocks": blocks}
        self.founder_block = {"blocks": {}}
        self.canonical_name = self.company_id = "acme"


def test_a_dossier_without_economics_takes_the_founder_block():
    d = DS._with_founder_economy(_Dossier(), FE.block(STATE, ("wages",)))
    state, ids = DS._economic(d)
    assert state == DS.ECONOMIC_AVAILABLE and ids == ("US:LABOR",)
    assert DS._facts(d, "").economic_ids == ("US:LABOR",)
    # the dossier's own availability is NOT rewritten by the fallback
    assert d.market_block["availability"] == "UNAVAILABLE"


def test_a_dossier_with_its_own_economics_keeps_them():
    """POSITIVE CONTROL: the market engine's block wins where it ran."""
    own = {"state": "AVAILABLE", "ids": ["US:COMMODITY"]}
    d = DS._with_founder_economy(_Dossier(own), FE.block(STATE, ("wages",)))
    assert DS._economic(d)[1] == ("US:COMMODITY",)


def test_without_a_founder_block_the_old_answer_stands():
    d = DS._with_founder_economy(_Dossier(), {})
    assert DS._economic(d)[0] == DS.ECONOMIC_NOT_RUN


# --- one economy, different companies, different consequences ---------------
SOFTWARE = ("Acme sells subscription software to finance teams, priced per "
            "user per month on annual contracts, delivered as a cloud "
            "service. Customers renew each year and expand seats. ") * 4


def _econ_weight(ids):
    s = select("acme", name="Acme", published_text=SOFTWARE, evidence_text="",
               facts=RecordFacts(economic_ids=ids))
    assert s.considered, "the selector considered nothing; proves nothing"
    return {r["archetype"]: r["contributions"]["econ"]
            for r in s.considered if r["contributions"]["econ"]}


def test_a_rate_channel_weighs_on_a_software_company_s_pricing():
    ids = tuple(FE.block(STATE, ("policy_rate",))["ids"])
    assert _econ_weight(()) == {}
    assert _econ_weight(ids) == {"PRICING": 4}


def test_a_channel_with_no_decision_on_this_menu_moves_nothing():
    """POSITIVE CONTROL against generic economics: labour cost bears on cost
    structure and capacity, and a subscription-software menu has neither,
    so the SAME measured economy leaves this company's decision alone."""
    ids = tuple(FE.block(STATE, ("wages",))["ids"])
    assert ids == ("US:LABOR",)
    assert _econ_weight(ids) == {}


# --- the callers ------------------------------------------------------------
def _app(tmp_path):
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=lambda u, t: (404, {}, b"", False), resolver=False)


def test_the_app_builds_the_block_from_the_runs_own_context(tmp_path):
    app = _app(tmp_path)
    app._external_cache["r1"] = SimpleNamespace(
        economy=STATE, economy_exposures=("wages", "inflation"))
    b = app._founder_economy("r1")
    assert b["ids"] == ["US:LABOR", "US:INFLATION"]


def test_the_xray_composer_is_handed_the_block(tmp_path, monkeypatch):
    """THE CALLER: `_executive_read` passes what `own` carries to compose."""
    app = _app(tmp_path)
    seen = {}

    def spy(dossier, **kw):
        seen.update(kw)
        raise RuntimeError("stop here")
    monkeypatch.setattr(DS, "compose", spy)
    monkeypatch.setattr(app, "_demo_dossier_store",
                        lambda: SimpleNamespace(previous=lambda *a, **k: None))
    monkeypatch.setattr(app, "_registrant", lambda d: None)
    block = FE.block(STATE, ("wages",))
    app._executive_read(SimpleNamespace(company_id="acme", dossier_version=1),
                        own={"founder_economy": block})
    assert seen.get("founder_economy") == block


def test_the_intro_s_canonical_selection_reads_the_same_channels(
        tmp_path, monkeypatch):
    """ONE RUN, ONE ANSWER: the selection behind /intro and /brief is handed
    the same founder channels the X-Ray composer is, not empty facts."""
    from intent_engine.executive import analysis_selection as AS
    app = _app(tmp_path)
    run = app.ci.create_run(company_name="Acme", website="https://acme.example",
                            user_id="u", as_of="2026-11-26T00:00:00+00:00")
    block = FE.block(STATE, ("policy_rate",))
    monkeypatch.setattr(app, "_founder_economy", lambda run_id: block)
    seen = {}
    real = AS.select

    def spy(*a, **k):
        seen["facts"] = k.get("facts")
        return real(*a, **k)
    monkeypatch.setattr(AS, "select", spy)
    app._canonical_selection(run["run_id"], "Acme", "acme.example")
    assert seen["facts"] is not None
    assert seen["facts"].economic_ids == ("US:MARKET_RATE",)
