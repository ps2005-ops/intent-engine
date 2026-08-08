"""Competitor relevance is claim-specific, never mention-based.

The two failures these encode:

  * a compensation peer group read as a competitor list. It is chosen for
    revenue and headcount comparability and routinely contains companies in
    unrelated businesses, so it tells a founder to worry about a company they
    have never lost a deal to;
  * a bare name near the subject's name treated as a competitive claim.
"""
import pytest

from intent_engine.external_intel import competitor_contract as CC
from intent_engine.external_intel import competitor_finder as CF

TODAY = "2026-08-04"

_FILING = """Our business is described below. We operate in a highly
competitive market. We compete with Databricks Inc. and Snowflake Inc. for the
same customers in commercial data integration. Certain government customers may
instead build these capabilities in-house using their own engineering teams. We
also compete against consulting firms such as Booz Allen Hamilton, which
deliver similar outcomes as professional services engagements. Our revenue grew
during the period."""

_PROXY = """The compensation committee selected a compensation peer group of
comparable companies including Adobe Inc., Salesforce Inc. and Workday Inc. for
benchmarking executive compensation. These companies were chosen for revenue
and market capitalization comparability."""

_BARE = """The vendor announced a new release. Acme Corp. was mentioned in the
announcement."""


def _doc(text, **kw):
    base = dict(observation_id="ev-1", source_title="10-Q",
                source_class="regulatory_filing", date="2026-05-05",
                text=text)
    base.update(kw)
    return base


def _found(*docs, subject="Palantir Technologies"):
    return CF.find_competitors(list(docs), subject=subject, today=TODAY)


# --- the classification -----------------------------------------------------
def test_a_stated_overlap_is_claim_relevant():
    verdict = CC.assess(CC.Mention(
        name="Databricks",
        passage="We compete with Databricks for the same customers."),
        today=TODAY)
    assert verdict.relevance == CC.CLAIM_RELEVANT
    assert verdict.supports_conclusion


def test_competition_talk_without_a_specific_claim_is_context_only():
    verdict = CC.assess(CC.Mention(
        name="Databricks",
        passage="We operate in a highly competitive market. Databricks is one "
                "of the market participants."), today=TODAY)
    assert verdict.relevance == CC.COMPETITIVE_CONTEXT
    assert not verdict.supports_conclusion, \
        "framing may shape the section and must not corroborate a position"


def test_a_bare_mention_supports_nothing():
    verdict = CC.assess(CC.Mention(
        name="Acme Corp",
        passage="Acme Corp. was mentioned in the announcement."), today=TODAY)
    assert verdict.relevance == CC.BARE_MENTION
    assert not verdict.supports_conclusion


def test_a_compensation_peer_group_is_never_competitor_evidence():
    verdict = CC.assess(CC.Mention(name="Adobe Inc.", passage=_PROXY),
                        today=TODAY)
    assert verdict.relevance == CC.IRRELEVANT
    assert "comparability" in verdict.reason


def test_disqualifying_context_is_checked_before_overlap_language():
    """The ordering that makes the peer-group rule work.

    A proxy statement's peer-group passage also contains competitive-sounding
    words, so a keyword check alone reads it as competitive evidence.
    """
    passage = ("The compensation peer group includes companies we compete "
               "with for talent, such as Adobe Inc.")
    verdict = CC.assess(CC.Mention(name="Adobe Inc.", passage=passage),
                        today=TODAY)
    assert verdict.relevance == CC.IRRELEVANT


def test_a_customer_list_is_not_a_competitor_list():
    passage = "Our customers include Acme Corp. and Globex Inc."
    assert CC.assess(CC.Mention(name="Acme Corp.", passage=passage),
                     today=TODAY).relevance == CC.IRRELEVANT


def test_an_old_competitive_claim_is_stale_rather_than_current():
    verdict = CC.assess(CC.Mention(
        name="Databricks", date="2019-01-01",
        passage="We compete with Databricks for the same customers."),
        today=TODAY)
    assert verdict.relevance == CC.STALE
    assert not verdict.supports_conclusion


def test_only_claim_relevant_may_corroborate():
    assert CC.CONCLUSIVE == {CC.CLAIM_RELEVANT}


# --- the competitor object refuses to exist without evidence ----------------
def test_a_competitor_without_evidence_is_rejected():
    with pytest.raises(CC.CompetitorRejected):
        CC.Competitor(name="X", relationship=CC.DIRECT_COMPETITOR,
                      overlap="same buyer", evidence_ids=())


def test_a_competitor_without_a_stated_overlap_is_rejected():
    with pytest.raises(CC.CompetitorRejected) as exc:
        CC.Competitor(name="X", relationship=CC.DIRECT_COMPETITOR,
                      overlap="", evidence_ids=("ev-1",))
    assert "not a competitive claim" in str(exc.value)


def test_an_unknown_relationship_is_rejected():
    with pytest.raises(CC.CompetitorRejected):
        CC.Competitor(name="X", relationship="RIVAL", overlap="same buyer",
                      evidence_ids=("ev-1",))


# --- extraction from a real filing shape ------------------------------------
def test_a_filing_competition_section_yields_real_competitors():
    names = [c.name for c in _found(_doc(_FILING))]
    assert "Databricks Inc" in names
    assert "Snowflake Inc" in names


def test_the_compensation_peer_group_never_reaches_the_result():
    names = [c.name for c in _found(_doc(_FILING),
                                    _doc(_PROXY, observation_id="ev-2"))]
    for peer in ("Adobe Inc", "Salesforce Inc", "Workday Inc"):
        assert peer not in names


def test_a_bare_mention_never_reaches_the_result():
    names = [c.name for c in _found(_doc(_FILING),
                                    _doc(_BARE, observation_id="ev-3"))]
    assert "Acme Corp" not in names


def test_the_in_house_alternative_is_found_though_it_has_no_name():
    """The most common thing an enterprise product loses to.

    A name-based finder cannot see it -- there is no capitalised span to
    match -- so it was missing from the first run against a real filing whose
    Competition section said exactly that customers build in-house.
    """
    found = _found(_doc(_FILING))
    internal = [c for c in found if c.relationship == CC.INTERNAL_BUILD]
    assert internal, "the buyer's own engineering team is an alternative"
    assert "in-house" in internal[0].overlap.lower()


def test_a_consulting_alternative_keeps_its_own_relationship():
    """Found on the first real run: reading the relationship from the whole
    passage made every competitor in a Competition section inherit the same
    one, because a single sentence mentioned in-house building."""
    found = {c.name: c.relationship for c in _found(_doc(_FILING))}
    assert found["Databricks Inc"] == CC.DIRECT_COMPETITOR
    assert found["Snowflake Inc"] == CC.DIRECT_COMPETITOR
    assert found["Booz Allen Hamilton"] == CC.CONSULTING_ALTERNATIVE


def test_every_competitor_carries_evidence_and_a_decision_implication():
    for competitor in _found(_doc(_FILING)):
        assert competitor.evidence_ids
        assert competitor.overlap
        assert competitor.decision_implication
        assert competitor.limitation


def test_the_overlap_quote_is_a_whole_sentence_a_reader_can_check():
    """Splitting naively on '.' turned the citation for Snowflake into
    "and Snowflake Inc." -- a quote that proves nothing to the person
    checking it."""
    found = {c.name: c.overlap for c in _found(_doc(_FILING))}
    quote = found["Snowflake Inc"]
    assert quote.startswith("We compete with Databricks")
    assert "same customers" in quote


def test_the_subject_is_not_its_own_competitor():
    doc = _doc("We compete with Palantir Technologies and Snowflake Inc. for "
               "the same customers.")
    names = [c.name for c in _found(doc, subject="Palantir Technologies")]
    assert not any("Palantir" in n for n in names)


def test_a_clause_is_not_mistaken_for_a_company_name():
    names = CF.candidate_names(
        "Certain Government Customers may instead use other providers.",
        subject="Acme")
    assert names == []


def test_an_observation_without_an_id_yields_nothing():
    """A competitor a reader cannot click through to is unfalsifiable."""
    assert _found(_doc(_FILING, observation_id="")) == []


def test_a_company_with_no_competition_evidence_yields_nothing():
    doc = _doc("The company makes accounting software for small businesses. "
               "Revenue grew 20 percent.")
    assert _found(doc) == []


def test_corroborating_and_framing_are_separable():
    found = _found(_doc(_FILING))
    assert all(c.relevance == CC.CLAIM_RELEVANT
               for c in CC.corroborating(found))
    assert all(c.relevance == CC.COMPETITIVE_CONTEXT
               for c in CC.framing_only(found))
