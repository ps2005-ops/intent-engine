"""A guest analysis must never end in a dead end. Measured, not assumed.

WHAT WAS MEASURED, AND WHERE THE FAULT ACTUALLY IS
--------------------------------------------------
Two of two live canary runs on the deployed preview disappeared between the
customer steps and the Q&A step, with no deploy in the window. Every later
request answered

    "This session does not have an analysis with that id."

`/readyz` on that same service reports `durability: EPHEMERAL_LIKELY` and
`separate_filesystem: false`: there is no persistent disk, so the ownership
record, the evidence and the composed decision all live inside the container
image and go when the instance is replaced.

So the analysis is genuinely gone and no code in this repository can bring it
back. What these tests pin is the thing that IS in the product's control: a
reader whose analysis was destroyed must be told that, by name, with the one
action that still works -- and a reader who was never entitled to that run
must still be refused exactly as before.

THE THREE OUTCOMES, KEPT APART
------------------------------
    RUN_RESTART_LOST   this session started this run; the service lost it
    RUN_NOT_OWNED      somebody else's run
    RUN_NOT_FOUND      no such run, and nothing to prove otherwise

The defect being fixed is that all three rendered the same page.
"""
import io
import time

import pytest

from intent_engine.webapp import run_recovery as R
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

SECRET = "s" * 40


class CookieClient:
    """Tracks EVERY cookie, not only `sid`.

    The journeys client keeps `sid` alone, which is enough for a suite that
    only ever asks about identity. The claim that survives an instance
    replacement is a second cookie, so a client that dropped it would prove
    the recovery path unreachable for reasons of its own making.
    """

    def __init__(self, app, host="127.0.0.1"):
        self.app, self.host = app, host
        self.cookies: dict = {}

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": self.host,
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for key, value in out["headers"]:
            if key != "Set-Cookie":
                continue
            name, _, rest = value.partition("=")
            if "Max-Age=0" in value:
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = rest.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def get(self, path):
        return self.request("GET", path)

    def sid(self):
        return self.cookies.get("sid")

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


def _make(tmp_path, **overrides):
    base = dict(env="test", secret=SECRET, demo_mode=True,
                web_store_path=tmp_path / "web.jsonl",
                fi_store_path=tmp_path / "fi.jsonl",
                ci_store_path=tmp_path / "ci.jsonl")
    base.update(overrides)
    return WebApp(AppConfig(**base), transport=_no_network, resolver=False)


def _instance_replaced(app, tmp_path):
    """A NEW instance with the SAME secret and NO disk carried over.

    This is the event that actually happens on the preview: not a process
    restart over a surviving disk (already covered in the demo-mode suite),
    but an instance replacement. The stores are empty because the filesystem
    they were on no longer exists.
    """
    return _make(tmp_path)


def _start_demo(client):
    """A guest starts an analysis. Returns its run id."""
    client.request("POST", "/demo", "")
    status, headers, _ = client.request(
        "POST", "/analyze", f"consent=on&csrf={client.csrf()}"
                            f"&website=https://northwind-demo.example")
    assert status.startswith("303"), status
    return headers["Location"].split("/runs/")[1].split("/")[0]


# --- the claim itself -------------------------------------------------------

def test_claim_round_trips():
    token = R.mint(SECRET, user_id="anon-1", run_id="r1", company="Meta")
    claim = R.verify(SECRET, token)
    assert claim and claim["uid"] == "anon-1" and claim["co"] == "Meta"
    assert R.proves(claim, user_id="anon-1", run_id="r1")


def test_a_tampered_claim_proves_nothing():
    token = R.mint(SECRET, user_id="anon-1", run_id="r1", company="Meta")
    head, body, sig = token.split(".")
    forged = R.mint("another-secret" * 4, user_id="anon-1", run_id="r1")
    assert R.verify(SECRET, forged) is None
    assert R.verify(SECRET, f"{head}.{body}x.{sig}") is None
    assert R.verify(SECRET, f"{head}.{body}.{sig[:-2]}xy") is None
    assert R.verify("", token) is None


def test_a_claim_is_scoped_to_one_run_and_one_session():
    claim = R.verify(SECRET, R.mint(SECRET, user_id="anon-1", run_id="r1"))
    assert not R.proves(claim, user_id="anon-1", run_id="r2")
    assert not R.proves(claim, user_id="anon-2", run_id="r1")
    assert not R.proves(claim, user_id="", run_id="r1")
    assert not R.proves(None, user_id="anon-1", run_id="r1")


def test_a_stale_or_future_claim_proves_nothing():
    now = time.time()
    old = R.mint(SECRET, user_id="u", run_id="r", now=now - R.CLAIM_TTL_SECONDS - 1)
    assert R.verify(SECRET, old, now=now) is None
    ahead = R.mint(SECRET, user_id="u", run_id="r", now=now + 3600)
    assert R.verify(SECRET, ahead, now=now) is None


def test_the_cookie_is_not_readable_by_page_script():
    header = R.cookie_header("v", secure=True)
    assert "HttpOnly" in header and "SameSite=Lax" in header
    assert "Secure" in header
    assert "Secure" not in R.cookie_header("v", secure=False)


# --- the product behaviour --------------------------------------------------

def test_a_run_is_claimed_the_moment_it_opens(tmp_path):
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    claim = R.verify(SECRET, client.cookies.get(R.COOKIE_NAME))
    assert claim is not None, "no claim was minted when the run opened"
    assert claim["run"] == run_id
    assert claim["co"], "the claim must name the company, or retry is a form"


def test_a_lost_run_is_named_and_offers_the_same_company(tmp_path, tmp_path_factory):
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    company = R.verify(SECRET, client.cookies[R.COOKIE_NAME])["co"]

    client.app = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))
    status, _, body = client.get(f"/runs/{run_id}")

    assert status == "200 OK", status
    assert "lost when the service restarted" in body.lower(), body[:400]
    assert "does not have an analysis with that id" not in body
    # The one action that still works, pre-filled: a reader who has to retype
    # the company has been handed a form, not a recovery.
    assert 'action="/analyze"' in body
    assert company in body


def test_every_customer_surface_recovers_not_just_the_result(tmp_path,
                                                             tmp_path_factory):
    """A restart between the steps and Q&A is the measured failure window."""
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    client.app = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))
    for route in ("", "/progress", "/intro", "/answer", "/slides", "/full",
                  "/story", "/history", "/connect", "/brief", "/evidence"):
        status, _, body = client.get(f"/runs/{run_id}{route}")
        assert status == "200 OK", f"{route} -> {status}"
        assert "lost when the service restarted" in body.lower(), route


def test_qa_after_an_instance_replacement_is_a_recovery_not_a_dead_end(
        tmp_path, tmp_path_factory):
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    csrf = client.csrf()
    client.app = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))
    status, _, body = client.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={csrf}&question=What+should+management+do%3F")
    assert "lost when the service restarted" in body.lower(), body[:300]


def test_the_retry_offered_on_the_recovery_page_actually_runs(
        tmp_path, tmp_path_factory):
    """A recovery button that cannot be pressed is a worse dead end."""
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    client.app = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))
    _s, _h, body = client.get(f"/runs/{run_id}")
    csrf = body.split('name="csrf" value="')[1].split('"')[0]
    company = body.split('name="company_name" value="')[1].split('"')[0]
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name={company.replace(' ', '+')}"
        f"&website=https://northwind-demo.example")
    assert status.startswith("303"), status
    assert "/runs/" in headers["Location"]


# --- isolation is unchanged -------------------------------------------------

def test_another_session_still_gets_the_ordinary_refusal(tmp_path,
                                                         tmp_path_factory):
    app = _make(tmp_path)
    owner = CookieClient(app)
    run_id = _start_demo(owner)
    replaced = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))

    stranger = CookieClient(replaced)
    stranger.request("POST", "/demo", "")
    status, _, body = stranger.get(f"/runs/{run_id}")
    assert status.startswith("404"), status
    assert "lost when the service restarted" not in body.lower()


def test_a_stolen_claim_cookie_proves_nothing_for_another_session(
        tmp_path, tmp_path_factory):
    """The claim names the user it was minted for. Presenting it from a
    different session must not widen anything -- otherwise a copied cookie
    would be an access-control hole rather than an explanation."""
    app = _make(tmp_path)
    owner = CookieClient(app)
    run_id = _start_demo(owner)
    stolen = owner.cookies[R.COOKIE_NAME]

    replaced = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))
    stranger = CookieClient(replaced)
    stranger.request("POST", "/demo", "")
    stranger.cookies[R.COOKIE_NAME] = stolen
    status, _, body = stranger.get(f"/runs/{run_id}")
    assert status.startswith("404"), status
    assert "lost when the service restarted" not in body.lower()


def test_a_claim_never_opens_a_run_that_still_exists_for_someone_else(
        tmp_path):
    """The claim is consulted only AFTER ownership fails, so it can never
    reach a live run. A forged claim for another visitor's live run must not
    change the refusal."""
    app = _make(tmp_path)
    owner = CookieClient(app)
    run_id = _start_demo(owner)

    stranger = CookieClient(app)
    stranger.request("POST", "/demo", "")
    uid = app.auth.session(stranger.sid())["user_id"]
    stranger.cookies[R.COOKIE_NAME] = R.mint(
        SECRET, user_id=uid, run_id=run_id, company="Northwind")
    status, _, body = stranger.get(f"/runs/{run_id}")
    assert status.startswith("404"), status
    assert "northwind" not in body.lower() or "lost when" not in body.lower()


def test_an_unknown_run_id_is_still_a_plain_refusal(tmp_path):
    app = _make(tmp_path)
    client = CookieClient(app)
    client.request("POST", "/demo", "")
    status, _, body = client.get("/runs/does-not-exist")
    assert status.startswith("404"), status
    assert "lost when the service restarted" not in body.lower()


def test_a_live_run_is_untouched_by_any_of_this(tmp_path):
    app = _make(tmp_path)
    client = CookieClient(app)
    run_id = _start_demo(client)
    status, _, body = client.get(f"/runs/{run_id}")
    assert status.startswith("30") or status == "200 OK", status
    assert "lost when the service restarted" not in body.lower()


# --- the instrument ---------------------------------------------------------

def test_version_reports_who_is_serving(tmp_path):
    app = _make(tmp_path)
    client = CookieClient(app)
    status, _, body = client.get("/version")
    import json
    payload = json.loads(body)
    assert status == "200 OK"
    process = payload.get("process") or {}
    assert process.get("boot_id"), "a restart must be observable from outside"
    assert isinstance(process.get("uptime_seconds"), (int, float))


def test_readyz_reports_whether_a_disk_exists_at_all(tmp_path):
    app = _make(tmp_path)
    client = CookieClient(app)
    import json
    _s, _h, body = client.get("/readyz")
    payload = json.loads(body)
    mounts = payload.get("persistent_mounts")
    assert isinstance(mounts, list) and mounts
    assert {"path", "exists", "writable", "separate_filesystem"} <= set(
        mounts[0])
    assert payload.get("process", {}).get("boot_id")


def test_a_claim_does_not_survive_into_the_next_request_on_the_thread(
        tmp_path, tmp_path_factory):
    """Worker threads are reused; a claim is not.

    Driven through the app the way the server does -- one thread, several
    requests, different browsers -- because the leak this guards against is
    invisible to a test that builds one client and asks once.
    """
    app = _make(tmp_path)
    owner = CookieClient(app)
    run_id = _start_demo(owner)
    replaced = _instance_replaced(app, tmp_path_factory.mktemp("replaced"))

    # Browser 1 presents its claim to the replaced instance and is recovered.
    owner.app = replaced
    _s, _h, recovered = owner.get(f"/runs/{run_id}")
    assert "lost when the service restarted" in recovered.lower()

    # Browser 2, same thread, immediately after, carrying no claim at all.
    stranger = CookieClient(replaced)
    stranger.request("POST", "/demo", "")
    status, _h, body = stranger.get(f"/runs/{run_id}")
    assert status.startswith("404"), status
    assert "lost when the service restarted" not in body.lower()
    assert replaced._request.claim is None
