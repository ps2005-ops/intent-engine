"""How hard we looked, as a measurement rather than a constant.

THE DEFECT THIS CLOSES. `discovery_coverage` was read by the provenance drawer
and written by NOTHING. Every analysis therefore reported DISCOVERY_NOT_RUN, so
the drawer could only ever say "we failed to find independent coverage" -- even
for a company where the search had in fact been exhaustive. The consumer was
correct and the producer did not exist, which is this codebase's recurring
shape: a rule that never receives its input.

The states here are branches over what a run DID -- candidates considered,
documents actually read, budget spent -- so a coverage state cannot be asserted
where it was not earned. The negative controls below exist because a coverage
field that always reads ADEQUATE would pass every happy-path test in this file.
"""
import datetime as dt

from intent_engine.company_ingestion import relevance as REL
from intent_engine.company_ingestion import third_party_filings as TPF

TODAY = dt.date(2026, 8, 2)

_SUBSTANTIVE = ("The company competes with Datadog in observability. "
                "Datadog's pricing pressured our renewal revenue this year.")


def _hit(cik, name, form="10-K", date="2026-01-15", hit_id="0001-26-1:x.htm"):
    return {"_id": hit_id,
            "_source": {"ciks": [cik], "display_names": [name],
                        "file_type": form, "file_date": date}}


def _transport(hits, total=None):
    return lambda url: {"hits": {"total": {"value": total or len(hits)},
                                 "hits": hits}}


def _fetcher(text=_SUBSTANTIVE):
    return lambda url: f"<html><body><p>{text}</p></body></html>"


def _peers(n, prose=True):
    hits = [_hit(str(700000 + i), f"Peer {i} Corp",
                 hit_id=f"000{i}-26-1:x.htm") for i in range(n)]
    return _transport(hits)


def test_reading_every_candidate_is_exhausted_not_partial():
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(3), fetcher=_fetcher(), today=TODAY)
    assert report["candidates_considered"] == 3
    assert report["candidates_fetched"] == 3
    assert report["coverage"] == REL.DISCOVERY_EXHAUSTED
    assert report["budget_exhausted"] is False


def test_stopping_at_the_budget_is_partial_never_exhausted():
    """Candidates we chose not to read cannot be spoken for."""
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(20), fetcher=_fetcher(), today=TODAY, max_fetches=5)
    assert report["budget_exhausted"] is True
    assert report["candidates_fetched"] == 5
    assert report["coverage"] == REL.DISCOVERY_PARTIAL
    assert report["coverage"] not in REL.SUPPORTS_FOUND_NONE


def test_an_unreachable_channel_is_blocked_never_a_measured_zero():
    def _boom(url):
        raise OSError("efts unreachable")

    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_boom, fetcher=_fetcher(), today=TODAY)
    assert report["coverage"] == REL.DISCOVERY_BLOCKED
    assert report["candidates"] == []
    assert report["channels_successful"] == []
    # The whole point: a channel we could not reach never licenses
    # "this company has no independent coverage".
    assert report["coverage"] not in REL.SUPPORTS_FOUND_NONE


def test_a_full_result_set_is_adequate():
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(12), fetcher=_fetcher(), today=TODAY, limit=4)
    assert len(report["candidates"]) == 4
    assert report["coverage"] == REL.DISCOVERY_ADEQUATE
    assert report["coverage"] in REL.SUPPORTS_FOUND_NONE


def test_documents_that_all_fail_to_fetch_are_never_adequate():
    """NEGATIVE CONTROL. Reading nothing is not searching thoroughly.

    Without this, a coverage state derived from the CANDIDATE list alone
    would read EXHAUSTED here -- every candidate was 'processed' -- while the
    run had in fact read not one word of any filing.
    """
    def _dead(url):
        raise OSError("403")

    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(3), fetcher=_dead, today=TODAY)
    assert report["candidates"] == []
    assert report["independent_relevant_origins"] == 0
    assert "FETCH_FAILED" in report["rejection_reasons"]
    assert report["coverage"] != REL.DISCOVERY_ADEQUATE


def test_rejection_reasons_are_counted_so_a_zero_can_be_read():
    """A zero with no reasons is unreadable. These counts are the reading."""
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0001561550", "Datadog, Inc."),
                              _hit("0001477333", "Cloudflare", form="4"),
                              _hit("0000999", "Old Corp", date="2009-01-02")]),
        fetcher=_fetcher(), today=TODAY)
    reasons = report["rejection_reasons"]
    assert reasons["SUBJECT_OWN_FILING"] == 1
    assert reasons["NON_SUBSTANTIVE_FORM"] == 1
    assert reasons["OUTSIDE_RECENCY_WINDOW"] == 1


def test_an_injected_search_without_a_fetcher_never_claims_coverage():
    """A replay that reads no documents did not search, whatever it returned."""
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(3), today=TODAY)
    assert report["coverage"] == REL.DISCOVERY_NOT_RUN
    assert report["candidates"] == []


def test_selection_prefers_decision_value_over_search_rank():
    """§6/§7: rank is not relevance, and the count is never the target.

    The vendor-list filer is returned FIRST by the index. The filing that
    actually discusses the company is returned last, and must win.
    """
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0000111", "Vendor List Co",
                                   hit_id="0001-26-1:a.htm"),
                              _hit("0000222", "Real Rival Inc",
                                   hit_id="0002-26-1:b.htm")]),
        fetcher=lambda url: (
            "<html><body><p>We use Datadog, such as for our own monitoring."
            "</p></body></html>" if "a.htm" in url else
            f"<html><body><p>{_SUBSTANTIVE}</p></body></html>"),
        today=TODAY, limit=1)
    assert [c["third_party_filer"] for c in report["candidates"]] == [
        "Real Rival Inc"]


def test_the_coverage_state_reaches_the_dossier():
    """PRODUCER -> BRIDGE -> READ MODEL. A field the bridge drops is a field
    the drawer will report as never measured."""
    from intent_engine.demo_dossier.contracts import read_founder_snapshot
    from intent_engine.external_intel import founder_demo_snapshot as FDS

    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_peers(3), fetcher=_fetcher(), today=TODAY)
    snapshot = read_founder_snapshot(FDS.build_payload(
        run_id="r1", company_id="datadog", canonical_name="Datadog, Inc.",
        discovery=report))
    crossed = snapshot.discovery_coverage
    assert crossed is not None
    assert crossed["coverage"] == REL.DISCOVERY_EXHAUSTED
    assert crossed["candidates_fetched"] == 3


def test_no_discovery_producer_crosses_as_absent_not_as_zero():
    """NEGATIVE CONTROL for the bridge. An absent producer must stay absent:
    a default block would let the drawer read a coverage we never measured."""
    from intent_engine.demo_dossier.contracts import read_founder_snapshot
    from intent_engine.external_intel import founder_demo_snapshot as FDS

    snapshot = read_founder_snapshot(FDS.build_payload(
        run_id="r0", company_id="datadog", canonical_name="Datadog, Inc."))
    assert snapshot.discovery_coverage is None
    reading = REL.zero_reading(independent_relevant=0,
                               coverage=REL.DISCOVERY_NOT_RUN)
    assert reading["reading"] == REL.FAILED_TO_FIND


def test_an_exhausted_search_with_nothing_found_may_say_found_none():
    """The state that was unreachable before a producer existed."""
    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0000111", "Vendor List Co")]),
        fetcher=_fetcher("We use Datadog, such as for our own monitoring."),
        today=TODAY)
    assert report["coverage"] == REL.DISCOVERY_EXHAUSTED
    reading = REL.zero_reading(independent_relevant=0,
                               coverage=report["coverage"])
    assert reading["reading"] == REL.FOUND_NONE
    assert "finding about the company" in reading["statement"]


def test_the_rejected_filers_never_cross_the_bridge():
    """A rejection row names a company that is not the subject. Counts cross;
    names do not."""
    from intent_engine.external_intel import founder_demo_snapshot as FDS

    report = TPF.discover_third_party_filings(
        company_name="Datadog", subject_cik="0001561550",
        transport=_transport([_hit("0000111", "Vendor List Co")]),
        fetcher=_fetcher("We use Datadog, such as for our own monitoring."),
        today=TODAY)
    payload = FDS.build_payload(run_id="r1", company_id="datadog",
                                canonical_name="Datadog, Inc.",
                                discovery=report)
    assert "Vendor List Co" not in str(payload["discovery_coverage"])
    assert payload["discovery_coverage"]["rejection_reasons"]["IRRELEVANT"] == 1


# --- what "independent and relevant" survived a live measurement ---------------
#
# The first live run of fetch-then-select returned four independent relevant
# origins for Cloudflare. Reading them is what produced everything below: two
# were executive biographies, two were customers disclosing their own vendor
# arrangements, and Caterpillar's top-ranked source was its own captive finance
# subsidiary. The mechanism worked and the output was still not evidence.


def test_an_executive_biography_is_not_evidence_about_the_company():
    """Adobe's proxy: "Garfield served as the Vice President of Finance of
    Cloudflare, Inc." A sentence whose subject is a person is about the person.
    """
    got = TPF.discover_third_party_filings(
        company_name="Cloudflare", subject_cik="0001477333",
        transport=_transport([_hit("0000796343", "ADOBE INC.")]),
        fetcher=_fetcher("Mr. Garfield served as the Vice President of "
                         "Finance of Cloudflare, Inc."),
        today=TODAY)
    assert got["candidates"] == []
    assert got["rejection_reasons"]["IRRELEVANT"] == 1


def test_a_customer_disclosing_its_own_vendor_is_not_an_outside_account():
    """ChargePoint's 10-K, live. There is no "we" in the sentence -- the filer
    names ITSELF -- so a first-person rule reads a supplier disclosure as an
    independent account of the supplier."""
    got = TPF.discover_third_party_filings(
        company_name="Cloudflare", subject_cik="0001477333",
        transport=_transport([_hit("0001777393", "ChargePoint Holdings, Inc.")]),
        fetcher=_fetcher("ChargePoint's primary environments are behind the "
                         "Content Delivery Network operated by Cloudflare."),
        today=TODAY)
    assert got["candidates"] == []


def test_a_rival_naming_itself_beside_the_subject_is_still_evidence():
    """NEGATIVE CONTROL for the rule above. Author-voice must demote only in
    combination with a supply verb, or every competitor that signs its own
    name disappears -- which would delete the exact evidence we are short of.
    """
    got = TPF.discover_third_party_filings(
        company_name="Cloudflare", subject_cik="0001477333",
        transport=_transport([_hit("0001086222", "Akamai Technologies, Inc.")]),
        fetcher=_fetcher("Akamai competes directly with Cloudflare for "
                         "enterprise CDN contracts. Cloudflare's pricing has "
                         "pressured Akamai's renewal revenue."),
        today=TODAY)
    assert [c["third_party_filer"] for c in got["candidates"]] == [
        "Akamai Technologies, Inc."]


def test_a_captive_finance_subsidiary_is_not_an_independent_voice():
    """MEASURED LIVE. Caterpillar's top-ranked independent source was
    CATERPILLAR FINANCIAL SERVICES CORP -- its own arm, filing under its own
    CIK, presented as an outside voice corroborating the company."""
    got = TPF.discover_third_party_filings(
        company_name="Caterpillar Inc.", subject_cik="0000018230",
        transport=_transport([_hit("0000024715",
                                   "CATERPILLAR FINANCIAL SERVICES CORP")]),
        fetcher=_fetcher("Caterpillar Inc. is the parent and its dealers "
                         "finance equipment revenue through this entity."),
        today=TODAY)
    assert got["candidates"] == []
    assert got["rejection_reasons"]["SUBJECT_OWN_FILING_BY_NAME"] == 1


def test_a_different_business_sharing_a_leading_word_is_not_an_affiliate():
    """NEGATIVE CONTROL. "Linear" once matched "Linear Minerals Corp." and the
    widening fix was worse than the defect. `minerals` is not a corporate
    function, so this filer is a different business and must survive."""
    got = TPF.discover_third_party_filings(
        company_name="Linear", subject_cik="0000123456",
        transport=_transport([_hit("0000999999", "Linear Minerals Corp.")]),
        fetcher=_fetcher("Linear Minerals competes with Linear for contract "
                         "manufacturing revenue in the region."),
        today=TODAY)
    assert [c["third_party_filer"] for c in got["candidates"]] == [
        "Linear Minerals Corp."]


# --- what the second live sweep found (J&J, BoA, Toyota, Vale) ----------------


def test_a_generic_leading_word_is_not_an_identity():
    """SEV1-CLASS, MEASURED LIVE. `_terms` emitted the bare leading word so
    that filings saying "Cloudflare" match "Cloudflare, Inc." -- but "Bank of
    America Corporation" leads with "Bank", so every sentence containing the
    word `bank` counted as a mention. All four of Bank of America's
    "independent relevant origins" were documents that never named it.
    """
    from intent_engine.company_ingestion import relevance as R
    assert R._terms("Bank of America Corporation", "") == [
        "Bank of America Corporation"]
    # Recall for a distinctive name is untouched -- this deletes collisions,
    # not observations.
    assert "Cloudflare" in R._terms("Cloudflare, Inc.", "")
    assert "Toyota" in R._terms("Toyota Motor Corporation", "")

    verdict = R.adjudicate(
        {"text_content": "Assets were held in segregated bank accounts to the "
                         "extent required by CFTC regulations. The fund keeps "
                         "several bank relationships open at all times."},
        subject_name="Bank of America Corporation")
    assert verdict["state"] == R.IRRELEVANT
    assert "never names the company" in verdict["reason"]


def test_a_holdings_table_row_is_not_a_claim():
    """MEASURED LIVE ON TWO SECTORS. Bank of America's strongest evidence was a
    fund's holdings row and Toyota's was a customer-concentration row. Both are
    independent, both name the company, neither asserts anything."""
    from intent_engine.company_ingestion import relevance as R
    filler = "This section describes the portfolio in detail. " * 12
    verdict = R.adjudicate(
        {"text_content": filler +
         "$ 1,500,000 3/11/27 Bank of America Corporation 1.66 % $ 1,497,566 "
         "2.16 %. Toyota Motor Corporation 12.2% 12.5% 11.5%."},
        subject_name="Bank of America Corporation")
    assert verdict["state"] == R.IRRELEVANT
    assert "tables" in verdict["reason"]


def test_a_short_excerpt_is_never_refused_for_its_shape():
    """OVER-REFUSAL CONTROL for the rule above. A span from a SHORT input is
    short because of our excerpting, not because the filing is a table."""
    from intent_engine.company_ingestion import relevance as R
    verdict = R.adjudicate({"text_content": "...Cloudflare..."},
                           subject_name="Cloudflare, Inc.")
    assert verdict["supports_corroboration"] is True


def test_the_excerpt_is_the_span_the_verdict_was_built_from():
    """MEASURED LIVE. The drawer printed a holdings row -- "Bank of America
    Corporation (14) 3,830,768 5.90" -- directly beside DIRECTLY_RELEVANT,
    because the excerpt was the first mention and the verdict came from
    different sentences entirely."""
    filler = "Portfolio detail follows for each position held. " * 12
    got = TPF.discover_third_party_filings(
        company_name="Cloudflare", subject_cik="0001477333",
        transport=_transport([_hit("0001086222", "Akamai Technologies, Inc.")]),
        fetcher=lambda url: (
            "<html><body><p>" + filler +
            "Cloudflare, Inc. 1.66 % $ 1,497,566 2.16 %. "
            "Akamai competes directly with Cloudflare for enterprise CDN "
            "contracts. Cloudflare's pricing pressured our renewal revenue."
            "</p></body></html>"),
        today=TODAY)
    excerpt = got["candidates"][0]["mention_excerpt"]
    assert "competes" in excerpt or "pricing" in excerpt
    assert "1,497,566" not in excerpt
