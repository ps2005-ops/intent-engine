"""An archetype a class can propose must be able to ask its own question.

MEASURED offline against the two companies' own filings, 2026-08-20.
ADVERTISING_PLATFORM proposes exactly two decision archetypes — ENGAGEMENT
and MONETISATION_RATE — and NEITHER had a row in `_ARCHETYPE_SUBJECT`. So
`_decision_question` fell through to the epistemic fallback and Meta's
CENTRAL QUESTION, the single most important line on the page, read:

    "What does the published record establish about Meta Platforms, Inc.,
     and what would have to be true before a commitment rests on it?"

Alphabet's read the same with the name swapped. Composing both reads from
their own filings gave twelve projected fields identical on ten, and this was
one of only two that differed — by company name.

THE SHAPE, FOR THE THIRD TIME. A model class was added and a table keyed on
something that class INTRODUCES never got its rows. `_ARCHETYPE_SUBJECT` is
keyed on ARCHETYPE, not on model class, so the model-class registry guard in
`test_a_model_class_registry.py` could not see it. The registry guard was
right to discover tables rather than name them; it was looking one key-space
to the left.
"""
import pytest

from intent_engine.executive.analysis_selection import (
    _ARCHETYPE_SUBJECT, select,
)
from intent_engine.executive.company_profile import (
    _ECONOMICS, MODEL_CLASSES, profile_for,
)

EPISTEMIC_FALLBACK = "What does the published record establish about"


def proposable_archetypes():
    """Every archetype any REGISTERED class can put on its own menu."""
    out = set()
    for model in MODEL_CLASSES:
        out |= set((_ECONOMICS.get(model) or {}).get("archetypes", ()))
    return out


def test_the_menu_is_not_empty():
    """A guard that discovers nothing passes for free."""
    assert len(proposable_archetypes()) >= 15


@pytest.mark.parametrize("archetype", sorted(proposable_archetypes()))
def test_every_proposable_archetype_has_a_subject(archetype):
    assert archetype in _ARCHETYPE_SUBJECT, (
        f"{archetype} is on a registered class's menu and has no subject, so "
        f"every company that ranks it first is handed the epistemic fallback "
        f"as its central question")
    assert _ARCHETYPE_SUBJECT[archetype].strip()


@pytest.mark.parametrize("model", sorted(MODEL_CLASSES))
def test_every_class_can_ask_a_question_of_its_own(model):
    """The end-to-end property, per class: a company of this kind must not
    receive the epistemic fallback as its central question."""
    menu = (_ECONOMICS.get(model) or {}).get("archetypes", ())
    if not menu:
        pytest.skip(f"{model} proposes no archetypes")
    missing = sorted(set(menu) - set(_ARCHETYPE_SUBJECT))
    assert not missing, f"{model} can propose {missing}, which cannot ask"


def test_meta_asks_an_advertising_question_not_an_epistemic_one():
    """The measured case, end to end through `select`."""
    registrant = {"sic": "7370",
                  "sic_description": "SERVICES-COMPUTER PROGRAMMING"}
    evidence = ("We generate substantially all of our revenue from selling "
                "advertising placements to marketers.")
    profile = profile_for(name="Meta Platforms, Inc.", domain="meta.com",
                          registrant=registrant, evidence_text=evidence)
    assert profile.business_model_class == "ADVERTISING_PLATFORM"
    selection = select("", name="Meta Platforms, Inc.", domain="meta.com",
                       profile=profile, registrant=registrant,
                       evidence_text=evidence)
    question = selection.decision_question
    assert EPISTEMIC_FALLBACK not in question, question
    assert "attention" in question or "ad load" in question, question
    # and it names this business's own driver, not a generic one
    assert "engagement" in question, question


def test_a_thirteenth_archetype_fails_closed():
    """Today's rows already cover today's archetypes, so nothing above proves
    the next one is caught. This simulates one."""
    invented = "NEW_ARCHETYPE_18"
    assert invented not in _ARCHETYPE_SUBJECT
    assert invented not in proposable_archetypes()
    # If it were ever added to a class menu without a subject, the
    # per-archetype guard above would fail for it — which is the whole point.
    menu = proposable_archetypes() | {invented}
    assert sorted(menu - set(_ARCHETYPE_SUBJECT)) == [invented]
