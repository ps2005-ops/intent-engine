"""One page of one analysis said two incompatible things.

MEASURED ON THE DEPLOYED PRODUCT. Caterpillar's executive brief said, in one
section, "WHAT COULD ACTUALLY BE READ / SEC 10-K", and in the next, "Filings
and investor material — none".

Both were computed correctly, from different denominators. The bibliography
counts DOCUMENTS RETRIEVED; `source_class_coverage` counted OBSERVATIONS
DERIVED. A filing we read but could not extract an observation from therefore
vanished from the inventory while remaining in the source list.

The deeper defect is that a family's state was an INTEGER. Zero had to mean
"never looked", "was refused", "read it and it said nothing" and "cannot
apply" all at once, and a reader acts differently on each.
"""
from intent_engine.company_ingestion import source_coverage as SC
from intent_engine.founder_brief.dossier import evidence_families


def _doc(cls):
    return {"source_class": cls}


def test_a_document_read_with_no_observation_is_never_none():
    """THE EXACT LIVE CASE."""
    got = SC.assess(documents=[_doc("investor_material")], observations=[])
    row = got["families"]["investor_material"]
    assert row["state"] == SC.RETRIEVED_NO_SIGNAL
    assert row["documents"] == 1
    assert "read" in row["reason"]


def test_the_inventory_can_never_disagree_with_the_bibliography():
    """THE GUARD AGAINST THIS DEFECT RETURNING. Any family holding documents
    while claiming nothing was attempted is the contradiction itself."""
    got = SC.assess(documents=[_doc("investor_material"), _doc("company_owned")],
                    observations=[_doc("company_owned")])
    assert SC.contradicts(got) == []


def test_a_blocked_first_party_fetch_is_distinguished_from_silence():
    got = SC.assess(documents=[], observations=[],
                    failures={"http_status": 6})["families"]
    assert got["company_owned"]["state"] == SC.BLOCKED
    assert got["company_owned"]["absence_is_ours"] is True


def test_a_blocked_subject_site_never_explains_a_third_party_family():
    """A competitor's filing is not missing because the SUBJECT's website
    refused us."""
    got = SC.assess(documents=[], observations=[],
                    failures={"http_status": 6})["families"]
    assert got["competitor"]["state"] == SC.NOT_ATTEMPTED
    assert got["independent_reporting"]["state"] == SC.NOT_ATTEMPTED


def test_nothing_proposed_and_nothing_blocked_is_not_attempted():
    got = SC.assess()["families"]
    assert {r["state"] for r in got.values()} == {SC.NOT_ATTEMPTED}
    assert all(not r["supports_analysis"] for r in got.values())


def test_candidates_that_all_failed_are_attempted_not_unattempted():
    got = SC.assess(documents=[], observations=[],
                    proposed=[_doc("customer_voice")])["families"]
    assert got["customer_voice"]["state"] == SC.ATTEMPTED_NONE


def test_only_a_derived_observation_supports_the_analysis():
    got = SC.assess(documents=[_doc("company_owned")],
                    observations=[_doc("company_owned")])["families"]
    assert got["company_owned"]["state"] == SC.PRESENT
    assert got["company_owned"]["supports_analysis"] is True


def test_a_blocked_family_absence_is_ours_not_the_companys():
    """A surface may never turn "we were refused" into "they published
    nothing".

    NOT_ATTEMPTED is also ours -- we did not look. The state that is NOT
    about us is RETRIEVED_NO_SIGNAL: we reached the material and it had
    nothing to say, which is a fact about the material.
    """
    got = SC.assess(failures={"javascript_only": 2})["families"]
    assert got["company_owned"]["absence_is_ours"] is True
    assert got["customer_voice"]["absence_is_ours"] is True

    reached = SC.assess(documents=[_doc("investor_material")],
                        observations=[])["families"]
    assert reached["investor_material"]["absence_is_ours"] is False


# --- the surface must read the same object -------------------------------------


def test_the_brief_shows_a_read_filing_as_present():
    """THE LIVE CONTRADICTION, at the surface that displayed it."""
    coverage = SC.assess(documents=[_doc("investor_material")],
                         observations=[], failures={"http_status": 6})
    rows = evidence_families({"source_class_coverage": {},
                              "source_coverage": coverage,
                              "retrieval_failures": {"http_status": 6}})
    filings = [r for r in rows if r["key"] == "investor_material"][0]
    assert filings["present"] is True
    assert filings["count"] == 1


def test_the_brief_still_reads_a_run_that_produced_no_typed_object():
    """NEGATIVE CONTROL for the migration: an older run carries only the
    integer map, and must render exactly as it did before."""
    rows = evidence_families({"source_class_coverage": {"company_owned": 5}})
    owned = [r for r in rows if r["key"] == "company_owned"][0]
    assert owned["present"] is True and owned["consequence"] == ""
    absent = [r for r in rows if r["key"] == "competitor"][0]
    assert absent["present"] is False and absent["consequence"]


def test_the_legacy_count_shape_is_unchanged_for_old_consumers():
    coverage = SC.assess(documents=[_doc("company_owned")],
                         observations=[_doc("company_owned"),
                                       _doc("company_owned")])
    assert SC.legacy_counts(coverage) == {"company_owned": 2}
