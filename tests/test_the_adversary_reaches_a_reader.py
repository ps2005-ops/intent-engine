"""The L0/L1/L2 adversary must run for a company outside the manifest.

MEASURED across the 50-company gauntlet: the adversarial response appears on
NO surface of ANY of the fifty. The engine is not missing -- `_adversary`
builds a complete L0/L1/L2 reading -- it was gated:

    if not profile.known or not profile.strategic_competitors:
        return ()

`profile.known` is True only for companies in the curated validation
manifest, and almost none of the fifty are in it. A complete engine that ran
for nobody.

A rival established from the SUBJECT'S OWN FILING is not a lesser fact than a
rival typed into a manifest. Neither source may invent one: with no rival
from either, this still returns nothing.
"""
from intent_engine.executive.analysis_selection import _adversary
from intent_engine.executive.company_profile import (
    CompanyIntelligenceProfile, Competitor,
)


class _Rival:
    def __init__(self, name, why=""):
        self.name, self.why = name, why


def _profile(known: bool, competitors=()):
    return CompanyIntelligenceProfile(
        company_id="c", company_name="Test Co", known=known,
        business_model_class="SOFTWARE_PLATFORM",
        primary_revenue_drivers=("subscription revenue",),
        relevant_evidence_types=("pricing pages",),
        strategic_competitors=tuple(competitors))


def test_an_unmanifested_company_gets_an_adversary_from_its_filing():
    """THE DEFECT."""
    moves = _adversary(_profile(False), "PRICING", None,
                       rivals=(_Rival("Komatsu", "it sells the same machine"),))
    assert [m.level for m in moves] == ["L0", "L1", "L2"]
    assert all(m.actor == "Komatsu" for m in moves)


def test_every_level_carries_what_a_reader_needs():
    moves = _adversary(_profile(False), "PRICING", None,
                       rivals=(_Rival("Komatsu", "it sells the same machine"),))
    for move in moves:
        assert move.action and move.rationale
        assert move.observable_signal and move.impact
        assert move.countermeasure and move.kill_switch


def test_the_manifest_still_wins_when_it_has_one():
    """A curated rival outranks a discovered one, as before."""
    curated = Competitor(name="Deere & Company", why="it sells the same machine", basis="manifest")
    moves = _adversary(_profile(True, (curated,)), "PRICING", None,
                       rivals=(_Rival("Somebody Else"),))
    assert moves and moves[0].actor == "Deere & Company"


def test_no_rival_from_either_source_invents_nothing():
    """THE CONTROL. Reasoning against a placeholder is worse than silence."""
    assert _adversary(_profile(False), "PRICING", None, rivals=()) == ()
    assert _adversary(_profile(True), "PRICING", None, rivals=()) == ()


def test_an_unknown_profile_does_not_borrow_the_manifest_list():
    """`known` False means the manifest row is not about this company."""
    other = Competitor(name="Not This Company's Rival", why="", basis="manifest")
    moves = _adversary(_profile(False, (other,)), "PRICING", None,
                       rivals=(_Rival("Komatsu"),))
    assert moves and moves[0].actor == "Komatsu"
