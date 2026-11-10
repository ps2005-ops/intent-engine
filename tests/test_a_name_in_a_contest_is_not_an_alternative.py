"""A named entity in a competitive sentence is not an economic alternative.

MEASURED LIVE ON THREE BATCH-A COMPANIES, then re-measured offline against
the same SEC filings:

    Meta        "contested most directly by S&P"
    Walmart     "contested most directly by ... Medicare Part D"
    Caterpillar "contested most directly by Alstom SA, America Leasing"

The spans that produced them, quoted from the filings:

    Meta        "the inclusion, exclusion, or deletion of our stock from any
                 trading indices, such as the S&P 500 Index"
    Walmart     "changes in the scope of or the elimination of Medicare Part D
                 or Medicaid drug programs"
    Caterpillar "Cat Financial's competitors include Wells Fargo Equipment
                 Finance Inc., Banc of America Leasing & Capital LLC, ..."

None of them says a customer could buy the named thing instead. Meta's blob
is 2,262 characters and fifteen bullets, with the word "competitors" five
bullets away from S&P; Walmart's is 2,677 characters and seventeen
semicolons; Caterpillar's names its CAPTIVE LENDER as the owner of the
contest, not itself.

THE TESTS BELOW ARE A MATRIX, NOT A DENY-LIST. Every false case is paired
with a true one that must survive, because a repair that empties the
competition section is not a repair (§11) — and the non-company alternatives
the ladder depends on (open source, the in-house build, doing nothing) are
legitimate competitive alternatives that a "must be a company" rule would
destroy.
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from intent_engine.executive import competitive_qualification as Q
from intent_engine.external_intel import competitor_contract as CC
from intent_engine.external_intel import competitor_finder as CF


# --- the measured spans, verbatim ------------------------------------------
META_INDEX = (
    "the inclusion, exclusion, or deletion of our stock from any trading "
    "indices, such as the S&P 500 Index;\n"
    "•media coverage of our business and financial performance")

WALMART_PROGRAM = (
    "changes in the scope of or the elimination of Medicare Part D or "
    "Medicaid drug programs; increased competition from other retail "
    "pharmacy operations including competitors offering online retail "
    "pharmacy options")

CAT_FINANCIAL = (
    "Cat Financial’s competitors include Wells Fargo Equipment Finance "
    "Inc., Banc of America Leasing & Capital LLC, BNP Paribas Leasing "
    "Solutions Limited, Australia and New Zealand Banking Group Limited, "
    "Société Générale S.A. and various other banks and "
    "finance companies.")

CAT_SUBSIDIARIES = (
    "In addition, many of the manufacturers that compete with Caterpillar "
    "also own financial subsidiaries, such as John Deere Capital "
    "Corporation, Komatsu Financial L.P., Volvo Financial Services and "
    "Kubota Credit Corporation, which utilize many below-market interest "
    "rate programs to support machine sales.")

CAT_CONSTRUCTION = (
    "Examples of global competitors include CASE (part of CNH Industrial "
    "N.V.), Deere Construction & Forestry (part of Deere & Company), Doosan "
    "Bobcat (Part of Doosan Group), Hitachi Construction Machinery Co., "
    "Ltd., Hyundai Heavy Industries Group.")

CAT_RAIL = (
    "In rail-related businesses, our global competitors include Wabtec Corp, "
    "Greenbrier Companies, Inc., Voestalpine AG, Vossloh AG, Alstom SA, and "
    "Siemens Mobility A/S.")

#: THE OWNER RULE ON ITS OWN. Nothing about "Acme Robotics" is an index, a
#: programme or a lender, so the only thing that can demote it is the
#: possessor of the verb — which is a subsidiary, not the company.
#: A CONTEST-BEARING BLOB WHOSE LAST CLAUSE IS NOT ABOUT COMPETING. This is
#: the Meta and Walmart shape with a plain company in the innocent clause, so
#: the clause test is the only rule that can refuse it.
NEIGHBOURING_CLAUSE = (
    "we face intense competition across every product line;\n"
    "•changes in fuel and freight rates, including the rates charged by "
    "Northwind Logistics Inc.")

SEGMENT_CONTEST = (
    "Orion Robotics’ competitors include Acme Robotics Inc. and Beta "
    "Machines Ltd. in the warehouse automation market.")

#: The negative control for the lender rule. A bank's rivals ARE banks and
#: the financier demotion must not reach them.
BANK_RIVALS = (
    "We compete with other banks and financial institutions, including "
    "Citizens Financial Group, Inc. and Regions Financial Corporation, for "
    "deposits and for lending relationships.")


def _q(candidate, evidence, subject, model=""):
    return Q.qualify(candidate=candidate, evidence=evidence, subject=subject,
                     business_model=model)


# ===========================================================================
# §9. THE VALIDATION MATRIX. Each row: state, allowed as a direct rival, and
# the wording a customer is allowed to be shown.
# ===========================================================================
@pytest.mark.parametrize("candidate,evidence,subject,model,state,direct", [
    # --- the three measured failures --------------------------------------
    ("S&P", META_INDEX, "Meta Platforms, Inc.", "ADVERTISING_PLATFORM",
     Q.INDEX_OR_BENCHMARK, False),
    ("Medicare Part D", WALMART_PROGRAM, "Walmart Inc.", "SCALE_RETAIL",
     Q.PROGRAM_OR_POLICY, False),
    ("Banc of America Leasing", CAT_FINANCIAL, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.FINANCIER_STATE, False),
    ("BNP Paribas Leasing Solutions", CAT_FINANCIAL, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.FINANCIER_STATE, False),
    ("John Deere Capital Corporation", CAT_SUBSIDIARIES, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.FINANCIER_STATE, False),
    # --- the controls that must survive -----------------------------------
    ("CNH Industrial N.V", CAT_CONSTRUCTION, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.DIRECT_COMPETITOR, True),
    ("Hyundai Heavy Industries Group", CAT_CONSTRUCTION, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.DIRECT_COMPETITOR, True),
    ("Alstom SA", CAT_RAIL, "Caterpillar Inc.",
     "MANUFACTURE_AND_AFTERMARKET", Q.DIRECT_COMPETITOR, True),
    # A BANK'S RIVALS ARE BANKS. The lender rule is keyed on what the
    # SUBJECT sells (§43), never on the candidate's name.
    ("Citizens Financial Group", BANK_RIVALS, "JPMorgan Chase & Co.",
     "BALANCE_SHEET_OR_NETWORK", Q.DIRECT_COMPETITOR, True),
    # A SEGMENT'S CONTEST IS ADJACENT, NEVER DIRECT — and it is still a real
    # competitive fact, so it stays on the ladder with adjacent wording.
    ("Acme Robotics Inc.", SEGMENT_CONTEST, "Orion Industrial Corp",
     "MANUFACTURE_AND_AFTERMARKET", Q.ADJACENT_THREAT_STATE, True),
    # A PLAIN COMPANY IN A CLAUSE THAT SAYS NOTHING ABOUT COMPETING. No
    # entity rule can reach this one: only the clause test can.
    ("Northwind Logistics Inc.", NEIGHBOURING_CLAUSE, "Orion Industrial Corp",
     "MANUFACTURE_AND_AFTERMARKET", Q.INCIDENTALLY_NAMED, False),
])
def test_the_qualification_matrix(candidate, evidence, subject, model,
                                  state, direct):
    q = _q(candidate, evidence, subject, model)
    assert q.qualification_state == state, q.reason
    assert q.may_contest is direct, q.reason


def test_every_state_has_customer_wording():
    """§8. The sentence a reader sees must match the state behind it."""
    for state in Q.QUALIFICATION_STATES:
        assert Q.WORDING[state].strip()


def test_only_three_states_may_reach_a_competitive_claim():
    """§3. And only two of those may say 'contested most directly by'."""
    assert set(Q.MAY_CONTEST) == {Q.DIRECT_COMPETITOR, Q.SUBSTITUTE_STATE,
                                  Q.ADJACENT_THREAT_STATE}
    assert Q.ADJACENT_THREAT_STATE not in Q.MAY_CONTEST_DIRECTLY


# ===========================================================================
# §6. NOT SUPPRESSED — ROUTED. The system should become smarter, not quieter.
# ===========================================================================
def test_an_index_keeps_its_place_in_market_context():
    q = _q("S&P", META_INDEX, "Meta Platforms, Inc.", "ADVERTISING_PLATFORM")
    assert q.section == "Market, index and capital-market context"


def test_a_payer_programme_keeps_its_place_in_regulation():
    q = _q("Medicare Part D", WALMART_PROGRAM, "Walmart Inc.", "SCALE_RETAIL")
    assert q.section == "Regulation and payer economics"


def test_a_lender_keeps_its_place_in_customer_financing():
    q = _q("Banc of America Leasing", CAT_FINANCIAL, "Caterpillar Inc.",
           "MANUFACTURE_AND_AFTERMARKET")
    assert q.section == "Customer financing and purchase enablement"


def test_routed_groups_the_non_competitors_under_their_headings():
    qs = [_q("S&P", META_INDEX, "Meta Platforms, Inc.", "ADVERTISING_PLATFORM"),
          _q("Medicare Part D", WALMART_PROGRAM, "Walmart Inc.",
             "SCALE_RETAIL"),
          _q("CNH Industrial N.V", CAT_CONSTRUCTION, "Caterpillar Inc.",
             "MANUFACTURE_AND_AFTERMARKET")]
    grouped = Q.routed(qs)
    assert "Market, index and capital-market context" in grouped
    assert "Regulation and payer economics" in grouped
    # the real rival is NOT routed away — it belongs on the ladder
    assert all("CNH" not in q.candidate
               for rows in grouped.values() for q in rows)


# ===========================================================================
# THE CLAUSE IS THE CLAIM. A fifteen-bullet list is not one sentence.
# ===========================================================================
def test_the_governing_clause_is_the_bullet_the_name_is_in():
    clause = Q.governing_clause(META_INDEX, "S&P")
    assert "S&P 500 Index" in clause
    assert "media coverage" not in clause


def test_the_quoted_evidence_is_the_clause_that_names_the_candidate():
    """The excerpt shown beside a claim must be the span that makes it.

    The deployed page quoted characters 0-400 of a fifteen-bullet blob — a
    sentence about income tax — under a competitor called S&P.
    """
    q = _q("S&P", META_INDEX, "Meta Platforms, Inc.", "ADVERTISING_PLATFORM")
    assert "S&P 500 Index" in q.evidence_basis
    assert "media coverage" not in q.evidence_basis


def test_a_name_does_not_inherit_a_contest_from_another_clause():
    """The competition word five bullets away established nothing about S&P."""
    blob = ("•we face significant competition in every part of our "
            "business;\n•price and volume fluctuations in the overall "
            "stock market;\n•the inclusion of our stock in the S&P 500 "
            "Index")
    q = _q("S&P", blob, "Meta Platforms, Inc.", "ADVERTISING_PLATFORM")
    assert not q.may_contest


def test_a_list_header_still_covers_the_names_under_it():
    """Bounded inheritance: the IMMEDIATELY preceding clause, and only when
    it introduces a list. Unbounded inheritance is the defect itself."""
    blob = ("Our principal competitors include;\nAcme Robotics Inc.;\n"
            "Beta Machines Ltd.")
    q = _q("Acme Robotics Inc.", blob, "Gamma Corp",
           "MANUFACTURE_AND_AFTERMARKET")
    assert q.qualification_state == Q.DIRECT_COMPETITOR, q.reason


# ===========================================================================
# THE CONTEST HAS AN OWNER.
# ===========================================================================
def test_a_segments_contest_is_not_the_companys_contest():
    assert Q.contest_owner(CAT_FINANCIAL, "Caterpillar Inc.") == "Cat Financial"


def test_the_companys_own_contest_has_no_other_owner():
    assert Q.contest_owner(CAT_RAIL, "Caterpillar Inc.") == ""
    assert Q.contest_owner(CAT_CONSTRUCTION, "Caterpillar Inc.") == ""


# ===========================================================================
# §7. A DIRECT CLAIM CANNOT BE CONSTRUCTED WITHOUT A CHOICE MECHANISM.
# ===========================================================================
def test_a_competitive_state_requires_a_customer_choice():
    """A mechanism is supplied, so only the CHOICE guard can refuse this."""
    with pytest.raises(Q.QualificationRefused):
        Q.CompetitiveQualification(
            candidate="Anything", entity_type=Q.ENTITY_COMPANY,
            relationship_type=Q.COMPETITOR, focal_need="need",
            substitution_mechanism="a customer could buy it instead",
            customer_choice_possible=False,
            evidence_basis="x", confidence="HIGH",
            qualification_state=Q.DIRECT_COMPETITOR, reason="because")


def test_a_competitive_state_requires_a_substitution_mechanism():
    with pytest.raises(Q.QualificationRefused):
        Q.CompetitiveQualification(
            candidate="Anything", entity_type=Q.ENTITY_COMPANY,
            relationship_type=Q.COMPETITOR, focal_need="",
            substitution_mechanism="", customer_choice_possible=True,
            evidence_basis="x", confidence="HIGH",
            qualification_state=Q.DIRECT_COMPETITOR, reason="because")


def test_every_qualification_states_its_basis():
    with pytest.raises(Q.QualificationRefused):
        Q.CompetitiveQualification(
            candidate="Anything", entity_type=Q.ENTITY_COMPANY,
            relationship_type=Q.UNKNOWN, focal_need="",
            substitution_mechanism="", customer_choice_possible=False,
            evidence_basis="", confidence="LOW",
            qualification_state=Q.UNKNOWN_STATE, reason="")


# ===========================================================================
# THE SEAM. The last repair in this area shipped completely inert because a
# field died at a projection boundary, so these pin the boundary rather than
# the behaviour.
# ===========================================================================
def _docs(text):
    return [{"text_content": text, "observation_id": "obs-1",
             "source_title": "SEC 10-K", "source_class": "investor_material",
             "date": "2026-01-01"}]


def test_the_extractor_carries_the_qualification_onto_the_competitor():
    """`Competitor` is what the ladder receives; a state that stops at the
    qualification object cannot govern anything the reader sees."""
    assert "qualification_state" in {
        f.name for f in dataclasses.fields(CC.Competitor)}
    found = CF.find_competitors(
        _docs("We compete in construction. " + CAT_CONSTRUCTION),
        subject="Caterpillar Inc.", limit=6,
        business_model="MANUFACTURE_AND_AFTERMARKET")
    assert found, "the control rivals must survive"
    assert all(c.qualification_state for c in found)


def test_the_extractor_refuses_the_three_measured_non_actors():
    for candidate, blob, subject, model in (
            ("S&P", "We face competition. " + META_INDEX,
             "Meta Platforms, Inc.", "ADVERTISING_PLATFORM"),
            ("Medicare Part D", "We face competition. " + WALMART_PROGRAM,
             "Walmart Inc.", "SCALE_RETAIL")):
        found = CF.find_competitors(_docs(blob), subject=subject, limit=8,
                                    business_model=model)
        assert candidate not in {c.name for c in found}, candidate


def test_the_extractor_hands_back_what_it_refused_and_where_it_belongs():
    """§6. Refusing quietly would make the analysis poorer, not better."""
    refusals = []
    CF.find_competitors(
        _docs("We face competition. " + WALMART_PROGRAM),
        subject="Walmart Inc.", limit=8, business_model="SCALE_RETAIL",
        refusals=refusals)
    routed = Q.routed(refusals)
    assert "Regulation and payer economics" in routed


def test_selection_is_not_alphabetical():
    """Caterpillar's filing named forty-three firms and the four that reached
    the page were the four earliest in the alphabet.

    The fixture puts the RAIL sentence first, as a filing that led with rail
    would. Alphabetical selection returns Alstom; the company's own order
    returns Wabtec. The two answers differ, which is the whole point.
    """
    text = ("We compete globally. " + CAT_RAIL + " " + CAT_CONSTRUCTION)
    found = CF.find_competitors(_docs(text), subject="Caterpillar Inc.",
                                limit=4,
                                business_model="MANUFACTURE_AND_AFTERMARKET")
    names = [c.name for c in found]
    assert names, "controls must survive"
    assert names != sorted(names, key=str.lower), names
    assert names[0] == "Wabtec Corp", names


def test_the_ranking_puts_a_direct_rival_above_an_adjacent_threat():
    direct = _q("CNH Industrial N.V", CAT_CONSTRUCTION, "Caterpillar Inc.",
                "MANUFACTURE_AND_AFTERMARKET")
    adjacent = Q.CompetitiveQualification(
        candidate="Some Unit", entity_type=Q.ENTITY_COMPANY,
        relationship_type=Q.ADJACENT_THREAT, focal_need="x",
        substitution_mechanism="a customer could choose it instead",
        customer_choice_possible=True, evidence_basis="x",
        confidence="MEDIUM", qualification_state=Q.ADJACENT_THREAT_STATE,
        reason="segment contest", contest_owner="A Segment")
    # the adjacent threat appears FIRST in the document and must still rank
    # behind the direct rival
    assert [q.candidate for q in Q.rank([(adjacent, 0), (direct, 5)])] == \
        ["CNH Industrial N.V", "Some Unit"]


# ===========================================================================
# §8. THE SENTENCE CONTRACT. The wording must match the state behind it.
# ===========================================================================
from intent_engine.executive import strategic_read as SR      # noqa: E402


def _row(name, kind, rung="DISPLACEMENT"):
    return SR.CompetitorRead(
        name=name, why_a_rival="", exposure="", likely_response="",
        response_likelihood="", counter_move="", signal_to_watch="",
        rung=rung, kind=kind)


def test_the_kind_survives_the_projection_into_the_read():
    """THE SEAM THE LAST REPAIR IN THIS AREA DIED AT. `rung` did not exist on
    `CompetitorRead` and a filter reading it silently kept everything; `kind`
    is the same shape of field and gets the same proof."""
    assert "kind" in {f.name for f in dataclasses.fields(SR.CompetitorRead)}
    source = inspect.getsource(SR._from_ground)
    assert "kind=rival.kind" in source, \
        "the ladder's kind must be carried into the row the renderer reads"


def test_an_in_house_build_is_not_described_as_a_direct_contest():
    clauses = SR._by_alternative_kind([
        _row("The advertiser spending the budget on its own channels",
             "BUILD_IN_HOUSE", "INTERNAL_BUILD")])
    joined = " ".join(clauses)
    assert "internalise the work" in joined
    assert "contested directly by" not in joined


def test_a_substitute_is_not_described_as_a_direct_contest():
    joined = " ".join(SR._by_alternative_kind([
        _row("Another surface holding the same attention hour", "SUBSTITUTE")]))
    assert "customers can substitute" in joined
    assert "contested directly by" not in joined


def test_doing_nothing_is_described_as_delay_not_as_a_rival():
    joined = " ".join(SR._by_alternative_kind([
        _row("Deferring replacement and rebuilding instead", "DO_NOTHING",
             "WORKFLOW_SUBSTITUTE")]))
    assert "delaying the purchase" in joined


def test_a_named_firm_still_earns_the_direct_sentence():
    joined = " ".join(SR._by_alternative_kind([
        _row("CNH Industrial N.V", "DIRECT", "NAMED_BY_SUBJECT")]))
    assert "contested directly by CNH Industrial N.V" in joined


def test_a_retrieved_firm_keeps_its_capital_and_a_read_phrase_does_not():
    named = " ".join(SR._by_alternative_kind([
        _row("Komatsu Ltd", "DIRECT", "NAMED_BY_SUBJECT")]))
    read = " ".join(SR._by_alternative_kind([
        _row("Another surface holding the same attention hour", "SUBSTITUTE")]))
    assert "Komatsu Ltd" in named
    assert "another surface holding" in read


# ===========================================================================
# §6. THE ROUTING MUST REACH A READER. A classification with no caller and no
# surface is a capability that reads as done and shows nobody anything.
# ===========================================================================
def test_the_run_collects_the_refusals_rather_than_discarding_them():
    source = inspect.getsource(SR._ground)
    assert "refusals=refused" in source or "refusals=refused" in \
        inspect.getsource(SR._named_rivals), \
        "the production call site must ask for the refusals"
    # NOT merely that the keyword is passed: that it is passed THE REFUSALS.
    # `other_relationships=()` satisfies a substring test and routes nothing,
    # which is exactly the shape of inert repair this area keeps shipping.
    assert "other_relationships=_routed(refused)" in source, \
        "the refusals themselves must reach the ground the surfaces read"


def test_the_ground_carries_the_routed_relationships():
    from intent_engine.executive.competitive_ladder import CompetitiveGround
    ground = CompetitiveGround(
        company="Walmart Inc.",
        other_relationships=(("Regulation and payer economics",
                              "Medicare Part D", "a programme"),))
    assert ground.as_dict()["other_relationships"] == [
        ["Regulation and payer economics", "Medicare Part D", "a programme"]]


def test_the_full_analysis_renders_the_routed_relationships():
    from intent_engine.founder_brief import dossier

    class _Ground:
        other_relationships = (
            ("Regulation and payer economics", "Medicare Part D",
             "a programme or policy whose terms move this business"),)

    class _Read:
        competitive_ground = _Ground()

    paras = dossier._other_relationships(_Read())
    assert paras and "Medicare Part D" in paras[0]
    assert "Regulation and payer economics" in paras[0]


def test_nothing_is_rendered_when_nothing_was_routed():
    from intent_engine.founder_brief import dossier

    class _Read:
        competitive_ground = None

    assert dossier._other_relationships(_Read()) == []


def test_the_frame_verb_is_not_repeated_by_the_identity():
    """MEASURED LIVE on c719979, Exxon: "customers can substitute substitute
    materials at the customer's plant". The frame supplies the verb; when the
    ladder's identity opens with the same word, two layers write it."""
    joined = " ".join(SR._by_alternative_kind([
        _row("Substitute materials at the customer's plant", "SUBSTITUTE")]))
    assert "substitute substitute" not in joined.lower(), joined
    assert "substitute materials at the customer's plant" in joined


def test_an_identity_that_merely_starts_differently_is_untouched():
    joined = " ".join(SR._by_alternative_kind([
        _row("Rental and used equipment in place of a new purchase",
             "SUBSTITUTE")]))
    assert "rental and used equipment" in joined


# ===========================================================================
# A ONE-LETTER WORD IS AN ARTICLE, NOT AN ACRONYM
# ===========================================================================
def test_the_article_a_is_lowercased_mid_sentence():
    """MEASURED LIVE on Amazon: "contested directly by A specialist doing one
    engine better than the bundle". `"A".isupper()` is True, so the guard that
    protects initialisms protected the article."""
    assert SR._lower_first("A specialist doing one engine better than the "
                           "bundle").startswith("a specialist")


def test_an_initialism_is_still_protected():
    for name in ("AI replacing the workflow", "IBM Corporation",
                 "A. Smith Holdings", "I. M. Pei Associates"):
        assert SR._lower_first(name) == name, name


def test_the_pronoun_i_is_still_protected():
    assert SR._lower_first("I would not") == "I would not"


def test_the_position_sentence_reads_it_as_an_article():
    joined = " ".join(SR._by_alternative_kind([
        _row("A specialist doing one engine better than the bundle",
             "ADJACENT", "WORKFLOW_SUBSTITUTE")]))
    assert "by a specialist doing one engine" in joined, joined
