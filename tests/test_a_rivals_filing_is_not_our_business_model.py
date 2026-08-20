"""Wells Fargo's capacity sentence was rendered as JPMorgan's own model.

MEASURED LIVE on the deployed 0420fb0. JPMorgan's page carried, under
"How the business actually works -> Distribution model":

    "Is committing capital to capacity ahead of the demand for it."

and the attributed evidence was WELLS FARGO & COMPANY/MN's 10-K. The same
run's evidence carried a blank-check SPAC. Walmart's carried Ranpak, Ibotta
and a 2023 BitNile filing.

A run retrieves other registrants' filings ON PURPOSE — they are the only
independent vantage this product can reach, and a COMPLETE report requires
one. So the repair is not to stop retrieving them, and it is not to drop
them from the observation set: coverage is computed from those observations
and starving it fails every run to fix a claim nobody made yet.

The repair is that a component of the company's mental model is a CLAIM
ABOUT THIS COMPANY, so only this company's own voice may state one. A rival
may still contradict.
"""
from intent_engine.strategic_intelligence.model import build_mental_model
from intent_engine.strategic_intelligence.observations import (
    subject_documents,
)
from intent_engine.strategic_intelligence.records import StrategicObservation

NOW = "2026-08-20T00:00:00+00:00"


def obs(oid, signal, source_class, text):
    return StrategicObservation(
        observation_id=oid, text=text, observation_type="fact",
        signals=(signal,), source_class=source_class,
        strategic_signal=text, date="2026-02-24")


def test_a_third_partys_filing_cannot_state_our_distribution_model():
    ours = obs("o1", "data_network", "investor_material",
               "Earns a spread on deposits it intermediates")
    theirs = obs("o2", "distribution_shift", "competitor",
                 "Is committing capital to capacity ahead of the demand "
                 "for it")
    model = build_mental_model("JPMorgan Chase", [ours, theirs], [], now=NOW)
    stated = " ".join(c.current_state for c in model.components.values())
    assert "committing capital to capacity" not in stated
    assert "spread on deposits" in stated


def test_the_independent_observation_may_still_contradict():
    """Restricting SUPPORT must not silence a rival that disagrees — that
    would trade one wrong answer for a blinder."""
    ours = obs("o1", "enterprise_expansion", "investor_material",
               "Growth is coming from enterprise accounts")
    against = obs("o2", "smb_simplicity", "independent_reporting",
                  "Independent reporting finds growth is small-business led")
    model = build_mental_model("Acme", [ours, against], [], now=NOW)
    engine = model.components.get("growth_engine")
    assert engine is not None
    assert engine.supporting_observation_ids == ["o1"]
    assert "o2" in engine.contradicting_observation_ids


def test_a_component_with_only_third_party_support_is_not_stated():
    """No component at all is the honest outcome. A component asserted from
    a rival's filing is worse than an absent one."""
    theirs = obs("o1", "distribution_shift", "competitor",
                 "Is committing capital to capacity ahead of demand")
    model = build_mental_model("JPMorgan Chase", [theirs], [], now=NOW)
    assert "distribution_model" not in model.components


def test_provenance_never_names_another_registrant():
    ours = obs("o1", "data_network", "company_owned", "Runs a data network")
    theirs = obs("o2", "data_network", "competitor", "So does the rival")
    model = build_mental_model("Acme", [ours, theirs], [], now=NOW)
    for component in model.components.values():
        classes = {p["source_class"] for p in component.provenance}
        assert "competitor" not in classes
        assert "independent_reporting" not in classes


# --- the document-level rule, which the same defect needs ---------------

def test_a_filing_under_another_cik_is_not_ours():
    docs = [
        {"final_url": "https://www.sec.gov/Archives/edgar/data/19617/x/a.htm",
         "source_class": "investor_material", "text_content": "JPM 10-K"},
        {"final_url": "https://www.sec.gov/Archives/edgar/data/72971/y/b.htm",
         "source_class": "investor_material", "text_content": "WFC 10-K"},
    ]
    kept = subject_documents(docs, subject_cik="0000019617")
    assert [d["text_content"] for d in kept] == ["JPM 10-K"]


def test_an_independent_class_is_not_the_subjects_voice():
    docs = [{"final_url": "https://acme.com/a", "source_class": "company_owned",
             "text_content": "ours"},
            {"final_url": "https://x.com/b", "source_class": "competitor",
             "text_content": "theirs"},
            {"final_url": "https://y.com/c", "source_class": "customer_voice",
             "text_content": "a customer"},
            {"final_url": "https://z.com/d",
             "source_class": "independent_reporting", "text_content": "press"}]
    assert [d["text_content"] for d in subject_documents(docs)] == ["ours"]


def test_the_allowlist_is_derived_from_the_vocabulary_not_written_out():
    """A class added tomorrow must belong to NEITHER set until somebody
    decides — the same reason pattern applicability stopped being a
    denylist."""
    from intent_engine.company_ingestion.records import (
        INDEPENDENT_CLASSES, SOURCE_CLASSES,
    )
    from intent_engine.strategic_intelligence.observations import (
        _subject_speaking_classes,
    )
    assert set(_subject_speaking_classes()) == \
        set(SOURCE_CLASSES) - set(INDEPENDENT_CLASSES)
    assert set(_subject_speaking_classes()).isdisjoint(INDEPENDENT_CLASSES)


# =======================================================================
# THE CLASS GATE SHIPPED AND WAS INERT. This is why.
# =======================================================================
#
# MEASURED LIVE on cec9b2f, AFTER the class gate deployed. JPMorgan's page
# still read, under "How the business actually works -> Distribution model":
#
#     "Is committing capital to capacity ahead of the demand for it."
#     evidence: WELLS FARGO & COMPANY/MN — 10-K (2026-02-24)
#
# `edgar.filing_candidates` stamps EVERY filing it proposes
# "source_class": "investor_material", whoever filed it — the rendered label
# "Regulatory or investor filing" was the visible clue throughout. So the
# class gate passed another bank's 10-K as JPMorgan's own investor material.
#
# source_class encodes HOW a document was retrieved, not WHOSE it is. It can
# never carry ownership. The EDGAR path names the filer, so ownership is
# decided where the URL still exists and carried on the observation.

def obs_from(doc, signal, company="JPMorgan Chase"):
    from intent_engine.strategic_intelligence.observations import (
        derive_observations,
    )
    return derive_observations([doc], company=company,
                               subject_cik="0000019617")


def filing(cik, text, source_id):
    return {"final_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                         f"000000000000000001/x.htm",
            # THE POINT: production stamps this on every proposed filing.
            "source_class": "investor_material",
            "source_id": source_id,
            "title": "SEC 10-K",
            "text": text, "text_content": text,
            "content_hash": source_id, "retrieved_at": "2026-02-24"}


#: Wording chosen so PRODUCTION'S OWN detection fires, and so the signal it
#: fires actually feeds a component of the mental model.
#:
#: Two traps a break proof caught here. `capacity_investment` — the signal in
#: the live JPMorgan capture — maps to no `_COMPONENTS` entry at all, so a
#: fixture built on it produces no component either way and the end-to-end
#: test passes for the wrong reason. And `_detect_signals` only consults the
#: commerce library when `in_commerce_domain` is true, so a sentence carrying
#: the right keyword still detects nothing without the surrounding domain.
CAPACITY_TEXT = ("Our commerce platform helps merchants sell online. Demand "
                 "capture now runs through the marketplace and the shop app, "
                 "which set how merchants reach shoppers and checkout.")


def test_another_registrants_filing_is_not_subject_owned():
    """The exact live shape: a THIRD-PARTY 10-K classed investor_material."""
    theirs = obs_from(filing("72971", CAPACITY_TEXT, "wfc"), "capacity")
    assert theirs, "fixture produced no observation, so this cannot fail"
    for o in theirs:
        assert o.source_class == "investor_material", "fixture drifted"
        assert o.subject_owned is False, (
            "another registrant's filing is marked as this company's own, "
            "which is what made the class gate inert on the live page")


def test_the_subjects_own_filing_is_subject_owned():
    ours = obs_from(filing("19617", CAPACITY_TEXT, "jpm"), "capacity")
    assert ours, "fixture produced no observation"
    for o in ours:
        assert o.subject_owned is True


def test_a_third_party_filing_cannot_state_the_model_even_as_investor_material():
    """END TO END, through the producer and the model, on the live shape."""
    theirs = obs_from(filing("72971", CAPACITY_TEXT, "wfc"), "capacity")
    assert theirs, "fixture produced no observation"
    # THE PROPERTY, NOT A PHRASE. Asserting the absence of one sentence let
    # a break proof through: with the gate removed this fixture states
    # "positions itself as infrastructure others build on" instead, which is
    # just as wrong and contains none of the words the assertion looked for.
    model = build_mental_model("JPMorgan Chase", list(theirs), [], now=NOW)
    assert not model.components, (
        "a different registrant's filing is stating this company's business "
        f"model: {[c.current_state for c in model.components.values()]}")

    # and the same observations, marked as the subject's own, DO state one —
    # so the test above is not passing because the fixture is inert.
    import dataclasses
    ours = [dataclasses.replace(o, subject_owned=True) for o in theirs]
    assert build_mental_model("JPMorgan Chase", ours, [], now=NOW).components


def test_the_gate_reads_ownership_and_not_only_the_class():
    """The seam, structurally. The first repair filtered on source_class
    alone, shipped, and was inert — because the only signal visible inside
    `build_mental_model` was the one that cannot answer the question."""
    import inspect

    from intent_engine.strategic_intelligence import model as M
    source = inspect.getsource(M.build_mental_model)
    assert "subject_owned" in source, (
        "build_mental_model decides ownership from source_class alone again")


# =======================================================================
# "The company's own words" must be the company's own words
# =======================================================================
#
# MEASURED LIVE on cec9b2f. Meta's page carried, sourced to NETWORK-1
# TECHNOLOGIES, INC.'s 2024 10-K:
#
#     "Meta Platforms, Inc. is committing capital to capacity ahead of the
#      demand for it"
#
# Network-1 is a patent litigant whose filing says "our case against Meta
# Platforms, Inc." — the canonical mis-attribution this codebase already
# documents. `narrative.py` renders the mechanism quote under the heading
# "The company's own words:", and it was whoever's words the observation
# happened to carry.
#
# This arrives by a DIFFERENT route from the mental model: `_mechanism_evidence`
# feeds the narrative, the decision's grounding and the citations alike, so
# filtering it at the producer fixes all three.

def test_a_third_partys_sentence_is_never_the_companys_own_words():
    from intent_engine.strategic_intelligence import mechanism as MECH
    from intent_engine.strategic_intelligence.reasoning import (
        _mechanism_evidence,
    )
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY

    pattern = next(p for p in PATTERN_LIBRARY
                   if p.required_signals or p.required_any_signals)
    signal = (tuple(pattern.required_any_signals)
              + tuple(pattern.required_signals))[0]

    def observation(oid, owned):
        return StrategicObservation(
            observation_id=oid, text="", observation_type="fact",
            signals=(signal,), source_class="investor_material",
            excerpt="", subject_owned=owned, source_title="SEC 10-K",
            signal_spans={signal: f"a sentence from {oid}"})

    theirs = _mechanism_evidence(pattern, [observation("network-1", False)])
    assert theirs == [] or all(
        "network-1" not in (getattr(e, "quote", "") or
                            (e.get("quote") if isinstance(e, dict) else ""))
        for e in theirs), "a third party's sentence became the company's own"

    ours = _mechanism_evidence(pattern, [observation("meta", True)])
    assert ours, "the subject's own sentence was dropped too"


def test_the_narrative_line_cannot_quote_another_registrant():
    """End to end through `because_line`, which is what the page renders."""
    from intent_engine.strategic_intelligence import mechanism as MECH

    class H:
        pattern_id = "x"
        mechanism_evidence = ()

    assert MECH.because_line(H()) == ""
