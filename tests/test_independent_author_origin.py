"""Batch 13: an author is not a venue, and an attested source is not a guess.

Two measured defects are pinned here.

ONE. `origin_family` read the HOST, so every document filed with the SEC was
one origin. United Airlines' own 10-K describing Boeing was labelled
SAME_ORIGIN as Boeing's own 10-K and dropped from the independent count.

TWO. Inside the `independent` evidence family a guessed review-site URL and an
attested third-party filing both scored 4, and the family takes one candidate,
so insertion order decided. Ten of ten companies spent their single
independent slot on a slug-built g2.com URL.

The negative controls matter more than the positives here: a change that
separates authors is only correct if it still collapses the same author, and a
ranking change is only correct if it never outranks relevance.
"""
from intent_engine.company_ingestion.independence import (
    DERIVED_REPUBLICATION, INDEPENDENT_EXTERNAL_SOURCE,
    REGULATOR_OR_PRIMARY_FILING, SAME_ORIGIN, UNKNOWN_LINEAGE, assess,
    filing_author, origin_family,
)
from intent_engine.company_ingestion.third_party_filings import (
    _same_organisation, propose_third_party_filings,
)
from intent_engine.webapp.app import WebApp


def _filing(source_id, cik, source_class, words="alpha beta gamma delta"):
    return {"source_id": source_id,
            "final_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                         f"{source_id}.htm",
            "source_class": source_class, "filing": True,
            "content_hash": source_id,
            "text_content": f"{words} {source_id} " * 40}


# --- the author axis --------------------------------------------------------
def test_two_registrants_are_two_origins():
    """THE MEASURED DEFECT: a customer's own filing was a duplicate."""
    rows = assess([_filing("own", "12927", "investor_material"),
                   _filing("ual", "100517", "competitor")])
    assert rows["independent_evidence_count"] == 2
    assert rows["rows"][1]["lineage"] == INDEPENDENT_EXTERNAL_SOURCE


def test_same_registrant_twice_is_still_one_origin():
    """NEGATIVE CONTROL. Separating authors must not stop collapsing one."""
    rows = assess([_filing("a", "100517", "competitor"),
                   _filing("b", "100517", "competitor")])
    assert rows["rows"][1]["lineage"] == SAME_ORIGIN
    assert rows["independent_evidence_count"] == 1


def test_subjects_own_filing_never_becomes_independent():
    """The gate is the vantage class, not the venue."""
    rows = assess([_filing("own", "12927", "investor_material")])
    assert rows["rows"][0]["lineage"] == REGULATOR_OR_PRIMARY_FILING
    assert rows["independent_external_count"] == 0


def test_non_filing_hosts_keep_host_grouping():
    """REGRESSION. Only EDGAR paths change; everything else is untouched."""
    assert origin_family("https://blog.acme.com/x") == "acme.com"
    assert origin_family("https://www.acme.com/y") == "acme.com"


def test_unknown_lineage_is_not_independent():
    rows = assess([{"source_id": "u", "final_url": "https://x.example/a",
                    "text_content": "w " * 40, "content_hash": "u"}])
    assert rows["rows"][0]["lineage"] == UNKNOWN_LINEAGE
    assert rows["independent_evidence_count"] == 0


# --- adversarial: a URL that only LOOKS like a filing -----------------------
def test_edgar_path_on_another_host_is_not_a_filer():
    """An attacker-controlled host must not mint origins by path shape."""
    assert filing_author("https://evil.example/Archives/edgar/data/999/x") == ""
    assert origin_family(
        "https://evil.example/Archives/edgar/data/999/x") == "evil.example"


def test_sec_gov_as_a_subdomain_of_another_host_is_not_edgar():
    assert filing_author("https://www.sec.gov.evil.example/Archives/edgar/"
                         "data/999/x") == ""


def test_real_sec_subdomain_is_edgar():
    assert filing_author(
        "https://efts.sec.gov/Archives/edgar/data/00012927/x.htm") == "12927"


def test_the_same_filing_mirrored_off_edgar_is_not_a_second_observation():
    """SYNDICATION ACROSS ORIGINS. The text is identical; the host is not.

    The fixture must carry the SAME words, not merely similar ones — an
    earlier version of this test interpolated the row id into the body, so
    the two documents never reached the republication threshold and the
    property held for a reason that had nothing to do with the code.
    """
    body = "alpha beta gamma delta epsilon zeta eta theta " * 40
    original = {"source_id": "ual", "content_hash": "ual",
                "final_url": "https://www.sec.gov/Archives/edgar/data/100517/"
                             "ual.htm",
                "source_class": "competitor", "filing": True,
                "text_content": body}
    mirror = {"source_id": "m", "final_url": "https://mirror.example/ual.htm",
              "source_class": "competitor", "filing": True,
              "content_hash": "m", "text_content": body}
    rows = assess([original, mirror])
    assert rows["rows"][0]["lineage"] == INDEPENDENT_EXTERNAL_SOURCE
    assert rows["rows"][1]["lineage"] == DERIVED_REPUBLICATION
    assert rows["independent_evidence_count"] == 1


# --- the subject-name lock --------------------------------------------------
def test_filer_that_is_the_subject_is_excluded_by_name():
    assert _same_organisation("Cloudflare, Inc.  (NET)  (CIK 0001477333)",
                              "Cloudflare, Inc.")
    assert _same_organisation("BOEING CO", "The Boeing Company")


def test_name_lock_does_not_over_match_a_different_company():
    """THE COLLISION LESSON. Over-matching DELETES a true observation."""
    assert not _same_organisation("Linear Minerals Corp.", "Linear")
    assert not _same_organisation("Agnico Eagle Mines Limited",
                                  "Eagle Materials Inc.")


def test_subject_own_filing_is_dropped_when_cik_resolution_failed():
    """The resolver's failure is swallowed upstream; the name still holds."""
    payload = {"hits": {"hits": [{
        "_id": "0001-x:doc.htm",
        "_source": {"ciks": ["0001477333"],
                    "display_names": ["Cloudflare, Inc.  (NET)  (CIK 1477333)"],
                    "file_type": "10-K", "file_date": "2026-03-01"}}]}}
    out = propose_third_party_filings(
        company_name="Cloudflare, Inc.", subject_cik="",
        transport=lambda url: payload)
    assert out == []


# --- selection: attested beats guessed, inside the independent family -------
def _candidate(cid, method, source_class, url, source_type="external_approved",
               why=""):
    return {"candidate_id": cid, "discovery_method": method,
            "source_class": source_class, "url": url,
            "source_type": source_type, "why_relevant": why}


def test_attested_filing_takes_the_independent_slot_over_a_guess():
    """THE MEASURED DEFECT: 10 of 10 slots went to a guessed g2.com URL."""
    candidates = [
        _candidate("g2", "external_proposed", "customer_voice",
                   "https://www.g2.com/products/boeing/reviews"),
        _candidate("ual", "third_party_filing", "competitor",
                   "https://www.sec.gov/Archives/edgar/data/100517/ual.htm"),
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert picked[0] == "ual"


def test_independent_candidate_not_crowded_out_by_many_company_pages():
    """§13 METAMORPHIC. 20 company-owned + regulator + customer + independent.

    The independent high-value candidates must not lose their place merely
    because the company's own domain produced more URLs. All three outside
    candidates here are ATTESTED — a filing an index returned, and a source a
    human supplied — which is what makes them high-value. The unverified
    template guess is a different case and is pinned separately below.
    """
    candidates = [
        _candidate(f"own{i}", "known_path", "company_owned",
                   f"https://acme.example/p{i}", source_type="product")
        for i in range(20)]
    candidates += [
        _candidate("reg", "third_party_filing", "competitor",
                   "https://www.sec.gov/Archives/edgar/data/1/r.htm"),
        _candidate("cust", "user_pasted", "customer_voice",
                   "https://bigcustomer.example/why-we-chose-acme"),
        _candidate("indep", "third_party_filing", "competitor",
                   "https://www.sec.gov/Archives/edgar/data/2/i.htm"),
    ]
    picked = set(WebApp._recommended_candidate_ids(candidates))
    assert {"reg", "indep", "cust"} <= picked


def test_unverified_review_guess_is_demoted_but_not_excluded():
    """§36. Measured to fail on this cohort, so it loses priority — and it is
    still selected when the budget is not contested, because for a consumer
    software company it is exactly the right source."""
    contested = [
        _candidate(f"own{i}", "homepage_link", "company_owned",
                   f"https://acme.example/p{i}", source_type="product")
        for i in range(20)]
    contested.append(_candidate("g2", "external_proposed", "customer_voice",
                                "https://www.g2.com/products/acme/reviews"))
    # one independent family slot exists, so it is taken; what must NOT happen
    # is the guess outranking attested evidence for the *other* slots.
    picked = WebApp._recommended_candidate_ids(contested)
    assert picked.index("g2") > 0

    uncontested = [
        _candidate("home", "entered", "company_owned",
                   "https://acme.example/", source_type="homepage"),
        _candidate("g2", "external_proposed", "customer_voice",
                   "https://www.g2.com/products/acme/reviews"),
    ]
    assert "g2" in WebApp._recommended_candidate_ids(uncontested)


def test_entered_homepage_outranks_a_fresh_origin_guess():
    """REGRESSION, and the defect the concentration tie-break introduced.

    The founder's own URL and a slug-built review URL were the same tier, so
    preferring an unseen origin dropped the company's homepage out of the run
    entirely (measured on the `non_english` fixture: 4 documents became 3).
    """
    candidates = [
        _candidate("home", "entered", "company_owned",
                   "https://acme.example/", source_type="homepage"),
        _candidate("g2", "external_proposed", "customer_voice",
                   "https://www.g2.com/products/acme/reviews"),
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert picked.index("home") < picked.index("g2")


def test_diversity_never_outranks_relevance():
    """NEGATIVE CONTROL for the concentration tie-break.

    A curated official source on an origin we already hold must still be
    chosen ahead of a guess on a fresh origin. If this ever fails, the
    selector has started trading evidence for variety.
    """
    candidates = [
        _candidate("official", "official_fallback", "company_owned",
                   "https://acme.example/investors",
                   source_type="product"),
        _candidate("guess", "known_path", "company_owned",
                   "https://elsewhere.example/careers",
                   source_type="careers"),
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert picked.index("official") < picked.index("guess")


def test_leftover_budget_prefers_an_unseen_origin_within_a_tier():
    """Same tier, same family: the new origin is taken first."""
    candidates = [
        _candidate("a1", "known_path", "company_owned",
                   "https://acme.example/one", source_type="product"),
        _candidate("a2", "known_path", "company_owned",
                   "https://acme.example/two", source_type="product"),
        _candidate("b1", "known_path", "company_owned",
                   "https://other.example/one", source_type="product"),
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert picked.index("b1") < picked.index("a2")
