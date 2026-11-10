"""Everyone uses AWS. Almost nobody says they depend on it."""
from __future__ import annotations

from intent_engine.market import dependencies as DEP

FILING = (
    # A dependency needs a NAMED party. "a single supplier" names nobody,
    # and an edge to nobody connects nothing while looking like one.
    "We rely on Fabrinet as a single source supplier for the optical "
    "components used in our network hardware, and a disruption would have a "
    "material adverse effect on our ability to deliver service. "
    "Our platform runs on Amazon Web Services across three regions. "
    "We purchase transit capacity from Lumen Technologies under a multi-year "
    "agreement. "
    "The company was founded in 2009 and serves customers worldwide."
)


# --- the distinction ------------------------------------------------------

def test_running_on_a_platform_is_use_not_dependency():
    kind, _ = DEP.classify("Our platform runs on Amazon Web Services.")
    assert kind == DEP.USES


def test_purchasing_is_a_trade_relation_not_a_dependency():
    kind, _ = DEP.classify(
        "We purchase transit capacity from Lumen Technologies.")
    assert kind == DEP.BUYS_FROM


def test_a_stated_materiality_makes_it_a_dependency():
    kind, span = DEP.classify(
        "We rely on a single supplier for optical components, and a "
        "disruption would have a material adverse effect.")
    assert kind == DEP.DEPENDS_ON
    assert span


def test_materiality_beats_usage_in_the_same_sentence():
    """A sentence carrying both is a dependency; one carrying only "uses" is
    not, however important the named party is."""
    kind, _ = DEP.classify(
        "We use a single source supplier for this component and have no "
        "readily available substitute.")
    assert kind == DEP.DEPENDS_ON


# --- extraction over a filing ---------------------------------------------

def test_the_filing_yields_one_dependency_and_one_purchase():
    found, refused = DEP.extract(FILING, subject="Cloudflare",
                                 source="https://sec.gov/x",
                                 observed_at="2026-08-08")
    kinds = {c.kind for c in found}
    assert DEP.DEPENDS_ON in kinds
    assert DEP.BUYS_FROM in kinds
    got = DEP.summarise(found)
    assert got["dependencies"] == 1


def test_a_dependency_sentence_naming_nobody_is_refused():
    """"We rely on a single supplier" names nobody, and an edge to nobody
    connects nothing while looking exactly like one that does."""
    found, refused = DEP.extract(
        "We rely on a single supplier for certain critical components and "
        "have no readily available substitute for them.",
        subject="Cloudflare", source="s")
    assert not [c for c in found if c.kind == DEP.DEPENDS_ON]
    assert refused.get("names_no_counterparty", 0) >= 1


def test_the_subject_is_never_its_own_counterparty():
    found, _ = DEP.extract(
        "Cloudflare relies on a single source supplier, Cloudflare Inc, "
        "with no readily available substitute.",
        subject="Cloudflare", source="s")
    assert all("cloudflare" not in c.counterparty.lower() for c in found)


def test_nothing_is_inferred_from_sector_knowledge():
    """"Semiconductor firms depend on ASML" is true and is not evidence."""
    found, _ = DEP.extract(
        "The company designs advanced semiconductor products for global "
        "customers in many markets.", subject="Nvidia", source="s")
    assert found == ()


def test_the_dependency_carries_the_span_that_made_it_one():
    found, _ = DEP.extract(FILING, subject="Cloudflare", source="s")
    dep = next(c for c in found if c.kind == DEP.DEPENDS_ON)
    assert dep.materiality_span
    assert dep.materiality_span.lower() in dep.evidence_span.lower()


def test_the_same_relation_twice_in_one_document_is_one_claim():
    text = FILING + " " + FILING
    found, refused = DEP.extract(text, subject="Cloudflare", source="s")
    assert refused.get("duplicate_in_document", 0) >= 1
    keys = [(c.subject, c.kind, c.counterparty) for c in found]
    assert len(keys) == len(set(keys))


def test_the_summary_names_why_dependency_is_strict():
    got = DEP.summarise([])
    assert "everyone depends on everyone" in got["note"]


def test_a_lone_sentence_opening_capital_is_not_a_supplier():
    """Live: "Fast-growing stir-fry concept leverages Olo Pay" offered
    "Fast-growing" as the counterparty. Third module to meet this shape."""
    found, _ = DEP.extract(
        "Fast-growing stir-fry concept leverages Olo Pay to simplify "
        "payments across its restaurants.",
        subject="Olo", source="s")
    assert all("fast-growing" not in c.counterparty.lower() for c in found)


def test_a_multi_word_opener_can_still_be_a_company():
    """"Amazon Web Services announced" opens the sentence and is a name."""
    assert "Amazon Web Services" in DEP._named_parties(
        "Amazon Web Services supplies the company with compute capacity.",
        "Cloudflare")
