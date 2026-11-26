"""A stopping rule names the quantity that has to move.

"If the direction is not visible by the next review" and "commit no more than
can be withdrawn inside one planning cycle" were the same two sentences on 71
of 95 prospect-100 round-7 briefs.
"""
from __future__ import annotations

from intent_engine.executive.analysis_selection import select

SOFTWARE = ("Acme sells subscription software to finance teams, priced per "
            "user per month on annual contracts, delivered as a cloud "
            "service. Customers renew each year and expand seats. ") * 4


def test_the_base_case_stopping_rule_names_the_variable():
    s = select("acme", name="Acme", published_text=SOFTWARE, evidence_text="")
    base = next(sc for sc in s.scenarios if sc.name == "BASE")
    assert "direction is not visible" not in base.kill_switch
    driver = s.profile.primary_revenue_drivers[0].lower()
    assert driver in base.kill_switch.lower()
