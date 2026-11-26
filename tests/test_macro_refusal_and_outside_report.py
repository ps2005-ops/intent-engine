"""A provider's refusal, delivered with a 200, is never cached as data."""
from __future__ import annotations

import json

from intent_engine.external_intel import macro_provider as MP

REFUSAL = {"status": "REQUEST_NOT_PROCESSED", "responseTime": 0,
           "message": ["daily threshold ... has been reached."], "Results": {}}
GOOD = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [1]}]}}


def test_a_refusal_is_not_cached(tmp_path):
    assert MP._cached_get(tmp_path, "bls_x", "u", now=1000.0,
                          fetcher=lambda u: REFUSAL) is None
    assert not MP._cache(tmp_path, "bls_x").exists()


def test_the_last_good_copy_is_served_instead(tmp_path):
    MP._cached_get(tmp_path, "bls_x", "u", now=1000.0, fetcher=lambda u: GOOD)
    later = 1000.0 + MP.CACHE_TTL_SECONDS + 1
    assert MP._cached_get(tmp_path, "bls_x", "u", now=later,
                          fetcher=lambda u: REFUSAL) == GOOD
    cached = json.loads(MP._cache(tmp_path, "bls_x").read_text())["body"]
    assert cached == GOOD


def test_a_success_and_a_status_free_body_are_kept(tmp_path):
    """POSITIVE CONTROL: Treasury bodies carry no status key at all."""
    assert MP._cached_get(tmp_path, "t", "u", now=1.0,
                          fetcher=lambda u: {"data": [1]}) == {"data": [1]}
    assert MP._cached_get(tmp_path, "g", "u", now=1.0,
                          fetcher=lambda u: GOOD) == GOOD


def test_an_outside_report_reads_as_a_sentence_and_carries_its_date():
    from intent_engine.strategic_intelligence import observations as O
    doc = {"source_id": "s1", "final_url": "https://betakit.com/x",
           "title": "BetaKit", "source_class": "independent_reporting",
           "retrieval_status": "OK", "content_hash": "h",
           "published_date": "2026-07-28T15:08:57+00:00",
           "retrieved_at": "2026-11-26T07:00:00+00:00",
           "text_content": ("FinTech company Vena Solutions has entered an "
                            "agreement to acquire fellow Toronto startup "
                            "Morpheo AI.")}
    obs = O.derive_observations([doc], company="Vena Solutions Inc.")
    assert obs[0].date == "2026-07-28"
    assert obs[0].text.endswith("an account the company did not write.")
    assert len(obs[0].text) < 200
