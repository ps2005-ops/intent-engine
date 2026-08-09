"""The economy stops being one country and one series.

V4 session 1 measured one condition. These are the guards that made it safe to
measure thirteen: an area on every figure, a declared primary series per
condition, a derived spread that is never mistaken for a measurement, and
adapters that survive the shapes real publishers actually return.
"""
from __future__ import annotations

import pytest

from intent_engine.market import macro_ingest as MI
from intent_engine.market import macro_state as MS


def obs(kind=MS.MARKET_RATE, *, area=MS.US, series="S1", value=1.0,
        period="2026-06-30", published="2026-07-30", standing=MS.OBSERVED,
        basis=MS.ASSUMED_LAG, unit="%", measure=MS.LEVEL, label="rate"):
    return MS.MacroObservation(
        state_kind=kind, area=area, series_id=series, label=label,
        value=value, unit=unit, measure=measure, standing=standing,
        reference_period=period, published_at=published,
        publication_basis=basis, source="test")


# --- an area is part of what a figure is ------------------------------------

def test_an_unnamed_economy_is_refused():
    with pytest.raises(MS.MacroRejected) as err:
        obs(area="ZZ")
    assert "area" in str(err.value)


def test_existing_records_keep_meaning_us():
    """Rows written before the field existed were all US Treasury figures."""
    row = {"state_kind": MS.MARKET_RATE, "series_id": "TREASURY_NOTES_AVG_RATE",
           "label": "x", "value": 3.2, "unit": "%",
           "reference_period": "2026-06-30", "published_at": "2026-07-30",
           "publication_basis": MS.ASSUMED_LAG}
    assert MS.from_dict(row).area == MS.US


def test_two_countries_do_not_share_one_condition():
    history = [obs(area=MS.US, series="US_RATE", value=3.2,
                   period="2026-06-30", published="2026-07-30"),
               obs(area=MS.CA, series="CA_RATE", value=2.8,
                   period="2026-08-05", published="2026-08-08")]
    us = MS.state_of(MS.MARKET_RATE, history, as_of="2026-08-09", area=MS.US)
    ca = MS.state_of(MS.MARKET_RATE, history, as_of="2026-08-09", area=MS.CA)
    assert us.observation.value == 3.2 and us.area == MS.US
    assert ca.observation.value == 2.8 and ca.area == MS.CA


def test_a_direction_is_never_computed_across_economies():
    """The failure the area field was added to stop.

    Canada publishes daily and the US monthly, so the Canadian figure wins on
    recency; without an area the two would be differenced and the engine would
    report a 0.4-point move that is really a change of subject.
    """
    with pytest.raises(MS.MacroRejected) as err:
        MS.direction(obs(area=MS.CA, series="S1", value=2.8),
                     obs(area=MS.US, series="S1", value=3.2))
    assert "two economies" in str(err.value)


# --- one condition is at most one series ------------------------------------

def test_the_condition_does_not_change_identity_when_a_series_publishes():
    """A 2-year and a 10-year yield are both MARKET_RATE and only one is it."""
    history = [
        obs(area=MS.CA, series="BOC_BD.CDN.10YR.DQ.YLD", value=3.61,
            period="2026-08-06", published="2026-08-09"),
        obs(area=MS.CA, series="BOC_BD.CDN.2YR.DQ.YLD", value=2.92,
            period="2026-08-06", published="2026-08-09"),
    ]
    state = MS.state_of(MS.MARKET_RATE, history, as_of="2026-08-10",
                        area=MS.CA)
    assert state.observation.series_id == "BOC_BD.CDN.10YR.DQ.YLD"
    assert state.observation.value == 3.61
    # AND IT MUST BE THE DECLARED RULE DOING THE WORK. Sorted alphabetically
    # "BOC_BD.CDN.10YR..." already comes first, so deleting PRIMARY_SERIES
    # left this test passing on the fallback; the US pair is the one where
    # the declared choice and the alphabetical one disagree.
    us = [obs(area=MS.US, series="TREASURY_BILLS_AVG_RATE", value=3.758),
          obs(area=MS.US, series="TREASURY_NOTES_AVG_RATE", value=3.283)]
    assert MS.state_of(MS.MARKET_RATE, us, as_of="2026-08-10",
                       area=MS.US).observation.series_id == \
        "TREASURY_NOTES_AVG_RATE"


def test_the_unread_series_is_named_rather_than_hidden():
    history = [obs(area=MS.CA, series="BOC_BD.CDN.10YR.DQ.YLD", value=3.61),
               obs(area=MS.CA, series="BOC_BD.CDN.2YR.DQ.YLD", value=2.92)]
    state = MS.state_of(MS.MARKET_RATE, history, as_of="2026-08-10",
                        area=MS.CA)
    assert "BOC_BD.CDN.2YR.DQ.YLD" in state.reason
    assert "were not read" in state.reason


def test_an_undeclared_choice_is_stable_rather_than_arbitrary():
    history = [obs(kind=MS.INFLATION, series="B_SERIES", value=2.0),
               obs(kind=MS.INFLATION, series="A_SERIES", value=9.0)]
    first = MS.state_of(MS.INFLATION, history, as_of="2026-08-10")
    second = MS.state_of(MS.INFLATION, list(reversed(history)),
                         as_of="2026-08-10")
    assert first.observation.series_id == second.observation.series_id


def test_a_prior_comes_from_the_chosen_series_only():
    """The previous reading must be the same question asked earlier."""
    history = [
        obs(area=MS.CA, series="BOC_BD.CDN.10YR.DQ.YLD", value=3.40,
            period="2026-08-04", published="2026-08-07"),
        obs(area=MS.CA, series="BOC_BD.CDN.2YR.DQ.YLD", value=2.99,
            period="2026-08-05", published="2026-08-08"),
        obs(area=MS.CA, series="BOC_BD.CDN.10YR.DQ.YLD", value=3.61,
            period="2026-08-06", published="2026-08-09"),
    ]
    state = MS.state_of(MS.MARKET_RATE, history, as_of="2026-08-10",
                        area=MS.CA)
    assert state.prior.series_id == "BOC_BD.CDN.10YR.DQ.YLD"
    assert state.prior.value == 3.40
    assert state.moved == MS.UP


# --- a spread is derived, and says so ---------------------------------------

def test_a_spread_is_inferred_not_observed():
    history = [obs(series="LONG", value=3.61, period="2026-08-06",
                   published="2026-08-09"),
               obs(series="SHORT", value=2.92, period="2026-08-06",
                   published="2026-08-09")]
    spread = MS.term_spread(history, as_of="2026-08-10",
                            long_series="LONG", short_series="SHORT")
    assert spread.standing == MS.INFERRED
    assert spread.state_kind == MS.CREDIT_CONDITIONS
    assert round(spread.value, 2) == 0.69
    assert not spread.anchors is False  # INFERRED may anchor a chain


def test_a_spread_refuses_mismatched_periods():
    """Two legs from different months describe no month at all."""
    history = [obs(series="LONG", value=3.61, period="2026-08-06",
                   published="2026-08-09"),
               obs(series="SHORT", value=2.92, period="2026-03-06",
                   published="2026-03-09")]
    assert MS.term_spread(history, as_of="2026-08-10",
                          long_series="LONG", short_series="SHORT") is None


def test_a_spread_is_not_knowable_before_its_slower_leg():
    history = [obs(series="LONG", value=3.61, period="2026-08-06",
                   published="2026-08-09"),
               obs(series="SHORT", value=2.92, period="2026-08-06",
                   published="2026-08-20")]
    spread = MS.term_spread(history, as_of="2026-08-30",
                            long_series="LONG", short_series="SHORT")
    assert spread.published_at == "2026-08-20"
    assert not spread.known_at("2026-08-19")


def test_a_spread_of_a_measured_and_an_assumed_date_is_assumed():
    history = [obs(series="LONG", value=3.61, basis=MS.PUBLISHER,
                   published="2026-08-09"),
               obs(series="SHORT", value=2.92, basis=MS.ASSUMED_LAG,
                   published="2026-08-09")]
    spread = MS.term_spread(history, as_of="2026-08-30",
                            long_series="LONG", short_series="SHORT")
    assert spread.publication_basis == MS.ASSUMED_LAG


def test_a_spread_refuses_two_economies():
    history = [obs(area=MS.US, series="LONG", value=3.61),
               obs(area=MS.CA, series="SHORT", value=2.92)]
    with pytest.raises(MS.MacroRejected):
        MS.term_spread(history, as_of="2026-08-30",
                       long_series="LONG", short_series="SHORT")


# --- what the engine meant to hold ------------------------------------------

def test_tracked_conditions_are_not_the_cross_product():
    assert (MS.GLOBAL, MS.HOUSING) not in MS.TRACKED_CONDITIONS
    assert (MS.GLOBAL, MS.CURRENCY) in MS.TRACKED_CONDITIONS
    assert (MS.US, MS.CURRENCY) not in MS.TRACKED_CONDITIONS
    assert (MS.CA, MS.EMPLOYMENT) in MS.TRACKED_CONDITIONS


def test_all_states_reports_the_gaps_as_well_as_the_readings():
    states = MS.all_states([obs(area=MS.US, series="TREASURY_NOTES_AVG_RATE")],
                           as_of="2026-08-10")
    assert len(states) == len(MS.TRACKED_CONDITIONS)
    known = [s for s in states if s.known]
    assert len(known) == 1 and known[0].key == (MS.US, MS.MARKET_RATE)


def test_summary_counts_a_blind_spot_per_economy():
    states = MS.all_states([obs(area=MS.US, series="TREASURY_NOTES_AVG_RATE")],
                           as_of="2026-08-10")
    got = MS.summarise(states)
    assert "US:MARKET_RATE" not in got["unknown_keys"]
    assert "CA:MARKET_RATE" in got["unknown_keys"]
    assert got["by_area"][MS.US]["known"] == 1


# --- the adapters, against the shapes publishers really return ---------------

def _fiscal_interest_rows():
    """Three accounting lines per month, one of them negative."""
    # THE NEGATIVE LINE COMES FIRST. With accrued interest first, the
    # per-period de-duplication drops the other two and the group filter is
    # never exercised — a break proof against the filter passed on the wrong
    # guard. Ordered this way, only the group filter can save the figure.
    return {"data": [
        {"record_date": "2026-07-31", "expense_type_desc": "Treasury Notes",
         "expense_group_desc": "AMORTIZED PREMIUM",
         "month_expense_amt": "-138894838.86"},
        {"record_date": "2026-07-31", "expense_type_desc": "Treasury Notes",
         "expense_group_desc": "AMORTIZED DISCOUNT",
         "month_expense_amt": "959912479.75"},
        {"record_date": "2026-07-31", "expense_type_desc": "Treasury Notes",
         "expense_group_desc": "ACCRUED INTEREST EXPENSE",
         "month_expense_amt": "43854569972.32"},
    ]}


def test_the_government_is_not_paid_to_borrow():
    """The live defect: the premium line sorted last and became the state."""
    got = MI.treasury_interest_expense(
        retrieved_at="2026-08-08", fetcher=lambda url: _fiscal_interest_rows())
    assert len(got) == 1
    assert got[0].state_kind == MS.FISCAL
    assert got[0].value > 0
    assert round(got[0].value, 2) == 43.85


@pytest.mark.parametrize("cell", ["", None, "(D)", "n/a", "NULL"])
def test_a_suppressed_cell_is_not_a_zero(cell):
    """Feeds write absence several ways and float() turns none of them into 0.

    The empty string is covered by an explicit check AND by the parse guard,
    so a break proof against either one passed on the other. A suppression
    marker is covered only by the parse guard, which is what makes it the
    case worth asserting.
    """
    body = {"data": [{"record_date": "2026-07-31",
                      "avg_interest_rate_amt": cell}]}
    assert MI.treasury_bill_rate(retrieved_at="2026-08-08",
                                 fetcher=lambda url: body) == []


def test_bank_of_canada_marks_a_cross_rate_global():
    body = {"observations": [{"d": "2026-08-05", "FXUSDCAD": {"v": "1.403"}}]}
    got = MI.bank_of_canada(retrieved_at="2026-08-08",
                            fetcher=lambda url: body, only=("FXUSDCAD",))
    assert got[0].area == MS.GLOBAL
    assert got[0].state_kind == MS.CURRENCY


def test_bank_of_canada_never_claims_same_day_knowledge():
    body = {"observations": [{"d": "2026-08-05", "V39079": {"v": "2.25"}}]}
    got = MI.bank_of_canada(retrieved_at="2026-08-08",
                            fetcher=lambda url: body, only=("V39079",))
    assert got[0].publication_basis == MS.ASSUMED_LAG
    assert got[0].published_at > "2026-08-05"
    assert not got[0].known_at("2026-08-05")


def test_statistics_canada_uses_the_publishers_own_release_date():
    """The only keyless source that dates itself."""
    body = [{"status": "SUCCESS", "object": {
        "vectorId": 2062815,
        "vectorDataPoint": [{"refPer": "2026-07-01", "value": 6.4,
                             "releaseTime": "2026-08-07T08:30"}]}}]
    got = MI.statistics_canada(retrieved_at="2026-08-08",
                               fetcher=lambda url, payload: body)
    assert got[0].publication_basis == MS.PUBLISHER
    assert got[0].published_at == "2026-08-07"
    assert got[0].known_at("2026-08-07")
    assert not got[0].known_at("2026-08-06")


def test_statistics_canada_drops_a_point_with_no_release_date():
    """No release date means no vintage, and no vintage means no figure."""
    body = [{"status": "SUCCESS", "object": {
        "vectorId": 2062815,
        "vectorDataPoint": [{"refPer": "2026-07-01", "value": 6.4,
                             "releaseTime": None}]}}]
    assert MI.statistics_canada(retrieved_at="2026-08-08",
                                fetcher=lambda url, payload: body) == []


def test_statistics_canada_ignores_a_failed_vector():
    body = [{"status": "FAILURE", "object": {"vectorId": 2062815}}]
    assert MI.statistics_canada(retrieved_at="2026-08-08",
                                fetcher=lambda url, payload: body) == []


def test_bls_refusal_is_an_error_not_an_empty_economy():
    """503 must not read as 'US inflation did not move'."""
    body = {"status": "REQUEST_NOT_PROCESSED", "message": ["down"]}
    with pytest.raises(RuntimeError):
        MI.bureau_of_labor_statistics(retrieved_at="2026-08-08",
                                      fetcher=lambda url, payload: body)


def test_collect_reports_a_dead_feed_by_name():
    def boom(*_a, **_k):
        raise OSError("unreachable")
    got = MI.collect(retrieved_at="2026-08-08", fetcher=boom, poster=boom)
    assert got["observation_count"] == 0
    assert got["series_succeeded"] == 0
    assert set(got["series_failed"]) == set(MI.SERIES)


def test_collect_gives_a_poster_to_the_post_adapters_only():
    """One injected double called with two arities is a silent half-failure."""
    seen = {"get": 0, "post": 0}

    def getter(url):
        seen["get"] += 1
        return {"data": [], "observations": []}

    def poster(url, payload):
        seen["post"] += 1
        # StatCan answers with a list, BLS with an envelope; one double has to
        # satisfy both or the test measures its own fixture.
        return ([] if "statcan" in url
                else {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}})

    got = MI.collect(retrieved_at="2026-08-08", fetcher=getter, poster=poster)
    assert got["series_failed"] == []
    assert seen["post"] == len(MI.POST_SERIES)
