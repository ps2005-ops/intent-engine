"""V1.0.1 — configuration and authentication contracts."""
import pytest

from intent_engine.webapp.auth import AuthService, hash_password, verify_password
from intent_engine.webapp.config import AppConfig, ConfigError, from_env
from intent_engine.webapp.records import WebAppError
from intent_engine.webapp.store import WebStore


def _cfg(tmp_path, **kw):
    base = dict(env="test", secret="s" * 40,
                web_store_path=tmp_path / "web.jsonl",
                fi_store_path=tmp_path / "fi.jsonl")
    base.update(kw)
    return AppConfig(**base)


# --- configuration -----------------------------------------------------------

def test_production_requires_secret_no_default(tmp_path):
    with pytest.raises(ConfigError, match="no default production secret"):
        _cfg(tmp_path, env="production", secret="", debug=False,
             cookie_secure=True, trusted_hosts=("app.example",)).validate()


def test_production_requires_trusted_hosts(tmp_path):
    with pytest.raises(ConfigError, match="TRUSTED_HOSTS"):
        _cfg(tmp_path, env="production", secret="s" * 40, debug=False,
             cookie_secure=True).validate()


def test_production_forces_debug_off_and_secure_cookies(tmp_path):
    with pytest.raises(ConfigError, match="debug"):
        _cfg(tmp_path, env="production", secret="s" * 40, debug=True,
             cookie_secure=True, trusted_hosts=("h",)).validate()
    with pytest.raises(ConfigError, match="cookies"):
        _cfg(tmp_path, env="production", secret="s" * 40, debug=False,
             cookie_secure=False, trusted_hosts=("h",)).validate()


def test_from_env_production_valid_and_debug_off():
    cfg = from_env({"WEBAPP_ENV": "production", "WEBAPP_SECRET": "x" * 40,
                    "WEBAPP_TRUSTED_HOSTS": "app.example"})
    assert cfg.debug is False and cfg.cookie_secure is True


def test_from_env_dev_generates_ephemeral_secret():
    cfg = from_env({"WEBAPP_ENV": "development"})
    assert len(cfg.secret) >= 32 and cfg.env == "development"


def test_unknown_environment_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown environment"):
        _cfg(tmp_path, env="staging").validate()


# --- password hashing --------------------------------------------------------

def test_password_hash_salted_and_verifies():
    h1, h2 = hash_password("password123"), hash_password("password123")
    assert h1 != h2                       # unique salts
    assert verify_password("password123", h1)
    assert not verify_password("wrong-password", h1)


def test_short_password_rejected():
    with pytest.raises(WebAppError, match="8 characters"):
        hash_password("short")


# --- accounts / login / sessions ---------------------------------------------

def _auth(tmp_path, now=None, **cfg_kw):
    clock = {"t": 1000.0}
    def now_fn():
        return clock["t"]
    config = _cfg(tmp_path, **cfg_kw)
    auth = AuthService(WebStore(config.web_store_path), config, now_fn=now_fn)
    return auth, clock


def test_admin_creates_account_registration_closed(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("founder@example.com", "password123")
    with pytest.raises(WebAppError, match="registration is closed"):
        auth.create_user("x@example.com", "password123", via_registration=True)


def test_duplicate_account_rejected(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    with pytest.raises(WebAppError, match="already exists"):
        auth.create_user("a@example.com", "otherpassword")


def test_login_error_is_generic(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    with pytest.raises(WebAppError, match="invalid credentials"):
        auth.login("a@example.com", "wrong-password")
    with pytest.raises(WebAppError, match="invalid credentials"):
        auth.login("nobody@example.com", "password123")


def test_login_lockout_and_recovery(tmp_path):
    auth, clock = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    for _ in range(5):
        with pytest.raises(WebAppError):
            auth.login("a@example.com", "wrong-password")
    # locked out even with the RIGHT password
    with pytest.raises(WebAppError, match="too many attempts"):
        auth.login("a@example.com", "password123")
    clock["t"] += 16 * 60                  # lockout window passes
    assert auth.login("a@example.com", "password123")


def test_session_expires(tmp_path):
    auth, clock = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    sid = auth.login("a@example.com", "password123")
    assert auth.session(sid) is not None
    clock["t"] += 9 * 3600
    assert auth.session(sid) is None


def test_csrf_bound_to_session(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    sid = auth.login("a@example.com", "password123")
    token = auth.csrf_token(sid)
    assert auth.check_csrf(sid, token)
    assert not auth.check_csrf(sid, "forged")
    assert not auth.check_csrf("no-such-session", token)


def test_logout_kills_session(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    sid = auth.login("a@example.com", "password123")
    auth.logout(sid)
    assert auth.session(sid) is None


def test_login_events_are_appended(tmp_path):
    auth, _ = _auth(tmp_path)
    auth.create_user("a@example.com", "password123")
    with pytest.raises(WebAppError):
        auth.login("a@example.com", "nope-nope")
    auth.login("a@example.com", "password123")
    types = [r.event_type for r in auth.store.read_all()]
    assert "web.login_failed" in types and "web.login_succeeded" in types
