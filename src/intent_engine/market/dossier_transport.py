"""Ship published dossiers to a deployed founder service.

WHY A TRANSPORT AT ALL
----------------------
`strategic_publish` writes `reports/market/strategic/<company_id>.json` and the
founder side reads that directory. On one machine that IS the transport, and it
is the right design: no network, no second store, no serialisation format to
keep in sync.

Deployed, the two ends are on different machines. Measured 2026-08-05: no
Render service in this account has a persistent disk (production included), the
market engine does not run inside the founder service, and the founder branch
does not contain the `market` package. So a dossier published here could never
appear on a deployed founder, and every "live crossing" was a local one.

WHAT IS AND IS NOT MOVED
------------------------
Only the sanitized artifact `strategic_publish` already produced, byte for
byte. Canonical learning truth stays in the append-only learning ledger and
does not travel. This module cannot create, edit or interpret a dossier — if
it is not already on disk here, it is not sent.

SILENCE UNLESS ASKED
--------------------
Off unless both the URL and the token are configured. A cycle with no
transport configured publishes locally exactly as before and says so, rather
than failing or retrying into a service that does not exist.

FAILURE IS REPORTED, NOT RAISED
-------------------------------
Learning has already happened and is already recorded by the time a dossier
exists. A transport that took the cycle down would lose that, so every failure
is counted and returned in the row — and never swallowed into a success count,
because a silent transport failure is indistinguishable from a founder that
was never meant to receive anything.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Sequence

URL_ENV = "DOSSIER_TRANSPORT_URL"
TOKEN_ENV = "DOSSIER_INGEST_TOKEN"

#: Retries are safe because the receiver is idempotent on content: an
#: unchanged dossier answers `unchanged` and creates no revision. Kept small
#: because a founder preview that is down stays down for longer than a cycle
#: is willing to wait.
ATTEMPTS = 3
TIMEOUT_SECONDS = 20


def configured(env=None) -> bool:
    e = env or os.environ
    return bool(e.get(URL_ENV, "").strip() and e.get(TOKEN_ENV, "").strip())


def ship(root=".", *, companies: Optional[Sequence[str]] = None,
         env=None, opener=None) -> dict:
    """POST each published dossier to the configured founder service.

    `companies` limits the send to particular company ids; by default every
    dossier currently published is sent, which is what makes a retry after a
    partial failure a simple re-run.
    """
    e = env or os.environ
    if not configured(e):
        return {"configured": False, "sent": [], "unchanged": [],
                "failed": [], "attempted": 0,
                "note": (f"set {URL_ENV} and {TOKEN_ENV} to ship dossiers to "
                         f"a deployed founder service")}

    url = e[URL_ENV].strip()
    token = e[TOKEN_ENV].strip()
    directory = pathlib.Path(root) / "reports" / "market" / "strategic"
    if not directory.is_dir():
        return {"configured": True, "sent": [], "unchanged": [], "failed": [],
                "attempted": 0, "note": "no dossier directory to ship from"}

    wanted = set(companies or ())
    sent: List[dict] = []
    unchanged: List[dict] = []
    failed: List[dict] = []
    attempted = 0

    for path in sorted(directory.glob("*.json")):
        if wanted and path.stem not in wanted:
            continue
        attempted += 1
        body = path.read_bytes()
        outcome, detail = _post(url, token, body, opener=opener)
        if outcome == "unchanged":
            unchanged.append({"company_id": path.stem, **detail})
        elif outcome == "sent":
            sent.append({"company_id": path.stem, **detail})
        else:
            failed.append({"company_id": path.stem, "error": detail})

    return {"configured": True, "url": _redacted(url), "attempted": attempted,
            "sent": sent, "unchanged": unchanged, "failed": failed}


def _redacted(url: str) -> str:
    """The host, never a query string — a URL is not a place for a secret but
    a report is not a place to find out."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    except ValueError:  # pragma: no cover - urlsplit is total in practice
        return "<unparseable>"


def _post(url: str, token: str, body: bytes, *, opener=None):
    """One dossier, with bounded retries. Returns (outcome, detail)."""
    send = opener or urllib.request.urlopen
    last = ""
    for attempt in range(1, ATTEMPTS + 1):
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "X-Dossier-Token": token})
        try:
            with send(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
            status = payload.get("status")
            detail = {"revision": payload.get("revision", ""),
                      "as_of": payload.get("as_of", ""), "attempts": attempt}
            return ("unchanged" if status == "unchanged" else "sent"), detail
        except urllib.error.HTTPError as exc:
            # A 4xx is a REFUSAL and retrying cannot change it — the contract
            # said no. Only a transport-level failure is worth another go.
            detail = _reason(exc)
            if 400 <= exc.code < 500:
                return "failed", f"HTTP {exc.code}: {detail}"
            last = f"HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, OSError,
                json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {exc}"
    return "failed", last


def _reason(exc) -> str:
    try:
        return json.loads(exc.read().decode("utf-8")).get("error", "")
    except Exception:  # noqa: BLE001 - an error body is best-effort
        return exc.reason if hasattr(exc, "reason") else ""
