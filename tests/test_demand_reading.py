"""demand_reading.v2: the 2026-11-25 trace of the 15 demand-weakening cases."""
import pytest
from intent_engine.market import demand_reading as DR


@pytest.mark.parametrize("text,family", [
    ("Duolingo (DUOL) Stock Falls on Q2 2026 Earnings", DR.ABSTAIN),
    ("Cloudflare Q2 2026 Earnings: Revenue Rises 36% as Restructuring Widens GAAP Loss",
     DR.STRENGTHENING),
    ("Earnings call transcript: NextEra Energy beats Q2 2026 EPS, misses on revenue",
     DR.SURPRISE_NEG),
    ("Shopify Inc Reports Q3 2026 Earnings: EPS Matches Estimates at $0.38, "
     "Revenue Falls Short at $3,742 Million", DR.SURPRISE_NEG),
    ("Honda Motor (HMC) Releases Q2 2027 Earnings: Revenue Up, Profitability Falls",
     DR.STRENGTHENING),
    ("J&J lowers 2026 profit forecast on deal costs, sees further hit in 2027",
     DR.ABSTAIN),
    ("Check Point Software first-quarter profit beats estimates, cuts 2026 revenue outlook",
     DR.WEAKENING),
    ("Linde PLC Reports Q3 Revenue of $9.4 Billion, Misses EPS Estimat", DR.ABSTAIN),
    ("Retailer says same-store sales declined 4% from a year earlier", DR.WEAKENING),
])
def test_only_a_demand_quantity_against_its_own_past_opens_a_demand_reading(text, family):
    assert DR.read(text).family == family, DR.read(text)


def test_a_price_move_is_never_demand():
    r = DR.read("Shares drop 8% after the report")
    assert r.family == DR.ABSTAIN and "not demand" in r.reason


def test_a_same_period_article_may_not_grade_the_belief_it_formed():
    assert not DR.admissible_grade("2026-11-03", "2026-11-04")
    assert DR.admissible_grade("2026-08-05", "2026-10-29")
