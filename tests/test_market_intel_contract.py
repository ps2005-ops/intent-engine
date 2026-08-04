"""`market_intel_export.v2` — the allowlist, and what it refuses.

The audit these tests encode: the market engine's own daily report carries
`funnel.counts.positions_opened`, `funnel.rates.signal_fired`,
`leaderboard.rows`, `fdr.discoveries` and `health.lock.path`. Not one of those
names appears in v1's blacklist, so every one of them would have passed a
blacklist check. Hence an allowlist, and hence the recursive tests below.
"""
import json

import pytest

from intent_engine.external_intel import market_contract as MC
from intent_engine.external_intel import market_producer as MP
from intent_engine.external_intel import prices as P


# --- fixtures ---------------------------------------------------------------
def _closes(n=300, start=100.0, step=0.25, first="2025-01-01"):
    """A deterministic ascending series on consecutive weekdays."""
    from datetime import date, timedelta
    out, day, price = {}, date.fromisoformat(first), start
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = round(price, 4)
            price += step
        day += timedelta(days=1)
    return out


def _bench(n=300):
    return _closes(n=n, start=400.0, step=0.10)


def _built(**kw):
    base = dict(ticker="ACME", closes=_closes(), benchmark_closes=_bench(),
                as_of=max(_closes()), exchange="NYSE", currency="USD",
                company_id="c-1")
    base.update(kw)
    return MP.build_export(**base)


# --- the allowlist ----------------------------------------------------------
def test_a_produced_export_validates():
    MC.validate(_built())


def test_an_unknown_top_level_field_fails_closed():
    payload = _built()
    payload["win_rate_by_strategy"] = 0.62
    with pytest.raises(MC.ExportViolation) as exc:
        MC.validate(payload)
    assert "unsanctioned" in str(exc.value)


@pytest.mark.parametrize("path,value", [
    (("data_freshness", "positions_opened"), 4),
    (("benchmark", "sharpe"), 1.8),
    (("source_lineage", "paper_book_path"), "/var/data/paper.db"),
    (("market_regime", "expected_return"), 0.12),
    (("annualized_volatility", "strategy_key"), "mom-20"),
])
def test_an_unknown_nested_field_fails_closed_at_any_depth(path, value):
    """The failure a top-level check misses.

    `funnel.counts.positions_opened` is three levels down. A guard that walks
    only the root would have passed it.
    """
    payload = _built()
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_an_unknown_field_inside_a_list_item_fails_closed():
    payload = _built()
    payload["relevant_market_events"] = [
        {"date": "2026-07-01", "label": "Q2 results published",
         "kind": "disclosure", "source": "filing", "evidence_id": "ev-1",
         "trade_direction": "long"}]
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_an_unknown_field_inside_a_wildcard_mapping_fails_closed():
    """Period labels are data; the fields under them are still schema."""
    payload = _built()
    payload["price_periods"]["1m"]["profit_factor"] = 1.4
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_a_sanctioned_field_holding_forbidden_content_fails():
    """The allowlist alone would pass this: the KEY is legitimate."""
    payload = _built()
    payload["market_regime"]["label"] = "favourable; strategy sharpe 1.8"
    with pytest.raises(MC.ExportViolation) as exc:
        MC.validate(payload)
    assert "forbidden content" in str(exc.value)


def test_a_forbidden_word_smuggled_into_a_limitation_fails():
    payload = _built()
    payload["limitations"].append("Our win rate on this name is 62%.")
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_the_fixed_contract_text_cannot_be_rewritten():
    """`disclaimer` is exempt from the content scan ONLY because it is fixed.

    If a producer could put free text there, the exemption would be the hole.
    """
    payload = _built()
    payload["disclaimer"] = "Descriptive context. Our alpha on this name is 4%."
    with pytest.raises(MC.ExportViolation) as exc:
        MC.validate(payload)
    assert "verbatim" in str(exc.value)


def test_a_wrong_schema_version_is_refused_rather_than_best_efforted():
    payload = _built()
    payload["schema_version"] = "market_intel_export.v1"
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_the_engine_daily_report_shape_cannot_validate():
    """The real artefact this boundary exists to stop.

    These are the actual key names from the market engine's
    `reports/market/2026-08-01_day.1.json`.
    """
    payload = _built()
    payload["funnel"] = {"counts": {"buy": 0, "positions_opened": 0,
                                    "signal_fired": 0},
                         "rates": {"tradable": 0.96}}
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_no_founder_facing_module_imports_the_market_engine():
    """Structural, not behavioural.

    The strongest form of "trading internals cannot leak" is that there is no
    code path to them. This asserts the absence of the import edge.
    """
    import pathlib
    root = pathlib.Path(MP.__file__).resolve().parents[1]
    banned = ("intent_engine.market", "from intent_engine import market",
              "paper_engine", "strategy_library", "paper_book")
    offenders = []
    for area in ("external_intel", "founder_brief", "founder_intelligence"):
        for py in (root / area).rglob("*.py"):
            text = py.read_text()
            for name in banned:
                # A line that merely NAMES the boundary in prose is fine; an
                # import is not.
                for line in text.splitlines():
                    if name in line and line.lstrip().startswith(
                            ("import ", "from ")):
                        offenders.append(f"{py.name}: {line.strip()}")
    assert not offenders, offenders


# --- missing is never zero --------------------------------------------------
def test_an_unmeasurable_measurement_cannot_carry_a_value():
    with pytest.raises(MC.ExportViolation):
        MC.measurement(0.0, MC.UNMEASURABLE, period="1m", unit="percent",
                       source="x")


def test_an_observed_measurement_cannot_be_none():
    with pytest.raises(MC.ExportViolation):
        MC.measurement(None, MC.OBSERVED, period="1m", unit="percent",
                       source="x")


def test_a_short_history_reports_unmeasurable_not_zero():
    payload = _built(closes=_closes(n=40), benchmark_closes=_bench(n=40))
    year = payload["price_periods"]["1y"]
    assert year["status"] == MC.UNMEASURABLE
    assert year["value"] is None, "absence must never become a number"
    assert "has 40" in year["note"]


def test_no_price_history_produces_a_stated_limitation_not_a_blank():
    payload = _built(closes={}, benchmark_closes={})
    assert payload["data_freshness"]["latest_session"] == ""
    assert any("reported as unavailable rather than estimated" in x
               for x in payload["limitations"])
    assert all(m["value"] is None
               for m in payload["price_periods"].values())


def test_every_numeric_value_carries_its_period_unit_and_source():
    """A number without its period gets relabelled the first time a consumer
    iterates the mapping in a different order."""
    payload = _built()
    for group in ("price_periods", "benchmark_relative_periods"):
        for label, m in payload[group].items():
            assert m["period"], f"{group}.{label} has no period"
            assert m["unit"], f"{group}.{label} has no unit"
            assert m["source"], f"{group}.{label} has no source"
    for key in ("annualized_volatility", "period_drawdown",
                "distance_from_period_high"):
        assert payload[key]["period"] and payload[key]["unit"]


def test_an_unmeasurable_window_still_names_the_period_in_words():
    """Found in the first live run: the unmeasurable branch fell back to the
    raw key, so a founder read the period as "1y" while every measurable
    sibling said "the past year"."""
    payload = _built(closes=_closes(n=40), benchmark_closes=_bench(n=40))
    assert payload["price_periods"]["1y"]["period"] == "the past year"


# --- freshness --------------------------------------------------------------
def test_a_stale_export_is_labelled_stale(tmp_path):
    payload = _built()
    MP.write_export(payload, tmp_path)
    fresh = MP.load_export(tmp_path, "ACME", today=payload["as_of"])
    assert fresh.available and not fresh.stale
    later = "2027-01-01"
    stale = MP.load_export(tmp_path, "ACME", today=later)
    assert stale.available and stale.stale
    assert stale.age_days > MP.MAX_AGE_DAYS


def test_a_stale_export_cannot_present_itself_as_current(tmp_path):
    """Break proof: forge the freshness block, keep the old session."""
    payload = _built()
    payload["data_freshness"]["age_days"] = 0
    payload["data_freshness"]["stale"] = False
    MP.write_export(payload, tmp_path)
    # The consumer recomputes age from the SESSION DATE rather than trusting
    # the field, so a forged flag changes nothing a founder sees.
    loaded = MP.load_export(tmp_path, "ACME", today="2027-01-01")
    assert loaded.stale, "freshness must be recomputed, not trusted"


def test_a_ticker_mismatch_is_refused(tmp_path):
    MP.write_export(_built(), tmp_path)
    path = MP.export_path(tmp_path, "ACME")
    blob = json.loads(path.read_text())
    blob["ticker"] = "OTHER"
    path.write_text(json.dumps(blob))
    got = MP.load_export(tmp_path, "ACME", today=blob["as_of"])
    assert not got.available
    assert "OTHER" in got.reason


def test_an_export_violating_the_contract_is_not_shown_degraded(tmp_path):
    MP.write_export(_built(), tmp_path)
    path = MP.export_path(tmp_path, "ACME")
    blob = json.loads(path.read_text())
    blob["leaderboard"] = {"rows": [{"strategy": "mom-20", "rank": 1}]}
    path.write_text(json.dumps(blob))
    got = MP.load_export(tmp_path, "ACME", today=blob["as_of"])
    assert not got.available, "a violating export must not render partially"
    assert got.payload is None


def test_a_missing_export_reads_as_a_reason_not_an_exception(tmp_path):
    got = MP.load_export(tmp_path, "NOPE", today="2026-08-04")
    assert not got.available and "NOPE" in got.reason


# --- the chart series -------------------------------------------------------
def test_the_series_uses_only_sessions_both_lines_traded():
    payload = _built()
    series = payload["series"]
    assert len(series["dates"]) == len(series["company_indexed"])
    assert len(series["dates"]) == len(series["benchmark_indexed"])
    assert series["company_indexed"][0] == 100 == series["benchmark_indexed"][0]


def test_too_few_observations_omits_the_series_rather_than_drawing_it():
    """A chart with three points reads as a trend. It is not one."""
    payload = _built(closes=_closes(n=20), benchmark_closes=_bench(n=20))
    assert "series" not in payload
    assert any("too few sessions" in x.lower() for x in payload["limitations"])


def test_a_null_close_is_dropped_never_carried_forward():
    """A carried-forward price makes a flat stretch the data never saw."""
    raw = {"chart": {"result": [{
        "timestamp": [1735689600, 1735776000, 1735862400],
        "indicators": {"quote": [{"close": [10.0, None, 12.0]}]},
        "meta": {"currency": "USD", "exchangeName": "NYSE"}}]}}
    series = P._parse("ACME", raw)
    assert len(series.closes) == 2
    assert 11.0 not in series.closes.values()
    assert 10.0 in series.closes.values() and 12.0 in series.closes.values()


# --- point-in-time ----------------------------------------------------------
def test_only_sessions_on_or_before_as_of_are_read():
    closes = _closes(n=300)
    cut = sorted(closes)[200]
    payload = _built(closes=closes, benchmark_closes=_bench(), as_of=cut)
    assert payload["data_freshness"]["latest_session"] == cut


# --- idempotence ------------------------------------------------------------
def test_rewriting_the_same_day_changes_nothing_a_founder_reads(tmp_path):
    a = _built()
    MP.write_export(a, tmp_path)
    b = _built()
    MP.write_export(b, tmp_path)
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


def test_a_render_path_never_triggers_a_fetch(tmp_path):
    """`allow_fetch=False` is what a page render uses.

    A founder loading a page must not be able to start a network download; the
    refresh job owns that.
    """
    def explode(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("a render path attempted a network fetch")

    got = MP.ensure_export(ticker="ACME", root=tmp_path, today="2026-08-04",
                           fetcher=explode, allow_fetch=False)
    assert not got.available


def test_a_failed_fetch_keeps_the_last_good_export(tmp_path):
    """Stale-but-labelled beats blank."""
    MP.write_export(_built(), tmp_path)
    got = MP.ensure_export(ticker="ACME", root=tmp_path, today="2027-01-01",
                           fetcher=lambda *a, **k: None)
    assert got.available and got.stale


def test_a_failed_fetch_with_nothing_stored_states_the_absence(tmp_path):
    got = MP.ensure_export(ticker="ACME", root=tmp_path, today="2026-08-04",
                           fetcher=lambda *a, **k: None)
    assert not got.available
    assert "nothing is estimated" in got.reason.lower()


# --- volatility honesty -----------------------------------------------------
def test_a_single_gap_day_is_named_rather_than_silently_annualised():
    """Measured on Palantir, 2026-08-04.

    A 20-session window over one +29.5% earnings gap annualises to 112%, which
    reads as "the market has no idea what this is worth". The window is 60
    sessions now, and when one session still dominates, the note says so.
    """
    closes = _closes(n=120)
    last = max(closes)
    closes[last] = closes[last] * 1.30
    payload = _built(closes=closes)
    note = payload["annualized_volatility"]["note"]
    assert "one session moved" in note
    assert "single event" in note


def test_a_calm_series_gets_no_dominance_caveat():
    note = _built()["annualized_volatility"]["note"]
    assert "one session moved" not in note
