"""Sony identity + bounded official-source fallback.

The incident these pin: `sony.com` returns 403 to automated clients, the run
fell back to a single SEC 6-K, and the report then described Sony Group
Corporation — a Japanese multinational — on the strength of one interim filing.
Two separate defects: the entity was never established independently of the
retrieved documents, and there was no way to reach official material once the
primary domain refused access.
"""
import pytest

from intent_engine.company_ingestion.entities import (
    AMBIGUOUS, AUTHORITY_OFFICIAL_PRIMARY, AUTHORITY_REGULATORY,
    AUTHORITY_SUBSIDIARY_OFFICIAL, MAX_FALLBACK_SOURCES, REGISTRY, REL_PARENT,
    REL_SELF, RESOLVED, UNKNOWN, entity_identity_facts,
    official_fallback_candidates, resolve_choice, resolve_entity,
)


# --- identity ---------------------------------------------------------------
def test_sony_resolves_to_the_group_not_a_subsidiary():
    r = resolve_entity(company_name="Sony Group Corporation")
    assert r.status == RESOLVED
    assert r.profile.legal_name == "Sony Group Corporation"
    assert r.profile.country == "Japan"
    assert not r.profile.parent_entity_id


def test_sony_website_resolves_the_group():
    r = resolve_entity(company_name="Sony", website="https://www.sony.com")
    assert r.status == RESOLVED
    assert r.profile.entity_id == "sony-group"


def test_bare_sony_is_ambiguous_and_never_silently_picks_a_subsidiary():
    r = resolve_entity(company_name="Sony")
    assert r.status == AMBIGUOUS
    ids = [c.entity_id for c in r.choices]
    assert "sony-group" in ids
    assert "sony-interactive-entertainment" in ids
    assert "sony-electronics" in ids
    # the parent is offered first, but it is offered — not chosen
    assert ids[0] == "sony-group"
    assert r.profile is None


def test_ambiguity_is_settled_by_the_users_explicit_choice():
    r = resolve_choice("sony-interactive-entertainment")
    assert r.status == RESOLVED
    assert r.profile.legal_name == "Sony Interactive Entertainment LLC"
    assert r.profile.parent_entity_id == "sony-group"


def test_subsidiary_domain_beats_the_parent_common_name():
    # The person typed the group's common name but a subsidiary's domain. The
    # domain is the specific thing they had to know, so it wins.
    r = resolve_entity(company_name="Sony",
                       website="https://electronics.sony.com/tv")
    assert r.status == RESOLVED
    assert r.profile.entity_id == "sony-electronics"


def test_playstation_alias_resolves_to_sony_interactive():
    r = resolve_entity(company_name="PlayStation")
    assert r.status == RESOLVED
    assert r.profile.entity_id == "sony-interactive-entertainment"


def test_unknown_company_is_unknown_not_guessed():
    r = resolve_entity(company_name="Hooli Dynamics Unlimited")
    assert r.status == UNKNOWN
    assert r.profile is None
    assert r.choices == ()


def test_identity_facts_carry_the_full_multinational_record():
    facts = entity_identity_facts(
        resolve_entity(company_name="Sony Group Corporation").profile)
    assert facts["canonical_legal_name"] == "Sony Group Corporation"
    assert facts["common_name"] == "Sony"
    assert facts["country"] == "Japan"
    assert facts["primary_domain"] == "sony.com"
    assert facts["investor_relations_domain"]
    tickers = {(l["exchange"], l["ticker"]) for l in facts["listings"]}
    assert ("TSE", "6758") in tickers      # the primary listing, in Japan
    assert ("NYSE", "SONY") in tickers     # the ADR
    assert "20-F" in facts["sec_relationship"]
    assert facts["sec_cik"]
    assert facts["identity_confidence"] == "HIGH"
    assert facts["ambiguity_notes"]


def test_sony_is_not_described_as_a_domestic_sec_filer():
    relationship = entity_identity_facts(
        resolve_entity(company_name="Sony Group Corporation").profile
    )["sec_relationship"]
    # Sony is a foreign private issuer. Treating it as a domestic filer is how
    # a report ends up hunting for a 10-K that does not exist and settling for
    # whatever 6-K it finds instead. The record must say so explicitly rather
    # than leaving the reader to assume the US default.
    assert "Foreign private issuer" in relationship
    assert "20-F" in relationship
    assert "no 10-K" in relationship
    assert "American Depositary Receipt" in relationship


# --- bounded official fallback ----------------------------------------------
def test_fallback_reaches_beyond_one_filing_across_several_families():
    profile = resolve_entity(company_name="Sony Group Corporation").profile
    candidates = official_fallback_candidates(profile)
    assert len(candidates) >= 5
    assert len(candidates) <= MAX_FALLBACK_SOURCES
    classes = {c["source_class"] for c in candidates}
    # not "several filings" — several genuinely different kinds of evidence
    assert len(classes) >= 3
    kinds = {c["why_useful"] for c in candidates}
    assert len(kinds) >= 4


def test_every_fallback_source_is_classified_by_authority_and_relationship():
    for profile in REGISTRY:
        for candidate in official_fallback_candidates(profile):
            assert candidate["authority"] in (
                AUTHORITY_REGULATORY, AUTHORITY_OFFICIAL_PRIMARY,
                "official_secondary", AUTHORITY_SUBSIDIARY_OFFICIAL)
            assert candidate["entity_relationship"] in (
                REL_SELF, REL_PARENT, "subsidiary", "listing_or_adr")
            assert candidate["entity_id"] == profile.entity_id
            assert candidate["why_relevant"].strip()


def test_parent_sources_under_a_subsidiary_are_attributed_to_the_parent():
    profile = resolve_choice("sony-interactive-entertainment").profile
    parent_sources = [c for c in official_fallback_candidates(profile)
                      if c["entity_relationship"] == REL_PARENT]
    assert parent_sources, "PlayStation's results are reported by the group"
    for candidate in parent_sources:
        why = candidate["why_relevant"]
        assert "Sony Group Corporation" in why
        assert "not to Sony Interactive Entertainment LLC" in why


def test_subsidiary_official_pages_never_claim_primary_group_authority():
    profile = resolve_choice("sony-electronics").profile
    own = [c for c in official_fallback_candidates(profile)
           if c["entity_relationship"] == REL_SELF]
    assert own
    assert all(c["authority"] == AUTHORITY_SUBSIDIARY_OFFICIAL for c in own)


def test_fallback_skips_urls_a_previous_attempt_already_failed():
    profile = resolve_entity(company_name="Sony Group Corporation").profile
    first = official_fallback_candidates(profile)
    failed = [first[0]["url"], first[1]["url"]]
    retry = official_fallback_candidates(profile, exclude_urls=failed)
    urls = {c["url"] for c in retry}
    assert not (urls & set(failed))
    assert urls, "a retry must still have somewhere new to look"


def test_fallback_is_bounded_even_with_a_large_registry_entry():
    profile = resolve_entity(company_name="Sony Group Corporation").profile
    assert len(official_fallback_candidates(profile, limit=3)) == 3


def test_fallback_candidates_match_the_discovery_candidate_shape():
    # They flow through the same approval + retrieval path as any candidate,
    # so a missing key would fail at approval time rather than here.
    required = {"url", "source_type", "discovery_method", "same_domain",
                "source_class", "why_useful", "why_relevant", "availability"}
    profile = resolve_entity(company_name="Palantir").profile
    for candidate in official_fallback_candidates(profile):
        assert required <= set(candidate)
        assert candidate["discovery_method"] == "official_fallback"
        assert candidate["availability"] == "UNVERIFIED"


@pytest.mark.parametrize("entity_id", [p.entity_id for p in REGISTRY])
def test_every_registry_entity_is_internally_consistent(entity_id):
    profile = resolve_choice(entity_id).profile
    assert profile.legal_name and profile.common_name and profile.country
    assert profile.primary_domain
    assert profile.official_sources, "an entity with no official source " \
                                     "cannot help a blocked run"
    if profile.parent_entity_id:
        assert resolve_choice(profile.parent_entity_id).status == RESOLVED
    for source in profile.official_sources:
        assert source.url.startswith("https://")
        assert source.title.strip()
