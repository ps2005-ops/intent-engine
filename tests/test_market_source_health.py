"""A dead source is not a quiet economy, and the tests say which is which.

The central test here is `test_a_dark_source_never_weakens_the_claim`. Every
other test in this file protects a detail; that one protects the reason the
module exists. A belief fed by a source that went dark stops receiving
confirming evidence, and the tempting inference — fewer confirmations, so
believe it less — converts "we stopped looking" into "we were wrong".
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import source_health as SH

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")


# --- classification ---------------------------------------------------------

def test_the_live_bls_failure_is_classified():
    """The exact string production has produced on every recorded cycle."""
    assert SH.classify("HTTPError: HTTP Error 503: Service Unavailable") == \
        SH.UNAVAILABLE


@pytest.mark.parametrize("message,expected", [
    ("HTTP Error 429: Too Many Requests", SH.RATE_LIMITED),
    ("HTTP Error 401: Unauthorized", SH.AUTH_EXPIRED),
    ("HTTP Error 403: Forbidden", SH.AUTH_EXPIRED),
    ("invalid api key supplied", SH.AUTH_EXPIRED),
    ("HTTP Error 502: Bad Gateway", SH.UNAVAILABLE),
    ("socket timed out", SH.UNAVAILABLE),
    ("KeyError: 'value'", SH.SCHEMA_CHANGED),
    ("json.decoder.JSONDecodeError: Expecting value", SH.PARSER_BROKEN),
])
def test_known_signatures_are_recognised(message, expected):
    assert SH.classify(message) == expected


def test_an_unrecognised_failure_is_never_guessed():
    """An unrecognised error message is the only information there is.

    Mapping it onto the nearest known state would destroy the one signal the
    outage produced, and a 503 and a schema change need opposite responses.
    """
    state = SH.classify("the feed returned a teapot")
    assert state == SH.UNCLASSIFIED
    assert state not in (SH.UNAVAILABLE, SH.SCHEMA_CHANGED)


def test_no_failure_is_healthy():
    assert SH.classify("") == SH.HEALTHY
    assert SH.classify("   ") == SH.HEALTHY


# --- state and streaks ------------------------------------------------------

def test_one_outage_is_degraded_and_three_is_unavailable():
    """One 503 is a bad minute; three in a row is an outage."""
    health = None
    states = []
    for _ in range(SH.OUTAGE_STREAK):
        health = SH.assess(source_family="bls", as_of="2026-08-09",
                           failure="HTTP Error 503: Service Unavailable",
                           prior=health)
        states.append(health.state)
    assert states[0] == SH.DEGRADED
    assert states[-1] == SH.UNAVAILABLE
    assert health.failure_streak == SH.OUTAGE_STREAK


def test_a_success_resets_the_streak_and_dates_it():
    prior = SH.assess(source_family="bls", as_of="2026-08-08",
                      failure="HTTP Error 503: Service Unavailable")
    ok = SH.assess(source_family="bls", as_of="2026-08-09", prior=prior)
    assert ok.state == SH.HEALTHY
    assert ok.failure_streak == 0
    assert ok.last_success == "2026-08-09"


def test_last_success_survives_a_failure():
    """The question a streak cannot answer: when did this last work."""
    ok = SH.assess(source_family="bls", as_of="2026-08-01")
    bad = SH.assess(source_family="bls", as_of="2026-08-09",
                    failure="HTTP Error 503: Service Unavailable", prior=ok)
    assert bad.last_success == "2026-08-01"


def test_an_impaired_state_must_carry_its_evidence():
    """A state with no evidence cannot be disputed and cannot be resolved."""
    with pytest.raises(ValueError, match="failure that"):
        SH.SourceHealth(source_family="bls", state=SH.UNAVAILABLE)


def test_an_unknown_state_is_refused():
    with pytest.raises(ValueError, match="unknown source state"):
        SH.SourceHealth(source_family="bls", state="BROKEN_ISH",
                        failure="x")


# --- the rule this module exists for ----------------------------------------

def test_a_dark_source_never_weakens_the_claim():
    """Uncertainty rises; standing and confidence come back untouched."""
    healths = [SH.assess(source_family="bls", as_of="2026-08-09",
                         failure="HTTP Error 503: Service Unavailable"),
               SH.assess(source_family="fred", as_of="2026-08-09")]
    got = SH.apply_to_claim(standing="OBSERVED", confidence=0.8,
                            healths=healths, sources_used=["bls", "fred"])
    assert got["standing"] == "OBSERVED"
    assert got["confidence"] == 0.8
    assert got["uncertainty"] == "RAISED"
    assert got["observability_reduced"] is True
    assert got["impaired_sources"] == ["bls"]
    assert "not evidence against it" in got["reason"]


def test_a_healthy_source_raises_nothing():
    healths = [SH.assess(source_family="fred", as_of="2026-08-09")]
    got = SH.apply_to_claim(standing="INFERRED", confidence=0.4,
                            healths=healths, sources_used=["fred"])
    assert got["uncertainty"] == "UNCHANGED"
    assert got["observability_reduced"] is False


def test_observability_falls_while_the_claim_stands():
    """The two numbers that must move independently."""
    before = [SH.assess(source_family=f, as_of="2026-08-08")
              for f in ("bls", "fred", "ecb")]
    after = [SH.assess(source_family="bls", as_of="2026-08-09",
                       failure="HTTP Error 503: Service Unavailable"),
             SH.assess(source_family="fred", as_of="2026-08-09"),
             SH.assess(source_family="ecb", as_of="2026-08-09")]
    assert SH.observability(before)["observability"] == 1.0
    assert SH.observability(after)["observability"] < 1.0
    claim = SH.apply_to_claim(standing="OBSERVED", confidence=0.9,
                              healths=after, sources_used=["bls"])
    assert claim["confidence"] == 0.9


def test_no_source_attempted_is_unmeasured_not_complete():
    got = SH.observability([])
    assert got["observability"] is None
    assert "unmeasured rather than complete" in got["reason"]


# --- fallback routing -------------------------------------------------------

def test_a_substitution_is_recorded_as_a_substitution():
    healths = [SH.assess(source_family="bls", as_of="2026-08-09",
                         failure="HTTP Error 503: Service Unavailable"),
               SH.assess(source_family="fred", as_of="2026-08-09")]
    got = SH.route(healths, question="us_inflation", preferred="bls",
                   alternatives=["fred"])
    assert got is not None
    assert got.substitute_family == "fred"
    assert got.unavailable_family == "bls"
    assert "DEGRADED" in got.reason or "UNAVAILABLE" in got.reason


def test_a_healthy_preferred_source_produces_no_fallback_record():
    """A fallback record for a substitution that did not happen is a lie."""
    healths = [SH.assess(source_family="bls", as_of="2026-08-09")]
    assert SH.route(healths, question="us_inflation", preferred="bls",
                    alternatives=["fred"]) is None


def test_no_healthy_alternative_yields_no_silent_substitution():
    healths = [SH.assess(source_family="bls", as_of="2026-08-09",
                         failure="503 Service Unavailable"),
               SH.assess(source_family="fred", as_of="2026-08-09",
                         failure="429 Too Many Requests")]
    assert SH.route(healths, question="us_inflation", preferred="bls",
                    alternatives=["fred"]) is None


# --- from a real collection -------------------------------------------------

def test_from_collection_records_successes_not_only_failures():
    collected = {"failures": {"bls": "HTTP Error 503: Service Unavailable"},
                 "series_attempted": 3}
    got = SH.from_collection(collected, as_of="2026-08-09",
                             attempted=["bls", "fred", "ecb"])
    assert len(got) == 3
    assert {h.source_family for h in got} == {"bls", "fred", "ecb"}
    assert [h.state for h in got if h.source_family == "fred"] == [SH.HEALTHY]


def test_summarise_carries_the_rule_it_enforces():
    healths = SH.from_collection(
        {"failures": {"bls": "503 Service Unavailable"}},
        as_of="2026-08-09", attempted=["bls", "fred"])
    got = SH.summarise(healths)
    assert got["impaired_families"] == ["bls"]
    assert got["observability"] == 0.5
    assert "never weakens a claim" in got["note"]


# --- against the live artifact ----------------------------------------------

def test_the_live_macro_failure_becomes_a_state():
    """Production's own reported failure, run through the classifier.

    This reads the newest dated report rather than a fixture, so it stays
    honest as the live failure changes. If BLS recovers, the report carries
    no failure and the test asserts the healthy path instead.
    """
    reports = sorted((MARKET_ROOT / "reports" / "market").glob("2026-*.json"))
    if not reports:                                    # pragma: no cover
        pytest.skip("no dated report available")
    macro = {}
    for path in reversed(reports):
        payload = json.loads(path.read_text(encoding="utf-8"))
        macro = (payload.get("research") or {}).get("macro") or {}
        if macro:
            break
    if not macro:                                      # pragma: no cover
        pytest.skip("no macro block in any dated report")

    healths = SH.from_collection(
        macro, as_of="2026-08-09",
        attempted=sorted(set(macro.get("series_failed") or ())
                         | {"__succeeded__"}))
    summary = SH.observability(healths)
    assert summary["sources"] >= 1
    for health in healths:
        # Whatever production reported, it must land in the closed
        # vocabulary and never as a bare unexplained state.
        assert health.state in SH.STATES
        if health.impaired:
            assert health.failure


# --- wiring: the state must survive the cycle -------------------------------

def _stub_collect(failure: str):
    def collect(**_kwargs):
        return {"contract": "x", "series_attempted": 6, "series_succeeded": 5,
                "series_failed": ["bureau_of_labor_statistics"] if failure
                                 else [],
                "failures": ({"bureau_of_labor_statistics": failure}
                             if failure else {}),
                "observations": [], "observation_count": 0,
                "periods_covered": [], "areas_covered": [], "kinds_covered": []}
    return collect


def test_the_macro_sweep_records_health_for_every_family(tmp_path,
                                                         monkeypatch):
    from intent_engine.market import cycle as C
    from intent_engine.market import macro_ingest as MI
    from intent_engine.market import steps as S

    monkeypatch.setattr(
        MI, "collect",
        _stub_collect("HTTPError: HTTP Error 503: Service Unavailable"))
    ctx = C.CycleContext(cycle="night", as_of="2026-08-09", root=tmp_path,
                         session=None, run_id="t", dry_run=True)
    got = S._macro_sweep(ctx)["source_health"]
    assert got["sources"] == len(MI.SERIES)
    assert got["impaired_families"] == ["bureau_of_labor_statistics"]
    assert got["observability"] < 1.0
    # Successes are recorded, not only failures.
    assert got["by_state"][SH.HEALTHY] == len(MI.SERIES) - 1


def test_the_streak_survives_across_cycles(tmp_path, monkeypatch):
    """The whole reason this is a state: one 503 is not three.

    Each cycle re-reads the newest standing per family from the ledger, so
    the third consecutive outage is UNAVAILABLE rather than a fourth
    rediscovery of a bad minute.
    """
    from intent_engine.market import cycle as C
    from intent_engine.market import learning_store as LS
    from intent_engine.market import macro_ingest as MI
    from intent_engine.market import steps as S

    monkeypatch.setattr(
        MI, "collect",
        _stub_collect("HTTPError: HTTP Error 503: Service Unavailable"))
    states = []
    for day in range(SH.OUTAGE_STREAK):
        ctx = C.CycleContext(cycle="night", as_of=f"2026-08-0{day + 1}",
                             root=tmp_path, session=None, run_id="t",
                             dry_run=False)
        got = S._macro_sweep(ctx)["source_health"]
        detail = {d["source_family"]: d for d in got["sources_detail"]}
        states.append(detail["bureau_of_labor_statistics"]["state"])

    assert states[0] == SH.DEGRADED
    assert states[-1] == SH.UNAVAILABLE

    store = LS.LearningStore(tmp_path / LS.DEFAULT_PATH)
    rows = store.source_health()
    # Every family, every cycle: repeats are real observations, not noise.
    assert len(rows) == len(MI.SERIES) * SH.OUTAGE_STREAK
    assert store.latest_source_health()["bureau_of_labor_statistics"][
        "failure_streak"] == SH.OUTAGE_STREAK


def test_recovery_is_visible_in_the_ledger(tmp_path, monkeypatch):
    from intent_engine.market import cycle as C
    from intent_engine.market import learning_store as LS
    from intent_engine.market import macro_ingest as MI
    from intent_engine.market import steps as S

    monkeypatch.setattr(MI, "collect", _stub_collect("503 Service Unavailable"))
    S._macro_sweep(C.CycleContext(cycle="night", as_of="2026-08-01",
                                  root=tmp_path, session=None, run_id="t",
                                  dry_run=False))
    monkeypatch.setattr(MI, "collect", _stub_collect(""))
    S._macro_sweep(C.CycleContext(cycle="night", as_of="2026-08-02",
                                  root=tmp_path, session=None, run_id="t",
                                  dry_run=False))

    store = LS.LearningStore(tmp_path / LS.DEFAULT_PATH)
    latest = store.latest_source_health()["bureau_of_labor_statistics"]
    assert latest["state"] == SH.HEALTHY
    assert latest["failure_streak"] == 0
    assert latest["last_success"] == "2026-08-02"


def test_a_dry_run_writes_no_health_rows(tmp_path, monkeypatch):
    from intent_engine.market import cycle as C
    from intent_engine.market import learning_store as LS
    from intent_engine.market import macro_ingest as MI
    from intent_engine.market import steps as S

    monkeypatch.setattr(MI, "collect", _stub_collect("503 Service Unavailable"))
    S._macro_sweep(C.CycleContext(cycle="night", as_of="2026-08-01",
                                  root=tmp_path, session=None, run_id="t",
                                  dry_run=True))
    assert LS.LearningStore(tmp_path / LS.DEFAULT_PATH).source_health() == ()
