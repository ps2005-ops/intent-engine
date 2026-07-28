"""The second person to analyse a company must not get a 500.

Found on the live service. Two anonymous visitors analysed the same company
against the same persistent store; the first succeeded and the second was
shown "Something went wrong".

    ValueError: idempotency_key 'complete:<run>' was already used for
                different content

An idempotency key is a promise that re-recording the SAME thing is safe.
Keyed on the run alone it also promised that a run completes exactly once with
exactly one result -- untrue, because re-analysing produces a fresh set of
limitations from freshly retrieved pages. The guard correctly refused the
mismatch and the exception reached the user.
"""
import pathlib

from company_fixture_pages import transport as fixture_pages
from test_webapp_demo_mode import Client, _make


def _two_visitors(tmp_path, company, website):
    app = _make(tmp_path, transport=fixture_pages, autorun_sources=True,
                demo_ip_analyses_per_hour=50,
                demo_session_analyses_per_day=50)
    out = []
    for _ in range(3):
        c = Client(app)
        status, headers, _ = c.request(
            "POST", "/analyze",
            f"consent=on&company_name={company}&website={website}")
        out.append(status)
    return out


def test_analysing_the_same_company_repeatedly_does_not_500(tmp_path):
    statuses = _two_visitors(tmp_path, "Northwind",
                             "https://northwind-demo.example")
    assert not any(s.startswith("500") for s in statuses), statuses


def test_identical_results_produce_one_key_and_different_results_do_not():
    """The property the fix rests on. Identical content keeps collapsing onto
    one event (the idempotency guarantee survives); genuinely different
    content gets its own key and appends instead of raising."""
    from intent_engine.founder_intelligence.service import _payload_digest
    same_a = {"complete": True, "limitations": ["a", "b"]}
    same_b = {"complete": True, "limitations": ["a", "b"]}
    other = {"complete": True, "limitations": ["a"]}
    assert _payload_digest(same_a) == _payload_digest(same_b)
    assert _payload_digest(same_a) != _payload_digest(other)


def test_the_digest_is_stable_across_key_order(tmp_path):
    from intent_engine.founder_intelligence.service import _payload_digest
    assert _payload_digest({"a": 1, "b": [1, 2]}) == \
        _payload_digest({"b": [1, 2], "a": 1})
