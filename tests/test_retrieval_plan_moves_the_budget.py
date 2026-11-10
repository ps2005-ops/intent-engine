"""A refusing website must not decide how much evidence a run may have.

MEASURED on 743df06 across the 50-company gauntlet. Twelve of fifty companies
composed on SEC filings alone, capped at three, because the retrieval budget
was being spent on hosts that answer 403 to this deployment's egress:

    Goldman Sachs   failed=26/24   compose=3 families=investor
    Mastercard      failed=24/22   compose=3 families=investor
    Union Pacific   failed=27/24   compose=2 families=investor
    UPS (no domain) failed=1/0     compose=2 families=investor

`lilly.com` answers 200 to the same User-Agent from a laptop and refused this
service seventeen times, so this is the egress being refused rather than a
User-Agent being detected -- which is why the repair is to spend the budget
where it is served, not to try the same host differently.
"""
from company_fixture_pages import BASE, transport
from intent_engine.company_ingestion.edgar import (
    MAX_EDGAR_CANDIDATES, MAX_EDGAR_CANDIDATES_WEB_BLOCKED,
)
from intent_engine.company_ingestion.service import (
    OFFICIAL_WEB_ABSENT, OFFICIAL_WEB_BLOCKED, OFFICIAL_WEB_RETRIEVED,
    CompanyIngestionService,
)

AS_OF = "2026-08-21T00:00:00+00:00"


def _service(tmp_path, tr=transport):
    return CompanyIngestionService(tmp_path / "ci.jsonl", transport=tr,
                                   resolver=False)


def _refusing(url, timeout, *a):
    """Every request answered 403, exactly as goldmansachs.com does."""
    import email
    import urllib.error
    raise urllib.error.HTTPError(url, 403, "forbidden",
                                 email.message_from_string(""), None)


def test_a_site_that_answers_keeps_the_ordinary_budget(tmp_path):
    """THE CONTROL. Nothing changes for a company we can actually read."""
    ci = _service(tmp_path)
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    ci.discover(run["run_id"])
    plan = ci.retrieval_plan(run["run_id"])
    assert plan["official_web"] == OFFICIAL_WEB_RETRIEVED, plan


def test_a_refusing_site_is_named_as_blocked_not_as_thin_evidence(tmp_path):
    ci = _service(tmp_path, tr=_refusing)
    run = ci.create_run(company_name="The Goldman Sachs Group, Inc.",
                        website="https://www.goldmansachs.com",
                        user_id="u", as_of=AS_OF)
    ci.discover(run["run_id"])
    assert ci.retrieval_plan(run["run_id"])["official_web"] \
        == OFFICIAL_WEB_BLOCKED


def test_a_run_with_no_domain_says_absent_not_blocked(tmp_path):
    """A site we never had is not a site that refused us."""
    ci = _service(tmp_path, tr=_refusing)
    run = ci.create_run(company_name="United Parcel Service, Inc.",
                        website="", cik="1090727", user_id="u", as_of=AS_OF)
    ci.discover(run["run_id"])
    assert ci.retrieval_plan(run["run_id"])["official_web"] \
        == OFFICIAL_WEB_ABSENT


def test_the_plan_is_empty_before_discovery_runs(tmp_path):
    """An empty dict means nobody looked, never "nothing was available"."""
    ci = _service(tmp_path)
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    assert ci.retrieval_plan(run["run_id"]) == {}


def test_the_blocked_budget_is_strictly_larger_and_is_the_one_used(tmp_path):
    """The number the blocked path asks EDGAR for is the wider one.

    Pinned as literals rather than by re-reading the constants: a test that
    asserts `X == X` cannot fail when someone sets both to three.
    """
    assert MAX_EDGAR_CANDIDATES == 3
    assert MAX_EDGAR_CANDIDATES_WEB_BLOCKED == 5

    asked = []
    import intent_engine.company_ingestion.service as svc
    real = svc.propose_edgar_candidates

    def spy(**kw):
        asked.append(kw.get("limit"))
        return []
    svc.propose_edgar_candidates = spy
    try:
        ci = _service(tmp_path, tr=_refusing)
        blocked = ci.create_run(company_name="Mastercard Incorporated",
                                website="https://www.mastercard.com",
                                user_id="u", as_of=AS_OF)
        ci.discover(blocked["run_id"])

        ci2 = _service(tmp_path / "b", tr=transport)
        (tmp_path / "b").mkdir(exist_ok=True)
        ok = ci2.create_run(company_name="Brightlake", website=BASE,
                            user_id="u", as_of=AS_OF)
        ci2.discover(ok["run_id"])
    finally:
        svc.propose_edgar_candidates = real
    assert asked == [5, 3], asked
