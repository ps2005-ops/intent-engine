"""What a reader is told when an analysis cannot finish.

MEASURED LIVE, deployed preview, 2026-08-05. A Datadog run reached the source
review step and `GET /runs/{id}` answered:

    Bad request
    approve at least one source

That is a framework status line and an internal exception message. It does not
say what the analysis established before it stopped, why it stopped, whether
anything is recoverable, or what to do next -- and "Bad request" tells a reader
that THEY did something wrong, when the run had simply not reached its next
step yet.

THE CONTRACT. Every customer-visible failure resolves to one named category.
Each category carries the four things a reader needs and nothing else:

    what_worked   what the product DID establish -- never nothing
    what_failed   the step that did not complete, in plain words
    why           the cause, at the reader's level of interest
    next_step     the one action worth taking, and whether retrying helps

Internal exception text never reaches a reader. It travels as `diagnostic`,
which is a short opaque id an operator can correlate with the logs.

WHY A TABLE AND NOT MESSAGES AT THE CALL SITES. There were three call sites
doing `return self._error_page(400, str(exc))` and each would have drifted on
its own. A category is a decision about what the reader is owed; a call site is
a place where an exception happened to be caught.
"""
from __future__ import annotations

COMPANY_RESOLUTION_FAILED = "COMPANY_RESOLUTION_FAILED"
RETRIEVAL_INSUFFICIENT = "RETRIEVAL_INSUFFICIENT"
RETRIEVAL_BLOCKED = "RETRIEVAL_BLOCKED"
PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
PROVIDER_CREDIT_EXHAUSTED = "PROVIDER_CREDIT_EXHAUSTED"
ANALYSIS_TIMEOUT = "ANALYSIS_TIMEOUT"
ANALYSIS_INTERRUPTED = "ANALYSIS_INTERRUPTED"
EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
REASONING_WITHHELD = "REASONING_WITHHELD"
MALFORMED_REASONING = "MALFORMED_REASONING"
RENDERING_FAILED = "RENDERING_FAILED"
PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
DEPLOYMENT_VERSION_MISMATCH = "DEPLOYMENT_VERSION_MISMATCH"
AWAITING_SOURCE_APPROVAL = "AWAITING_SOURCE_APPROVAL"
SHARE_LINK_UNAVAILABLE = "SHARE_LINK_UNAVAILABLE"
NOT_FOUND = "NOT_FOUND"
INTERNAL_FAILURE = "INTERNAL_FAILURE"

CATEGORIES = (
    COMPANY_RESOLUTION_FAILED, RETRIEVAL_INSUFFICIENT, RETRIEVAL_BLOCKED,
    PROVIDER_RATE_LIMITED, PROVIDER_CREDIT_EXHAUSTED, ANALYSIS_TIMEOUT,
    ANALYSIS_INTERRUPTED, EVIDENCE_INSUFFICIENT, REASONING_WITHHELD,
    MALFORMED_REASONING, RENDERING_FAILED, PERSISTENCE_FAILED,
    DEPLOYMENT_VERSION_MISMATCH, AWAITING_SOURCE_APPROVAL,
    SHARE_LINK_UNAVAILABLE, NOT_FOUND,
    INTERNAL_FAILURE,
)

#: category -> (title, what_failed, why, next_step, retryable)
#: `what_worked` is supplied per-call, because it is the only part that depends
#: on the particular run rather than on the kind of failure.
_COPY = {
    AWAITING_SOURCE_APPROVAL: (
        "This analysis is waiting for you",
        "The reading has not been built yet.",
        "Sources were found and are ready to review. Nothing is analysed "
        "until you confirm which of them to read.",
        "Review the sources and start the analysis.",
        False),
    COMPANY_RESOLUTION_FAILED: (
        "We could not tell which company this is",
        "The analysis did not start.",
        "The name and website did not resolve to one company. That usually "
        "means a shared name, a subsidiary rather than the group, or a site "
        "that does not identify its owner.",
        "Enter the company again with its full legal name, or the exact "
        "website of the entity you mean.",
        True),
    RETRIEVAL_INSUFFICIENT: (
        "There was not enough public evidence",
        "No reading could be built.",
        "Too few sources could be read to support a view worth acting on. A "
        "company can publish very little and still be perfectly healthy.",
        "Add an official page, report or filing you know of, or try again "
        "later.",
        True),
    RETRIEVAL_BLOCKED: (
        "The company's own sources refused automated access",
        "Most of the evidence could not be read.",
        "The site answered automated requests with a refusal or did not "
        "respond. This is a statement about the site's settings, not about "
        "the company.",
        "Add a source directly, or try again later.",
        True),
    PROVIDER_RATE_LIMITED: (
        "The analysis was rate limited",
        "The reading did not complete.",
        "An upstream service asked us to slow down. Nothing is wrong with "
        "the company or with what was retrieved.",
        "Wait a few minutes and run it again. Evidence already retrieved is "
        "kept.",
        True),
    PROVIDER_CREDIT_EXHAUSTED: (
        "The analysis service is temporarily unavailable",
        "The reasoning step did not run.",
        "The capacity that produces the written reading is exhausted. The "
        "evidence below was still retrieved and is still valid.",
        "Try again later. What was retrieved remains available now.",
        True),
    ANALYSIS_TIMEOUT: (
        "The analysis ran out of time",
        "The reading did not finish.",
        "Retrieval or reasoning took longer than the budget allows, usually "
        "because a source was slow to respond.",
        "Run it again — sources already retrieved are reused, so a second "
        "attempt is normally faster.",
        True),
    ANALYSIS_INTERRUPTED: (
        "The analysis was interrupted",
        "The reading did not finish.",
        "The service restarted while this run was in progress.",
        "Run it again.",
        True),
    EVIDENCE_INSUFFICIENT: (
        "The evidence did not support a reading",
        "No strategic view is asserted.",
        "Sources were read, but none of them supported a view strongly "
        "enough to put one forward. That absence is itself a finding.",
        "See what was established below, and add a source if you have one.",
        True),
    REASONING_WITHHELD: (
        "No reading cleared the evidence bar",
        "A recommendation is deliberately not given.",
        "What is public describes what this company does without supporting "
        "a strategic reading. Asserting one anyway would be a guess wearing "
        "the clothes of an analysis.",
        "See what was confirmed below.",
        False),
    MALFORMED_REASONING: (
        "The reading could not be assembled",
        "The written analysis did not come back usable.",
        "The reasoning step returned something this product could not verify "
        "against its evidence, so it was rejected rather than shown.",
        "Run it again. Rejecting it is the intended behaviour — an "
        "unverifiable reading is worse than none.",
        True),
    RENDERING_FAILED: (
        "This page could not be built",
        "The analysis exists but this view of it did not render.",
        "The underlying reading is intact; presenting it in this particular "
        "layout failed.",
        "Open the full analysis, or run it again.",
        True),
    PERSISTENCE_FAILED: (
        "This analysis could not be saved",
        "The result may not survive a restart.",
        "Storage on this environment is temporary, so completed analyses can "
        "be lost when the service restarts.",
        "Open anything you want to keep now.",
        False),
    DEPLOYMENT_VERSION_MISMATCH: (
        "This analysis was produced by an older version",
        "The stored result no longer matches the current product.",
        "The service was updated after this analysis ran.",
        "Run a fresh analysis.",
        True),
    SHARE_LINK_UNAVAILABLE: (
        "That shared link no longer works",
        "The analysis behind this link could not be opened.",
        "The link may have expired, been revoked by whoever shared it, or "
        "the analysis may have been cleared when the service restarted.",
        "Ask whoever shared it for a fresh link.",
        False),
    NOT_FOUND: (
        "That analysis is not available here",
        "Nothing could be opened.",
        "This session does not have an analysis with that id. Analyses are "
        "kept per session and are cleared when the service restarts.",
        "Start a new analysis.",
        False),
    INTERNAL_FAILURE: (
        "Something went wrong on our side",
        "The analysis did not complete.",
        "This is a fault in the product, not in what you entered or in the "
        "company.",
        "Run it again. If it keeps happening, the reference below identifies "
        "this run in our logs.",
        True),
}

#: Internal exception text -> category. Matched on substrings, because the
#: exceptions are raised by name in one place and read here in another; the
#: default is INTERNAL_FAILURE so an unmapped cause is never silently dressed
#: up as an explained one.
_SIGNATURES = (
    ("approve at least one source", AWAITING_SOURCE_APPROVAL),
    ("no approval recorded", AWAITING_SOURCE_APPROVAL),
    ("cannot fetch unknown candidates", INTERNAL_FAILURE),
    ("share link", SHARE_LINK_UNAVAILABLE),
    ("no such run", NOT_FOUND),
    ("could not resolve", COMPANY_RESOLUTION_FAILED),
    ("unknown company", COMPANY_RESOLUTION_FAILED),
    ("no approved source could be retrieved", RETRIEVAL_INSUFFICIENT),
    ("run byte budget exhausted", RETRIEVAL_INSUFFICIENT),
    ("rate limit", PROVIDER_RATE_LIMITED),
    ("credit", PROVIDER_CREDIT_EXHAUSTED),
    ("timed out", ANALYSIS_TIMEOUT),
    ("timeout", ANALYSIS_TIMEOUT),
)


def classify(message: str) -> str:
    """The category an internal failure message belongs to."""
    blob = (message or "").lower()
    for needle, category in _SIGNATURES:
        if needle in blob:
            return category
    return INTERNAL_FAILURE


def explain(category: str, *, what_worked: str = "") -> dict:
    """The four things a reader is owed, for one failure category."""
    if category not in _COPY:
        category = INTERNAL_FAILURE
    title, what_failed, why, next_step, retryable = _COPY[category]
    return {
        "category": category,
        "title": title,
        # NEVER EMPTY. A page that says only what went wrong reads as a dead
        # end; a reader who is told what WAS established can still act on it.
        "what_worked": what_worked or "Your request was received and the "
                                      "company you entered was recorded.",
        "what_failed": what_failed,
        "why": why,
        "next_step": next_step,
        "retryable": retryable,
    }
