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
                    base: str = DEFAULT_BASE,
                    root: pathlib.Path = None, sha: str = "") -> dict:
    """One company, end to end, through the customer flow. Never raises."""
    root = pathlib.Path(root or "docs/execution/v5/pre100_60/live_captures")
    sha = sha or deployed_sha(base)
    cap = Capture(root, sha, name)
    session = Session(base)
    result = {"company": name, "deployed_sha": sha, "status": FAILED,
              "run_id": "", "capture_path": str(cap.dir)}

    session.get("/")
    session.post("/demo", {})
    _s, _u, entry = session.get("/demo")
    csrf = Session.csrf(entry)
    if not csrf:
        result["failure"] = "no csrf on the entry page"
        cap.manifest.update(result)
        cap.flush()
        return result

    form = {"csrf": csrf, "consent": "on", "company_name": name}
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

    for route in ("", *STEPS, *EXTRA):
        path = f"/runs/{run_id}" + (f"/{route}" if route else "")
        rstatus, rurl, raw = session.get(path)
        cap.route(route or "run", rstatus, rurl, raw)

    answers = []
    for question in BOARD_QUESTIONS:
        _s, _u, ask = session.get(f"/runs/{run_id}/answer")
        token = Session.csrf(ask) or csrf
        astatus, aurl, apage = session.post(
            f"/runs/{run_id}/answer", {"csrf": token, "question": question},
            ref=f"/runs/{run_id}")
        answers.append({"question": question, "status": astatus,
                        "answer": text_of(apage)})
        cap.json_file("qa.json", answers)

    result["routes"] = len(cap.manifest["routes"])
    result["errors"] = session.errors
    cap.manifest.update({"errors": session.errors})
    cap.flush()
    return result
