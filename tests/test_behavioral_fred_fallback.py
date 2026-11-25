"""When BLS refuses, the same series arrive once, from FRED, with real vintages."""
from intent_engine.market import behavioral_ingest as BI

REFUSE = lambda url, body: {"status": "REQUEST_NOT_PROCESSED",
                            "message": ["daily threshold ... reached"]}


def _fred(sid, start, end):
    return [{"date": "2026-08-01", "value": "2.0", "realtime_start": "2026-10-07"},
            {"date": "2026-09-01", "value": "2.1", "realtime_start": "2026-11-30"}]  # future


def test_refusal_falls_back_to_the_fred_mirror_with_first_release_dates():
    nodes = BI.bls_with_fred_fallback(retrieved_at="2026-11-25", fetcher=REFUSE,
                                      fred_fetcher=_fred)
    assert {n.kind for n in nodes} == {"quits", "labour_participation"}
    assert all(n.available_at == "2026-10-07" for n in nodes)   # future vintage dropped
    assert all("FRED mirror" in n.provenance.venue for n in nodes)


def test_a_test_double_for_bls_never_reaches_the_network():
    import pytest
    with pytest.raises(RuntimeError):
        BI.bls_with_fred_fallback(retrieved_at="2026-11-25", fetcher=REFUSE)


def test_success_from_bls_does_not_also_fetch_fred():
    called = []
    ok = lambda url, body: {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
    BI.bls_with_fred_fallback(retrieved_at="2026-11-25", fetcher=ok,
                              fred_fetcher=lambda *a: called.append(a) or [])
    assert not called
