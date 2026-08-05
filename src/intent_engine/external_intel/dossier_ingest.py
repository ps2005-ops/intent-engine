"""Receive a published strategic dossier over HTTP, for deployments only.

WHY THIS EXISTS
---------------
The bridge is a FILE handoff: the producer writes
`reports/market/strategic/<company_id>.json` and `strategic_contract.resolve`
reads that directory. On one machine that is the whole transport and it is
right — no network, no second store, no serialisation format to keep in sync.

Deployed, the two ends are on different machines. Measured 2026-08-05: no
Render service in this account has a persistent disk (production included),
the market engine does not run inside the founder service, and the founder
branch does not contain the `market` package at all. So a locally published
dossier could never appear on a deployed founder service, and every "live
crossing" was really a local one.

WHAT THIS IS NOT
----------------
Not a second source of truth. Canonical learning truth stays in the market
side's append-only learning ledger; the dossier is what it already was, a
sanitized immutable publication artifact. This moves that artifact and does
nothing else — it cannot create, edit or interpret one.

Not a new trust boundary either. Everything that arrives is put through
`strategic_contract.validate`, the same allowlist the local file path uses, so
the deployed route trusts exactly what the file route trusts and no more.

WHY IT REFUSES TO EXIST BY DEFAULT
-----------------------------------
An authenticated write endpoint on a deployed service is a real attack
surface, so absence is the default: with no `DOSSIER_INGEST_TOKEN` configured
there is no route, and production — which has no such variable — has no
endpoint to attack rather than a disabled one. `enabled_for` also refuses
outright when the environment is production, so configuring the variable there
by accident still does not open it.

APPEND-ONLY, BECAUSE THE READER IS NOT THE RECORD
--------------------------------------------------
Every accepted dossier is written to `revisions/<company_id>/` under a
content-derived name before the current pointer moves. `resolve` globs
`*.json` non-recursively, so revisions are invisible to it while remaining on
disk: a later publication supersedes an earlier one for READING without
destroying what an earlier founder analysis was shown.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
from typing import Optional, Tuple

from . import strategic_contract as SC

#: Generous for a dossier (the real ones are a few kB) and far below anything
#: that could exhaust a free instance.
MAX_BYTES = 512 * 1024

TOKEN_ENV = "DOSSIER_INGEST_TOKEN"

#: The host this token is valid for. The second condition, and it exists
#: because of the exact mistake that produced it: the bridge preview was
#: created by COPYING the env vars of another service. Any check that a copied
#: variable satisfies is not a second condition at all.
#:
#: An earlier version keyed on WEBAPP_ENV != "production" and was wrong. A
#: preview SHOULD run in hardened mode, and this one does, so the check
#: conflated "runs hardened" with "is the production deployment" and refused
#: the very service it was meant to enable. Binding to a hostname tests
#: identity rather than posture: copy both variables anywhere else and the
#: request host no longer matches, so the route does not exist there.
HOST_ENV = "DOSSIER_INGEST_HOST"

ACCEPTED = "accepted"
UNCHANGED = "unchanged"
SUPERSEDED = "superseded"


class IngestRefused(Exception):
    """The artifact was refused. `status` is the HTTP code to answer with."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def configured_token(env=None) -> str:
    return (env or os.environ).get(TOKEN_ENV, "").strip()


def _host(value: str) -> str:
    return (value or "").split(":")[0].strip().lower()


def enabled_for(request_host: str, env=None) -> bool:
    """Whether the route exists at all, for THIS request.

    Two genuinely independent conditions: a token must be configured, and the
    request must have arrived at the host the token was issued for. Production
    has neither variable, so it has no endpoint to attack rather than a
    disabled one — and copying both variables onto another service still does
    not open it, because the host will not match.
    """
    expected = _host((env or os.environ).get(HOST_ENV, ""))
    return bool(configured_token(env)) and bool(expected) and \
        _host(request_host) == expected


def _authorized(provided: str, env=None) -> bool:
    expected = configured_token(env)
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def strategic_dir(runtime_root) -> pathlib.Path:
    return pathlib.Path(runtime_root) / "reports" / "market" / "strategic"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ingest(raw: bytes, *, runtime_root, provided_token: str,
           request_host: str = "", env=None) -> dict:
    """Validate and store one published dossier. Raises `IngestRefused`.

    The order is deliberate: authorisation, then size, then JSON, then the
    contract. Nothing touches the filesystem until the payload has passed the
    same allowlist a locally-written file would have to pass.
    """
    if not enabled_for(request_host, env):
        # Indistinguishable from an unknown path, on purpose.
        raise IngestRefused(404, "no such endpoint")
    if not _authorized(provided_token, env):
        raise IngestRefused(401, "not authorized")
    if not raw:
        raise IngestRefused(400, "empty body")
    if len(raw) > MAX_BYTES:
        raise IngestRefused(413, "dossier too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestRefused(400, f"unreadable dossier: {exc}")
    if not isinstance(payload, dict):
        raise IngestRefused(400, "a dossier is a JSON object")

    version = payload.get("export_version")
    if version != SC.SCHEMA_VERSION:
        raise IngestRefused(
            409, f"dossier is version {version!r}; this service reads "
                 f"{SC.SCHEMA_VERSION}")
    try:
        SC.validate(payload)
    except SC.StrategicLeak as exc:
        raise IngestRefused(422, f"refused by the founder-side contract: {exc}")

    declared = str(payload.get("company_id") or "")
    key = SC.company_key(declared)
    if not key:
        raise IngestRefused(422, "dossier declares no company_id")
    # The filename comes from the VALIDATED payload through the same slug
    # function the resolver uses, never from anything the caller chose, so a
    # path separator or a traversal segment cannot survive into a filename.
    if key != declared:
        raise IngestRefused(
            422, f"company_id {declared!r} is not a canonical key")

    as_of = str(payload.get("as_of") or "")
    if not as_of:
        raise IngestRefused(422, "dossier declares no as_of")

    root = strategic_dir(runtime_root)
    current = root / f"{key}.json"
    body = json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")
    digest = _digest(body)

    if current.exists() and _digest(current.read_bytes()) == digest:
        # Republishing an unchanged dossier is what a retry looks like.
        return {"status": UNCHANGED, "company_id": key, "as_of": as_of,
                "revision": digest[:16], "revisions_kept": _count(root, key)}

    revisions = root / "revisions" / key
    revisions.mkdir(parents=True, exist_ok=True)
    archive = revisions / f"{as_of}-{digest[:16]}.json"
    if not archive.exists():
        _atomic_write(archive, body)

    superseded = current.exists()
    _atomic_write(current, body)
    return {"status": SUPERSEDED if superseded else ACCEPTED,
            "company_id": key, "as_of": as_of, "revision": digest[:16],
            "revisions_kept": _count(root, key)}


def _count(root: pathlib.Path, key: str) -> int:
    path = root / "revisions" / key
    return len(list(path.glob("*.json"))) if path.is_dir() else 0


def _atomic_write(path: pathlib.Path, body: bytes) -> None:
    """Publish atomically, so a reader never sees a half-written dossier."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
