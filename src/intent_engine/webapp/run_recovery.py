"""What a run id means when the service no longer holds the run.

WHY THIS EXISTS
---------------
Measured on the preview: a guest submitted a company, watched the progress
page, opened the result, and then every later request answered

    "This session does not have an analysis with that id."

Two of two canary runs in one window, with no deploy between the steps. The
cause is not a bug in ownership: `/readyz` on that service reports
``durability: EPHEMERAL_LIKELY`` and ``separate_filesystem: false``. There is
no persistent disk, so the append-only web store lives inside the container
image. When the instance is replaced the ownership record goes with it, the
run's evidence goes with it, and `_owned` correctly answers "no".

WHAT CAN AND CANNOT BE FIXED FROM INSIDE THE APPLICATION
--------------------------------------------------------
Nothing in this module makes a lost analysis come back. The evidence, the
documents and the composed decision were on a disk that no longer exists;
only a fresh run can produce them again. What IS fixable is the difference
between the two sentences the customer can be shown:

    "That analysis is not available here."          (a dead end)
    "This analysis was lost when the service
     restarted. Run <company> again."               (a next step)

Telling those apart needs one fact the store can no longer supply: did THIS
session ever own THIS run? So the claim is carried by the browser, signed,
instead of being looked up.

WHY A SIGNED CLAIM RATHER THAN A LOOKUP
---------------------------------------
A cookie the customer's browser holds survives an instance replacement, which
is exactly the event that destroys the server-side record. The claim is HMAC'd
with ``WEBAPP_SECRET``, so it cannot be forged, and it names the ``user_id``
it was minted for, so it only ever proves something about the session that
made it. A different visitor presenting a stolen run id has no matching claim
and still receives the ordinary refusal — isolation is unchanged, because the
claim can only ever WIDEN what its own holder is told about a run that is
already gone. It grants no access to a run that still exists: every caller
checks ownership first and only consults this when ownership already failed.

The claim carries the company name so the recovery page can offer to run that
company again rather than sending the reader back to an empty form.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

#: Version prefix. A future field change gets a new prefix rather than a
#: reinterpretation of an old payload.
CLAIM_VERSION = "run1"

#: Cookie name. Deliberately not "sid"-adjacent: this is not an identity.
COOKIE_NAME = "lastrun"

#: How long a claim can prove anything. A claim older than this is treated as
#: absent — a week-old tab reopening a run the service never heard of is not
#: evidence of a restart, and offering to "recover" it would be a guess.
CLAIM_TTL_SECONDS = 24 * 3600

# --- the states a run id can be in, from the reader's point of view ---------
#
# The failure this replaces collapsed every one of these into "analysis
# unavailable", which is why a restart, a typo and another person's run were
# indistinguishable on screen and in the capture artifacts.
RUN_READY = "RUN_READY"
RUN_FAILED_FINAL = "RUN_FAILED_FINAL"
RUN_NOT_FOUND = "RUN_NOT_FOUND"
RUN_NOT_OWNED = "RUN_NOT_OWNED"
RUN_RESTART_LOST = "RUN_RESTART_LOST"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, signed: str) -> str:
    return _b64u(hmac.new(secret.encode(), signed.encode(),
                          hashlib.sha256).digest())


def mint(secret: str, *, user_id: str, run_id: str, company: str = "",
         now: float = None) -> str:
    """A signed claim that ``user_id`` started ``run_id`` for ``company``."""
    payload = {"uid": user_id, "run": run_id, "co": (company or "")[:120],
               "iat": float(now if now is not None else time.time())}
    body = _b64u(json.dumps(payload, sort_keys=True,
                            separators=(",", ":")).encode())
    signed = f"{CLAIM_VERSION}.{body}"
    return f"{signed}.{_sign(secret, signed)}"


def verify(secret: str, token, *, now: float = None):
    """The claim this token proves, or ``None``. Never raises.

    Nothing is read out of the payload before the signature and the age have
    both been checked, so a tampered claim is indistinguishable from no claim.
    """
    if not isinstance(token, str) or not secret:
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != CLAIM_VERSION:
        return None
    _, body, sig = parts
    if not hmac.compare_digest(_sign(secret, f"{CLAIM_VERSION}.{body}"), sig):
        return None
    try:
        payload = json.loads(_unb64u(body).decode())
    except Exception:                                        # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    issued = payload.get("iat")
    if not isinstance(issued, (int, float)):
        return None
    moment = time.time() if now is None else now
    if moment - issued > CLAIM_TTL_SECONDS or issued - moment > 300:
        return None                       # expired, or minted in the future
    if not payload.get("uid") or not payload.get("run"):
        return None
    return payload


def proves(claim, *, user_id: str, run_id: str) -> bool:
    """Does this claim say THIS session started THIS run?

    Both halves are required. A claim for another run proves nothing about
    this one, and a claim minted for another ``user_id`` proves nothing at
    all — that second check is what keeps a shared or copied cookie from
    widening anything across sessions.
    """
    if not isinstance(claim, dict):
        return False
    return (claim.get("run") == run_id
            and bool(user_id) and claim.get("uid") == user_id)


def cookie_header(value: str, *, secure: bool, max_age: int = None) -> str:
    """The Set-Cookie value. HttpOnly: no page script has any use for it."""
    age = CLAIM_TTL_SECONDS if max_age is None else max_age
    tail = "; Secure" if secure else ""
    return (f"{COOKIE_NAME}={value}; HttpOnly; SameSite=Lax; Path=/; "
            f"Max-Age={age}{tail}")
