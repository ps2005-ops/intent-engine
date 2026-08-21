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

#: A progress poll answers in well under a second when the service is well.
#: The session-wide 180s applies to ANALYSIS routes, which legitimately take
#: minutes; applying it to a poll meant one hung request consumed three
#: minutes and then killed the capture.
POLL_TIMEOUT = 45.0
#: How many consecutive transport errors on the progress page are needed
#: before the run is believed dead. One is not evidence of anything.
#:
#: SIX, NOT THREE, AND THE REASON IS MEASURED. On 0d02c0b Meta's service
#: stopped answering `/runs/<id>/progress` for at least 105 CONSECUTIVE
#: seconds -- three 45-second timeouts back to back, from t=78 to t=183 --
#: on a run that had started normally. Three strikes declared that run dead
#: while the analysis was, as far as anything here can tell, still running.
#:
#: This is a real product defect and it is recorded as one: a customer
#: watching their own analysis sees a page that stops answering. But the
#: instrument's job is to observe it, not to be the second thing that fails
#: because of it. Six consecutive misses is about five minutes of silence,
#: and the 480-second wall clock in `wait_for_run` remains the real backstop.
MAX_POLL_ERRORS = 6
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

    #: Set by `get` on every request, so a caller can ask WHY a body was
    #: empty without a second round trip. Measured need: three of three live
    #: companies polled a progress page that returned no text for most of the
    #: wait, with no network error recorded -- and the same page renders 740
    #: characters in every non-terminal state locally. A status code and a
    #: content length separate "the service sent nothing" from "the harness
    #: could not read what it sent", and nothing on disk could tell them
    #: apart.
    last_status: int = 0
    last_headers: dict = None
    last_bytes: int = 0
    #: The outcome the SERVICE stated for this response, read from the
    #: `X-Analysis-Outcome` header. The instrument that passed Meta searched
    #: rendered prose for the literal string "Limited analysis" and therefore
    #: scored "Analysis could not be completed" as a success. A named state
    #: on the response is the fix: the harness stops having to know every
    #: sentence the product can write.
    last_outcome: str = ""
    #: What the readiness gate held versus what the store holds. Meta's
    #: bounded page said "7 page(s) read; 1 carried usable evidence" and no
    #: artifact recorded which document set the gate was looking at, so three
    #: mechanisms had to be falsified one at a time from the outside.
    last_gate: str = ""

    def get(self, path: str, timeout: float = None):
        req = urllib.request.Request(self.base + path,
                                     headers={"User-Agent": UA})
        try:
            with self.opener.open(req,
                                  timeout=timeout or self.timeout) as r:
                raw = r.read()
                self.last_status = r.status
                self.last_headers = dict(r.headers)
                self.last_bytes = len(raw)
                self.last_outcome = r.headers.get("X-Analysis-Outcome", "")
                self.last_gate = r.headers.get("X-Evidence-Gate", "")
                return r.status, r.geturl(), raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            self.last_status, self.last_outcome = exc.code, exc.headers.get(
                "X-Analysis-Outcome", "")
            self.last_gate = exc.headers.get("X-Evidence-Gate", "")
            return exc.code, self.base + path, exc.read().decode("utf-8",
                                                                 "replace")
        except Exception as exc:                            # noqa: BLE001
            # STALE IS WORSE THAN ABSENT. A failed request that keeps the
            # PREVIOUS route's outcome makes a dead surface look healthy.
            self.last_status, self.last_outcome, self.last_gate = 0, "", ""
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


def suggested_domain(name: str, *, base: str = DEFAULT_BASE) -> str:
    """The domain the entry page's own autocomplete offers for this name.

    The customer types a name, picks a row, and the form posts that row's
    domain as `suggest_domain`. A harness that posts the CIK and not the
    domain opens every run on the domainless-filer path and analyses the
    company from EDGAR alone -- which is not the product, and cost two of
    eleven Wave-1 companies a full analysis.

    Returns "" when the registry has no domain for the company, which is the
    honest answer for an SEC-registrant row: the customer's pick carries none
    either. Never raises.
    """
    try:
        url = (base.rstrip("/") + "/api/companies?q="
               + urllib.parse.quote(name[:60]))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.load(r).get("companies") or []
    except Exception:                                       # noqa: BLE001
        return ""
    wanted = (name or "").strip().lower()
    for row in rows:
        if str(row.get("legal_name") or "").strip().lower() == wanted:
            return str(row.get("domain") or "")
    # No exact legal-name match: take the first row ONLY if it is the sole
    # candidate. Guessing between several is how one company's evidence gets
    # attributed to another.
    if len(rows) == 1:
        return str(rows[0].get("domain") or "")
    return ""


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


#: What `deployed_sha` returns when it could not find out. Callers must REFUSE
#: to capture on it rather than write a directory nothing can be compared
#: with -- see `UnknownDeployment`.
UNKNOWN_SHA = "unknown"


class UnknownDeployment(RuntimeError):
    """The build under test could not be identified, so nothing may be run."""


def deployed_sha(base: str = DEFAULT_BASE, *, attempts: int = 3) -> str:
    """The SHA the capture is against, or UNKNOWN_SHA.

    A capture without one cannot be compared to anything, which is how eight
    companies came to be spread across five builds.

    RETRIED, BECAUSE ONE TIMEOUT IS NOT AN ANSWER. Measured: a wave of eight
    opened with `sha=unknown` after a single transient failure on a service
    that answered `/version` in 145ms before and after. The whole wave would
    have landed in an uncomparable directory, and the first company was
    already running before anyone could see the header line.
    """
    last = UNKNOWN_SHA
    for attempt in range(max(1, attempts)):
        try:
            req = urllib.request.Request(base.rstrip("/") + "/version",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                sha = str(json.load(r).get("commit") or "")[:7]
                if sha:
                    return sha
        except Exception:                                   # noqa: BLE001
            pass
        if attempt + 1 < max(1, attempts):
            time.sleep(2 * (attempt + 1))
    return last


def require_deployed_sha(base: str = DEFAULT_BASE) -> str:
    """The SHA, or raise. The gate every wave runner goes through.

    Refusing costs one retry. Not refusing costs the wave: a capture written
    under "unknown" is invisible to a `--resume`, is not comparable with the
    canaries it was meant to extend, and is discovered only after the live
    analyses have been spent.
    """
    sha = deployed_sha(base)
    if sha == UNKNOWN_SHA:
        raise UnknownDeployment(
            f"{base}/version did not identify the build after 3 attempts; "
            f"refusing to capture into an uncomparable directory")
    return sha


class Capture:
    """The canonical on-disk artifact for one company on one SHA."""

    def __init__(self, root: pathlib.Path, sha: str, company: str):
        self.dir = pathlib.Path(root) / sha / slug(company)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = {"company": company, "deployed_sha": sha,
                         "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                      time.gmtime()),
                         "routes": {}, "progress": []}

    def route(self, name: str, status: int, url: str, raw: str,
              seconds: float = None, outcome: str = "") -> None:
        """Write a route THE MOMENT IT SETTLES. See the module docstring."""
        body = text_of(raw)
        if seconds is not None:
            self.manifest.setdefault("route_seconds", {})[name] = round(
                seconds, 2)
        (self.dir / f"{name}.txt").write_text(body, "utf-8")
        (self.dir / f"{name}.html").write_text(raw, "utf-8")
        self.manifest["routes"][name] = {
            "status": status, "final_url": url, "chars": len(body),
            "html_chars": len(raw), "outcome": outcome}
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
    transport_errors = 0
    while time.time() - started < timeout:
        status, url, page = session.get(f"/runs/{run_id}/progress",
                                        timeout=POLL_TIMEOUT)
        # EVERY SAMPLE, not the first three. The stage sentence is the only
        # thing a guest-side harness can see of retrieval-versus-composition,
        # so a truncated sample list makes the dominant phase unknowable --
        # and "the wait is too long" is not actionable without it. Only the
        # text CHANGES are kept, so a four-minute run costs a handful of rows
        # rather than forty near-identical ones.
        stage = text_of(page)[:300]
        if not samples or samples[-1]["text"] != stage:
            row = {"t": round(time.time() - started, 1), "text": stage,
                   "status": status, "html_bytes": getattr(
                       session, "last_bytes", len(page))}
            if not stage:
                # AN EMPTY STAGE IS THE THING BEING INVESTIGATED, so it gets
                # its headers. Everything else stays one line.
                row["headers"] = {
                    k.lower(): v for k, v in
                    (getattr(session, "last_headers", None) or {}).items()
                    if k.lower() in ("content-type", "content-length",
                                     "content-encoding", "location",
                                     "cf-cache-status", "x-render-origin-"
                                     "server", "etag")}
                row["final_url"] = url
                row["head"] = (page or "")[:300]
            samples.append(row)
        # ONE DROPPED POLL IS NOT A DEAD ANALYSIS.
        #
        # MEASURED: Adobe on 10d1620 and Meta on b37bee2 both ended FAILED
        # with `status=0` at t=219.1s and t=218.8s -- one progress poll
        # hanging for the session's 180-second socket timeout, on runs that
        # were progressing normally ("Stress-testing the reading" at t=33).
        # Adobe had completed the SAME analysis in 229s one SHA earlier.
        #
        # So two live companies were scored as failures by the instrument,
        # and each one cost an analysis out of a quota of ten per hour. The
        # server not answering ONE poll says nothing about the run; the
        # run page is the thing that says whether the run is alive.
        #
        # The poll timeout is now short, because a progress page that takes
        # 45 seconds is already telling us something, and a transport error
        # has to happen repeatedly before it is believed.
        if status in (0, 500, 502, 503):
            transport_errors += 1
            if transport_errors >= MAX_POLL_ERRORS:
                return FAILED, url, round(time.time() - started), samples
            time.sleep(poll)
            continue
        transport_errors = 0
        if "/progress" not in url:
            return READY, url, round(time.time() - started), samples
        low = text_of(page).lower()
        if "limit reached" in low or "429" in low:
            return BLOCKED, url, round(time.time() - started), samples
        time.sleep(poll)
    return TIMEOUT, "", round(time.time() - started), samples


def capture_company(name: str, cik: str = "", ticker: str = "", *,
                    base: str = DEFAULT_BASE, website: str = "",
                    domain: str = "",
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
    # THE DOMAIN THE CUSTOMER'S OWN PICK CARRIES.
    #
    # `/api/companies` returns a domain for most rows, and the entry page
    # posts it as `suggest_domain` when the customer chooses one. This
    # harness sent the CIK and the ticker and NOT the domain, so every
    # company opened on the domainless-filer path and the product analysed it
    # from EDGAR alone -- which is not what a customer gets, and is the
    # harness under-serving the product rather than automating it.
    #
    # Measured on 8397d67: Cloudflare reached 2 usable sources and ServiceNow
    # 3, against a floor of 5, both with `1 kind(s) of evidence (investor)`
    # and no official company page. Both rendered a Limited analysis. Adobe
    # cleared the floor on EDGAR alone, so this is not "SEC-only always
    # fails" -- it is that a company's own site was never asked for.
    if not domain:
        # ASK THE PAGE'S OWN AUTOCOMPLETE, which is what the customer's
        # keystrokes do. A static table would drift from the registry the
        # product actually serves, and would have nothing to say about the
        # companies that are not in the manifest at all.
        domain = suggested_domain(name, base=base)
    if domain:
        form["suggest_domain"] = domain
    result["entry_domain"] = domain
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
    # §4. T_FIRST_USEFUL is the moment the customer stops waiting: the run
    # left the progress page for something readable. It is the number the
    # 30-second target is about, and it is NOT the same as `seconds` on a run
    # that keeps enriching afterwards.
    first_useful = seconds if state == READY else None
    result.update({"status": state, "seconds": seconds,
                   "first_useful": first_useful,
                   "auto_advanced": bool(landed), "landed_on": landed})
    cap.manifest.update({"status": state, "seconds": seconds,
                         "first_useful": first_useful,
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
        at = time.time()
        rstatus, rurl, raw = session.get(path)
        cap.route(route or "run", rstatus, rurl, raw, time.time() - at,
                  outcome=session.last_outcome)
        if session.last_gate:
            cap.manifest["evidence_gate"] = session.last_gate

    # THE OUTCOME, AS THE SERVICE STATED IT, AND WHETHER IT STATED ONE THING.
    #
    # Six surfaces rendering a real analysis while `/full` rendered a failure
    # page was one run telling two stories, and no capture on disk recorded
    # that -- it had to be found by reading seven pages by eye. A
    # disagreement is now a field.
    stated = {r: v.get("outcome", "")
              for r, v in cap.manifest["routes"].items() if v.get("outcome")}
    distinct = sorted(set(stated.values()))
    result["outcome"] = distinct[0] if len(distinct) == 1 else (
        distinct[0] if distinct else "")
    result["outcome_by_route"] = stated
    result["outcome_disagreement"] = distinct if len(distinct) > 1 else []
    cap.manifest.update({"outcome": result["outcome"],
                         "outcome_by_route": stated,
                         "outcome_disagreement": result["outcome_disagreement"]})
    cap.flush()

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
        # THE ENDPOINT IS PART OF THE MEASUREMENT. A qa.json that does not
        # say where it asked cannot be audited for the defect that produced
        # it: ten answers captured from a GET-only route look exactly like
        # ten answers until somebody re-reads the route table.
        answers.append({"question": question, "status": astatus,
                        "endpoint": f"/runs/{{run_id}}/conversation",
                        "answer": body})
        cap.json_file("qa.json", answers)

    # THE WALK FINISHED. `qa.json` is flushed after every answer, so a reader
    # opening the capture mid-walk cannot tell seven-of-ten-so-far from a
    # company that answered seven. Without this the audit either scores an
    # in-flight capture as a collapse, or -- worse -- suppresses every real
    # incomplete Q&A to avoid doing so, which is a rule that cannot fail.
    cap.manifest["qa_complete"] = True
    cap.manifest["answers_captured"] = len(answers)
    cap.flush()

    for route in EXTRA:
        rstatus, rurl, raw = session.get(f"/runs/{run_id}/{route}")
        if run_is_gone(raw):
            break
        cap.route(route, rstatus, rurl, raw)

    result["routes"] = len(cap.manifest["routes"])
    result["errors"] = session.errors
    cap.manifest.update({"errors": session.errors})
    # §19/§42. What this run COST, kept beside what it said. Written last
    # because it is the only artifact that is not evidence about the company.
    cap.json_file("runtime.json", {
        "company": name, "deployed_sha": sha, "run_id": run_id,
        "analysis_seconds": result.get("seconds"),
        "stage_transitions": cap.manifest.get("progress") or [],
        "route_seconds": cap.manifest.get("route_seconds") or {},
        "answers": len(answers),
        "process_before": result.get("process_before") or {},
        "process_after": process_identity(base),
        "errors": session.errors,
    })
    return result
