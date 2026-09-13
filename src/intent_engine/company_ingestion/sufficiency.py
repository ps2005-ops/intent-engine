"""When does CORE already have enough evidence to stop making the reader wait?

THE QUESTION THIS ANSWERS
-------------------------
Acquisition used to run to the end of the approved list -- fourteen sources --
and only then ask whether the evidence was any good. `readiness.assess_readiness`
is the product's own declared contract for "this may become a full report", and
it was consulted AFTER every source had been paid for.

MEASURED locally, replaying each run's documents in retrieval order and asking
the contract after every one (docs/PRE100_MINIMUM_CORE_PREREGISTRATION.md):

    NVIDIA           13 documents fetched, READY_FOR_FULL_REPORT at 5
    Microsoft         8 documents fetched, READY_FOR_FULL_REPORT at 5
    JPMorgan Chase   10 documents fetched, READY_FOR_FULL_REPORT at 8

and in every case the state never changed again. Two to eight documents per
run were acquired after the contract the product itself declares was already
satisfied, with the customer waiting on every one.

WHAT THIS IS NOT
----------------
It is NOT a smaller evidence set. Nothing is dropped: acquisition stops
BLOCKING, the remaining approved sources are handed to the post-`core_ready`
continuation, and a source that never arrives is recorded as a gap the reader
is shown. "Fetch fewer sources" and "make the reader wait for fewer sources"
are different changes, and only the second one is here.

It is NOT a fixed document count. A sparse or contradictory company needs more
evidence and will keep acquiring until the contract closes or the budget ends;
a heavily documented one closes early. The stopping condition is the contract,
which is why it generalises to a company nobody has run.

WHY THE CONTRACT AND NOT A NEW RULE
-----------------------------------
Writing a second definition of "enough evidence" beside the one that decides
whether a report may be published would let acquisition stop on one standard
while composition refused on another -- and the run would be fast because it
had stopped producing a product, which this project has already shipped once.
`assess_readiness` is the only definition, consulted twice.
"""
from __future__ import annotations

from intent_engine.company_ingestion.readiness import (
    READY_FOR_FULL_REPORT, assess_readiness,
)

#: A floor beneath the contract, in documents. `assess_readiness` can reach
#: READY_FOR_FULL_REPORT on unusually generous evidence, and stopping at two
#: sources would leave a report with no room to lose one to a later quality
#: check. This never lets acquisition stop EARLIER than the contract -- it only
#: refuses to stop earlier than this.
MIN_CORE_DOCUMENTS = 4

#: The subject's OWN authoritative filing, when the subject is a filer, is not
#: interchangeable with a third party's mention of it. A run may not declare
#: itself sufficient while the one document the regulator holds in the
#: company's own name is still queued.
REQUIRE_SUBJECT_FILING_WHEN_FILER = True


class Sufficiency(dict):
    """{sufficient, reason, state, documents, checks_unmet}"""


def _subject_filing_present(documents, subject_cik: str) -> bool:
    import re
    digits = "".join(c for c in str(subject_cik or "") if c.isdigit())
    want = digits.lstrip("0")
    if not want:
        return True                     # not a filer: nothing to wait for
    for document in documents:
        # `original_url`/`final_url` ARE THE KEYS `retrieved_record` WRITES.
        # There is no `url`, so reading one made this scan return False for
        # every document -- and a guard that can never be satisfied is not a
        # weaker guard, it is a different behaviour: with a CIK resolved,
        # CORE waited for the whole approved list again.
        #
        # MEASURED before the fix: Apple blocked on 11 of 14 and deferred 0,
        # NVIDIA on 12 of 14 and deferred 0, with the subject's own filing
        # sitting at position 2 in both. The unit test passed throughout,
        # because its fixture used `url` -- the key production does not write.
        for key in ("original_url", "final_url", "url"):
            match = re.search(r"/edgar/data/(\d+)",
                              str(document.get(key) or ""))
            if match and match.group(1).lstrip("0") == want:
                return True
    return False


def evaluate(documents, *, identity=None, failures=(), subject_cik="",
             pending: int = 0) -> Sufficiency:
    """Whether CORE may stop BLOCKING on further acquisition.

    `pending` is how many approved sources have not been fetched. It is
    reported, never consulted: a run that is sufficient is sufficient whether
    one source remains or nine, and letting the queue length decide would make
    the stopping point a fact about discovery rather than about the evidence.
    """
    documents = list(documents)
    if len(documents) < MIN_CORE_DOCUMENTS:
        return Sufficiency(sufficient=False, state="",
                           reason=f"{len(documents)} document(s); at least "
                                  f"{MIN_CORE_DOCUMENTS} before the contract "
                                  f"is consulted",
                           documents=len(documents), pending=pending,
                           checks_unmet=[])
    verdict = assess_readiness(documents=documents, identity=identity,
                               failures=list(failures))
    state = verdict.get("state")
    if state != READY_FOR_FULL_REPORT:
        return Sufficiency(sufficient=False, state=state,
                           reason=f"readiness is {state}",
                           documents=len(documents), pending=pending,
                           checks_unmet=list(verdict.get("unmet_checks") or ()))
    if REQUIRE_SUBJECT_FILING_WHEN_FILER and not _subject_filing_present(
            documents, subject_cik):
        return Sufficiency(
            sufficient=False, state=state,
            reason="the subject's own EDGAR filing has not been read yet",
            documents=len(documents), pending=pending, checks_unmet=[])
    return Sufficiency(sufficient=True, state=state,
                       reason="the readiness contract is satisfied",
                       documents=len(documents), pending=pending,
                       checks_unmet=[])
