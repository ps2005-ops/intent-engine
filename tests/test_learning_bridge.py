"""Learning is published; it just does not cross per company.

`strategic_publish` never passes `learning_summary` to the per-company
snapshot, so it serialises UNAVAILABLE in all 26 -- which read as "learning
is not published". It is published, globally, under contract
`market_learning_report.v1`, because a learning session reads many companies
at once and its effects belong to the engine rather than to any one subject.

These tests pin the crossing, and pin the two things a learning surface must
never do: compute its own metric, or turn a busy period into a productive one.
"""
import json

import pytest

from intent_engine.demo_dossier import learning_bridge as LB


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / LB.DIRNAME / "daily"
    folder.mkdir(parents=True)
    return tmp_path


def _write(root, payload, period="daily", name="2026-08-12.json"):
    folder = root / LB.DIRNAME / period
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(payload))


def _report(**evidence):
    base = {"arrivals_total": 86, "evidence_rows": 6, "re_observations": 80,
            "evidence_that_changed_something": 17,
            "new_information_share": 0.0698,
            "effects_by_type": {"NO_CHANGE": 19, "CREATED": 6}}
    base.update(evidence)
    return {"contract": LB.CONTRACT, "period": "day",
            "channels": {"evidence": base},
            "bottleneck": {"bottleneck": "RECONCILIATION"}}


# --- the crossing ----------------------------------------------------------

def test_a_published_report_is_read(root):
    _write(root, _report())
    out = LB.load("day", root=root)
    assert out.available is True
    assert out.payload["bottleneck"]["bottleneck"] == "RECONCILIATION"


def test_the_latest_report_wins(root):
    _write(root, _report(arrivals_total=1), name="2026-08-01.json")
    _write(root, _report(arrivals_total=99), name="2026-08-12.json")
    out = LB.load("day", root=root)
    assert out.payload["channels"]["evidence"]["arrivals_total"] == 99


# --- absence is three different facts --------------------------------------

def test_an_unconfigured_deployment_is_not_no_learning(monkeypatch):
    """'The disk is not mounted' and 'we learned nothing' are different, and
    a reader who cannot tell them apart reads the first as the second.

    `_root` is patched rather than passing root=None: None means "use the
    configured root", and a first version of this test read the repository's
    own committed reports and asserted the opposite of what it meant.
    """
    monkeypatch.setattr(LB, "_root", lambda: None)
    out = LB.load("day")
    assert out.state == LB.NOT_CONFIGURED
    assert "no market snapshot root is configured" in out.reason


def test_passing_no_root_uses_the_configured_one(root):
    """The default is not "nowhere" -- it is the deployment's own root."""
    _write(root, _report())
    monkeypatch_root = root
    import intent_engine.demo_dossier.learning_bridge as _LB
    original = _LB._root
    try:
        _LB._root = lambda: monkeypatch_root
        assert _LB.load("day").available is True
    finally:
        _LB._root = original


def test_an_empty_root_says_nothing_was_published(root):
    out = LB.load("day", root=root)
    assert out.state == LB.NOT_PUBLISHED
    assert "published no day learning report" in out.reason


def test_a_foreign_document_is_refused(root):
    """Refusing a document whose shape is not the one this understands is
    better than reading fields out of it and hoping."""
    _write(root, {"contract": "something_else.v1", "channels": {}})
    out = LB.load("day", root=root)
    assert out.state == LB.UNREADABLE
    assert "not a market_learning_report" in out.reason


def test_unparseable_is_a_state_not_a_crash(root):
    (root / LB.DIRNAME / "daily" / "2026-08-12.json").write_text("{ broken")
    out = LB.load("day", root=root)
    assert out.state == LB.UNREADABLE


# --- activity is not learning ----------------------------------------------

def test_a_busy_period_that_taught_nothing_is_not_productive(root):
    """The headline defect this surface prevents: 86 arrivals looks like
    progress, and if nothing changed the model it is not."""
    _write(root, _report(evidence_that_changed_something=0))
    out = LB.activity_versus_learning(LB.load("day", root=root))
    assert out["verdict"] == LB.PLATEAUING
    assert "taught the engine nothing" in out["why"]


def test_mostly_re_observed_reads_as_stable(root):
    _write(root, _report())
    out = LB.activity_versus_learning(LB.load("day", root=root))
    assert out["verdict"] == LB.STABLE
    assert out["arrivals"] == 86 and out["novel"] == 6
    assert out["re_observed"] == 80


def test_the_tested_and_unchanged_count_survives(root):
    """NO_CHANGE is a RESULT -- something was tested and held. Dropping it
    makes a careful period look like an idle one."""
    _write(root, _report())
    out = LB.activity_versus_learning(LB.load("day", root=root))
    assert out["tested_and_unchanged"] == 19


def test_a_thin_period_refuses_to_judge(root):
    _write(root, _report(arrivals_total=3, evidence_that_changed_something=0))
    out = LB.activity_versus_learning(LB.load("day", root=root))
    assert out["verdict"] == LB.INSUFFICIENT_SAMPLE


def test_no_metric_is_invented_when_the_report_is_absent(root):
    out = LB.activity_versus_learning(LB.load("day", root=root))
    assert out["state"] == LB.NOT_PUBLISHED
    assert "verdict" not in out


def test_the_reports_own_unavailable_survives(root):
    """The report marks independence UNAVAILABLE with a note saying it is
    produced founder-side. That honesty must reach the reader rather than
    being quietly completed from founder data."""
    payload = _report()
    payload["channels"]["evidence"]["independent_evidence_rows"] = "UNAVAILABLE"
    _write(root, payload)
    out = LB.load("day", root=root)
    ev = out.payload["channels"]["evidence"]
    assert ev["independent_evidence_rows"] == "UNAVAILABLE"


# --- the live surface ------------------------------------------------------

def test_the_learning_page_renders_and_leads_with_learning(tmp_path):
    """The headline must not be the arrival count. A cycle that re-reads
    eighty pages and changes nothing has been busy, not productive."""
    import io

    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    from intent_engine.webapp.storage_state import record_boot

    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "w.jsonl",
                       fi_store_path=tmp_path / "f.jsonl",
                       ci_store_path=tmp_path / "c.jsonl", demo_mode=True)
    record_boot(tmp_path, boot_id="prev")
    app = WebApp(config, transport=lambda u, t: None, resolver=False)
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/learning-acceleration",
           "CONTENT_LENGTH": "0", "HTTP_HOST": "127.0.0.1",
           "HTTP_COOKIE": "", "wsgi.input": io.BytesIO(b"")}
    out = {}

    def sr(status, headers):
        out["status"] = status

    body = b"".join(app(env, sr)).decode()
    assert out["status"].startswith("200")
    # the page states the distinction rather than only the counts
    assert "reading more is not the same as knowing more" in body
    # and never leaks a raw contract or enum wall to the reader
    assert "market_learning_report.v1" not in body
