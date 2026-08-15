"""Independent is not the same as relevant, and one number cannot say both.

THE MEASURED CASE. On the deployed preview, Cloudflare's SOLE independent
origin was EVENTIKO INC.'s 10-K. Fetched from EDGAR, that filing names
Cloudflare exactly once, in 77,627 characters:

    "All hosting and hosting related services of these websites are engaged
     via reputable companies such as Namecheap, Godaddy and Cloudflare."

A genuinely independent registrant. Also a sentence about EVENTIKO's own
hosting arrangements, carrying nothing about Cloudflare's strategy, market or
competitive position. Counting it produced PARTIALLY_INDEPENDENT when the
honest reading is that nothing independent AND relevant supports the claim.

The hazard on this side is the opposite one: over-refusing deletes real
independent observations, and the independent count is already scarce. So
only a POSITIVE finding of irrelevance demotes, and half of this file is the
controls that prove the wall did not become a shredder.
"""
import pytest

from intent_engine.company_ingestion import independence as IND
from intent_engine.company_ingestion import relevance as R

NAME = "Cloudflare, Inc."
DOMAIN = "cloudflare.com"
SUBJECT = dict(subject_name=NAME, subject_domain=DOMAIN)

# The real sentence, from the real filing.
EVENTIKO = (
    "Table of Contents. U.S. SECURITIES AND EXCHANGE COMMISSION. Form 10-K. "
    "All hosting and hosting related services of these websites are engaged "
    "via reputable companies such as Namecheap, Godaddy and Cloudflare. "
    "These aforementioned companies utilize the latest industrial standards "
    "for security and data protection.")

RIVAL = (
    "We compete with Cloudflare in the edge security market. Several "
    "enterprise customers migrated to Cloudflare during the year, and "
    "pricing pressure from Cloudflare reduced our renewal revenue.")

CUSTOMER = (
    "Our infrastructure spend rose after we expanded our contract with "
    "Cloudflare to cover additional regions.")


def _doc(text, url="https://www.sec.gov/Archives/edgar/data/1816554/x/y.htm"):
    return {"final_url": url, "source_class": "competitor", "filing": True,
            "content_hash": text[:12], "text_content": text}


# --- the adjudication -------------------------------------------------------

def test_the_real_eventiko_sentence_is_irrelevant():
    """The exact live case, adjudicated."""
    got = R.adjudicate(_doc(EVENTIKO), **SUBJECT)
    assert got["state"] == R.IRRELEVANT
    assert got["supports_corroboration"] is False
    assert "example" in got["reason"]


def test_a_competitor_discussing_the_company_is_directly_relevant():
    got = R.adjudicate(_doc(RIVAL), **SUBJECT)
    assert got["state"] == R.DIRECTLY_RELEVANT
    assert got["supports_corroboration"] is True


def test_a_customer_describing_its_own_contract_still_counts():
    """A customer's spend on the company IS commercially informative, even
    though the sentence is in the author's voice. The incidental rule must
    key on the ENUMERATION, not on first person alone -- otherwise every
    customer voice in the corpus is discarded."""
    got = R.adjudicate(_doc(CUSTOMER), **SUBJECT)
    assert got["supports_corroboration"] is True
    assert got["state"] in (R.DIRECTLY_RELEVANT, R.CONTEXTUALLY_RELEVANT)


def test_a_document_that_never_names_the_company_is_irrelevant():
    got = R.adjudicate(_doc("An unrelated registrant describes its mining "
                            "operations and quarterly results."), **SUBJECT)
    assert got["state"] == R.IRRELEVANT
    assert "never names" in got["reason"]


# --- over-refusal controls --------------------------------------------------

def test_unreadable_text_is_unmeasurable_and_still_counts():
    """"We could not read it" must never silently delete an independent
    observation. UNMEASURABLE is reported, and it does not demote."""
    got = R.adjudicate({"final_url": "https://x.test/a", "text_content": ""},
                       **SUBJECT)
    assert got["state"] == R.UNMEASURABLE
    assert got["supports_corroboration"] is True


def test_no_subject_is_unmeasurable_not_irrelevant():
    got = R.adjudicate(_doc(RIVAL))
    assert got["state"] == R.UNMEASURABLE
    assert got["supports_corroboration"] is True


def test_the_companys_own_page_is_relevant_even_without_its_name():
    """A pricing page rarely spells the company's own name. Judging it by
    mentions would mark it irrelevant for a reason unrelated to content."""
    got = R.adjudicate({"final_url": f"https://www.{DOMAIN}/plans",
                        "text_content": "Enterprise plans start at..."},
                       self_authored=True, **SUBJECT)
    assert got["state"] == R.DIRECTLY_RELEVANT


def test_a_leading_word_does_not_match_inside_a_longer_company():
    """"alpha" inside "Alphabet Inc." refused whole snapshots once. Terms are
    matched on word boundaries."""
    got = R.adjudicate(
        _doc("Alphabet Inc. reported strong advertising revenue this year."),
        subject_name="Alpha Corp", subject_domain="alpha.test")
    assert got["state"] == R.IRRELEVANT


def test_every_state_is_in_the_closed_set():
    for text in (EVENTIKO, RIVAL, CUSTOMER, "", "nothing here"):
        assert R.adjudicate(_doc(text), **SUBJECT)["state"] in \
            R.RELEVANCE_STATES


# --- the gate, which is where it has to reach -------------------------------

def _edgar(cik, body):
    return {"final_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/x.htm",
            "source_class": "competitor", "filing": True,
            "content_hash": str(cik), "text_content": body}


SELF = {"final_url": f"https://www.{DOMAIN}/plans", "source_class":
        "company_owned", "content_hash": "self",
        "text_content": "Enterprise plans and pricing for teams."}
GATE = dict(subject_filers=("0001477333",), subject_domain=DOMAIN,
            subject_name=NAME)


def test_an_irrelevant_independent_filing_does_not_corroborate():
    """§5: independent AND relevant, or it does not add an origin."""
    out = IND.assess([SELF, _edgar(1816554, EVENTIKO)], **GATE)
    assert out["independent_evidence_count"] == 0
    assert out["corroboration_state"] != IND.INDEPENDENTLY_CORROBORATED


def test_it_is_still_reported_as_an_independent_voice():
    """Set aside, not erased. A reader must be able to see that the source
    WAS independent and why it still did not count."""
    row = [r for r in IND.classify([SELF, _edgar(1816554, EVENTIKO)], **GATE)
           if "1816554" in r["origin_family"]][0]
    assert row["independent_voice"] is True         # independence intact
    assert row["independence_bearing"] is False     # but it does not count
    assert row["relevance"] == R.IRRELEVANT
    assert row["relevance_reason"]


def test_a_relevant_independent_filing_still_corroborates():
    """THE CONTROL. If this breaks, the wall deleted real evidence."""
    out = IND.assess([SELF, _edgar(1816554, EVENTIKO),
                      _edgar(320193, RIVAL)], **GATE)
    assert out["independent_evidence_count"] == 1
    assert out["corroboration_state"] == IND.PARTIALLY_INDEPENDENT


def test_two_relevant_independent_filings_corroborate():
    out = IND.assess([SELF, _edgar(320193, RIVAL),
                      _edgar(789019, CUSTOMER)], **GATE)
    assert out["independent_evidence_count"] == 2
    assert out["corroboration_state"] == IND.INDEPENDENTLY_CORROBORATED


def test_the_subjects_own_filing_is_still_refused_on_the_other_axis():
    """Both walls stand at once: authorship AND relevance."""
    own = _edgar(1477333, "Our annual report. Cloudflare competes broadly.")
    row = [r for r in IND.classify([own], **GATE)
           if "1477333" in r["origin_family"]][0]
    assert row["independent_voice"] is False
    assert row["independence_bearing"] is False


def test_the_domain_alone_is_enough_to_judge_relevance():
    """A first version of this test assumed relevance needed the NAME. It does
    not: the domain stem "cloudflare" is itself a usable term, so a caller
    that knows only the website still gets the wall. Worth pinning, because
    the website-only run is the ordinary production path -- the same path that
    made the previous independence repair ship inert."""
    out = IND.assess([SELF, _edgar(1816554, EVENTIKO)],
                     subject_filers=("0001477333",), subject_domain=DOMAIN)
    assert out["independent_evidence_count"] == 0


def test_with_no_subject_identification_at_all_the_gate_does_not_demote():
    """The real over-refusal control. With nothing to judge against every row
    is UNMEASURABLE, and the count is exactly what it was before this wall --
    an unverified number, never a silently reduced one."""
    docs = [SELF, _edgar(1816554, EVENTIKO)]
    blind = IND.assess(docs)
    assert blind["independent_evidence_count"] == 1
    rows = IND.classify(docs)
    assert all(r["relevance"] == R.UNMEASURABLE for r in rows)
