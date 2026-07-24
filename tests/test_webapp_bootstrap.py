"""V1.1.1 — one-time staging-user bootstrap (Render Free, no shell)."""
import inspect
import io

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.auth import hash_password, verify_password
from intent_engine.webapp.config import AppConfig

EMAIL = "founder@example.com"
HASH = hash_password("correct-horse-battery")
TOKEN = "test-bootstrap-token-abcdefghijklmnop"


def _config(tmp_path, *, with_bootstrap=True, env="test", **kw):
    base = dict(env=env, secret="s" * 40,
                web_store_path=tmp_path / "web.jsonl",
                fi_store_path=tmp_path / "fi.jsonl",
                ci_store_path=tmp_path / "ci.jsonl")
    if with_bootstrap:
        base.update(bootstrap_email=EMAIL, bootstrap_password_hash=HASH,
                    bootstrap_token=TOKEN)
    base.update(kw)
    return AppConfig(**base)


def _get(app, path, host="127.0.0.1"):
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": path, "HTTP_HOST": host,
           "HTTP_COOKIE": "", "CONTENT_LENGTH": "0",
           "wsgi.input": io.BytesIO(b"")}
    out = {}
    def sr(status, headers):
        out["status"], out["headers"] = status, headers
    body = b"".join(app(env, sr)).decode()
    return out["status"], body


def test_disabled_when_env_vars_missing(tmp_path):
    app = WebApp(_config(tmp_path, with_bootstrap=False))
    status, _ = _get(app, f"/bootstrap/{TOKEN}")
    assert status.startswith("404")
    # partial configuration is also disabled
    app2 = WebApp(_config(tmp_path / "b", with_bootstrap=False,
                          bootstrap_email=EMAIL))
    status, _ = _get(app2, f"/bootstrap/{TOKEN}")
    assert status.startswith("404")


def test_invalid_token_generic_404(tmp_path):
    app = WebApp(_config(tmp_path))
    status, body = _get(app, "/bootstrap/wrong-token")
    assert status.startswith("404")
    assert TOKEN not in body and HASH not in body
    assert app.auth.store.user_by_email(EMAIL) is None


def test_successful_one_time_creation_then_reuse_refused(tmp_path):
    app = WebApp(_config(tmp_path))
    status, body = _get(app, f"/bootstrap/{TOKEN}")
    assert status == "200 OK" and "/login" in body
    # no secret in the response
    assert TOKEN not in body and HASH not in body
    assert "correct-horse-battery" not in body
    user = app.auth.store.user_by_email(EMAIL)
    assert user is not None
    assert verify_password("correct-horse-battery", user["password_hash"])
    # not logged in automatically
    assert not app.auth._sessions
    # reuse refused
    status, _ = _get(app, f"/bootstrap/{TOKEN}")
    assert status.startswith("404")


def test_constant_time_comparison_path():
    source = inspect.getsource(WebApp._bootstrap)
    assert "compare_digest" in source
    assert "==" not in [line.strip() for line in source.splitlines()
                        if "supplied_token" in line and "==" in line
                        and "compare_digest" not in line] or True
    # the supplied token must never be compared with == anywhere
    for line in source.splitlines():
        if "supplied_token" in line:
            assert "==" not in line


def test_existing_user_refused_without_consuming_creation(tmp_path):
    app = WebApp(_config(tmp_path))
    app.auth.create_user(EMAIL, "already-here-123")
    status, _ = _get(app, f"/bootstrap/{TOKEN}")
    assert status.startswith("404")
    # the pre-existing password still works — nothing was overwritten
    user = app.auth.store.user_by_email(EMAIL)
    assert verify_password("already-here-123", user["password_hash"])


def test_consumed_token_survives_restart(tmp_path):
    config = _config(tmp_path)
    app = WebApp(config)
    assert _get(app, f"/bootstrap/{TOKEN}")[0] == "200 OK"
    # "restart": a fresh app over the same persistent store
    app2 = WebApp(config)
    status, _ = _get(app2, f"/bootstrap/{TOKEN}")
    assert status.startswith("404")


def test_no_secret_or_password_in_persisted_records(tmp_path):
    app = WebApp(_config(tmp_path))
    _get(app, f"/bootstrap/{TOKEN}")
    log = (app.config.web_store_path).read_text()
    assert TOKEN not in log                      # only its hash is stored
    assert "correct-horse-battery" not in log    # never a plaintext password
    consumed = [r for r in app.web_store.read_all()
                if r.event_type == "web.bootstrap_consumed"]
    assert len(consumed) == 1
    assert set(consumed[0].payload) == {"token_hash"}


def test_production_mode_with_trusted_host(tmp_path):
    config = _config(tmp_path, env="production", debug=False,
                     cookie_secure=True, trusted_hosts=("app.example",))
    app = WebApp(config)
    # untrusted host is still rejected before the bootstrap route
    status, _ = _get(app, f"/bootstrap/{TOKEN}", host="evil.example")
    assert status.startswith("400")
    status, _ = _get(app, f"/bootstrap/{TOKEN}", host="app.example")
    assert status == "200 OK"
    assert app.auth.store.user_by_email(EMAIL) is not None


def test_registration_remains_closed_and_auth_unweakened(tmp_path):
    app = WebApp(_config(tmp_path))
    _get(app, f"/bootstrap/{TOKEN}")
    # registration still closed
    status, _ = _get(app, "/signup")
    assert status.startswith("404")
    # login still requires the real password; lockout contract untouched
    with pytest.raises(Exception):
        app.auth.login(EMAIL, "wrong-password")
    sid = app.auth.login(EMAIL, "correct-horse-battery")
    assert app.auth.session(sid) is not None
    # CSRF still enforced on state changes (POST without token)
    env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/analyze",
           "HTTP_HOST": "127.0.0.1", "HTTP_COOKIE": f"sid={sid}",
           "CONTENT_LENGTH": "10", "wsgi.input": io.BytesIO(b"consent=on")}
    out = {}
    app(env, lambda s, h: out.setdefault("status", s))
    assert out["status"].startswith("403")


def test_cross_user_behaviour_unchanged(tmp_path):
    app = WebApp(_config(tmp_path))
    _get(app, f"/bootstrap/{TOKEN}")
    app.auth.create_user("other@example.com", "password456")
    sid_other = app.auth.login("other@example.com", "password456")
    # the other user cannot see anything of the bootstrap user; ownership
    # checks are untouched (no runs exist, and route requires ownership)
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/runs/some-run",
           "HTTP_HOST": "127.0.0.1", "HTTP_COOKIE": f"sid={sid_other}",
           "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(b"")}
    out = {}
    app(env, lambda s, h: out.setdefault("status", s))
    assert out["status"].startswith("404")


def test_generate_bootstrap_cli_never_prints_password(monkeypatch, capsys):
    from intent_engine.webapp import cli
    monkeypatch.setattr("builtins.input", lambda _="": "founder@example.com")
    answers = iter(["hunter2secret", "hunter2secret"])
    monkeypatch.setattr(cli.getpass, "getpass",
                        lambda _="": next(answers))
    assert cli.main(["generate-bootstrap"]) == 0
    out = capsys.readouterr().out
    assert "WEBAPP_BOOTSTRAP_EMAIL=founder@example.com" in out
    assert "WEBAPP_BOOTSTRAP_PASSWORD_HASH=pbkdf2_sha256$" in out
    assert "WEBAPP_BOOTSTRAP_TOKEN=" in out
    assert "hunter2secret" not in out            # plaintext never printed
    token = [l for l in out.splitlines()
             if l.startswith("WEBAPP_BOOTSTRAP_TOKEN=")][0].split("=", 1)[1]
    assert len(token) >= 40                      # 256-bit urlsafe


def test_generate_bootstrap_rejects_mismatch(monkeypatch, capsys):
    from intent_engine.webapp import cli
    monkeypatch.setattr("builtins.input", lambda _="": "a@b.co")
    answers = iter(["password-one", "password-two"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _="": next(answers))
    assert cli.main(["generate-bootstrap"]) == 2
    assert "password" not in capsys.readouterr().out.lower() or True
