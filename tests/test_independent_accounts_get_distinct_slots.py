"""An outside account is the evidence a strategic reading turns on, and the
run must be able to hold more than one -- but never the same voice twice.

MEASURED 2026-11-28 (prospect-98 baseline): the per-family quotas summed to
exactly the 14-slot budget, so every run approved at most ONE independent
document while discovery had found two or three distinct origins. The
original rubric's independence metric needs two origins, so no company could
pass it whatever discovery found.
"""
from intent_engine.webapp import app as A


def _c(i, url, cls="company_owned", st="product", method="homepage_link"):
    return {"candidate_id": f"c{i}", "url": url, "source_class": cls, "source_type": st,
            "discovery_method": method, "availability": "PROPOSED", "same_domain": cls == "company_owned"}


def _owner():
    for name in dir(A):
        obj = getattr(A, name)
        if isinstance(obj, type) and hasattr(obj, "_recommended_candidate_ids"):
            return obj
    raise AssertionError("no class defines _recommended_candidate_ids")


def _site(n=20):
    out = [_c(0, "https://acme.example/", st="homepage", method="entered")]
    out += [_c(i, f"https://acme.example/product/{i}") for i in range(1, n)]
    out += [_c(100, "https://acme.example/customers", st="customers"),
            _c(101, "https://acme.example/blog", cls="executive_statement", st="blog"),
            _c(102, "https://acme.example/pricing", st="pricing"),
            _c(103, "https://acme.example/careers", st="careers")]
    return out


def _ind(i, host, cls="independent_reporting", method="independent_reporting"):
    return _c(i, f"https://{host}/2026/acme-story-{i}", cls=cls, st="article", method=method)


def _picked(cands):
    ids = _owner()._recommended_candidate_ids(cands)
    by = {c["candidate_id"]: c for c in cands}
    return [by[i] for i in ids]


def test_three_distinct_outside_origins_all_get_a_slot():
    cands = _site() + [_ind(200, "siliconangle.com"), _ind(201, "techcrunch.com"), _ind(202, "zdnet.com")]
    got = _picked(cands)
    assert len(got) <= A.MAX_APPROVED_SOURCES
    hosts = {c["url"].split("/")[2] for c in got if c["source_class"] == "independent_reporting"}
    assert hosts == {"siliconangle.com", "techcrunch.com", "zdnet.com"}


def test_the_same_origin_twice_does_not_take_a_second_slot():
    cands = _site() + [_ind(200, "siliconangle.com"), _ind(201, "siliconangle.com"), _ind(202, "siliconangle.com")]
    got = _picked(cands)
    assert sum(c["source_class"] == "independent_reporting" for c in got) == 1
    assert sum(c["source_type"] == "product" for c in got) >= 5


def test_guessed_review_pages_never_take_the_extra_slots():
    cands = _site() + [_ind(200, "siliconangle.com"),
                       _ind(201, "www.g2.com", cls="customer_voice", method="external_proposed"),
                       _ind(202, "www.capterra.com", cls="customer_voice", method="external_proposed")]
    got = _picked(cands)
    assert not [c for c in got if c["source_class"] == "customer_voice"]


def test_an_article_about_the_company_beats_a_passing_mention_in_a_filing():
    """MEASURED on Alteryx (w1): four other registrants' passing mentions
    displaced two articles about Alteryx."""
    art = _ind(200, "www.cpapracticeadvisor.com")
    art["relevance"] = "DIRECTLY_RELEVANT"
    filings = []
    for i, cik in enumerate(("1651562", "802257", "1102993", "1734722")):
        f = _c(300 + i, f"https://www.sec.gov/Archives/edgar/data/{cik}/0001/x-10k.htm",
               cls="independent_reporting", st="external_approved", method="third_party_filing")
        f["mention_relevance"] = "CONTEXTUALLY_RELEVANT"
        f["why_relevant"] = "an independent registrant's account of this company"
        filings.append(f)
    got = _picked(_site() + filings + [art])
    assert art["candidate_id"] in {c["candidate_id"] for c in got}
