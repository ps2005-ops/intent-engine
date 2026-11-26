"""A business model's standing alternative is not this company's hypothesis.

Measured on prospect-100 round 7: the same "possibility worth testing" --
the competitor is the customer's own engineering; "closed-lost reasons
dominated by no-decision" -- headed 70 of 95 briefs, because the belief
engine bound it to a non-firm rival that `competitive_ground` adds to EVERY
subscription-software ladder as a reading of the model.
"""
from __future__ import annotations

from types import SimpleNamespace

from intent_engine.executive import belief_engine as BE
from intent_engine.executive import competitive_ladder as CL


def _rival(rung, evidence=""):
    return CL.Rival(identity="The customer's own engineering",
                    kind="BUILD_IN_HOUSE", rung=rung,
                    mechanism="the customer's team builds it instead",
                    evidence=evidence, disproof="customers stop building it",
                    why_it_matters="it decides what the product is priced against")


def _texts(rival):
    ground = SimpleNamespace(rivals=(rival,))
    return [h.hypothesis for h in BE._hypotheses(
        "Acme", "SUBSCRIPTION_SOFTWARE", ground, ("", ""))]


def test_the_model_s_standing_alternative_binds_nothing():
    texts = _texts(_rival(CL.INTERNAL_BUILD))
    assert not any("not a competing vendor" in t for t in texts), texts


def test_the_company_s_own_words_still_bind_it():
    """POSITIVE CONTROL: Acme itself says customers build it in-house."""
    rung = next(iter(CL.FROM_SUBJECT_WORDS & CL.ATTRIBUTED))
    texts = _texts(_rival(rung, evidence="Most prospects first try to build "
                                         "this in-house with their own team."))
    assert any("not a competing vendor" in t for t in texts), texts
