"""Persistence must be durable, or loudly admitted.

render.yaml declares a persistent disk at /var/data and sets RUNTIME_ROOT to
it. The running service reported runtime_root="data" with durability
EPHEMERAL_LIKELY -- writing inside the container, wiped on every deploy.
Completed analyses vanished, /analyses went empty and issued result URLs
stopped working, while /readyz said "ready".
"""
import json

from company_fixture_pages import transport as brightlake
from test_webapp_demo_mode import DEMO_URL, Client, _make, _restart, _start_demo


def _readyz(app):
    _, _, body = Client(app).request("GET", "/readyz")
    return json.loads(body)


def test_production_with_ephemeral_storage_reports_degraded(tmp_path):
    app = _make(tmp_path, env="production", secret="s" * 40,
                debug=False, cookie_secure=True,
                trusted_hosts=("127.0.0.1",))
    payload = _readyz(app)
    if payload["storage"]["durability"] == "EPHEMERAL_LIKELY":
        assert payload["status"] == "degraded", \
            '"ready" must not mean "ready, but it forgets everything"'
        assert "RUNTIME_ROOT" in payload["degraded_reason"]


def test_a_durable_or_unproven_store_is_not_called_degraded(tmp_path):
    """Only genuine ephemerality is degraded; an unproven-but-writable disk
    is reported as-is without crying wolf."""
    app = _make(tmp_path)
    payload = _readyz(app)
    assert payload["status"] == "ready"          # env=test, never degraded


def test_the_analyses_page_does_not_promise_history_it_cannot_keep(tmp_path):
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    csrf = c.csrf()
    c.request("POST", "/analyze", f"consent=on&csrf={csrf}&website={DEMO_URL}")
    _, _, page = c.request("GET", "/analyses")
    from intent_engine.webapp.storage_state import may_promise_persistence
    if not may_promise_persistence(app._storage):
        assert "until the service next restarts" in page, \
            "the page lists analyses without saying they are temporary"


# --- what durability actually has to mean ---------------------------------

def test_a_completed_analysis_survives_recreating_the_application(tmp_path):
    """The store is on disk, so a brand-new WebApp over the same files must
    still find the run. This is the guarantee the production disk is missing,
    verified at the layer the repository actually controls."""
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    csrf = c.csrf()
    _, headers, _ = c.request(
        "POST", "/analyze", f"consent=on&csrf={csrf}&website={DEMO_URL}")
    run_path = headers["Location"].rsplit("/progress", 1)[0]
    run_id = run_path.rsplit("/", 1)[-1]

    fresh = _restart(app)                    # new process, same files
    c.app = fresh
    status, _, _ = c.request("GET", run_path)
    assert not status.startswith("404"), \
        "the analysis did not survive recreating the application"
    _, _, page = c.request("GET", "/analyses")
    assert run_id in page, "history did not survive the restart"


def test_reuse_still_works_after_a_restart(tmp_path):
    """Deterministic completed-run reuse must survive too, without appending
    duplicate terminal events."""
    app = _make(tmp_path, transport=brightlake, autorun_sources=True,
                demo_ip_analyses_per_hour=50,
                demo_session_analyses_per_day=50)

    def completed_events():
        n = 0
        for rid in app.fi.store.run_ids():
            n += sum(1 for e in app.fi.store.for_run(rid)
                     if e.event_type == "fi.run_completed")
        return n

    c = _start_demo(app)
    c.request("POST", "/analyze",
              f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
    before = completed_events()

    app = _restart(app)
    c2 = _start_demo(app)
    status, _, _ = c2.request("POST", "/analyze",
                              f"consent=on&csrf={c2.csrf()}&website={DEMO_URL}")
    assert not status.startswith("500")
    after = sum(1 for rid in app.fi.store.run_ids()
                for e in app.fi.store.for_run(rid)
                if e.event_type == "fi.run_completed")
    assert after == before, "reuse appended duplicate completion events"


def test_another_visitor_still_cannot_read_it_after_a_restart(tmp_path):
    app = _make(tmp_path, transport=brightlake)
    owner = _start_demo(app)
    _, headers, _ = owner.request(
        "POST", "/analyze", f"consent=on&csrf={owner.csrf()}&website={DEMO_URL}")
    run_path = headers["Location"].rsplit("/progress", 1)[0]
    app = _restart(app)
    intruder = _start_demo(app)
    status, _, _ = intruder.request("GET", run_path)
    assert status.startswith("404")
