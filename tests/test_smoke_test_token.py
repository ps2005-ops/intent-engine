"""The production smoke-test path.

Engineering smoke traffic was consuming the same allowance as real visitors, so
repeated production checks returned 429 and live validation stalled twice. A
valid token buys exactly one thing -- the demo quota -- and nothing else.
"""
from company_fixture_pages import transport as fixture_pages
from test_webapp_demo_mode import DEMO_URL, Client, _make, _start_demo

TOKEN = "s3cr3t-smoke-token-value"
HEADER = "HTTP_X_FOUNDER_INTELLIGENCE_SMOKE_TEST"


def _app(tmp_path, *, token=None, per_hour=1):
    kw = dict(transport=fixture_pages, autorun_sources=True,
              demo_ip_analyses_per_hour=per_hour,
              demo_session_analyses_per_day=per_hour)
    if token is not None:
        kw["smoke_test_token"] = token
    return _make(tmp_path, **kw)


def _analyse(app, *, token=None):
    c = Client(app)
    env_extra = {HEADER: token} if token is not None else {}
    status, headers, _ = c.request(
        "POST", "/analyze", f"consent=on&website={DEMO_URL}",
        **({"env_extra": env_extra} if env_extra else {}))
    return status, headers


# --- the quota itself still exists -----------------------------------------

def test_public_quota_is_still_enforced_without_a_token(tmp_path):
    app = _app(tmp_path, token=TOKEN, per_hour=1)
    first, _ = _analyse(app)
    second, _ = _analyse(app)
    assert first.startswith("303")
    assert second.startswith("429"), \
        "the public rate limit must still apply to ordinary requests"


# --- the mechanism does not exist unless configured ------------------------

def test_no_token_configured_means_the_header_is_ignored(tmp_path):
    """Absent variable -> behaviour byte-for-byte what it was."""
    app = _app(tmp_path, token=None, per_hour=1)
    _analyse(app)
    status, _ = _analyse(app, token=TOKEN)
    assert status.startswith("429"), \
        "a header was honoured with no token configured"


def test_wrong_token_behaves_like_an_ordinary_request(tmp_path):
    app = _app(tmp_path, token=TOKEN, per_hour=1)
    _analyse(app)
    status, _ = _analyse(app, token="not-the-token")
    assert status.startswith("429")


def test_empty_token_header_behaves_like_an_ordinary_request(tmp_path):
    app = _app(tmp_path, token=TOKEN, per_hour=1)
    _analyse(app)
    status, _ = _analyse(app, token="")
    assert status.startswith("429")


def test_empty_configured_token_cannot_be_matched_by_an_empty_header(tmp_path):
    """A blank secret must not mean "everyone is a smoke test"."""
    app = _app(tmp_path, token="", per_hour=1)
    _analyse(app)
    status, _ = _analyse(app, token="")
    assert status.startswith("429")


# --- what a valid token does, and does not, buy ----------------------------

def test_a_valid_token_bypasses_the_quota(tmp_path):
    app = _app(tmp_path, token=TOKEN, per_hour=1)
    _analyse(app)
    assert _analyse(app)[0].startswith("429")        # quota is genuinely spent
    for _ in range(3):
        status, _ = _analyse(app, token=TOKEN)
        assert status.startswith("303"), status


def test_a_valid_token_does_not_bypass_consent(tmp_path):
    app = _app(tmp_path, token=TOKEN)
    c = Client(app)
    status, _, _ = c.request("POST", "/analyze", f"website={DEMO_URL}",
                             env_extra={HEADER: TOKEN})
    assert status.startswith("400"), "consent was skipped for a smoke request"


def test_a_valid_token_does_not_bypass_csrf(tmp_path):
    app = _app(tmp_path, token=TOKEN)
    c = _start_demo(app)
    status, _, _ = c.request(
        "POST", "/analyze", f"consent=on&website={DEMO_URL}&csrf=wrong",
        env_extra={HEADER: TOKEN})
    assert status.startswith("403"), "CSRF was skipped for a smoke request"


def test_a_valid_token_does_not_bypass_run_ownership(tmp_path):
    app = _app(tmp_path, token=TOKEN)
    owner = Client(app)
    _, headers, _ = owner.request("POST", "/analyze",
                                  f"consent=on&website={DEMO_URL}",
                                  env_extra={HEADER: TOKEN})
    run_path = headers["Location"].rsplit("/progress", 1)[0]
    intruder = _start_demo(app)
    status, _, _ = intruder.request("GET", run_path, env_extra={HEADER: TOKEN})
    assert status.startswith("404"), \
        "a smoke token reached another visitor's run"


# --- the secret must not leak ----------------------------------------------

def test_the_token_never_appears_in_rendered_output(tmp_path):
    app = _app(tmp_path, token=TOKEN)
    c = Client(app)
    _, _, landing = c.request("GET", "/")
    _, headers, _ = c.request("POST", "/analyze",
                              f"consent=on&website={DEMO_URL}",
                              env_extra={HEADER: TOKEN})
    _, _, page = c.request("GET", headers["Location"])
    for body in (landing, page):
        assert TOKEN not in body


def test_the_bypass_is_audited_without_the_token(tmp_path, caplog):
    import logging
    app = _app(tmp_path, token=TOKEN)
    with caplog.at_level(logging.INFO):
        _analyse(app, token=TOKEN)
    text = caplog.text
    assert "internal_smoke_test_rate_limit_bypass_used" in text
    assert TOKEN not in text, "the token was written to the log"
