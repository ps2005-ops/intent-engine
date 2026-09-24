"""The evidence-led decision must reach the composer the X-Ray renders.

MEASURED ON THE DEPLOYED REPAIR (1f70c8c0), first three companies of the
Cohort A re-run. Rubrik, Cohesity and project44 all still asked

    "what to charge, and for what, without losing more customer count than
     the price gains?"

and the X-Ray's own reason panel read "standing decision for this business
model" -- the CLASS PRIOR -- with the evidence reason absent.

It was not a calibration problem. project44's own attested pages carry NINE
distinct supply-chain terms (carrier, freight, logistics, port, procurement,
shipment, supply chain, tariff, customs), which scores 7 against a class prior
of 5 and wins comfortably.

THE TEXT NEVER REACHED THE SCORER. `_canonical_selection` passes
`evidence_text` and `published_text` to `select`, and that is the path
`/history` uses. The X-Ray renders `decision_synthesis.compose` ->
`_select`, which called `select` with name, facts and registrant ONLY.

TWO COMPOSERS, AND THE FIELD WENT TO THE OTHER ONE -- the same shape as
`grounded_in` and `adversary` before it, and the third time this product has
shipped a repair into one of two objects that both reach the page. So the seam
is pinned here rather than left to be noticed again: a defaulted parameter and
a caller that never supplies it is indistinguishable from a feature that was
never built.
"""
from __future__ import annotations

import inspect

from intent_engine.executive import decision_synthesis as DS


def test_compose_accepts_the_subject_s_own_record():
    params = inspect.signature(DS.compose).parameters
    assert "evidence_text" in params and "published_text" in params, (
        "compose cannot be given the company's own record, so the X-Ray's "
        "decision can only ever be ordered by the business model class")


def test_compose_forwards_the_record_to_the_selector():
    """A parameter accepted and dropped is the same as one never added."""
    src = inspect.getsource(DS.compose)
    assert "evidence_text=evidence_text" in src, src[-600:]
    assert "published_text=published_text" in src


def test_the_selector_hands_it_to_analysis_selection():
    src = inspect.getsource(DS._select)
    # BOTH branches: `_select` calls `select` twice -- once to see whether the
    # dossier's own resolution is known, once with the canonical profile. A
    # repair that reached only one of them fires for public companies and not
    # for private ones, which is backwards.
    assert src.count("evidence_text=evidence_text") == 2, (
        "only one of the two selection branches carries the company's own "
        "record, so which companies get an evidence-led decision depends on "
        "whether their profile resolved from the dossier")
    assert src.count("published_text=published_text") == 2


def test_the_xray_supplies_it():
    """THE CALL SITE. Every assertion above passes with an X-Ray that never
    supplies the text -- which is exactly the state this test was written
    from, on a deployed build, with a green suite."""
    from intent_engine.webapp import app as A
    src = inspect.getsource(A.WebApp._run_xray)
    assert "_canonical_profile_inputs" in src, (
        "the X-Ray composes a decision without the run's own record, so the "
        "class prior orders the menu for every privately held company")
    read = inspect.getsource(A.WebApp._executive_read)
    assert "evidence_text=own.get" in read and "published_text=own.get" in read


def test_the_dossier_facts_still_belong_to_the_dossier():
    """WHAT MUST NOT CHANGE. An earlier repair passed the whole SELECTION
    across this seam and the live X-Ray and the dossier X-Ray began asking
    two different questions about one company, because the archetype is
    scored from the DOSSIER's RecordFacts. The text is an ordering INPUT --
    the same shape as `registrant`, which already crosses here -- and the
    facts stay where they are."""
    src = inspect.getsource(DS._select)
    # COUNTED, NOT MERELY PRESENT. `_select` calls `select` twice, and an
    # assertion that the string appears SOMEWHERE stays green when one branch
    # loses it -- a break proof caught exactly that and reported NOT_CAUGHT,
    # which was true of the test rather than of the guard.
    assert src.count("facts=_facts(dossier, hidden)") == 2, (
        f"the selection scores against the dossier's own facts in only "
        f"{src.count('facts=_facts(dossier, hidden)')} of its two branches")
    compose_src = inspect.getsource(DS.compose)
    assert "selection = _select(dossier, hidden, registrant" in compose_src
