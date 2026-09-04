"""One company's competitor list is not another company's competitor list.

MEASURED LIVE on ebd0a6f. Meta Platforms' deployed Full Analysis carried:

    AT&T Inc: Meta Platforms, Inc. names it as a competitor in its own
    filing — our competitors include but are not limited to: 8x8, Inc.,
    Dialpad, Inc., LogMeIn, Inc., Microsoft Corporation, Nextiva, Inc.,
    Twilio Inc., Ericsson, Zoom, Amazon.com, Inc., AT&T I

That sentence is RINGCENTRAL'S. RingCentral is a UCaaS company; 8x8,
Dialpad, Nextiva and Zoom are ITS rivals. Its 10-K was retrieved because it
mentions Meta, and the extractor read the list as though Meta had written
it — then published every name at rung 1, NAMED_BY_SUBJECT, under an
attribution that was false: "names it as a competitor in its own filing".

The evidence drawer had the source class right the whole time ("a
regulatory filing written by another company"). `subject_text` and
`competition_text` both filter on it, and both document why. `_named_rivals`
— which feeds rung 1 and therefore OUTRANKS both — was handed every
document in the run.

A claim belongs to whoever made it.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import strategic_read as SR

SUBJECT = "Meta Platforms, Inc."

#: The exact shape that shipped: a third party's own competitor sentence.
_RIVAL_FILING = (
    "Our competitors include but are not limited to: 8x8, Inc., Dialpad, "
    "Inc., LogMeIn, Inc., Microsoft Corporation, Nextiva, Inc., Twilio Inc., "
    "Ericsson, Zoom, Amazon.com, Inc., AT&T Inc. We also reference Meta "
    "Platforms, Inc. in describing the market.")

_OWN_FILING = ("Competition. We compete with companies providing connection, "
               "sharing, discovery and communication products online.")


def _doc(source_class, text, url):
    return {"source_class": source_class, "text_content": text,
            "final_url": url, "title": "10-K"}


def _capture(monkeypatch):
    """Record exactly which documents reach the extractor."""
    seen = {}

    # **kwargs ON PURPOSE. `_named_rivals` swallows every exception, so a
    # double whose signature has drifted from the producer's returns an
    # empty list and this test reports the OPPOSITE defect — no documents
    # reached the extractor — with no sign of the TypeError that caused it.
    def fake_find(documents, *, subject, limit=4, **kwargs):
        seen["documents"] = list(documents)
        seen["kwargs"] = kwargs
        return ()

    import intent_engine.external_intel.competitor_finder as CF
    monkeypatch.setattr(CF, "find_competitors", fake_find)
    return seen


def test_a_third_party_filing_never_reaches_the_rival_extractor(monkeypatch):
    """THE defect. RingCentral's filing must not be read as Meta's."""
    seen = _capture(monkeypatch)
    SR._named_rivals(SUBJECT, [
        _doc("investor_material", _OWN_FILING, "https://sec.gov/meta"),
        _doc("competitor", _RIVAL_FILING, "https://sec.gov/rng"),
        _doc("independent_reporting", _RIVAL_FILING, "https://sec.gov/rng2"),
    ])
    urls = [d["final_url"] for d in seen.get("documents", [])]
    assert urls == ["https://sec.gov/meta"], urls


@pytest.mark.parametrize("source_class", ["competitor",
                                          "independent_reporting",
                                          "customer_voice"])
def test_no_class_outside_the_subjects_own_publications_is_read(
        monkeypatch, source_class):
    seen = _capture(monkeypatch)
    SR._named_rivals(SUBJECT, [_doc(source_class, _RIVAL_FILING,
                                    "https://sec.gov/other")])
    assert seen.get("documents", []) == []


@pytest.mark.parametrize("source_class", ["investor_material",
                                          "executive_statement",
                                          "company_owned"])
def test_the_subjects_own_publications_are_still_read(monkeypatch,
                                                      source_class):
    """The repair must not silence the company's own filing."""
    seen = _capture(monkeypatch)
    SR._named_rivals(SUBJECT, [_doc(source_class, _OWN_FILING,
                                    "https://sec.gov/meta")])
    assert len(seen.get("documents", [])) == 1


def test_a_run_holding_only_third_party_filings_names_no_rivals(monkeypatch):
    """Better no rival than another company's rival.

    This is the honest cost of the repair and it is the right trade: a run
    whose only competitive text belongs to somebody else has established
    nothing about the subject's market.
    """
    _capture(monkeypatch)
    assert SR._named_rivals(SUBJECT, [
        _doc("competitor", _RIVAL_FILING, "https://sec.gov/rng")]) == ()


def test_a_classless_document_is_not_treated_as_the_subjects_own(monkeypatch):
    """An absent class is not permission. Default-open is how this shipped."""
    seen = _capture(monkeypatch)
    SR._named_rivals(SUBJECT, [{"text_content": _RIVAL_FILING,
                                "final_url": "https://sec.gov/x"}])
    assert seen.get("documents", []) == []
