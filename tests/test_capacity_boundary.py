"""The admission boundary, driven through the real POST /analyze path.

MEASURED LIVE on 25409f14 under deliberate pressure: capacity is one active
plus three pending, six near-simultaneous submissions produced four admitted
runs and two refusals. The refusals were explicit 503s with no run created --
the mechanism was right; what the reader was TOLD was not. It said "the
company was identified and its public evidence was retrieved" about an
analysis that never started, because the refusal message contains "NO ANALYSIS
CREDIT WAS USED" and the classifier matched the bare needle "credit".

CAPACITY IS SET, NOT RACED. Two earlier versions of this file filled the pool
with a blocking transport and with fake `_analysis_inflight` entries. The
first depended on workers not finishing between submits and asserted on a
boundary it had never crossed; the second tripped the autouse fixture in
conftest, which waits for every in-flight run and correctly refused to find a
worker that did not exist. The constants ARE the admission gate, so setting
them reaches the same branch deterministically.
"""
from __future__ import annotations

from test_async_analysis import _async_app                       # noqa: F401
from test_strategic_intelligence import _WsgiClient              # noqa: F401


def _submit(app, company):
    client = _WsgiClient(app)
    client.request("POST", "/demo")
    status, headers, body = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={company}"
        f"&website=https://{company.lower()}.example")
    location = next((v for k, v in headers.items()
                     if k.lower() == "location"), "")
    return status, location, (body if isinstance(body, str) else body.decode())


def _at_capacity(app):
    app.MAX_ACTIVE_ANALYSES = 0
    app.MAX_PENDING_ANALYSES = 0


def test_a_refused_submission_never_reaches_a_progress_page(tmp_path):
    app = _async_app(tmp_path)
    _at_capacity(app)
    status, location, _body = _submit(app, "Acme")
    assert status.startswith("503"), f"admission was not refused: {status}"
    assert "/progress" not in location, (
        "a refused submission redirected to a progress page for work that "
        "was never queued")


def test_the_refusal_page_is_truthful_and_bounded(tmp_path):
    app = _async_app(tmp_path)
    _at_capacity(app)
    _status, _location, body = _submit(app, "Acme")
    text = body.lower()
    assert "did not start" in text
    assert "try again" in text
    # It may not claim work it never did.
    for lie in ("evidence was retrieved", "what was retrieved",
                "the evidence below"):
        assert lie not in text, f"the refusal page claims {lie!r}"
    # And it may not poll itself, which is a spinner in disguise.
    assert 'http-equiv="refresh"' not in text


def test_a_refused_submission_gives_back_its_quota(tmp_path):
    """THE LEDGER, NOT THE SENTENCE.

    An earlier version asserted only that the page says "no analysis credit
    was used" — so deleting `_release_demo_quota` left it green, and the
    product would have charged for work it never did while telling the reader
    it had not. The mutation reported NOT_CAUGHT and was right.
    """
    app = _async_app(tmp_path)
    _at_capacity(app)
    before = {ip: list(v) for ip, v in app._demo_ip_hits.items()}
    _status, _location, body = _submit(app, "Acme")
    after = {ip: list(v) for ip, v in app._demo_ip_hits.items()}
    charged = sum(len(v) for v in after.values()) - \
        sum(len(v) for v in before.values())
    assert charged == 0, (
        f"a refused submission consumed {charged} demo credit(s) for an "
        f"analysis that never started")
    # And it still says so, because a silent refund a reader cannot see is
    # indistinguishable from being charged.
    assert "no analysis credit was used" in body.lower()


def test_a_refused_submission_creates_no_run(tmp_path):
    """The reader is not handed an id for work nobody queued."""
    app = _async_app(tmp_path)
    _at_capacity(app)
    _status, location, body = _submit(app, "Acme")
    assert "/runs/" not in location
    assert not app._analysis_inflight


def test_an_admitted_run_is_unchanged(tmp_path):
    """The ordinary path must not move."""
    app = _async_app(tmp_path)
    status, location, _body = _submit(app, "Acme")
    assert status.startswith("303")
    assert "/progress" in location


def test_capacity_frees_and_a_retry_is_admitted(tmp_path):
    """Refusal is retryable in fact, not only in wording."""
    app = _async_app(tmp_path)
    _at_capacity(app)
    status, _location, _body = _submit(app, "Acme")
    assert status.startswith("503")
    app.MAX_ACTIVE_ANALYSES, app.MAX_PENDING_ANALYSES = 1, 3
    status, location, _body = _submit(app, "Retried")
    assert status.startswith("303"), "a retry after capacity freed was refused"
    assert "/progress" in location


def test_every_outcome_is_one_bounded_class(tmp_path):
    """No third state: admitted with a run, or refused with none."""
    app = _async_app(tmp_path)
    seen = []
    for i in range(4):
        if i == 2:
            _at_capacity(app)
        seen.append(_submit(app, f"Con{i}")[:2])
    for status, location in seen:
        admitted = status.startswith("303") and "/progress" in location
        refused = status.startswith("503") and "/progress" not in location
        assert admitted or refused, (
            f"ambiguous outcome: status={status} location={location!r}")
    assert any(s.startswith("503") for s, _ in seen), "capacity never refused"
    assert any(s.startswith("303") for s, _ in seen), "nothing was admitted"
