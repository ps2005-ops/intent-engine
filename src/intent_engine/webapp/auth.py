"""V1.0.1 authentication — the explicit minimum, nothing faked.

Provided: admin-created early-access accounts (+ optional registration),
login/logout, salted PBKDF2 password hashing, expiring server-side
sessions, per-session CSRF tokens, bounded login attempts with lockout,
and ownership checks (in app.py) on every run.

NOT provided, honestly: password reset (requires email delivery, which
does not exist in this repository) and external identity providers. Both
are recorded in docs/V101_GAPS.md rather than faked.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from intent_engine.webapp.records import WebAppError, WebEvent

PBKDF2_ITERATIONS = 200_000
PASSWORD_RESET_STATUS = ("NOT AVAILABLE — requires email delivery; an admin "
                         "may issue a new password out of band")

# Version tag for the signed anonymous demo-session cookie. Bumping it
# invalidates every previously issued anonymous token.
ANON_TOKEN_VERSION = "anon1"


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise WebAppError("password must be at least 8 characters")
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                 PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


class AuthService:
    """Accounts, sessions, CSRF, and bounded login attempts.

    Sessions are server-side (sid -> user_id, expiry); the cookie carries
    only the random sid. `now_fn` is injectable so expiry and lockout are
    deterministic under test.
    """

    def __init__(self, store, config, *, now_fn=None):
        import time
        self.store = store
        self.config = config
        self.now = now_fn or time.time
        self._sessions: dict = {}      # sid -> {user_id, expires, csrf}
        self._attempts: dict = {}      # email -> [timestamps]

    # --- accounts ------------------------------------------------------------
    def create_user(self, email: str, password: str, *, created_by="admin",
                    via_registration=False) -> str:
        if via_registration and not self.config.registration_open:
            raise WebAppError("registration is closed; accounts are "
                              "administrator-created in early access")
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise WebAppError("invalid email")
        if self.store.user_by_email(email) is not None:
            raise WebAppError("account already exists")
        user_id = f"user-{secrets.token_hex(8)}"
        self.store.append(WebEvent(
            event_type="web.user_created", actor_type="human",
            actor_id=created_by, subject_type="user", subject_id=user_id,
            idempotency_key=f"user:{email}",
            payload={"email": email, "user_id": user_id,
                     "password_hash": hash_password(password),
                     "via_registration": via_registration}))
        return user_id

    def create_user_with_hash(self, email: str, password_hash: str, *,
                              created_by="bootstrap") -> str:
        """Bootstrap path: the hash was precomputed locally by
        `generate-bootstrap` using this module's hashing contract; no
        plaintext password ever reaches the server."""
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise WebAppError("invalid email")
        if not password_hash.startswith("pbkdf2_sha256$"):
            raise WebAppError("password hash does not match the "
                              "application's hashing contract")
        if self.store.user_by_email(email) is not None:
            raise WebAppError("account already exists")
        user_id = f"user-{secrets.token_hex(8)}"
        self.store.append(WebEvent(
            event_type="web.user_created", actor_type="human",
            actor_id=created_by, subject_type="user", subject_id=user_id,
            idempotency_key=f"user:{email}",
            payload={"email": email, "user_id": user_id,
                     "password_hash": password_hash,
                     "via_registration": False}))
        return user_id

    # --- login with bounded attempts -----------------------------------------
    def _locked_out(self, email: str) -> bool:
        cutoff = self.now() - self.config.login_lockout_seconds
        recent = [t for t in self._attempts.get(email, []) if t > cutoff]
        self._attempts[email] = recent
        return len(recent) >= self.config.login_max_attempts

    def login(self, email: str, password: str) -> str:
        """Returns a session id, or raises WebAppError. Never says which of
        email/password was wrong."""
        email = email.strip().lower()
        if self._locked_out(email):
            self.store.append(WebEvent(
                event_type="web.login_locked", actor_type="human",
                actor_id=email, payload={"email": email}))
            raise WebAppError("too many attempts; try again later")
        user = self.store.user_by_email(email)
        ok = user is not None and verify_password(password,
                                                  user["password_hash"])
        if not ok:
            self._attempts.setdefault(email, []).append(self.now())
            self.store.append(WebEvent(
                event_type="web.login_failed", actor_type="human",
                actor_id=email, payload={"email": email}))
            raise WebAppError("invalid credentials")
        self._attempts.pop(email, None)
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = {
            "user_id": user["user_id"], "email": email,
            "expires": self.now() + self.config.session_ttl_seconds,
            "csrf": secrets.token_urlsafe(32)}
        self.store.append(WebEvent(
            event_type="web.login_succeeded", actor_type="human",
            actor_id=user["user_id"], payload={"email": email}))
        return sid

    def logout(self, sid: str) -> None:
        session = self._sessions.pop(sid, None)
        if session and not session.get("anonymous"):
            self.store.append(WebEvent(
                event_type="web.logout", actor_type="human",
                actor_id=session["user_id"], payload={}))

    # --- anonymous demo sessions (feature-flagged, restart-tolerant) ---------
    def create_anonymous_session(self) -> str:
        """Mint an ephemeral anonymous DEMO_MODE session and return a signed,
        self-contained token to be used as the ``sid`` cookie — the caller
        MUST have checked ``config.demo_mode`` first.

        No persistent user record is created (nothing is written to the
        store), so anonymous visitors leave no account behind. The returned
        token is ``anon1.<payload>.<hmac>`` signed with ``WEBAPP_SECRET``; the
        payload carries only the minimum anonymous identity: a unique
        ``user_id`` (prefix ``anon-``) so every existing ownership check
        isolates it from real users and from every other anonymous visitor, a
        CSRF token so state-changing POSTs stay CSRF-protected, and an absolute
        expiry. Because the token is *signed* rather than only held in memory,
        an otherwise-unexpired anonymous browser session survives a process
        restart: any app instance built from the same secret can verify and
        restore it (see :meth:`restore_anonymous`). The payload always forces
        ``anonymous=True``, so a valid signature can never mint a real account.

        A live copy is cached in ``_sessions`` under the token so that, within
        one process, the per-session ``analyses`` rate-limit timestamps accrue
        normally.
        """
        user_id = f"anon-{secrets.token_hex(8)}"
        csrf = secrets.token_urlsafe(32)
        expires = self.now() + self.config.session_ttl_seconds
        token = self._sign_anonymous(user_id, csrf, expires)
        self._sessions[token] = {
            "user_id": user_id, "email": None, "anonymous": True,
            "expires": expires, "csrf": csrf, "analyses": []}
        return token

    def restore_anonymous(self, token):
        """Rebuild an anonymous session from a signed ``sid`` cookie whose
        in-memory copy is gone (e.g. after a redeploy). Returns the session
        dict or ``None``.

        Restoration is completely disabled unless ``config.demo_mode`` is
        truthy, so turning DEMO_MODE off is a hard kill switch for anonymous
        access — no anonymous cookie is ever honoured. Nothing unsigned is
        trusted: the HMAC signature and the expiry are verified before any
        field is read, and only an anonymous session can ever result.
        """
        if not getattr(self.config, "demo_mode", False):
            return None
        data = self._verify_anonymous(token)
        if data is None:
            return None
        session = {"user_id": data["uid"], "email": None, "anonymous": True,
                   "expires": data["exp"], "csrf": data["csrf"],
                   "analyses": []}
        self._sessions[token] = session      # cache for this process lifetime
        return session

    def _sign_anonymous(self, user_id: str, csrf: str, expires: float) -> str:
        payload = {"uid": user_id, "csrf": csrf, "exp": float(expires)}
        body = _b64u_encode(json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode())
        signed = f"{ANON_TOKEN_VERSION}.{body}"
        sig = hmac.new(self.config.secret.encode(), signed.encode(),
                       hashlib.sha256).digest()
        return f"{signed}.{_b64u_encode(sig)}"

    def _verify_anonymous(self, token):
        if not isinstance(token, str):
            return None
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != ANON_TOKEN_VERSION:
            return None
        _, body, sig = parts
        expected = hmac.new(
            self.config.secret.encode(),
            f"{ANON_TOKEN_VERSION}.{body}".encode(), hashlib.sha256).digest()
        try:
            provided = _b64u_decode(sig)
        except (ValueError, TypeError):
            return None
        if not hmac.compare_digest(expected, provided):
            return None
        try:
            data = json.loads(_b64u_decode(body))
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        uid, csrf, exp = data.get("uid"), data.get("csrf"), data.get("exp")
        if not (isinstance(uid, str) and uid.startswith("anon-")
                and isinstance(csrf, str) and csrf
                and isinstance(exp, (int, float))):
            return None
        if exp <= self.now():
            return None
        return {"uid": uid, "csrf": csrf, "exp": float(exp)}

    # --- session reads --------------------------------------------------------
    def session(self, sid: str):
        """Live session dict or None (expired sessions are removed)."""
        s = self._sessions.get(sid)
        if s is None:
            return None
        if s["expires"] <= self.now():
            self._sessions.pop(sid, None)
            return None
        return s

    def csrf_token(self, sid: str):
        s = self.session(sid)
        return s["csrf"] if s else None

    def check_csrf(self, sid: str, token: str) -> bool:
        expected = self.csrf_token(sid)
        return bool(expected) and hmac.compare_digest(expected, token or "")
