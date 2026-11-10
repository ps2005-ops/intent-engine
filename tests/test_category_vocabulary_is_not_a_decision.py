"""A page that mentions a subject is not a company facing a decision (§P1-3).

WHAT THIS PINS
--------------
MEASURED across cohort A on 8495b00c. Three unrelated companies -- a
supply-chain planning vendor, an event-intelligence firm and a storage vendor
-- all received the same central question, "how the product is sold, and by
whom", because their pages carry "go-to-market" and "channel partner". Those
two phrases are on almost every B2B page ever published, and two hits of them
were enough to move SALES_MOTION above the class prior.

That is the ORIGINAL defect at a finer grain. The class prior handing every
software company the pricing question was replaced by category vocabulary
handing three of them the sales question, which is a new universal heuristic
rather than a company's own record speaking.

AND THE MATCH WAS A SUBSTRING. "support" and "reporting" contain "port", so
Cohesity's own page told the reader its record discusses "logistics, port,
supply chain" -- a term that does not appear in it as a word. "industrial"
contains "trial" the same way, and "free trial" is on every SaaS site. A
false term is a false statement about a company's record, and it also
inflated the hit count that decides which decision wins.

So two rules, pinned together because each is reachable only if the other
holds: a phrase must be DECISION-BEARING, and it must match as a WORD.
"""
from __future__ import annotations

from intent_engine.executive.analysis_selection import (
    _ARCHETYPE_EVIDENCE, _EVIDENCE_MIN_HITS, _evidence_archetypes,
    _evidence_bonus, _says,
)

#: An ordinary enterprise-software page. Every phrase in it is real marketing
#: copy, and NONE of it is a company telling us what it is deciding.
GENERIC_B2B = (
    "Start your free trial today. Our platform offers enterprise support and "
    "detailed reporting across your portfolio. We are SOC2 certified, GDPR "
    "compliant and meet HIPAA requirements; see our compliance and "
    "regulation pages for every regulatory certification. Our "
    "go-to-market motion includes "
    "channel partners and a partner program with resellers. See our roadmap "
    "and packaging options, now available. Industrial customers rely on us. "
    "Compare us versus the competitor alternatives. We serve mid-market and "
    "enterprise segment target customers. " * 4)

FREIGHT_RECORD = (
    "Our network connects shippers and carriers. We track every shipment "
    "across freight modes, manage customs and tariff exposure, and give "
    "procurement teams supply chain visibility with accurate lead time "
    "estimates from each supplier. " * 4)

CHANNEL_RECORD = (
    "We are shifting to a partner-led route to market. Channel conflict with "
    "our direct sales force is managed by quota capacity rules, and reseller "
    "margin is set so partner concentration stays bounded. Customer "
    "acquisition cost and payback period both improved. " * 4)

PRICING_RECORD = (
    "We announced a price increase this year and moved to consumption "
    "pricing. Discounting is now governed centrally and our pricing model is "
    "published, with per-seat plans retired for new customers. " * 4)


# --- the negative control, which is the whole point --------------------------

def test_an_ordinary_b2b_page_shows_no_decision_at_all():
    """Category vocabulary alone may not manufacture decision specificity."""
    assert _evidence_archetypes(GENERIC_B2B) == {}


def test_the_generic_page_is_long_enough_to_have_fired():
    """A negative control that passes by being too short proves nothing."""
    assert len(" ".join(GENERIC_B2B.split())) > 200
    # And it really does contain the words that used to fire.
    for phrase in ("go-to-market", "channel partner", "partner program",
                   "roadmap", "packaging", "compliance", "free trial",
                   "competitor", "we serve"):
        assert phrase in GENERIC_B2B.lower()


# --- the positive controls, one per repaired entry ---------------------------

def test_a_freight_record_still_reaches_supply_chain():
    shown = _evidence_archetypes(FREIGHT_RECORD)
    assert "SUPPLY_CHAIN" in shown
    hits, phrases = shown["SUPPLY_CHAIN"]
    assert hits >= 6, phrases
    assert _evidence_bonus(hits) > 5, "a whole record about freight must be "\
                                      "able to outrank a five-deep class menu"


def test_a_channel_dependence_record_still_reaches_sales_motion():
    """SALES_MOTION must stay REACHABLE for a company actually deciding it."""
    shown = _evidence_archetypes(CHANNEL_RECORD)
    assert "SALES_MOTION" in shown
    hits, phrases = shown["SALES_MOTION"]
    assert hits >= 5, phrases


def test_a_pricing_decision_record_still_reaches_pricing():
    shown = _evidence_archetypes(PRICING_RECORD)
    assert "PRICING" in shown


# --- the word boundary ------------------------------------------------------

def test_one_word_is_not_counted_as_two_phrases():
    """Overlapping phrases must not let one mention clear the two-hit gate.

    "displaced" contains "displace", and "phase iii" contains "phase ii". On
    a substring match a single word scores as two distinct terms, which is
    the two-hit applicability gate defeating itself.
    """
    once = ("We displaced the incumbent vendor on this account and nothing "
            "else is published about how we compete. " * 6)
    assert "COMPETITIVE_RESPONSE" not in _evidence_archetypes(once)

    trial = ("Our phase iii programme continues and nothing else is "
             "published about our pipeline. " * 6)
    assert "R&D_ROADMAP" not in _evidence_archetypes(trial)


def test_support_does_not_become_a_seaport():
    text = ("Our platform serves logistics teams and supply chain operators. "
            "We offer enterprise support and detailed reporting. " * 8)
    hits, phrases = _evidence_archetypes(text)["SUPPLY_CHAIN"]
    assert "port" not in phrases
    assert "seaport" not in phrases
    assert hits == 2, phrases


def test_industrial_does_not_become_a_clinical_trial():
    text = ("We serve industrial customers with research and development "
            "teams who need portfolio reporting. " * 8)
    assert "R&D_ROADMAP" not in _evidence_archetypes(text)


def test_a_free_trial_is_not_a_development_programme():
    text = ("Start your free trial. Our trial includes full support. " * 10)
    assert _evidence_archetypes(text) == {}


def test_says_matches_words_and_not_fragments():
    assert _says("we use a seaport for every shipment", "seaport")
    assert not _says("our support team reports weekly", "port")
    assert not _says("an industrial customer", "trial")
    # A phrase carrying punctuation still matches as its own words.
    assert _says("we moved to a partner-led model", "partner-led")
    assert _says("our go-to-market motion changed", "go-to-market")
    assert not _says("go-to-marketing is different", "go-to-market")


# --- the class prior must survive, which §2 asked for explicitly ------------

def test_a_record_with_nothing_to_say_leaves_the_class_prior_standing():
    """An evidence-poor company keeps the class prior. That is correct."""
    assert _evidence_archetypes("") == {}
    assert _evidence_archetypes("Home. About. Contact.") == {}


def test_one_decision_bearing_phrase_is_still_a_coincidence():
    text = ("We announced a price increase this year and nothing else is "
            "published about how we are paid. " * 6)
    shown = _evidence_archetypes(text)
    assert "PRICING" not in shown, "one phrase must not reorder the menu"
    assert _EVIDENCE_MIN_HITS == 2


# --- the rule itself, asserted over the whole table -------------------------

#: Words that name a SUBJECT rather than a decision. Any of these standing
#: alone as a phrase means the table has drifted back toward topic-matching.
_CATEGORY_ONLY = frozenset({
    "regulation", "regulatory", "compliance", "gdpr", "hipaa", "roadmap",
    "packaging", "bundled", "now available", "we serve", "target customer",
    "ideal customer", "competitor", "versus", "compared to", "trial",
    "clinical", "port", "throughput", "provisioning", "data center",
    "data centre", "raised", "investment in", "go-to-market",
    "channel partner", "partner program", "partner programme", "reseller",
    "sales motion", "self-serve", "product-led growth", "utilisation",
    "utilization",
})


def test_no_entry_in_the_table_is_bare_category_vocabulary():
    """The rule, applied to every entry rather than to the one that failed.

    A phrase list is a pattern library, and a library entry needs an
    applicability. Checking only SALES_MOTION would leave the next entry to
    be found by a cohort.
    """
    offenders = {
        archetype: sorted(p for p in phrases if p in _CATEGORY_ONLY)
        for archetype, phrases in _ARCHETYPE_EVIDENCE.items()
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert offenders == {}, offenders


# --- the boundary may not cost the run -------------------------------------

def test_the_word_boundary_is_prefiltered_by_a_substring_test():
    """Correctness that costs three seconds is a different defect.

    MEASURED on a 0.79MB record with the full table: substring 43ms/MB,
    bounded 1381ms/MB. `select` runs on up to 200KB of a company's own text
    and composes twice per run, so the naive boundary added seconds to CORE
    to remove a false term. A phrase cannot match as a word unless it matches
    as a substring, so the cheap test decides the ~90% that miss.

    Asserted structurally rather than by a stopwatch: a wall-clock threshold
    on a shared runner is a flake, and what must not regress here is the
    ORDER of the two tests, which is a property of the code.
    """
    import inspect

    src = inspect.getsource(_says)
    assert "if phrase not in text" in src, (
        "the boundary regex runs before the engine pays for the substring "
        "prefilter, so every phrase pays for the engine on every call")
    cheap = src.index("if phrase not in text")
    regex = src.index("re.compile")
    assert cheap < regex, (
        "the boundary regex runs before the substring prefilter, so every "
        "phrase pays for the engine on every call")
    assert "return False" in src[cheap:regex]


def test_the_prefilter_does_not_change_a_single_answer():
    """The optimisation is only allowed if it is an identity.

    Re-implements the unprefiltered semantics here and requires agreement on
    the cases that distinguish them -- a fragment inside a longer word, a
    phrase carrying punctuation, and an overlapping pair.
    """
    import re as _re

    def unprefiltered(text, phrase):
        return bool(_re.compile(r"(?<![0-9a-z])" + _re.escape(phrase)
                                + r"(?![0-9a-z])").search(text))

    cases = [
        ("our support team reports weekly", "port"),
        ("we use a seaport", "seaport"),
        ("an industrial customer", "trial"),
        ("our phase iii programme", "phase ii"),
        ("our phase iii programme", "phase iii"),
        ("we displaced the incumbent", "displace"),
        ("we displaced the incumbent", "displaced"),
        ("a partner-led route to market", "partner-led"),
        ("go-to-marketing is different", "go-to-market"),
        ("", "logistics"),
    ]
    for text, phrase in cases:
        assert _says(text, phrase) == unprefiltered(text, phrase), \
            (text, phrase)
