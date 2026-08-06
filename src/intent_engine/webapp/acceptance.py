"""Preview-only acceptance runs over the REAL analysis pipeline.

WHY THIS EXISTS. The public demo allows ten analyses per IP per rolling hour.
That is an abuse guardrail on a public URL and it must not move — which is
exactly why a twenty-company matrix cannot be driven through the guest flow,
and why every previous cycle measured one or five companies and generalised
from them.

WHAT IT IS NOT. It is not a second analysis path. The runner calls the same
`_analyze` the guest form calls, with `smoke=True`, and that flag already
buys exactly one thing: the quota. Consent, ownership, session isolation,
retrieval, reasoning, persistence and rendering are untouched. If the runner
could produce a result the product cannot, the matrix would be measuring the
runner.

WHAT IT ADDS. A bounded, resumable, authenticated way to ask for many of them
at once, and a deterministic verdict on each.

SCORING IS DETERMINISTIC ON PURPOSE. `USEFUL_FULL` and `USEFUL_BOUNDED` are
decided by checks over the rendered page, each recording the reason it passed
or failed. Nothing here asks a model whether its own output was good.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field

LEDGER_VERSION = "acceptance.v1"

#: Header carrying the acceptance token. Server-side only: never rendered,
#: never logged, never returned.
ACCEPTANCE_HEADER = "HTTP_X_FOUNDER_INTELLIGENCE_ACCEPTANCE"
ACCEPTANCE_TOKEN_ENV = "FOUNDER_INTELLIGENCE_ACCEPTANCE_TOKEN"

#: Hard ceilings. These are not configuration; they are the outer bound that
#: configuration may only lower. A matrix is twenty companies, so a request
#: for two hundred is a mistake or an attack and is refused either way.
MAX_COMPANIES_CEILING = 40
MAX_CONCURRENCY_CEILING = 3
DEFAULT_CONCURRENCY = 1
DEFAULT_MAX_COMPANIES = 20
#: A conservative per-analysis cost unit. The runner counts analyses, not
#: dollars — it cannot see provider billing — so the budget is expressed in
#: the only unit it can enforce honestly.
DEFAULT_ANALYSIS_BUDGET = 25

# --- states -------------------------------------------------------------------
PENDING = "pending"
RUNNING = "running"
USEFUL_FULL = "useful_full"
USEFUL_BOUNDED = "useful_bounded"
WITHHELD = "withheld"
FAILED = "failed"
TIMED_OUT = "timed_out"
CANCELLED = "cancelled"
BUDGET_EXHAUSTED = "budget_exhausted"

TERMINAL = frozenset({USEFUL_FULL, USEFUL_BOUNDED, WITHHELD, FAILED,
                      TIMED_OUT, CANCELLED, BUDGET_EXHAUSTED})
USEFUL = frozenset({USEFUL_FULL, USEFUL_BOUNDED})


class AcceptanceRefused(PermissionError):
    """The request may not run here. Never carries the reason to a client."""


# --- who may run it -----------------------------------------------------------

def token_from_env(environ=None) -> str:
    return ((environ if environ is not None else os.environ)
            .get(ACCEPTANCE_TOKEN_ENV, "") or "").strip()


def is_enabled(*, env: str, token: str) -> bool:
    """The mechanism exists only on a non-production service WITH a token.

    Two independent conditions, both required. A token accidentally present in
    a production environment does not enable it, and a non-production service
    without a token does not either — so neither a misconfigured environment
    nor a leaked variable is sufficient on its own.
    """
    return bool((token or "").strip()) and env != "production"


def authorise(*, env: str, expected: str, presented: str) -> None:
    """Raise unless this request may start an acceptance run."""
    if not is_enabled(env=env, token=expected):
        raise AcceptanceRefused("acceptance runs are not available here")
    if not presented:
        raise AcceptanceRefused("acceptance runs are not available here")
    # Constant time: a length-or-prefix leak lets the token be recovered a
    # character at a time.
    if not hmac.compare_digest(presented.strip(), expected.strip()):
        raise AcceptanceRefused("acceptance runs are not available here")


def plan(companies, *, max_companies=DEFAULT_MAX_COMPANIES,
         concurrency=DEFAULT_CONCURRENCY, budget=DEFAULT_ANALYSIS_BUDGET):
    """Validate and clamp a request. Refuses rather than silently truncating."""
    if not isinstance(companies, list) or not companies:
        raise AcceptanceRefused("a non-empty company list is required")
    ceiling = min(int(max_companies or DEFAULT_MAX_COMPANIES),
                  MAX_COMPANIES_CEILING)
    if len(companies) > ceiling:
        raise AcceptanceRefused(
            f"too many companies: {len(companies)} requested, {ceiling} is "
            "the maximum")
    cleaned = []
    seen = set()
    for entry in companies:
        if not isinstance(entry, dict):
            raise AcceptanceRefused("each company must be an object")
        name = str(entry.get("name") or "").strip()[:120]
        website = str(entry.get("website") or "").strip()[:300]
        if not name or not website.startswith(("http://", "https://")):
            raise AcceptanceRefused("each company needs a name and an "
                                    "http(s) website")
        key = name.lower()
        if key in seen:                 # a duplicate is a costly mistake
            continue
        seen.add(key)
        cleaned.append({"name": name, "website": website})
    return {
        "companies": cleaned,
        "concurrency": max(1, min(int(concurrency or DEFAULT_CONCURRENCY),
                                  MAX_CONCURRENCY_CEILING)),
        "budget": max(1, min(int(budget or DEFAULT_ANALYSIS_BUDGET),
                             MAX_COMPANIES_CEILING)),
    }


# --- the ledger ---------------------------------------------------------------

@dataclass
class Entry:
    requested_company: str
    website: str
    state: str = PENDING
    analysis_id: str = ""
    display_name: str = ""
    fresh_or_reused: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_seconds: float = 0.0
    internal_failure_category: str = ""
    source_classes: list = field(default_factory=list)
    filing_quality_states: list = field(default_factory=list)
    evidence_count: int = 0
    checks: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    safe_diagnostic_id: str = ""

    @property
    def key(self) -> str:
        return self.requested_company.lower()


class Ledger:
    """Append-only per-company progress, safe across restarts.

    Every state change is one JSON line, flushed and fsynced. A truncated or
    unparsable line is skipped rather than fatal — a corrupted tail must cost
    the entries after it, never the run.
    """

    def __init__(self, path, *, run_id: str):
        self.path = str(path)
        self.run_id = run_id
        self.entries: dict = {}
        self.cancelled = False
        self._load()

    def _load(self) -> None:
        try:
            handle = open(self.path, encoding="utf-8")
        except OSError:
            return
        with handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue                       # corrupted tail: skip
                if row.get("run_id") != self.run_id:
                    continue
                if row.get("kind") == "cancel":
                    self.cancelled = True
                    continue
                payload = row.get("entry") or {}
                try:
                    entry = Entry(**payload)
                except TypeError:
                    continue
                self.entries[entry.key] = entry

    def _append(self, row: dict) -> None:
        row = dict(row, run_id=self.run_id, version=LEDGER_VERSION,
                   at=time.time())
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def record(self, entry: Entry) -> None:
        self.entries[entry.key] = entry
        self._append({"kind": "entry", "entry": asdict(entry)})

    def cancel(self) -> None:
        self.cancelled = True
        self._append({"kind": "cancel"})

    def get(self, name: str):
        return self.entries.get(name.lower())

    def pending(self, companies, *, force_fresh=False, retry_failed=True):
        """Which companies still need work. Resume is the default."""
        out = []
        for company in companies:
            existing = self.get(company["name"])
            if force_fresh or existing is None:
                out.append(company)
                continue
            if existing.state in TERMINAL:
                retryable = existing.state in (FAILED, TIMED_OUT)
                if retry_failed and retryable:
                    out.append(company)
                continue
            out.append(company)             # pending or interrupted mid-run
        return out

    def summary(self) -> dict:
        states: dict = {}
        for entry in self.entries.values():
            states[entry.state] = states.get(entry.state, 0) + 1
        attempted = len(self.entries)
        useful = sum(1 for e in self.entries.values() if e.state in USEFUL)
        return {
            "run_id": self.run_id,
            "attempted": attempted,
            "useful": useful,
            "useful_rate": round(useful / attempted, 3) if attempted else 0.0,
            "states": states,
            "cancelled": self.cancelled,
        }


# --- deterministic scoring ----------------------------------------------------
#
# Every check is a substring or a structural fact about the page a reader was
# served. The failure reasons are recorded so a matrix row can be argued with.

_BAD_REQUEST = re.compile(
    r"\bBad Request\b|Internal Server Error|Traceback \(most recent"
    r"|\bundefined\b|\bNoneType\b", re.I)
_STYLE_IN_MAIN = re.compile(r"<style", re.I)

_FULL_MARKERS = {
    "direct_answer": ("The answer",),
    "why_it_matters": ("Why this matters",),
    "decision_implication": ("The decision this bears on",),
    "options": ("The options, and what each costs",),
    "limitation": ("What most limits this", "What argues against it"),
    "evidence": ("What supports this",),
}
_BOUNDED_MARKERS = {
    "explains_insufficiency": ("not enough public evidence",
                               "did not produce a report",
                               "no strategic reading",
                               "Limited analysis"),
    "names_what_was_read": ("What was found", "Pages read",
                            "What was verified"),
    "names_what_is_missing": ("What was missing", "minimum needed",
                              "Sources that could not be read"),
    "next_step": ("What you can do", "What to do next",
                  "Look again for the missing evidence"),
}


def _main_of(html: str) -> str:
    match = re.search(r"<main\b[^>]*>(.*?)</main>", html or "", re.S | re.I)
    return match.group(1) if match else (html or "")


def _text_of(fragment: str) -> str:
    stripped = re.sub(r"<script[^>]*>.*?</script>", " ", fragment,
                      flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def score(html: str, *, company: str) -> dict:
    """A deterministic verdict on one rendered result page."""
    main = _main_of(html)
    text = _text_of(main)
    checks, reasons = {}, []

    checks["no_raw_framework_error"] = not _BAD_REQUEST.search(text)
    if not checks["no_raw_framework_error"]:
        reasons.append("raw framework error on the page")
    checks["no_stylesheet_in_main"] = not _STYLE_IN_MAIN.search(main)
    if not checks["no_stylesheet_in_main"]:
        reasons.append("stylesheet inside <main>")
    checks["identity_named"] = bool(company) and company.split()[0].lower() \
        in text.lower()
    if not checks["identity_named"]:
        reasons.append("the company is not named in the result")
    checks["not_empty"] = len(text.split()) >= 120
    if not checks["not_empty"]:
        reasons.append(f"only {len(text.split())} words of content")

    for name, markers in _FULL_MARKERS.items():
        checks[name] = any(m in text for m in markers)
    for name, markers in _BOUNDED_MARKERS.items():
        checks[name] = any(m in text for m in markers)

    baseline = (checks["no_raw_framework_error"] and checks["identity_named"]
                and checks["not_empty"] and checks["no_stylesheet_in_main"])
    full = baseline and all(checks[name] for name in _FULL_MARKERS)
    bounded = baseline and all(checks[name] for name in _BOUNDED_MARKERS)

    if full:
        state = USEFUL_FULL
    elif bounded:
        state = USEFUL_BOUNDED
    else:
        state = FAILED
        for name in _FULL_MARKERS:
            if not checks[name]:
                reasons.append(f"missing: {name}")
    return {"state": state, "checks": checks, "reasons": reasons,
            "words": len(text.split())}
