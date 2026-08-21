"""Drive the real customer journey and persist everything it renders.

AUTOMATION OF THE CUSTOMER FLOW, NOT AN INTERNAL SHORTCUT. This walks
landing -> demo -> CSRF -> company entry -> progress -> auto-advance -> the
six steps -> Q&A -> evidence, exactly as a browser does. A harness that
posted straight to an internal entry point would measure something the
customer cannot reach, which is the one thing this programme may not do.

EVERY ROUTE IS WRITTEN THE MOMENT IT SETTLES. A free preview restarts, and a
restart clears in-memory guest sessions and destroys the run. Buffering a
company's journey and writing at the end means a restart costs the whole
company including the surfaces that had already rendered — measured, once,
at the cost of the most valuable run in a window.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://intent-engine-preview-bridge.onrender.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

#: The six customer steps, in the order the product walks them.
STEPS = ("intro", "slides", "full", "story", "history", "connect")
#: Routes reachable from the steps, captured for the audit.
EXTRA = ("sources", "evidence", "report", "brief")

#: The ten board questions, asked in ONE session rather than one per browser
#: visit. Strategic quality is judged from the persisted answers.
BOARD_QUESTIONS = (
    "What should management do?",
    "Why now?",
    "What's the biggest risk?",
    "What would prove this wrong?",
    "Who's the real competitor?",
    "What does the market believe?",
    "What's the weakest assumption?",
    "What impossible hypothesis should we investigate?",
    "What should we measure next?",
    "What would you tell the board?",
)

READY, FAILED, BLOCKED, TIMEOUT = "READY", "FAILED", "BLOCKED", "TIMEOUT"
#: The run existed and then did not. A free preview spins down and restarts,
#: and a restart clears in-memory guest sessions.
RUN_LOST = "RUN_LOST"
#: The run is alive and a response came back that is not an answer. Almost
#: always this harness's own fault; it is a state so that it is impossible to
#: mistake for the product's.
UNREADABLE = "UNREADABLE"

#: WHAT A DEAD RUN LOOKS LIKE FROM OUTSIDE. Measured: a canary wave captured
#: sixteen valid routes per company and then ten ERROR PAGES per company as
#: "answers" — "This session does not have an analysis with that id" — and
#: the audit compared them and reported a catastrophic collapse, because
#: forty identical error pages are, technically, identical. An unrecognised
#: page stored as an answer is the same defect as a zero denominator read as
#: absence.
RUN_GONE_MARKERS = (
    "does not have an analysis with that id",
    "that analysis is not available here",
    "analyses are kept per session",
    # The recovery screen. It is a BETTER page than the 404 it replaced and
    # it is still not an answer: a harness that stored it would report that
    # every company gave the same strategic reading.
    "was lost when the service restarted",
)

#: A response that is a product failure page rather than a strategic answer.
#: Distinct from RUN_GONE: these say the run is fine and this REQUEST was not.
#: Kept separate because the two have different causes and different fixes,
#: and collapsing them is how a routing mistake in the harness would have
#: been read as a reliability problem in the product.
NOT_AN_ANSWER_MARKERS = (
    "page not found",
    "something went wrong on our side",
    "that is not available to this session",
    "invalid csrf token",
    "too many analyses for now",
)


def run_is_gone(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in RUN_GONE_MARKERS)


def not_an_answer(text: str, status: int = 200) -> str:
    """Why this response is not a strategic answer, or "" if it is one.

    MEASURED, AND IT WAS THE HARNESS. This module posted every board question
    to `/runs/<id>/answer`, which is a GET-only route: the product's Q&A form
    posts to `/runs/<id>/conversation`. Ten "answers" per company would have
    been ten copies of "page not found", stored as answers and then compared
    for similarity -- the fifth instrument defect in this programme and the
    same shape as the four before it. An unrecognised page is named here so
    it can never be counted downstream.
    """
    body = (text or "").strip()
    if not body:
        return "EMPTY_RESPONSE"
    if status >= 400:
        return f"HTTP_{status}"
    low = body.lower()
    for marker in NOT_AN_ANSWER_MARKERS:
        if marker in low:
            return "FAILURE_PAGE"
    return ""


def _restart_observed(before: dict, after: dict):
    """Did the serving process change between these two samples?

    Returns True, False, or None when either sample is missing -- an unknown
    is not a no. A run that vanished while the boot id held steady is a
    DIFFERENT defect from one that vanished across a restart, and reporting
    both as "lost" is what sent a previous session hunting for an application
    bug that was an instance replacement.
    """
    a, b = (before or {}).get("boot_id"), (after or {}).get("boot_id")
    if not a or not b:
        return None
    return a != b


def text_of(page: str) -> str:
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    import html as _html
    return re.sub(r"\s+", " ", _html.unescape(body)).strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


class Session:
    """One anonymous guest session, with its own cookie jar."""

    def __init__(self, base: str = DEFAULT_BASE, timeout: float = 180.0):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.errors: list = []

    def get(self, path: str):
        req = urllib.request.Request(self.base + path,
                                     headers={"User-Agent": UA})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8",
                                                             "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, self.base + path, exc.read().decode("utf-8",
                                                                 "replace")
        except Exception as exc:                            # noqa: BLE001
            self.errors.append(f"GET {path}: {type(exc).__name__}")
            return 0, self.base + path, ""

    def post(self, path: str, data: dict, ref: str = "/demo"):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(self.base + path, data=body, headers={
            "User-Agent": UA, "Origin": self.base, "Referer": self.base + ref,
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8",
                                                             "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, self.base + path, exc.read().decode("utf-8",
                                                                 "replace")
        except Exception as exc:                            # noqa: BLE001
            self.errors.append(f"POST {path}: {type(exc).__name__}")
            return 0, self.base + path, ""

    @staticmethod
    def csrf(page: str) -> str:
        match = re.search(r'name="csrf" value="([^"]+)"', page)
        return match.group(1) if match else ""


def process_identity(base: str = DEFAULT_BASE) -> dict:
    """Which process is serving, right now. Cheap enough to call per company.

    A restart is the one explanation for a lost run that the application
    cannot report about itself -- the instance that would have logged it is
    the instance that went away. Sampling this before and after each company
    turns "the run disappeared" into "the run disappeared AND the boot id
    changed", which is a measurement rather than a hypothesis.
    """
    try:
        req = urllib.request.Request(base.rstrip("/") + "/version",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return dict(json.load(r).get("process") or {})
    except Exception:                                       # noqa: BLE001
        return {}


class KeepWarm:
    """Hold the preview awake for the duration of a wave.

    NOT A WAY OF HIDING RESTARTS. A free instance is recycled after a period
    of inactivity, and the wave's own pacing gap -- six minutes, which is the
    demo quota -- is a period of inactivity. That is a CONFOUND: a run lost to
    an idle recycle and a run lost to a crash look identical from outside, and
    only one of them says anything about the product.

    So the idle path is removed and the measurement kept: `restart_observed`
    still records every boot-id change, and a restart seen while this is
    running is a restart that idleness does not explain.

    `/healthz` returns a constant and touches no storage; it is the cheapest
    request the service serves.
    """

    def __init__(self, base: str = DEFAULT_BASE, every: float = 120.0):
        import threading
        self.base, self.every = base.rstrip("/"), every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, daemon=True)

    def _beat(self) -> None:
        while not self._stop.wait(self.every):
            try:
                req = urllib.request.Request(self.base + "/healthz",
                                             headers={"User-Agent": UA})
                urllib.request.urlopen(req, timeout=20).read()
            except Exception:                               # noqa: BLE001
                pass                # a missed beat is not worth stopping for

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        return False


def deployed_sha(base: str = DEFAULT_BASE) -> str:
    """The SHA the capture is against. A capture without one cannot be
    compared to anything, which is how eight companies came to be spread
    across five builds."""
    try:
        req = urllib.request.Request(base.rstrip("/") + "/version",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return str(json.load(r).get("commit") or "")[:7]
    except Exception:                                       # noqa: BLE001
        return "unknown"


class Capture:
    """The canonical on-disk artifact for one company on one SHA."""

    def __init__(self, root: pathlib.Path, sha: str, company: str):
        self.dir = pathlib.Path(root) / sha / slug(company)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = {"company": company, "deployed_sha": sha,
                         "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                      time.gmtime()),
                         "routes": {}, "progress": []}

    def route(self, name: str, status: int, url: str, raw: str) -> None:
        """Write a route THE MOMENT IT SETTLES. See the module docstring."""
        body = text_of(raw)
        (self.dir / f"{name}.txt").write_text(body, "utf-8")
        (self.dir / f"{name}.html").write_text(raw, "utf-8")
        self.manifest["routes"][name] = {
            "status": status, "final_url": url, "chars": len(body),
            "html_chars": len(raw)}
        self.flush()

    def json_file(self, name: str, payload) -> None:
        (self.dir / name).write_text(json.dumps(payload, indent=2), "utf-8")
        self.flush()

    def flush(self) -> None:
        (self.dir / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2), "utf-8")


def wait_for_run(session: Session, run_id: str, *, timeout: float = 480.0,
                 poll: float = 6.0):
    """Wait QUIETLY. Returns (state, landed_url, seconds, samples).

    Previous sessions burned model turns narrating "still running". A wait is
    a script's job; the only interesting moment is the state change.
    """
    started = time.time()
    samples = []
    while time.time() - started < timeout:
        status, url, page = session.get(f"/runs/{run_id}/progress")
        if len(samples) < 3:
            samples.append({"t": round(time.time() - started),
                            "text": text_of(page)[:300]})
        if status in (0, 500, 502, 503):
            return FAILED, url, round(time.time() - started), samples
        if "/progress" not in url:
            return READY, url, round(time.time() - started), samples
        low = text_of(page).lower()
        if "limit reached" in low or "429" in low:
            return BLOCKED, url, round(time.time() - started), samples
        time.sleep(poll)
    return TIMEOUT, "", round(time.time() - started), samples


def capture_company(name: str, cik: str = "", ticker: str = "", *,
                    base: str = DEFAULT_BASE, website: str = "",
                    root: pathlib.Path = None, sha: str = "") -> dict:
    """One company, end to end, through the customer flow. Never raises."""
    root = pathlib.Path(root or "docs/execution/v5/pre100_60/live_captures")
    sha = sha or deployed_sha(base)
    cap = Capture(root, sha, name)
    session = Session(base)
    result = {"company": name, "deployed_sha": sha, "status": FAILED,
              "run_id": "", "capture_path": str(cap.dir)}

    result["process_before"] = process_identity(base)
    cap.manifest["process_before"] = result["process_before"]
    cap.flush()

    session.get("/")
    session.post("/demo", {})
    _s, _u, entry = session.get("/demo")
    csrf = Session.csrf(entry)
    if not csrf:
        result["failure"] = "no csrf on the entry page"
        cap.manifest.update(result)
        cap.flush()
        return result

    # The landing form takes a name OR a website; both are fields a customer
    # fills in, so supplying either is still the customer flow. `website` is
    # what makes this harness drivable against a build with no outbound
    # network, which is where its own defects get found without live quota.
    form = {"csrf": csrf, "consent": "on", "company_name": name}
    if website:
        form["website"] = website
    if cik:
        form.update({"suggest_confirmed": name, "suggest_cik": cik})
    if ticker:
        form["suggest_ticker"] = ticker
    status, url, page = session.post("/analyze", form)
    if "/runs/" not in url:
        low = text_of(page).lower()
        result["status"] = BLOCKED if ("limit reached" in low) else FAILED
        result["failure"] = f"analyze did not open a run (HTTP {status})"
        result["entry_text"] = text_of(page)[:400]
        cap.manifest.update(result)
        cap.flush()
        return result

    run_id = url.split("/runs/")[1].split("/")[0]
    result["run_id"] = run_id
    cap.manifest["run_id"] = run_id
    cap.flush()

    state, landed, seconds, samples = wait_for_run(session, run_id)
    cap.manifest["progress"] = samples
    result.update({"status": state, "seconds": seconds,
                   "auto_advanced": bool(landed), "landed_on": landed})
    cap.manifest.update({"status": state, "seconds": seconds,
                         "auto_advanced": bool(landed)})
    cap.flush()
    if state != READY:
        return result

    # THE SIX CUSTOMER STEPS FIRST, THEN Q&A, THEN THE REST.
    #
    # Q&A is the fragile half: it needs the run object to still be resident,
    # and a free preview restarts. A wave that captured sixteen routes and
    # then asked ten questions lost every answer to "this session does not
    # have an analysis with that id" — the routes were fine and the answers
    # were error pages. Asking sooner does not make the preview stable; it
    # narrows the window in which it has to stay up.
    for route in ("", *STEPS):
        path = f"/runs/{run_id}" + (f"/{route}" if route else "")
        rstatus, rurl, raw = session.get(path)
        cap.route(route or "run", rstatus, rurl, raw)

    answers = []
    for question in BOARD_QUESTIONS:
        _s, _u, ask = session.get(f"/runs/{run_id}/answer")
        # THE RUN CAN DIE MID-CAPTURE, and an error page is not an answer.
        # Storing one turns a lost session into "every company said the same
        # thing", which is exactly what a collapse measurement is looking
        # for — so it must be named here, not discovered downstream.
        if run_is_gone(ask):
            after = process_identity(base)
            result.update({
                "status": RUN_LOST, "run_lost_after_routes": True,
                "answers_captured": len(answers), "process_after": after,
                "restart_observed": _restart_observed(
                    result.get("process_before") or {}, after)})
            cap.manifest.update({
                "status": RUN_LOST, "run_lost_after_routes": True,
                "answers_captured": len(answers), "process_after": after,
                "restart_observed": result["restart_observed"]})
            cap.flush()
            return result
        token = Session.csrf(ask) or csrf
        # THE ROUTE THE PRODUCT'S OWN FORM POSTS TO. `/answer` is GET-only;
        # posting there returned "page not found" and this harness would have
        # stored it as the company's strategic answer. See `not_an_answer`.
        astatus, aurl, apage = session.post(
            f"/runs/{run_id}/conversation",
            {"csrf": token, "question": question}, ref=f"/runs/{run_id}")
        body = text_of(apage)
        if run_is_gone(body):
            after = process_identity(base)
            result.update({
                "status": RUN_LOST, "answers_captured": len(answers),
                "process_after": after,
                "restart_observed": _restart_observed(
                    result.get("process_before") or {}, after)})
            cap.manifest.update({
                "status": RUN_LOST, "answers_captured": len(answers),
                "process_after": after,
                "restart_observed": result["restart_observed"]})
            cap.flush()
            return result
        refused = not_an_answer(body, astatus)
        if refused:
            # Named, stored, and NOT counted as an answer. The company keeps
            # every route it did render; the audit sees a gap where a gap is.
            result["status"] = UNREADABLE
            result["unreadable_because"] = refused
            result["answers_captured"] = len(answers)
            cap.manifest.update({"status": UNREADABLE,
                                 "unreadable_because": refused,
                                 "unreadable_sample": body[:400],
                                 "answers_captured": len(answers)})
            cap.flush()
            return result
        answers.append({"question": question, "status": astatus,
                        "answer": body})
        cap.json_file("qa.json", answers)

    for route in EXTRA:
        rstatus, rurl, raw = session.get(f"/runs/{run_id}/{route}")
        if run_is_gone(raw):
            break
        cap.route(route, rstatus, rurl, raw)

    result["routes"] = len(cap.manifest["routes"])
    result["errors"] = session.errors
    cap.manifest.update({"errors": session.errors})
    cap.flush()
    return result
