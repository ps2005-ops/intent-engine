"""One refused sentence may not cost the whole report.

`SourceClaim.validate` runs the editorial language wall, and a single claim
tripping it raised straight out of composition — so the run was abandoned and
the reader was told nothing had been produced. Measured live on preview-v3:

    stage=composition
    PersonalError: claim text overclaims: ['always']

for Alphabet, whose SEC 10-K and 10-Q had been read successfully.

The wall is not relaxed anywhere here. A refused claim is still refused; it is
refused ALONE.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import claims as C
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, BANNED_WORKSPACE_LANGUAGE, PersonalError,
    scan_banned_language,
)


def _doc(sid="s1", url="https://acme.example/", title="Acme",
         text="Acme builds things.\nMore body text here.\n", **kw):
    doc = {"source_id": sid, "source_type": "homepage", "final_url": url,
           "title": title, "meta_description": "Acme helps teams ship.",
           "text_content": text, "retrieval_status": "OK",
           "freshness": "CURRENT", "content_hash": sid,
           "retrieved_at": "2026-08-06", "parser_version": "p1"}
    doc.update(kw)
    return doc


def test_the_language_wall_still_refuses_workspace_overclaim():
    """The guard is untouched: this must still raise inside the builder."""
    with pytest.raises(PersonalError):
        C.SourceClaim(claim_id="x", text="This is always the best approach.",
                      availability=AVAIL_SUPPORTED, source_refs=(),
                      confidence="High").validate()


def test_no_banned_term_was_removed_from_the_wall():
    for term in ("always", "never", "best", "must", "proven", "guaranteed"):
        assert term in BANNED_WORKSPACE_LANGUAGE
    assert scan_banned_language("we always win", BANNED_WORKSPACE_LANGUAGE)


def test_an_optional_refused_claim_returns_none_instead_of_raising():
    out = C._claim("at.no_public_pricing",
                   "Pricing is always published.", AVAIL_SUPPORTED,
                   [_doc()], confidence="High")
    assert out is None
    assert any(r["claim_id"] == "at.no_public_pricing" for r in C._REFUSED)


def test_an_essential_refused_claim_still_aborts_and_names_itself():
    with pytest.raises(C.ClaimRefused) as caught:
        C._claim("u.identity", "The company is always the best.",
                 AVAIL_SUPPORTED, [_doc()], confidence="High")
    assert caught.value.claim_id == "u.identity"
    assert "overclaims" in caught.value.reason


def test_a_report_survives_one_refused_optional_claim():
    C._REFUSED.clear()
    """The whole point: the run keeps everything else it established."""
    text = ("Acme builds workflow software.\n"
            "A platform built for always-on operations teams.\n"
            "We serve customers worldwide.\n")
    built = C.build_claims(documents=[_doc(text=text)],
                           company_name="Acme", domain="acme.example")
    understanding = built["understanding"]
    assert understanding, "the report lost everything to one refused claim"
    assert all(c is not None for group in built.values()
               if isinstance(group, list) for c in group), \
        "a refused claim leaked through as None"
    # the refused one is the audience claim; identity and scope survive it
    ids = {c.claim_id for c in understanding}
    assert "u.identity" in ids, f"identity lost; got {sorted(ids)}"
    assert any(r["claim_id"] in ("u.customer", "p.homepage_audience")
               for r in C._REFUSED), \
        f"the overclaiming audience claim was not refused: {C._REFUSED}"


def test_every_surviving_claim_is_still_inside_the_wall():
    """Isolation must not become a bypass."""
    text = ("Acme builds workflow software.\n"
            "A platform built for always-on operations teams.\n")
    built = C.build_claims(documents=[_doc(text=text)],
                           company_name="Acme", domain="acme.example")
    for group in built.values():
        if not isinstance(group, list):
            continue
        for claim in group:
            claim.validate()          # raises if the wall was bypassed


def test_essential_ids_are_the_ones_a_report_would_mislead_without():
    assert C.ESSENTIAL_CLAIM_IDS == frozenset(
        {"u.identity", "u.offering", "u.scope"})
