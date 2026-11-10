"""Opportunity coverage — the counterweight to novelty.

Novelty asks whether a prediction is a new shape. Coverage asks whether the
universe those shapes come from is wide enough for the answer to generalise.
A system can be genuinely accurate and completely parochial.
"""
from intent_engine.market.coverage import assess, concentration, observed


class _Co:
    def __init__(self, sector=None, industry=None, market_cap=None,
                 region=None):
        self.sector = sector
        self.industry = industry
        self.market_cap = market_cap
        self.region = region


EXPECTED = {"sector": ["Technology", "Healthcare", "Energy"],
            "market_cap": ["large", "small"],
            "region": ["North America", "Europe"]}


def test_it_names_what_is_missing_not_just_what_was_seen():
    """The useful output is "no healthcare, no small-cap", which names the next
    companies to add — not a single coverage score, which invites exactly the
    optimisation this project has already been burned by."""
    result = assess([_Co(sector="Technology", market_cap="large",
                         region="North America")], expected=EXPECTED)
    assert result["gaps"]["sector"] == ["Energy", "Healthcare"]
    assert result["gaps"]["market_cap"] == ["small"]
    assert result["widest_gap"] == "sector"


def test_full_coverage_reports_no_gaps():
    companies = [_Co("Technology", None, "large", "North America"),
                 _Co("Healthcare", None, "small", "Europe"),
                 _Co("Energy", None, "large", "Europe")]
    assert assess(companies, expected=EXPECTED)["gaps"] == {}


def test_without_an_expected_universe_it_refuses_to_claim_completeness():
    """Reporting what was seen cannot distinguish "we cover every sector" from
    "we know of one sector"."""
    result = assess([_Co(sector="Technology")])
    assert result["gaps"] == {}
    assert "cannot say what is missing" in result["note"]


def test_breadth_does_not_hide_concentration():
    """A set can touch six sectors and still be 80% one of them."""
    companies = ([_Co(sector="Technology") for _ in range(8)]
                 + [_Co(sector="Energy"), _Co(sector="Healthcare")])
    result = assess(companies, expected=EXPECTED)
    assert result["counts"]["sector"] == 3        # looks broad
    assert concentration(companies, "sector") == 0.8   # is not


def test_a_dimension_the_data_does_not_carry_reads_as_zero_not_as_covered():
    """`market_cap` and `region` are absent from the real universe today. That
    must surface as a measured gap rather than silently passing."""
    seen = observed([_Co(sector="Technology")])
    assert seen["sector"] == {"Technology"}
    assert seen["market_cap"] == set() and seen["region"] == set()


def test_the_regime_is_recorded_because_a_lesson_can_be_regime_specific():
    assert observed([_Co(sector="Technology")], regime="calm")["regime"] \
        == {"calm"}
