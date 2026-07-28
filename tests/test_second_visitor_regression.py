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


# --- terminal-run reuse (the layer-2 fix) ----------------------------------

def _counts(app):
    tot = {"fi.section_assembled": 0, "fi.run_completed": 0,
           "fi.run_created": 0}
    for rid in app.fi.store.run_ids():
        for e in app.fi.store.for_run(rid):
            if e.event_type in tot:
                tot[e.event_type] += 1
    return tot


def _app(tmp_path):
    return _make(tmp_path, transport=fixture_pages, autorun_sources=True,
                 demo_ip_analyses_per_hour=50,
                 demo_session_analyses_per_day=50)


def _analyse(app, company="Northwind",
             website="https://northwind-demo.example"):
    c = Client(app)
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&company_name={company}&website={website}")
    return c, status, headers.get("Location", "")


def test_second_identical_analysis_appends_no_terminal_events(tmp_path):
    """The defect: fi.section_assembled on a terminal run (COMPLETE).
    A persistent store across requests is essential -- a fresh store per
    request is what hid this."""
    app = _app(tmp_path)
    _analyse(app)
    after_first = _counts(app)
    for _ in range(2):
        _, status, _ = _analyse(app)
        assert not status.startswith("500"), status
    assert _counts(app) == after_first, (
        "a repeated identical analysis wrote new events to a finished run")


def test_a_reused_result_is_the_canonical_one(tmp_path):
    """Reuse must reproduce the completed result, not a degraded stand-in."""
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    kwargs = dict(company_name="Northwind",
                  website="https://northwind-demo.example",
                  claims_by_section={}, as_of="2026-07-28T00:00:00+00:00",
                  approved_inputs=("a", "b"))
    first = fi.run(**kwargs)
    second = fi.run(**kwargs)
    assert second["run_id"] == first["run_id"]
    assert second["status"] == first["status"]
    assert second["sections"] == first["sections"]
    assert second["limitations"] == first["limitations"]
    assert second.get("reused") is True and not first.get("reused")


def test_different_evidence_creates_a_different_run(tmp_path):
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    base = dict(company_name="Northwind",
                website="https://northwind-demo.example",
                claims_by_section={}, as_of="2026-07-28T00:00:00+00:00")
    a = fi.run(**base, approved_inputs=("a",))
    b = fi.run(**base, approved_inputs=("a", "b"))
    assert a["run_id"] != b["run_id"], \
        "different approved evidence must not reuse the earlier run"


def test_a_different_pipeline_version_does_not_reuse(tmp_path, monkeypatch):
    from intent_engine.founder_intelligence import service as svc
    fi = svc.FounderIntelligenceService(tmp_path / "fi.jsonl")
    kwargs = dict(company_name="Northwind",
                  website="https://northwind-demo.example",
                  claims_by_section={}, as_of="2026-07-28T00:00:00+00:00",
                  approved_inputs=("a",))
    first = fi.run(**kwargs)
    monkeypatch.setattr(svc.FounderIntelligenceService, "analysis_version",
                        staticmethod(lambda: "a-different-pipeline"))
    assert fi.run(**kwargs)["run_id"] != first["run_id"], \
        "an obsolete run was reused after the pipeline changed"


def test_a_failed_run_is_never_returned_as_success(tmp_path):
    """A terminal FAILED run must not be handed back as a completed one, and
    must not be resumed either."""
    import pytest
    from intent_engine.founder_intelligence.records import (
        FounderIntelligenceError,
    )
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    kwargs = dict(company_name="Northwind",
                  website="https://northwind-demo.example",
                  claims_by_section={}, as_of="2026-07-28T00:00:00+00:00",
                  approved_inputs=("a",))
    result = fi.run(**kwargs)
    fi._record("fi.run_failed", run_id=result["run_id"],
               company_domain=result["company_domain"],
               payload={"reason": "simulated"})
    with pytest.raises(FounderIntelligenceError) as exc:
        fi.run(**kwargs)
    assert "cannot be reused" in str(exc.value)


def test_reuse_does_not_hand_over_another_visitors_run(tmp_path):
    """Reuse is of the ANALYSIS, not of the other visitor's session or URL."""
    app = _app(tmp_path)
    first_client, _, first_url = _analyse(app)
    second_client, status, second_url = _analyse(app)
    assert not status.startswith("500")
    assert second_url and second_url != first_url, \
        "the second visitor was handed the first visitor's run URL"
    # and still cannot read the other visitor's run
    st, _, _ = second_client.request("GET", first_url.rsplit("/progress", 1)[0])
    assert st.startswith("404"), st
