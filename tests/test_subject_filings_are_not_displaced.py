"""A third party's filing may not take the subject's slot.

MEASURED LIVE on 49b6c3a and 517e7ae, and again by a customer on the deployed
build. Meta Platforms -- one of the most heavily documented public companies
in existence -- read seven sources of which four belonged to other
registrants, produced one usable source, fell below the evidence floor, and
told the reader the analysis could not be completed.

    1326801  Meta Platforms, Inc.      the subject
    1849056  Oklo Inc.
     895728  Enbridge Inc
    1065078  Network-1 Technologies
    1384905  RingCentral, Inc.

Each of those filings does mention Meta, so finding them is correct. Ranking
them LEVEL with Meta's own 10-K is not: `_recommended_candidate_ids` returned
1 for `"SEC EDGAR" in why` and 1 for `third_party_filing`.

Why Meta and not the other nine Wave-1 companies: Meta is the only one with no
domain on record, so it has no homepage and no sitemap candidates and the
whole pool is EDGAR. With a domain, the other families absorb the collision.

Ownership is not a source_class. `/edgar/data/<CIK>/` names the FILER, so it
is decided from the URL.
"""
import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

SUBJECT_CIK = "1326801"


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "f.jsonl",
                            ci_store_path=tmp_path / "c.jsonl"),
                  transport=_no_network, resolver=False)


def _candidate(cid, url, *, method="external_proposed",
               why="SEC EDGAR filing", source_class="investor_material"):
    """The shape `propose_edgar_candidates` and `propose_third_party_filings`
    actually emit: source_type external_approved, source_class
    investor_material. Copied from the producers rather than invented -- a
    fixture that carries different keys tests the fixture."""
    return {"candidate_id": cid, "url": url, "discovery_method": method,
            "why_relevant": why, "source_type": "external_approved",
            "source_class": source_class}


#: The real shape of the live pool: the subject's own filings, and four other
#: registrants whose filings mention it.
SUBJECT = [
    _candidate("s1", "https://www.sec.gov/Archives/edgar/data/1326801/a/10k.htm"),
    _candidate("s2", "https://www.sec.gov/Archives/edgar/data/1326801/b/10q.htm"),
    _candidate("s3", "https://www.sec.gov/Archives/edgar/data/1326801/c/8k.htm"),
]
#: THE CASE THE URL CHECK EXISTS FOR. `propose_edgar_candidates` searches by
#: NAME, so a filing by another registrant that merely mentions the subject
#: arrives with the SAME discovery_method, the SAME source_class and the SAME
#: why_relevant as the subject's own. Nothing but the CIK in the URL tells
#: them apart. A fixture whose contaminants are tagged `third_party_filing`
#: is already separable without reading ownership at all -- which is why
#: three mutations of the ownership check ran green against it.
NAME_MATCHED_OTHERS = [
    _candidate("n1", "https://www.sec.gov/Archives/edgar/data/1849056/y/10k.htm"),
    _candidate("n2", "https://www.sec.gov/Archives/edgar/data/895728/y/10k.htm"),
    _candidate("n3", "https://www.sec.gov/Archives/edgar/data/1065078/y/10k.htm"),
    _candidate("n4", "https://www.sec.gov/Archives/edgar/data/1384905/y/10k.htm"),
]
OTHERS = [
    _candidate("o1", "https://www.sec.gov/Archives/edgar/data/1849056/x/10k.htm",
               method="third_party_filing", why="SEC EDGAR full-text mention"),
    _candidate("o2", "https://www.sec.gov/Archives/edgar/data/895728/x/10k.htm",
               method="third_party_filing", why="SEC EDGAR full-text mention"),
    _candidate("o3", "https://www.sec.gov/Archives/edgar/data/1065078/x/10k.htm",
               method="third_party_filing", why="SEC EDGAR full-text mention"),
    _candidate("o4", "https://www.sec.gov/Archives/edgar/data/1384905/x/10k.htm",
               method="third_party_filing", why="SEC EDGAR full-text mention"),
]


def _approve(app, run_id, candidates):
    """Call it the way the three production call sites do.

    They all pass `subject_cik` from `run_meta`. A helper that omitted it was
    testing a signature production never uses, and made the ownership check
    look broken when it was the harness that was not asking.
    """
    return app._recommended_candidate_ids(
        candidates, refusing_hosts=(),
        subject_cik=(app.ci.run_meta(run_id) or {}).get("cik"))


def _as_subject(app, cik=SUBJECT_CIK):
    app.ci.run_meta = lambda run_id: {"cik": cik, "domain": ""}


def test_the_subjects_own_filings_are_approved_before_any_third_party(app):
    """THE LIVE DEFECT. Four other registrants displaced Meta's own filings."""
    _as_subject(app)
    approved = _approve(app, "run-1", OTHERS + SUBJECT)
    assert approved, "nothing was approved at all"
    subject_ids = {c["candidate_id"] for c in SUBJECT}
    first_three = approved[:3]
    assert set(first_three) <= subject_ids, (
        f"a third party took a subject slot: {approved}")


def test_every_subject_filing_survives_a_pool_full_of_mentions(app):
    """Not merely 'first' -- none may be crowded out."""
    _as_subject(app)
    approved = set(_approve(app, "run-1", OTHERS * 3 + SUBJECT))
    for c in SUBJECT:
        assert c["candidate_id"] in approved, (
            f"{c['candidate_id']} was displaced by third-party mentions")


def test_a_leading_zero_cik_still_matches_its_own_filings(app):
    """The registry serves 1326801; the form submits 0001326801."""
    _as_subject(app, cik="0001326801")
    approved = _approve(app, "run-1", OTHERS + SUBJECT)
    assert set(approved[:3]) <= {c["candidate_id"] for c in SUBJECT}, approved


def test_third_party_filings_are_still_offered_not_discarded(app):
    """THE POSITIVE CONTROL. They are useful supplementary evidence; the
    defect was the slot they took, not their existence."""
    _as_subject(app)
    approved = _approve(app, "run-1", SUBJECT + OTHERS)
    assert any(cid in approved for cid in ("o1", "o2", "o3", "o4")), (
        "third-party filings must remain available as context")


def test_a_run_with_no_subject_cik_is_unchanged(app):
    """A private company has no CIK, and nothing here may change its pool."""
    app.ci.run_meta = lambda run_id: {"cik": "", "domain": "stripe.com"}
    approved = _approve(app, "run-1", OTHERS + SUBJECT)
    assert approved, "a run without a CIK must still approve candidates"


def test_a_name_matched_foreign_filing_is_separated_by_its_cik_alone(app):
    """The only signal is the CIK in the URL.

    These candidates carry the subject's own discovery_method, source_class
    and why_relevant, because that is what a name-based EDGAR search emits.
    If ownership is not read from the URL, nothing separates them.
    """
    _as_subject(app)
    approved = _approve(app, "run-1", NAME_MATCHED_OTHERS + SUBJECT)
    subject_ids = {c["candidate_id"] for c in SUBJECT}
    assert set(approved[:3]) <= subject_ids, (
        f"a foreign registrant's filing outranked the subject's own: "
        f"{approved}")


def test_the_subject_is_not_demoted_by_its_own_cik_check(app):
    """The mirror-image failure: if the check answers False for everything,
    the subject's filings sink to context rank behind the contaminants."""
    _as_subject(app)
    approved = _approve(app, "run-1", NAME_MATCHED_OTHERS + SUBJECT)
    for c in SUBJECT:
        assert approved.index(c["candidate_id"]) < 4, (
            f"{c['candidate_id']} ranked behind foreign filings: {approved}")


def test_a_padded_cik_still_separates_name_matched_filings(app):
    _as_subject(app, cik="0001326801")
    approved = _approve(app, "run-1", NAME_MATCHED_OTHERS + SUBJECT)
    assert set(approved[:3]) <= {c["candidate_id"] for c in SUBJECT}, approved
