"""Provenance a buyer can check, without leaking what they may not see.

The attribution wall is the point: HOST is who served the bytes, AUTHOR is who
wrote them, SUBJECT is who they are about. Collapsing host into author is what
made Cloudflare's own 10-K look like independent government confirmation on
the live preview.

The privacy wall is the other point: this projection must carry evidence and
never identity. `source_id`, run ids and content hashes are storage identity.
"""
import pytest

from intent_engine.company_ingestion import provenance as P

SUBJECT_CIK = "0001477333"
OTHER_CIK = "0001816554"
DOMAIN = "cloudflare.com"
NAME = "Cloudflare, Inc."
SUBJECT = dict(subject_filers=(SUBJECT_CIK,), subject_domain=DOMAIN,
               subject_name=NAME)


def _doc(url, source_class, *, title="t", digest="h", filing=False,
         desc="a reasonably long description of the document body here"):
    return {"final_url": url, "source_class": source_class, "title": title,
            "content_hash": digest, "filing": filing,
            "source_id": "src_PRIVATE_INTERNAL_ID",
            "meta_description": desc, "text_content": desc * 30}


# Each document needs DISTINCT text. Identical bodies are correctly labelled
# DERIVED_REPUBLICATION by `independence`, which caught the first version of
# this fixture -- the detector working, not a defect.
OWN_SITE = _doc(f"https://www.{DOMAIN}/pricing", "company_owned", digest="a",
                desc="enterprise pricing plans and add ons for network teams")
OWN_FILING = _doc(
    f"https://www.sec.gov/Archives/edgar/data/{SUBJECT_CIK.lstrip('0')}/x/y.htm",
    "investor_material", digest="b", filing=True, title="Annual report 10-K",
    desc="annual report risk factors competition and revenue concentration")
THIRD_FILING = _doc(
    f"https://www.sec.gov/Archives/edgar/data/{OTHER_CIK.lstrip('0')}/x/y.htm",
    "competitor", digest="c", filing=True,
    desc="unrelated registrant holdings description and vendor commitments")
ALL = [OWN_SITE, OWN_FILING, THIRD_FILING]


def _by_digest(projection):
    return {r["url"]: r for r in projection["records"]}


# --- the attribution wall ---------------------------------------------------

def test_host_author_and_subject_are_three_different_fields():
    rec = _by_digest(P.project(ALL, **SUBJECT))[OWN_FILING["final_url"]]
    assert rec["host"] == "www.sec.gov" or rec["host"].endswith("sec.gov")
    assert rec["author"] == NAME              # the company WROTE it
    assert rec["subject"] == NAME
    assert rec["self_authored"] is True


def test_the_subjects_own_filing_is_not_sold_as_government_confirmation():
    """THE LIVE FALSE CLAIM, in customer language this time."""
    rec = _by_digest(P.project(ALL, **SUBJECT))[OWN_FILING["final_url"]]
    assert rec["independence_bearing"] is False
    plain = rec["plain_statement"].lower()
    assert "wrote about itself" in plain
    assert "sec" in plain                      # the venue is still disclosed
    assert "independent" not in plain


def test_a_third_partys_filing_keeps_its_independence():
    """The negative control. An over-broad wall deletes real evidence."""
    rec = _by_digest(P.project(ALL, **SUBJECT))[THIRD_FILING["final_url"]]
    assert rec["self_authored"] is False
    assert rec["independence_bearing"] is True
    assert rec["author"] == f"SEC filer {OTHER_CIK.lstrip('0')}"


def test_a_third_partys_filing_is_called_a_filing_not_reporting():
    """MEASURED ON THE LIVE PAYLOAD. EVENTIKO's 10-K rendered as "Third-party
    reporting" because its LINEAGE is INDEPENDENT_EXTERNAL_SOURCE. Lineage
    answers whether a document adds an independent observation; it does not
    answer what the document IS. A sworn annual report is not journalism."""
    rec = _by_digest(P.project(ALL, **SUBJECT))[THIRD_FILING["final_url"]]
    plain = rec["plain_statement"].lower()
    assert "filing" in plain
    assert "reporting" not in plain
    assert "another company" in plain
    assert rec["independence_bearing"] is True     # still independent


def test_a_genuine_article_is_still_called_reporting():
    """The control: the filing branch must not swallow real journalism."""
    article = _doc("https://www.reuters.com/tech/story", "independent_reporting",
                   digest="z", desc="a reporter describes the market shift")
    rec = _by_digest(P.project([article], **SUBJECT))[article["final_url"]]
    assert "reporting" in rec["plain_statement"].lower()
    assert "filing" not in rec["plain_statement"].lower()


def test_the_author_is_never_just_the_host():
    for rec in P.project(ALL, **SUBJECT)["records"]:
        if rec["host"]:
            assert rec["author"] != rec["host"] or not rec["url"], rec["url"]


# --- the privacy wall -------------------------------------------------------

def test_no_internal_identifier_survives_the_projection():
    """`source_id` is storage identity. Exporting it under any key would be
    the leak this projection exists to avoid."""
    import json

    blob = json.dumps(P.project(ALL, **SUBJECT))
    assert "src_PRIVATE_INTERNAL_ID" not in blob
    assert "source_id" not in blob


def test_the_provenance_id_is_not_a_renamed_internal_id():
    recs = P.project(ALL, **SUBJECT)["records"]
    for rec in recs:
        assert rec["provenance_id"].startswith("prv_")
        assert "src_" not in rec["provenance_id"]
    assert len({r["provenance_id"] for r in recs}) == len(recs)


def test_the_passage_is_bounded():
    for rec in P.project(ALL, **SUBJECT)["records"]:
        assert len(rec["passage"]) <= P.MAX_PASSAGE + 1


# --- absence is a state (§13) ------------------------------------------------

def test_no_documents_is_a_state_not_an_empty_list():
    out = P.project([], **SUBJECT)
    assert out["state"] == P.PROVENANCE_UNAVAILABLE
    assert out["reason"]
    assert out["records"] == []


def test_a_claim_citing_nothing_is_not_applicable_not_unavailable():
    """Two different problems: a claim that cites nothing, and a claim whose
    citations are withheld. One empty list cannot say both."""
    projection = P.project(ALL, **SUBJECT)
    assert P.for_claim(projection, [])["state"] == P.PROVENANCE_NOT_APPLICABLE
    assert P.for_claim(projection, ["prv_nosuch"])["state"] == \
        P.PROVENANCE_UNAVAILABLE


def test_a_claim_resolves_to_only_its_own_sources():
    projection = P.project(ALL, **SUBJECT)
    one = projection["records"][1]["provenance_id"]
    got = P.for_claim(projection, [one])
    assert got["state"] == P.PROVENANCE_AVAILABLE
    assert [r["provenance_id"] for r in got["records"]] == [one]


def test_every_visibility_value_is_in_the_closed_set():
    for rec in P.project(ALL, **SUBJECT)["records"]:
        assert rec["visibility"] in P.VISIBILITY_STATES


# --- it must not re-implement lineage ---------------------------------------

def test_lineage_agrees_with_the_independence_module_exactly():
    """Two definitions of independence in one system is the defect this
    codebase has already shipped twice. The projection must MIRROR, never
    recompute."""
    from intent_engine.company_ingestion import independence as IND

    rows = IND.classify(ALL, subject_filers=(SUBJECT_CIK,),
                        subject_domain=DOMAIN)
    recs = P.project(ALL, **SUBJECT)["records"]
    assert [r["lineage"] for r in rows] == [r["lineage"] for r in recs]
    assert [r["independence_bearing"] for r in rows] == \
        [r["independence_bearing"] for r in recs]


def test_without_a_subject_nothing_is_claimed_to_be_self_authored():
    """Positive identification only, same rule as independence."""
    for rec in P.project(ALL)["records"]:
        assert rec["self_authored"] is False


# --- the whole chain, because a correct helper proved nothing twice ----------

def test_the_projection_survives_producer_transport_and_assembly():
    """PRODUCER -> CONTRACT -> SNAPSHOT -> DOSSIER.

    Both previous repairs in this area were correct in the helper and inert
    or invisible by the time a customer could see them: one because the
    subject never reached the filter, one because the record never crossed.
    So this asserts on the assembled dossier's founder block, which is what
    the live payload is built from -- not on `project()`.
    """
    from intent_engine.demo_dossier import read_founder_snapshot
    from intent_engine.external_intel import founder_demo_snapshot as fds

    projection = P.project(ALL, **SUBJECT)
    payload = fds.build_payload(
        run_id="run1", company_id="cloudflare", canonical_name=NAME,
        domain=DOMAIN, claim_provenance=projection)

    # 1. the contract accepts it as a KNOWN field, not an unknown one
    snapshot = read_founder_snapshot(payload, expected_company="cloudflare")
    assert "claim_provenance" not in snapshot.unknown_fields
    assert snapshot.claim_provenance is not None
    assert snapshot.claim_provenance["state"] == P.PROVENANCE_AVAILABLE

    # 2. the records arrive intact, with the attribution wall standing
    crossed = {r["url"]: r for r in snapshot.claim_provenance["records"]}
    own = crossed[OWN_FILING["final_url"]]
    assert own["author"] == NAME
    assert own["host"].endswith("sec.gov")
    assert own["self_authored"] is True
    assert own["independence_bearing"] is False

    # 3. and nothing private came with them
    import json
    assert "src_PRIVATE_INTERNAL_ID" not in json.dumps(
        snapshot.claim_provenance)


def test_an_older_producer_without_the_field_is_still_supported():
    """A snapshot built before this field existed is OLDER_SUPPORTED, not
    INCOMPATIBLE, and reads as "not measured" rather than "no sources"."""
    from intent_engine.demo_dossier import read_founder_snapshot
    from intent_engine.external_intel import founder_demo_snapshot as fds

    payload = fds.build_payload(run_id="run1", company_id="cloudflare",
                                canonical_name=NAME, domain=DOMAIN)
    payload.pop("claim_provenance", None)
    snapshot = read_founder_snapshot(payload, expected_company="cloudflare")
    assert snapshot.claim_provenance is None
    assert "claim_provenance" not in snapshot.unknown_fields
