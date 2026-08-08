"""Source voice survives as attributed evidence; workspace voice stays walled.

Claim isolation stopped one overclaiming sentence from costing the whole
report. It did not make the sentence right. The audience claim was still
DROPPED, and it was dropped for a reason that was never the company's fault:
the builder interpolated retrieved page text RAW into a workspace sentence, so
an absolute the *company* wrote — "always-on teams", "built for developers who
must ship" — read as the workspace asserting certainty, and the language wall
correctly refused it.

Containment is not preservation. The phrase is the source speaking, so it is
quoted, attributed, and verified to exist in a cited source. Everything outside
the quote remains the workspace's own voice and remains fully walled.

The wall is unchanged. Quoting is not an escape hatch: `assert_quotes_exist`
refuses an invented quotation, so a claim can only survive by quoting something
the source actually says.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import claims as C
from intent_engine.company_ingestion.records import IngestionError
from intent_engine.personal.records import (
    AVAIL_PARTIAL, BANNED_WORKSPACE_LANGUAGE, PersonalError,
    scan_banned_language,
)

AUDIENCE_IDS = ("u.customer", "p.homepage_audience")


def _doc(text, sid="s1"):
    return {"source_id": sid, "source_type": "homepage",
            "final_url": "https://acme.example/", "title": "Acme",
            "meta_description": "Acme helps teams ship.",
            "text_content": text, "retrieval_status": "OK",
            "freshness": "CURRENT", "content_hash": sid,
            "retrieved_at": "2026-08-06", "parser_version": "p1"}


def _build(text):
    C._REFUSED.clear()
    return C.build_claims(documents=[_doc(text)], company_name="Acme",
                          domain="acme.example")


def _audience_claims(built):
    out = []
    for group in built.values():
        if isinstance(group, list):
            out += [c for c in group if c.claim_id in AUDIENCE_IDS]
    return out


def _unquoted(text):
    """The workspace's own voice: the claim with every quoted span removed."""
    import re
    return re.sub(r'["“][^"”]*["”]', " ", text)


# --- 1-3: a banned term in the SOURCE no longer costs the claim -------------

@pytest.mark.parametrize("term,text", [
    ("always", "Acme ships.\nA platform built for always-on operations teams.\n"),
    ("must", "Acme ships.\nBuilt for developers who must deploy daily.\n"),
    ("best", "Acme ships.\nMade for best-in-class engineering teams.\n"),
])
def test_a_banned_word_in_the_source_phrase_no_longer_drops_the_claim(term, text):
    built = _build(text)
    claims = _audience_claims(built)
    assert claims, (
        f"the audience claim was dropped over source-written {term!r}; "
        f"refused={C._REFUSED}")
    for claim in claims:
        assert f'"{term}' in claim.text or f'{term}' in claim.text
        # the banned term is present ONLY inside the quotation
        assert term not in _unquoted(claim.text).lower(), (
            f"{term!r} leaked into workspace voice: {claim.text}")


# --- 4-5: quoting is what makes it survivable ------------------------------

def test_quoted_source_phrase_survives_the_wall():
    out = C._claim("u.customer",
                   'The homepage addresses "always-on teams". Composition '
                   'is not settled by the page.',
                   AVAIL_PARTIAL, [_doc("Built for always-on teams here.")],
                   docs_by_id={"s1": _doc("Built for always-on teams here.")})
    assert out is not None
    out.validate()


def test_the_same_phrase_unquoted_still_fails():
    """Proof the survival is due to attribution, not a relaxed wall."""
    out = C._claim("u.customer",
                   "The homepage addresses always-on teams.",
                   AVAIL_PARTIAL, [_doc("Built for always-on teams here.")])
    assert out is None, "an unquoted absolute passed the wall"


# --- 6: workspace interpretation is still walled ---------------------------

def test_workspace_interpretation_containing_a_banned_word_still_fails():
    doc = _doc("Built for small teams here.")
    out = C._claim("u.customer",
                   'The homepage addresses "small teams". This is always '
                   'the best reading of the market.',
                   AVAIL_PARTIAL, [doc], docs_by_id={"s1": doc})
    assert out is None, "quoting one span excused an overclaim in another"


# --- 7-9: provenance, verbatim-ness, visible attribution -------------------

def test_the_quoted_phrase_carries_an_evidence_reference():
    built = _build("Acme ships.\nA platform built for always-on teams.\n")
    for claim in _audience_claims(built):
        assert claim.source_refs, f"{claim.claim_id} quotes with no evidence"
        for ref in claim.source_refs:
            assert ref.subsystem == C.REAL_SUBSYSTEM
            ref.validate()


def test_the_quote_contains_only_text_the_source_actually_says():
    text = "Acme ships.\nA platform built for Always-On Operations Teams.\n"
    built = _build(text)
    claims = _audience_claims(built)
    assert claims
    for claim in claims:
        C.assert_quotes_exist(claim.text, {"s1": _doc(text)}, ["s1"])
    # verbatim, including the source's own casing — a lower-cased rewrite of
    # the source is not the source
    assert '"Always-On Operations Teams"' in claims[0].text, claims[0].text


def test_an_invented_quotation_is_refused():
    doc = _doc("Acme builds things for small teams.")
    out = C._claim("u.customer",
                   'The homepage addresses "global banks that always win".',
                   AVAIL_PARTIAL, [doc], docs_by_id={"s1": doc})
    assert out is None, "a fabricated quotation passed the quote checker"


def test_attribution_is_visible_in_the_claim_text():
    built = _build("Acme ships.\nA platform built for always-on teams.\n")
    for claim in _audience_claims(built):
        assert "homepage" in claim.text.lower(), (
            f"{claim.claim_id} quotes without naming its source: {claim.text}")


def test_the_claim_distinguishes_stated_audience_from_customer_composition():
    """The reader is told what the wording does NOT establish."""
    built = _build("Acme ships.\nA platform built for always-on teams.\n")
    claims = _audience_claims(built)
    assert claims
    joined = " ".join(c.text.lower() for c in claims)
    assert "customer" in joined
    assert "not the same" in joined or "not settled" in joined


# --- 10-11: report survival and safe refusal -------------------------------

def test_the_audience_claim_survives_without_aborting_the_report():
    built = _build("Acme builds workflow software.\n"
                   "A platform built for always-on operations teams.\n")
    ids = {c.claim_id for c in built["understanding"]}
    assert "u.identity" in ids
    assert "u.customer" in ids, f"audience still lost; got {sorted(ids)}"
    assert not [r for r in C._REFUSED if r["claim_id"] in AUDIENCE_IDS]


def test_no_audience_claim_when_the_source_span_is_unavailable():
    """Optional refusal remains available: no phrase, no claim, no abort."""
    built = _build("Acme builds workflow software.\nNothing about buyers.\n")
    assert _audience_claims(built) == []
    assert built["understanding"], "the report died over a missing phrase"


def test_a_sub_quotable_phrase_is_dropped_rather_than_quoted_unverified():
    """Below the quote checker's floor we cannot prove provenance, so we
    decline to quote rather than assert an unverifiable attribution."""
    assert C._audience_phrase(_doc("built for abc\n")) is None


# --- 12-13: nothing leaked, everything revalidates -------------------------

def test_no_banned_term_leaks_into_workspace_voice_anywhere():
    for text in ("Acme ships.\nBuilt for always-on operations teams.\n",
                 "Acme ships.\nBuilt for developers who must deploy daily.\n",
                 "Acme ships.\nMade for best-in-class engineering teams.\n"):
        built = _build(text)
        for group in built.values():
            if not isinstance(group, list):
                continue
            for claim in group:
                hits = scan_banned_language(_unquoted(claim.text),
                                            BANNED_WORKSPACE_LANGUAGE)
                assert not hits, f"{claim.claim_id} overclaims {hits}"


def test_every_surviving_claim_still_revalidates():
    built = _build("Acme builds workflow software.\n"
                   "A platform built for always-on operations teams.\n")
    for group in built.values():
        if isinstance(group, list):
            for claim in group:
                claim.validate()


def test_the_wall_and_its_vocabulary_are_untouched():
    for term in ("always", "never", "best", "must", "proven", "guaranteed"):
        assert term in BANNED_WORKSPACE_LANGUAGE
    with pytest.raises(PersonalError):
        C.assert_workspace_language("this is always the best approach")


def test_quote_checker_is_still_enforced_for_the_audience_builders():
    """If `docs_by_id` were dropped from the call sites, this fails."""
    with pytest.raises(IngestionError):
        C.assert_quotes_exist('addresses "phrase not in the page at all"',
                              {"s1": _doc("Acme builds things.")}, ["s1"])
