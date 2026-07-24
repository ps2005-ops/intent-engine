"""V1.1 targeted regression — the narrowly additive language-wall change.

The wall still rejects the workspace's own overclaiming voice, and now
correctly does NOT reject accurate quoted source material (the T023.5
spec: "the wall must not erase accurate quoted evidence")."""
import pytest

from intent_engine.personal.records import (
    PersonalError, assert_workspace_language,
)


def test_unquoted_overclaims_still_rejected():
    with pytest.raises(PersonalError, match="overclaims"):
        assert_workspace_language("this is obviously the best approach")
    with pytest.raises(PersonalError, match="overclaims"):
        assert_workspace_language("you must adopt this")


def test_quoted_source_material_is_allowed():
    assert_workspace_language(
        'The homepage presents itself as "Best Podcast Hosting".')
    assert_workspace_language(
        'The pricing page states "We’ve never done discounts" '
        "— that language is the company's, quoted verbatim.")


def test_overclaim_outside_a_quote_is_still_caught():
    with pytest.raises(PersonalError, match="overclaims"):
        assert_workspace_language(
            'The page says "fast setup" and is clearly the best option.')
