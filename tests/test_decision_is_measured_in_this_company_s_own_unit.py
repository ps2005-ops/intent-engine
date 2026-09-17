"""The decision question must be measured in THIS company's terms, or say so.

WHAT THIS PINS, AND WHY IT IS WORTH PINNING
-------------------------------------------
On the frozen 40-company qualification (`db6946fa`), 33 companies reached a
decision and produced FOUR distinct decision questions between them. Twenty-
two received one byte-identical string, because the question's variable slots
came from `_ECONOMICS[business_model_class]` -- a table keyed on the class --
and every subscription software business shares
`primary_revenue_drivers[0] == "customer count"`.

Every test below fails on that build. Each one states a property in English
rather than pinning a constant, because a test that pins the string it is
meant to be protecting cannot tell a repair from a regression.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import decision_object as DO
from intent_engine.executive import strategic_delta as SD
from intent_engine.executive.analysis_selection import select

_SUBSCRIPTION = ("We sell software on an annual subscription and recognise "
                 "revenue ratably over the contract term.")


def _run(name, text):
    body = f"{text} {_SUBSCRIPTION}"
    return select(name=name, published_text=body, evidence_text=body)


# --- the slot the company filled -------------------------------------------

def test_a_stated_billing_unit_reaches_the_decision_question():
    """A company that says what it charges for is asked about THAT."""
    sel = _run("Axonius", "Pricing is based on the number of managed devices.")
    assert "managed devices" in sel.decision_question, (
        "the company published what it charges for and the question did not "
        f"use it: {sel.decision_question!r}")
    assert "customer count" not in sel.decision_question, (
        "the class-prior unit survived beside the company's own unit")


def test_two_companies_with_different_units_get_different_questions():
    """The collapse this closes is two companies sharing one question."""
    a = _run("Cribl", "Our pricing is based on data volume ingested.")
    b = _run("Huntress", "Huntress is priced per managed endpoint.")
    assert a.decision_question != b.decision_question, (
        "two companies that charge for different things received one "
        f"question: {a.decision_question!r}")


def test_an_unread_company_keeps_the_class_prior_and_says_that_it_did():
    """Falling back is fine. Falling back silently is the defect."""
    sel = _run("Opaque Co", "We provide innovative solutions for the modern "
                            "enterprise and we are a leader in our field.")
    basis = sel.question_basis
    assert basis["billing_unit_state"] == DO.NOT_ESTABLISHED
    assert not basis["slots_from_company"], (
        "nothing was established, so no slot may be claimed as the "
        "company's own")
    assert "not from this company" in basis["why"], (
        f"the fallback was silent: {basis['why']!r}")


# --- the subject rule -------------------------------------------------------

def test_mentioning_a_thing_is_not_depending_on_it():
    """project44's lesson: a logistics vendor does not face a freight problem.

    A page ABOUT carriers is not a company saying it depends on carriers, and
    reading it as one is the subject/object confusion that made all three
    positive controls `EVIDENCE_LED` for the wrong reason.
    """
    obj = DO.build(
        company="Freightwatch",
        published_text=("Carriers depend on freight capacity. Supply chains "
                        "rely on lead times holding. Shippers depend on "
                        "customs clearance."))
    assert not obj.dependencies, (
        "a dependency was read from a sentence whose subject is somebody "
        f"else: {[d.value for d in obj.dependencies]}")


def test_a_first_person_dependency_is_read():
    """The same rule must still admit the company speaking for itself."""
    obj = DO.build(company="Obsidian",
                   published_text="We rely on API access from SaaS vendors.")
    assert obj.dependencies, "a first-party dependency statement was refused"
    assert "API access" in obj.dependencies[0].value


def test_the_company_name_as_subject_works_for_multi_word_names():
    """Single- and multi-word names must behave the same.

    A name pattern built from the first token only meant `arctic` had to be
    followed immediately by the verb, so every multi-word company silently
    failed the subject rule while single-word ones passed.
    """
    obj = DO.build(company="Arctic Wolf",
                   published_text="Arctic Wolf serves mid-market credit unions.")
    assert obj.buyer.known, f"multi-word subject failed: {obj.buyer.reason}"


# --- grounding: the name-swap test -----------------------------------------

def test_a_reading_built_only_from_the_class_prior_is_name_only():
    """NAME_ONLY must be REACHABLE, or the gate cannot fail."""
    sel = _run("Opaque Co", "We provide innovative solutions.")
    assert sel.delta.grounding.verdict == SD.NAME_ONLY, (
        "a reading with nothing of the company's own in it was not flagged: "
        f"{sel.delta.grounding.verdict}")


def test_a_reading_built_from_the_company_s_own_words_is_grounded():
    sel = _run("Verkada", "Verkada is priced per camera.")
    assert sel.delta.grounding.verdict == SD.GROUNDED
    assert sel.delta.grounding.grounds, "GROUNDED with no named ground"


def test_grounding_does_not_count_the_company_name_as_a_ground():
    """A name is an identity, never evidence.

    Without this the test above passes for every company, because every
    question begins "For <Company>:".
    """
    g = SD.ground("For Acme: what to charge, and for what?", company="Acme",
                  decision_object=DO.DecisionObject(company="Acme"))
    assert g.verdict != SD.GROUNDED


# --- strategic delta --------------------------------------------------------

def test_reframed_is_distinguished_from_no_change():
    """Same decision, different measure, is a real and separate outcome."""
    reframed = _run("Procore", "Pricing is based on annual construction "
                               "volume.")
    unchanged = _run("Opaque Co", "We provide innovative solutions.")
    assert reframed.delta.change_type == SD.REFRAMED
    assert unchanged.delta.change_type == SD.NO_CHANGE


def test_the_delta_comparator_is_a_real_second_reading():
    """Comparing against a placeholder measures the placeholder."""
    sel = _run("Procore", "Pricing is based on annual construction volume.")
    assert sel.delta.prior_question, "no prior reading was produced"
    assert sel.delta.prior_question != sel.delta.final_question
    assert "For Procore" in sel.delta.prior_question, (
        "the comparator is not the same builder run on the same company")


# --- information priority ---------------------------------------------------

def test_an_ungrounded_reading_names_what_would_have_to_be_learned():
    """A good abstention tells an executive what to find out."""
    sel = _run("Opaque Co", "We provide innovative solutions.")
    assert sel.information_priorities, (
        "nothing was established and nothing was asked for")
    assert any(p.expected_information_value == "HIGH"
               for p in sel.information_priorities)


def test_a_grounded_reading_does_not_ask_for_what_it_already_has():
    sel = _run("Verkada", "Verkada is priced per camera.")
    asked = " ".join(p.question for p in sel.information_priorities)
    assert "what is one unit of its revenue counted in" not in asked, (
        "the reading asked for a fact it had already established")


# --- what must NOT come back ------------------------------------------------

def test_marketing_adjectives_do_not_become_a_buyer():
    """"Built for the best experience" is a promise about a website."""
    obj = DO.build(company="Anyco",
                   published_text=("Built for the best experience on every "
                                   "device. Trusted by thousands."))
    assert not obj.buyer.known, f"marketing copy became a buyer: {obj.buyer.value!r}"


def test_a_buyer_that_names_everybody_is_refused():
    obj = DO.build(company="Anyco",
                   published_text="Anyco is built for businesses of all sizes.")
    assert not obj.buyer.known, (
        f"'businesses' was accepted as a buyer: {obj.buyer.value!r}")


def test_page_furniture_is_not_evidence():
    obj = DO.build(company="Anyco",
                   published_text=("Sign up for our newsletter. This site uses "
                                   "cookies. Built for enterprise customers "
                                   "who value privacy policy compliance."))
    assert not obj.buyer.known


@pytest.mark.parametrize("name,text", [
    ("Anyco", ""),
    ("Anyco", "short"),
    ("", "Pricing is based on seats."),
])
def test_extraction_never_raises(name, text):
    """A slot that cannot be established is an answer, not an exception."""
    obj = DO.build(company=name, published_text=text)
    assert obj.contract == DO.CONTRACT


# --- found live, on the deployed service ------------------------------------
#
# Everything below failed on a9ca9f8c against a real page. They are kept
# apart from the offline cases above because the offline fixtures could not
# have produced them: the defects needed a real company's real prose.

def test_a_buyer_is_not_read_from_a_sentence_about_somebody_else():
    """MEASURED LIVE on Arctic Wolf.

    Its threat-research post about the Karakurt and Conti ransomware gangs
    says "... the tools and infrastructure used by the rest of the group".
    The product read "rest of the group" as who Arctic Wolf sells to, put it
    in the central decision question, and marked the reading GROUNDED on it
    -- a fabricated ground, which is worse than NAME_ONLY because it claims
    a company-specificity it does not have.

    "used by", "built for" and "designed for" describe SOMETHING. Which
    something is decided by the rest of the sentence, so the sentence must
    name this company.
    """
    obj = DO.build(company="Arctic Wolf", published_text=(
        "However Karakurt is being run, it no doubt gains some advantage "
        "with access to Conti resources such as access to victims or the "
        "tools and infrastructure used by the rest of the group."))
    assert not obj.buyer.known, (
        f"a buyer was read from a sentence about a ransomware gang: "
        f"{obj.buyer.value!r}")


def test_the_first_person_pattern_requires_word_boundaries():
    """"we" matched inside "ho-we-ver", so every sentence named the company.

    This is the defect underneath the one above: without boundaries the
    subject discipline is decorative, and it was decorative everywhere it
    was used -- including the dependency rules, whose test passed only
    because its fixtures happened to contain no "we", "our" or "us" as a
    substring.
    """
    import re
    pattern = re.compile(DO._subject_patterns("Acme"))
    for decoy in ("however", "resources", "versus", "housing", "answer",
                  "wetland", "trousers"):
        assert not pattern.search(decoy), (
            f"{decoy!r} was read as the company speaking in the first person")
    for real in ("we build", "our platform", "acme sells"):
        assert pattern.search(real), f"{real!r} was not recognised"


def test_an_anaphoric_phrase_is_not_a_buyer():
    """"the rest of the group" passes every word-level gate and names nobody.

    Defence in depth behind the subject rule: a sentence that DOES name the
    company can still contain one.
    """
    obj = DO.build(company="Acme", published_text=(
        "Acme is built for the rest of the group, and we serve them daily."))
    assert not obj.buyer.known, f"an anaphor became a buyer: {obj.buyer.value!r}"


def test_a_real_buyer_in_a_company_naming_sentence_still_reads():
    """The repair must not close the door it exists to keep open."""
    obj = DO.build(company="Arctic Wolf", published_text=(
        "Arctic Wolf is built for mid-market credit unions and regional "
        "banks, and we serve them daily."))
    assert obj.buyer.known, obj.buyer.reason
    assert "credit unions" in obj.buyer.value
