"""Five rows with one reason is one reason, and a claim it cannot support.

WHAT THIS PINS (§P1-6)
----------------------
MEASURED on cohort A, 8495b00c. Rubrik's X-Ray and Commvault's X-Ray both
carried the SAME competitor set, under the heading "Competitors, and what
they would do — 5 selected":

    37signals LLC    operates the same business model (subscription software)
    Adobe Inc.       in the same sector (software platform), so it competes
    AgileBits Inc.   for the same customers ...

Three things were wrong together. The rationale is a CLASS statement, so it
is identical for every row and for every company sharing the class. The order
is the rank key's last tie-break -- `canonical_name` -- so when geography and
size match, the reader is shown the sector in dictionary order and reads it
as closeness. And the heading claims "competitors" for a set whose only basis
is a shared classification: nothing in the analysis says 37signals competes
with Rubrik.

Boomi's page, with no peers, was the HONEST one: "No competitor set was
selected: this company is not in the validation universe peers are drawn
from." That branch is preserved here, because a repair that empties the
section for everybody would trade one wrong answer for another.
"""
from __future__ import annotations

import re

from intent_engine.founder_brief.xray import _competitor_body

_CLASS_WHY = ("operates the same business model (subscription software) in "
              "the same sector (software platform), so it competes for the "
              "same customers and is exposed to the same cost and demand "
              "drivers")
_WEAK_WHY = ("same sector (software platform) but a different business model "
             "(perpetual licence): it competes for the same end demand "
             "without the same economics")


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _peers(n, why=_CLASS_WHY):
    names = ["37signals LLC", "Adobe Inc.", "AgileBits Inc.", "Cloudera",
             "Databricks"]
    return tuple({"name": nm, "why": why} for nm in names[:n])


def test_peers_that_share_a_reason_are_listed_together():
    html = _competitor_body({"competitors": _peers(3)})
    assert html.count("<li>") == 1, "three rows, one reason, one row"
    assert _text(html).count("operates the same business model") == 1


def test_the_shared_row_names_every_peer():
    html = _competitor_body({"competitors": _peers(3)})
    said = _text(html)
    for name in ("37signals LLC", "Adobe Inc.", "AgileBits Inc."):
        assert name in said


def test_the_shared_row_refuses_the_claim_it_cannot_support():
    said = _text(_competitor_body({"competitors": _peers(3)}))
    assert "no source in this analysis states that any of them competes" \
        in said
    assert "rather than ranked" in said


def test_a_peer_with_its_own_reason_keeps_its_own_row():
    """Grouping must not flatten a rationale that genuinely differs."""
    peers = _peers(2) + ({"name": "Veeam", "why": _WEAK_WHY},)
    html = _competitor_body({"competitors": peers})
    assert html.count("<li>") == 2
    said = _text(html)
    assert "Veeam" in said
    assert "different business model" in said
    assert "no source in this analysis" in said        # only on the group


def test_one_peer_is_rendered_plainly_with_no_group_language():
    html = _competitor_body({"competitors": _peers(1)})
    said = _text(html)
    assert "37signals LLC" in said
    assert "rather than ranked" not in said


def test_an_empty_peer_set_still_says_why_it_is_empty():
    html = _competitor_body({"competitors": (),
                             "company_profile": {"known": True}})
    said = _text(html)
    assert "No competitor set was selected" in said
    assert "validation universe" in said


def test_the_heading_states_the_basis_rather_than_implying_rivalry():
    from intent_engine.founder_brief import xray as X
    src = X.__dict__["render"].__doc__ or ""
    del src
    source = open(X.__file__).read()
    assert "same-class peer(s)" in source
    assert "} selected'," not in source, \
        "'5 selected' implied the set was selected BY competition"
