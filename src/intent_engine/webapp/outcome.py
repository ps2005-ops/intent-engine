"""What actually happened to a customer's analysis. ONE producer.

WHY THIS EXISTS
---------------
Meta Platforms rendered "Analysis could not be completed" on two deployed
builds and was scored as a pass, because the validation instrument tested for
the literal string "Limited analysis" and this is a different page. Seven
sources were read; four belonged to Oklo, Enbridge, Network-1 and RingCentral;
one was usable. One of the most heavily documented companies in the world was
reported to a customer as unanalysable, and to me as green.

The lesson is not "add the other string". It is that a customer outcome was
being inferred, separately, by every surface and every instrument, from the
words on a page. Words are a rendering of the outcome, not the outcome.

    TERMINAL is not SUCCESS.
    HTTP 200 is not SUCCESS.
    A non-empty page is not SUCCESS.
    A route existing is not SUCCESS.

So the outcome is computed once, named, and consumed everywhere: the progress
page, the run page, the six steps, the capture harness and the audit all read
the SAME value rather than each deciding for itself.

WHAT THE STATES MEAN
--------------------
The distinction that matters most is between evidence that is genuinely thin
and retrieval that did not work. Both used to render the same apologetic page,
which let retrieval defects hide behind honest-sounding copy.
"""
from __future__ import annotations

#: The complete analysis. Everything downstream may be rendered.
FULL_ANALYSIS = "FULL_ANALYSIS"
#: A complete analysis that is being refreshed against newer evidence.
FULL_ANALYSIS_REFRESHING = "FULL_ANALYSIS_REFRESHING"
#: The subject's evidence WAS correctly searched, prioritised and retrieved,
#: and there genuinely is not enough public material to support the whole
#: product. The only state that may render the customer-facing bounded page.
TRUE_EVIDENCE_SCARCITY = "TRUE_EVIDENCE_SCARCITY"
#: Retrieval did not work. Sources refused, timed out, failed to parse, or the
#: subject's own documents were displaced by somebody else's. An operational
#: fault, never a statement about the company.
RETRIEVAL_TEMPORARILY_UNAVAILABLE = "RETRIEVAL_TEMPORARILY_UNAVAILABLE"
#: A provider or this service refused the volume of requests.
RATE_LIMITED = "RATE_LIMITED"
#: The engine raised, or composition produced nothing readable.
ANALYSIS_FAILED = "ANALYSIS_FAILED"
#: The instance that held the run was replaced.
RUN_RESTART_LOST = "RUN_RESTART_LOST"
#: Still working, nothing readable yet.
WORKING = "WORKING"

OUTCOMES = (FULL_ANALYSIS, FULL_ANALYSIS_REFRESHING, TRUE_EVIDENCE_SCARCITY,
            RETRIEVAL_TEMPORARILY_UNAVAILABLE, RATE_LIMITED, ANALYSIS_FAILED,
            RUN_RESTART_LOST, WORKING)

#: Outcomes that mean the customer has a usable intelligence product.
SUCCESSFUL = frozenset({FULL_ANALYSIS, FULL_ANALYSIS_REFRESHING})
#: Outcomes that are OUR fault rather than a statement about the company.
OPERATIONAL_FAILURE = frozenset({RETRIEVAL_TEMPORARILY_UNAVAILABLE,
                                 RATE_LIMITED, ANALYSIS_FAILED,
                                 RUN_RESTART_LOST})
#: Terminal from the reader's point of view.
TERMINAL = frozenset(OUTCOMES) - {WORKING}

#: The name of the meta tag every customer-facing run page carries, so a
#: harness reads the OUTCOME rather than guessing from prose. A string match
#: is what falsely passed Meta; this is the metadata that replaces it.
META_NAME = "x-analysis-outcome"


def classify(*, readiness, run_state="", exhaustion=None) -> str:
    """The one decision. Never raises, never returns something unnamed.

    `readiness` is `WebApp.result_readiness(...)`, which already answers "is
    there something readable". This adds the two questions that were missing:
    is what is readable the WHOLE product, and when it is not, whose fault is
    that?

    `exhaustion` is `WebApp.evidence_report(...)`. It is what separates thin
    evidence from failed retrieval, and without it this REFUSES to claim
    scarcity -- an unexplained stop is an operational fault until something
    proves otherwise. Guessing the other way is how one of the most heavily
    documented companies in the world was reported as unanalysable.
    """
    readiness = readiness or {}
    report = exhaustion or {}
    state = str(run_state or readiness.get("state") or "")
    in_flight = bool(readiness.get("in_flight"))

    if readiness.get("opens_result") and not readiness.get("degraded"):
        # A composed strategic report: the whole product. Still refreshing is
        # a different, and honest, kind of complete.
        return FULL_ANALYSIS_REFRESHING if in_flight else FULL_ANALYSIS

    if state in ("INTERRUPTED", "RUN_RESTART_LOST"):
        return RUN_RESTART_LOST
    if not readiness.get("terminal") and state not in ("FAILED", "REJECTED"):
        return WORKING

    # EVERYTHING BELOW IS A BOUNDED PAGE OR A FAILURE PAGE, and the only
    # question left is which of them the customer is owed. THE BOUNDED PAGE
    # IS NOT A GRACEFUL FALLBACK FOR BROKEN RETRIEVAL. It is a statement
    # about the company, and it may only be made when the company's own
    # material was actually looked for and actually arrived.
    if report.get("rate_limited"):
        return RATE_LIMITED
    if report.get("displaced_by_foreign"):
        # Documents arrived; none of them were this company's. Meta's run
        # read seven sources of which four were filed by other registrants.
        return RETRIEVAL_TEMPORARILY_UNAVAILABLE
    # A COMPANY WHOSE OWN SITE REFUSED US IS NOT A THINLY DOCUMENTED
    # COMPANY. This check sits ABOVE the scarcity branch, and the ordering
    # is the whole point: the first version put scarcity first, so a run
    # with recorded refusals against the subject's own domain still told the
    # customer their evidence was thin. That is precisely the confusion the
    # top of this file says the states exist to prevent, reintroduced by the
    # order of two `if`s.
    #
    # MEASURED on dc17a9d: goldmansachs.com and mastercard.com answer 403 to
    # this service's user agent and costco.com times out, while nike.com,
    # walmart.com and coca-colacompany.com answer 200 -- and those three are
    # exactly the Wave-3 companies that produced a full analysis.
    if report.get("subject_failures"):
        return RETRIEVAL_TEMPORARILY_UNAVAILABLE
    if report.get("attempted") and report.get("subject_retrieval_ok"):
        return TRUE_EVIDENCE_SCARCITY
    if report.get("retrieval_failures") or report.get("attempted") is False:
        return RETRIEVAL_TEMPORARILY_UNAVAILABLE
    if not readiness.get("opens_result") and state in ("FAILED", "REJECTED"):
        return ANALYSIS_FAILED
    # NO REPORT AT ALL, or a bounded page whose evidence cannot be accounted
    # for. Refuse to call it scarcity on no information.
    return RETRIEVAL_TEMPORARILY_UNAVAILABLE


def is_success(outcome: str) -> bool:
    return outcome in SUCCESSFUL


def expected_full(*, cik: str = "", domain: str = "",
                  recent_filings: int = 0) -> bool:
    """Should this company be expected to yield a complete analysis?

    Derived from observable characteristics, never from a list of company
    names -- a hard-coded exception for Meta would pass Meta and keep failing
    Microsoft. A registrant with recent filings, or a company with a known
    official domain, has abundant public evidence by construction.
    """
    return bool((cik and recent_filings >= 2) or (cik and domain) or
                (domain and recent_filings >= 1))
