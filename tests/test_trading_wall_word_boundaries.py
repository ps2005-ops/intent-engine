"""Batch 16: the trading wall matches words, not letter sequences.

`_BANNED_SUBSTRINGS` was scanned with `in`, so "alpha" inside "Alphabet Inc."
refused the entire snapshot. Alphabet is one of the largest public companies
in the world and squarely inside the validation universe this programme is
built around — every founder-facing text naming it was rejected, and the
rejection was total rather than redacted.

The wall is NOT relaxed here. Every trading term still refuses when it stands
as its own word, including uppercase and hyphenated forms. What stops matching
is a term buried inside a longer word.

Both copies of the list are tested. They are deliberately duplicated (neither
package may import the other) and the failure mode of a duplicated rule is
that one copy gets fixed.
"""
import pytest

from intent_engine.demo_dossier.contracts import SnapshotRefused
from intent_engine.demo_dossier.contracts import _scan_text as scan_dossier
from intent_engine.external_intel.strategic_contract import StrategicLeak
from intent_engine.external_intel.strategic_contract import (
    _scan_text as scan_strategic,
)

_WALLS = (
    pytest.param(scan_dossier, SnapshotRefused, id="demo_dossier"),
    pytest.param(scan_strategic, StrategicLeak, id="strategic_contract"),
)

#: Must pass. A real company, a real place, an ordinary English word.
ALLOWED = (
    "Alphabet Inc. reported revenue growth",
    "Alphabet is a holding company for Google",
    "the alphabet of the industry",
    "Alpharetta, Georgia headquarters",
    "alphanumeric identifiers",
    "expectancies were not discussed",
)

#: Must refuse. The wall's whole purpose.
REFUSED = (
    "the strategy generated alpha of 3%",
    "ALPHA was 2.1 this quarter",
    "alpha-generating strategy",
    "our sharpe ratio improved",
    "win rate of 62%",
    "price target raised to 400",
    "position size was halved",
    "the shadow portfolio returned",
    "expectancy per trade",
)


@pytest.mark.parametrize("scan,error", _WALLS)
@pytest.mark.parametrize("text", ALLOWED)
def test_ordinary_text_containing_a_banned_substring_is_allowed(
        scan, error, text):
    scan(text)          # must not raise


@pytest.mark.parametrize("scan,error", _WALLS)
@pytest.mark.parametrize("text", REFUSED)
def test_trading_language_is_still_refused(scan, error, text):
    with pytest.raises(error):
        scan(text)


@pytest.mark.parametrize("scan,error", _WALLS)
def test_a_banned_term_nested_in_a_structure_is_still_found(scan, error):
    """The scan recurses; the boundary change must not stop it descending."""
    with pytest.raises(error):
        scan({"a": ["fine", {"b": "our sharpe ratio improved"}]})


@pytest.mark.parametrize("scan,error", _WALLS)
def test_the_refusal_names_the_term_it_found(scan, error):
    """A refusal a reviewer cannot audit is a refusal nobody can dispute."""
    with pytest.raises(error) as caught:
        scan("win rate of 62%")
    assert "win rate" in str(caught.value)


def test_both_walls_ban_the_same_terms():
    """The lists are duplicated by design; drift is the failure mode."""
    from intent_engine.demo_dossier.contracts import _BANNED_SUBSTRINGS as a
    from intent_engine.external_intel.strategic_contract import (
        _BANNED_SUBSTRINGS as b,
    )
    assert set(a) == set(b)
