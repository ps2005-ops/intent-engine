"""§: an analysis that never started may not claim work it never did.

MEASURED LIVE on 25409f14 under deliberate admission pressure: capacity is
one active plus three pending, six near-simultaneous submissions produced four
admitted runs and two 503 refusals — and the refusal page told the reader:

    What did work.  The company was identified and its public evidence was
                    retrieved.
    What did not.   The reasoning step did not run.
    Why.            ... The evidence below was still retrieved and is still
                    valid.
    Next.           Try again later. What was retrieved remains available now.

Four statements about work that never happened, because the refusal message
contains "NO ANALYSIS CREDIT WAS USED" and `_SIGNATURES` matched the bare
needle "credit".
"""
from __future__ import annotations

import inspect

from intent_engine.webapp import failures as F
from intent_engine.webapp.app import WebApp

REFUSAL = ("This preview is already running as many analyses as it can at "
           "once. Nothing was fetched and NO ANALYSIS CREDIT WAS USED — try "
           "again in a few minutes.")

#: Phrases that are true of a run that DID work and false of one that never
#: started. Any of them on an admission-refusal page is a lie to the reader.
_CLAIMS_OF_WORK = (
    "evidence was retrieved", "was still retrieved", "what was retrieved",
    "the evidence below", "reasoning step did not run",
)


def test_the_refusal_message_no_longer_classifies_as_credit_exhaustion():
    assert F.classify(REFUSAL) == F.ADMISSION_REFUSED, (
        "our own reassurance about credit is being read as credit exhaustion")


def test_the_refusal_page_claims_no_work_it_did_not_do():
    explained = F.explain(F.ADMISSION_REFUSED)
    blob = " ".join(str(explained[k]).lower() for k in
                    ("what_worked", "what_failed", "why", "next_step"))
    for claim in _CLAIMS_OF_WORK:
        assert claim not in blob, f"the page claims {claim!r} on a run that " \
                                  f"never started"
    # POSITIVE CONTROL: the detector must be able to fire. The category this
    # was misclassified as says every one of those things.
    credit = F.explain(F.PROVIDER_CREDIT_EXHAUSTED)
    credit_blob = " ".join(str(credit[k]).lower() for k in
                           ("what_worked", "what_failed", "why", "next_step"))
    assert any(c in credit_blob for c in _CLAIMS_OF_WORK), (
        "the detector cannot distinguish the two pages, so it proves nothing")


def test_the_refusal_is_terminal_and_retryable_and_says_so():
    explained = F.explain(F.ADMISSION_REFUSED)
    assert explained["retryable"] is True
    assert "try again" in explained["next_step"].lower()
    # It must not read as an analysis failure, and must not read as a finding.
    assert "did not start" in explained["title"].lower()
    assert "not a finding about the company" in explained["why"].lower()


def test_admission_refusal_is_not_an_abstention():
    """An abstention means the investigation RAN and could not conclude.

    Counting a refusal as one would let infrastructure pressure be reported
    as analytical judgement, which is how a usefulness gate gets passed by
    building prettier error pages.
    """
    refused = F.explain(F.ADMISSION_REFUSED)
    abstained = F.explain(F.EVIDENCE_INSUFFICIENT)
    assert refused["category"] != abstained["category"]
    assert refused["title"] != abstained["title"]
    assert "nothing was fetched" in refused["what_failed"].lower()


def test_the_admission_call_site_names_the_category_itself():
    """A branch that KNOWS the cause may not infer it from its own wording.

    The whole defect was a substring test reading our own sentence. Pinning
    the call site, not just the table, is what stops the next edit to that
    sentence from silently reclassifying the page.
    """
    source = inspect.getsource(WebApp._analyze) \
        if hasattr(WebApp, "_analyze") else ""
    if not source:
        for name in dir(WebApp):
            fn = getattr(WebApp, name, None)
            try:
                candidate = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            if "already running as many" in candidate:
                source = candidate
                break
    assert source, "the admission refusal call site was not found"
    code = "\n".join(line for line in source.split("\n")
                     if not line.strip().startswith("#"))
    assert "_failures.ADMISSION_REFUSED" in code, (
        "the admission branch does not name its category; it is relying on "
        "substring classification of its own message")


def test_error_page_accepts_an_explicit_category():
    signature = inspect.signature(WebApp._error_page)
    assert "category" in signature.parameters
