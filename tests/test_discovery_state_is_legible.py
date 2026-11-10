"""A channel we could not reach is BLOCKED, not unsearched (§J).

MEASURED LIVE 2026-09-11 on the deployed preview, Highspot run
01M27S4339SG0PE8EEZPYDWP5A, on the evidence page:

    Search coverage: no search was run
    No discovery run is recorded for this analysis, so how hard we
    searched is unknown.

The identical code searched EDGAR successfully from a laptop minutes
earlier -- 47 hits for ZoomInfo, six documents fetched, coverage
DISCOVERY_EXHAUSTED. So the deployment was not declining to search; it was
failing to, and reporting the failure as never having tried.

`_third_party_filing_candidates` wrapped the whole search in

    except Exception:  # discovery must never break
        return []

and recorded nothing, so `discovery_report` stayed empty and every consumer
read DISCOVERY_NOT_RUN -- the state whose whole meaning is "no producer
ran". The same happened when the interactive budget was spent before
discovery was dispatched: a deliberate skip, reported as an absence.

"We looked and found nothing", "we could not look" and "we did not look" are
three different sentences, and the reader is owed the right one. This is the
distinction the module's own docstring calls the one inference it exists to
guard, so the states are asserted here rather than left to a comment.
"""
import pytest

from intent_engine.company_ingestion import relevance as REL
from intent_engine.company_ingestion.service import CompanyIngestionService


@pytest.fixture()
def service(tmp_path):
    return CompanyIngestionService(tmp_path / "ci.jsonl", transport=None,
                                   resolver=False)


def test_a_raising_search_records_blocked_not_silence(service, monkeypatch):
    """The live failure, reproduced: the search raises and the reader is told
    the channel was blocked -- never that no search was run."""
    import intent_engine.company_ingestion.third_party_filings as TPF

    def _boom(**kwargs):
        raise OSError("egress refused")

    monkeypatch.setattr(TPF, "discover_third_party_filings", _boom)
    out = service._third_party_filing_candidates(
        {"company_name": "Acme"}, run_id="run-1")
    assert out == []                     # the caller still gets no candidates
    report = service.discovery_report("run-1")
    assert report, "a raising search recorded nothing at all"
    assert report["coverage"] == REL.DISCOVERY_BLOCKED
    assert report["channels_attempted"] == ["edgar_full_text_search"]
    assert report["channels_successful"] == []
    assert any("DISCOVERY_RAISED" in k for k in report["rejection_reasons"])


def test_blocked_is_not_the_same_state_as_not_run():
    """The two states must stay distinguishable, or the repair is cosmetic."""
    assert REL.DISCOVERY_BLOCKED != REL.DISCOVERY_NOT_RUN


def test_a_zero_under_blocked_never_licenses_none_exists():
    """The inference this whole module guards.

    ASSERTED AS A PROPERTY, NOT AS A MISSING PHRASE. The first version of
    this test searched the statement for "no independent coverage exists"
    and failed -- on a statement that reads "...not evidence that no
    independent coverage exists", which is the disclaimer working exactly as
    intended. Testing for the ABSENCE of a string tests the spelling of the
    sentence, not the claim it makes.
    """
    blocked = REL.zero_reading(
        independent_relevant=0, coverage=REL.DISCOVERY_BLOCKED,
        channels_attempted=1, channels_successful=0)
    assert blocked["reading"] != REL.NONE_EXISTS if hasattr(
        REL, "NONE_EXISTS") else True
    assert blocked["reading"] == "FAILED_TO_FIND"
    # the sentence must CARRY the disclaimer, not merely avoid the claim
    assert "not evidence that" in blocked["statement"]

    # A POSITIVE CONTROL beside it: a search that genuinely ran and
    # exhausted its candidates is allowed to say more than a blocked one.
    exhausted = REL.zero_reading(
        independent_relevant=0, coverage=REL.DISCOVERY_EXHAUSTED,
        channels_attempted=1, channels_successful=1)
    assert exhausted["reading"] != blocked["reading"], (
        "a blocked channel and a completed search read the same, so the "
        "distinction this module exists for is not reaching the reader")


def test_an_empty_report_still_reads_not_run(service):
    """A run where discovery genuinely never started keeps the old state."""
    assert service.discovery_report("never-ran") == {}
