"""A guessed path on a host that already refused us may not spend a slot.

MEASURED on 743df06. Ranking such a candidate last was not enough to stop the
request being made -- rank 9 is still eligible, and the leftover fill spends
the unused budget on exactly these once the real candidates run out:

    Union Pacific  failed=27, 24 of them at up.com
    Goldman Sachs  failed=26, 24 of them at goldmansachs.com
    Mastercard     failed=24, 22 of them at mastercard.com
    Costco         failed=23, 21 of them at costco.com

Twenty-odd requests per run to a door already known to be closed, each one
waiting out a refusal or a timeout before the customer sees anything.
"""
from intent_engine.webapp.app import WebApp


def _guess(url, family="product"):
    return {"candidate_id": f"g-{url}", "url": url,
            "discovery_method": "known_path", "source_type": family,
            "source_class": "company_owned", "same_domain": True,
            "why_relevant": "a path this kind of site usually has",
            "title": url}


def _curated(url):
    return {"candidate_id": f"c-{url}", "url": url,
            "discovery_method": "official_fallback", "source_type": "about",
            "source_class": "company_owned", "same_domain": True,
            "why_relevant": "curated official source", "title": url}


def _filing(url, cik="100885"):
    return {"candidate_id": f"f-{url}", "url": url,
            "discovery_method": "external_proposed",
            "source_type": "external_approved",
            "source_class": "investor_material", "same_domain": False,
            "why_relevant": "official 10-K filing from SEC EDGAR",
            "title": "SEC 10-K"}


UP = "up.com"
POOL = [
    _guess("https://up.com/about"), _guess("https://up.com/products"),
    _guess("https://up.com/customers"), _guess("https://up.com/pricing"),
    _guess("https://up.com/careers"), _guess("https://up.com/investors"),
    _filing("https://www.sec.gov/Archives/edgar/data/100885/a.htm"),
]


def _chosen(pool, refusing=()):
    return set(WebApp._recommended_candidate_ids(
        pool, refusing_hosts=refusing, subject_cik="100885"))


def test_without_a_refusal_the_guesses_are_still_eligible():
    """THE CONTROL. A host we have not watched refuse us is fair game."""
    chosen = _chosen(POOL)
    assert any(c.startswith("g-") for c in chosen), chosen


def test_a_guess_at_a_refusing_host_is_never_approved():
    chosen = _chosen(POOL, refusing={UP})
    guesses = [c for c in chosen if c.startswith("g-")]
    assert guesses == [], guesses


def test_the_filing_still_gets_its_slot():
    chosen = _chosen(POOL, refusing={UP})
    assert any(c.startswith("f-") for c in chosen), chosen


def test_a_curated_url_survives_the_refusal():
    """A human asserted this page exists; a 403 on the homepage does not
    disprove it, and the ranking comment has always said so."""
    pool = POOL + [_curated("https://up.com/investor-relations")]
    chosen = _chosen(pool, refusing={UP})
    assert any(c.startswith("c-") for c in chosen), chosen


def test_a_subdomain_of_a_refusing_host_is_also_a_closed_door():
    pool = [_guess("https://ir.up.com/overview"),
            _filing("https://www.sec.gov/Archives/edgar/data/100885/a.htm")]
    chosen = _chosen(pool, refusing={UP})
    assert not any(c.startswith("g-") for c in chosen), chosen


def test_another_host_is_untouched_by_this_hosts_refusal():
    pool = POOL + [_guess("https://unionpacificfoundation.org/about")]
    chosen = _chosen(pool, refusing={UP})
    assert "g-https://unionpacificfoundation.org/about" in chosen, chosen
