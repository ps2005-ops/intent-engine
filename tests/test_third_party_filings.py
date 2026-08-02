"""Independent evidence: filings written by someone OTHER than the subject.

Measured gap: ten real companies produced ZERO independent vantage points --
every source was the company describing itself. The families that would fix
that were probed live and are not reachable without bypassing controls we do
not bypass (G2/Trustpilot/Capterra 403; Reuters 401; AP 404). EDGAR full-text
search is public, and a competitor's own 10-K naming the subject is a genuinely
independent account.
"""
import datetime as dt

from intent_engine.company_ingestion import third_party_filings as TPF
from intent_engine.strategic_intelligence import source_semantics as S

TODAY = dt.date(2026, 8, 2)


def _hit(cik, name, form="10-K", date="2026-01-15", hit_id="0001-26-1:x.htm",
         snippet=("The company competes with Datadog in observability.")):
    return {"_id": hit_id,
            "_source": {"ciks": [cik], "display_names": [name],
                        "file_type": form, "file_date": date,
                        "_snippet": [snippet]}}


def _transport(hits):
    return lambda url: {"hits": {"hits": hits}}


def test_a_competitor_filing_is_independent_of_the_subject():
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare, Inc.  (NET)")]),
        today=TODAY)
    assert len(got) == 1
    assert got[0]["source_class"] == "competitor"
    assert S.is_independent_of_subject(got[0]["source_class"])
    assert got[0]["independence"] == "INDEPENDENT_OF_SUBJECT"


def test_the_subjects_own_filing_is_never_returned():
    """The whole point. A 10-K by the subject is company-authored, and
    returning it here would recreate the false independence this ends."""
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001561550", "Datadog, Inc.  (DDOG)")]),
        today=TODAY)
    assert got == []


def test_the_edgar_venue_does_not_make_a_filing_independent():
    """Both filings sit on sec.gov. Only the AUTHOR decides independence."""
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001561550", "Datadog, Inc."),
                              _hit("0001477333", "Cloudflare, Inc.")]),
        today=TODAY)
    assert [c["third_party_filer"] for c in got] == ["Cloudflare, Inc."]


def test_a_stale_filing_cannot_corroborate_a_current_claim():
    """Unfiltered search returned Adobe's newest third-party mention from 2006
    and ASML's from 2013."""
    got = TPF.propose_third_party_filings(
        company_name="Adobe", subject_cik="0000796343",
        transport=_transport([_hit("0000897893", "PEERLESS SYSTEMS CORP",
                                   date="2006-10-26")]),
        today=TODAY)
    assert got == []


def test_an_undated_filing_is_not_usable_as_evidence():
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare", date="")]),
        today=TODAY)
    assert got == []


def test_an_incidental_mention_is_not_evidence():
    """Named once in an exhibit index is not an account of the company."""
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare",
                                   snippet="EXHIBIT INDEX  Datadog  10.4")]),
        today=TODAY)
    assert got == []


def test_a_non_substantive_form_is_rejected():
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare", form="4")]),
        today=TODAY)
    assert got == []


def test_one_organisational_voice_per_filer():
    """Three filings by one competitor are one vantage point, not three."""
    hits = [_hit("0001477333", "Cloudflare", hit_id=f"0001-26-{i}:x.htm")
            for i in range(3)]
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport(hits), today=TODAY)
    assert len(got) == 1


def test_competitor_bias_is_recorded_not_hidden():
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare")]), today=TODAY)
    assert "interest in how it describes" in got[0]["bias_note"]


def test_every_candidate_carries_a_durable_citation_and_a_date():
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001477333", "Cloudflare")]), today=TODAY)
    c = got[0]
    assert c["url"].startswith("https://www.sec.gov/Archives/edgar/data/")
    assert c["filed_on"] == "2026-01-15"
    assert c["availability"] == "UNVERIFIED"     # approval-gated like any other


def test_the_adapter_never_raises_and_never_breaks_discovery():
    def boom(url):
        raise RuntimeError("efts is down")
    assert TPF.propose_third_party_filings(
        company_name="Datadog", transport=boom, today=TODAY) == []
    assert TPF.propose_third_party_filings(company_name="", today=TODAY) == []


def test_the_result_is_bounded():
    hits = [_hit(f"000{i:07d}", f"Filer {i}", hit_id=f"0001-26-{i}:x.htm")
            for i in range(1, 40)]
    got = TPF.propose_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport(hits), today=TODAY)
    assert len(got) <= TPF.MAX_CANDIDATES


def test_an_injected_transport_keeps_discovery_offline(tmp_path):
    """A test double is not the full-text index. Reaching the live endpoint
    from a suite is wrong and slow -- it tripled the suite runtime once."""
    from tests.test_strategic_intelligence import _live_transport
    from intent_engine.company_ingestion.service import CompanyIngestionService
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=_live_transport, resolver=False)
    assert ci._third_party_filing_candidates({"company_name": "Datadog"}) == []


# --- claim relevance: the seventeen measured false positives ----------------
def _relevance(text, company="Datadog"):
    from intent_engine.strategic_intelligence import claim_relevance as CR
    return CR.assess(text=text, company_name=company)


def test_a_compensation_peer_group_is_not_corroboration():
    """MEASURED on Cloudflare's and Confluent's filings: the only mention of
    Datadog sat in an executive-compensation peer group."""
    v = _relevance("Based on a review of the analysis prepared by Compensia, "
                   "the compensation committee removed Cloudflare and Datadog "
                   "from the peer group for 2025.")
    assert v.relationship == "UNRELATED"
    assert v.rejected_as == "compensation_peer_group"
    assert not v.usable_as_support


def test_an_xbrl_taxonomy_fragment_is_not_evidence():
    """MEASURED on Figma, Lifetime Brands, Ichor and Australian Oilseeds."""
    v = _relevance("2023-01-01 2023-12-31 0001579878 "
                   "us-gaap:ForeignTaxJurisdictionMember Datadog")
    assert v.rejected_as == "xbrl_fragment"


def test_a_director_biography_is_not_evidence():
    """MEASURED on Skillsoft, IPG Photonics and ProSomnus."""
    v = _relevance("He has served on the board of directors of Datadog, Inc. "
                   "and received a Bachelor of Science from the University of "
                   "Denver.")
    assert v.rejected_as == "director_biography"


def test_forward_looking_boilerplate_is_not_evidence():
    """MEASURED on SEMrush."""
    v = _relevance("These forward-looking statements involve circumstances "
                   "that are difficult to predict, including competition from "
                   "Datadog.")
    assert v.rejected_as == "forward_looking_boilerplate"


def test_naming_the_company_and_saying_nothing_is_rejected():
    v = _relevance("Our platform integrates with Datadog and other tools.")
    assert v.relationship == "UNRELATED"
    assert v.rejected_as == "weak_mention"


def test_a_long_competitor_list_is_context_only_never_support():
    """A company beside twenty others shows it competes here, nothing more."""
    v = _relevance("We compete with Datadog, Splunk, Elastic, Dynatrace, "
                   "New Relic, Sumo Logic, Grafana Labs and others.")
    assert v.relationship == "CONTEXTUALIZES"
    assert not v.usable_as_support, "context-only may never carry a conclusion"


def test_a_material_displacement_statement_is_genuine_support():
    """MEASURED: New Relic's filing is the one of eighteen that qualifies."""
    v = _relevance("Customers have migrated from our platform to Datadog, and "
                   "we lost a customer to them in the enterprise segment.")
    assert v.usable_as_support
    assert v.relationship in ("SUPPORTS", "WEAKENS")


def test_a_material_statement_about_a_different_subject_is_context_only():
    v = _relevance("We compete directly with Datadog in log management.",
                   company="Datadog")
    from intent_engine.strategic_intelligence import claim_relevance as CR
    scoped = CR.assess(text="We compete directly with Datadog in log "
                            "management.",
                       company_name="Datadog",
                       claim_terms=("electric vehicle", "battery"))
    assert scoped.relationship == "CONTEXTUALIZES"
    assert scoped.rejected_as == "different_subject"
    assert v.usable_as_support        # unscoped, it is still material


def test_a_document_that_never_names_the_company_is_wrong_entity():
    v = _relevance("This filing discusses semiconductor lithography demand.")
    assert v.rejected_as == "wrong_entity"
