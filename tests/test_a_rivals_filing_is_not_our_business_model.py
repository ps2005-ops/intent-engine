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
