"""V1.0.1 production configuration — three environments, validated at startup.

Rules (execution-grade prompt §production configuration):
- secrets only from environment variables; NO default production secret;
- production refuses to start without a strong secret and trusted hosts;
- secure cookies in production; explicit debug-off assertion;
- startup validation is loud, not lazy.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENVIRONMENTS = ("development", "test", "production")
MIN_SECRET_LEN = 32


class ConfigError(RuntimeError):
    """The configuration is unusable; the server must not start."""


@dataclass(frozen=True)
class AppConfig:
    env: str = "development"
    secret: str = ""                       # session/CSRF HMAC key
    trusted_hosts: tuple = ()              # required in production
    cookie_secure: bool = False            # forced True in production
    debug: bool = True                     # forced False in production
    session_ttl_seconds: int = 60 * 60 * 8
    login_max_attempts: int = 5
    login_lockout_seconds: int = 15 * 60
    registration_open: bool = False        # admin-created accounts by default
    web_store_path: Path = field(default=Path("data/webapp.jsonl"))
    fi_store_path: Path = field(default=Path("data/founder_intelligence.jsonl"))
    ci_store_path: Path = field(default=Path("data/company_ingestion.jsonl"))
    # One-time staging-user bootstrap (Render Free has no shell). All three
    # must be set for the route to exist; the hash is precomputed locally by
    # `generate-bootstrap`; no plaintext password ever reaches the server env.
    bootstrap_email: str = ""
    bootstrap_password_hash: str = ""
    bootstrap_token: str = ""
    # Temporary, feature-flagged Demo Mode for controlled usability testing.
    # OFF by default and OFF unless DEMO_MODE is explicitly truthy — when off,
    # the anonymous surface does not exist and the authentication flow is
    # byte-for-byte unchanged. Anonymous sessions are ephemeral (in-memory
    # only), isolated by a unique user_id through the existing ownership
    # checks, and may NOT create shares or any persistent-account artifact.
    # The two caps are abuse guardrails for the public URL while the beta is
    # live; the kill switch is DEMO_MODE=false + redeploy.
    demo_mode: bool = False
    demo_ip_analyses_per_hour: int = 10      # per client IP, rolling hour
    demo_session_analyses_per_day: int = 25  # per anon session, rolling day
    # Frictionless flow: when on (the default), submitting the analyze form
    # auto-approves the recommended sources (core company pages + authoritative
    # SEC filings) and runs straight through to the result — the separate
    # source-review page is skipped. Consent is still explicit (the analyze
    # form's checkbox). Set WEBAPP_AUTORUN_SOURCES=0 to restore the manual
    # source-review step.
    autorun_sources: bool = True

    def validate(self) -> None:
        if self.env not in ENVIRONMENTS:
            raise ConfigError(f"unknown environment {self.env!r}; expected one "
                              f"of {ENVIRONMENTS}")
        if self.env == "production":
            if not self.secret or len(self.secret) < MIN_SECRET_LEN:
                raise ConfigError(
                    "production requires WEBAPP_SECRET from the environment "
                    f"(>= {MIN_SECRET_LEN} chars); there is no default "
                    "production secret, by design")
            if not self.trusted_hosts:
                raise ConfigError("production requires WEBAPP_TRUSTED_HOSTS")
            if self.debug:
                raise ConfigError("debug must be off in production")
            if not self.cookie_secure:
                raise ConfigError("secure cookies are mandatory in production")
        if not self.secret:
            # dev/test still need a secret, but may generate an ephemeral one.
            raise ConfigError("a secret is required (set WEBAPP_SECRET or use "
                              "from_env which generates an ephemeral dev key)")
        if self.demo_mode:
            if self.demo_ip_analyses_per_hour < 1:
                raise ConfigError("demo_ip_analyses_per_hour must be >= 1")
            if self.demo_session_analyses_per_day < 1:
                raise ConfigError("demo_session_analyses_per_day must be >= 1")


def from_env(environ=None) -> AppConfig:
    """Build config from environment variables and validate it loudly."""
    env_map = os.environ if environ is None else environ
    env = env_map.get("WEBAPP_ENV", "development")
    secret = env_map.get("WEBAPP_SECRET", "")
    if not secret and env in ("development", "test"):
        import secrets as _secrets
        secret = _secrets.token_urlsafe(48)  # ephemeral, never for production
    hosts = tuple(h.strip() for h in
                  env_map.get("WEBAPP_TRUSTED_HOSTS", "").split(",")
                  if h.strip())
    is_prod = env == "production"

    def _truthy(name):
        return env_map.get(name, "").strip().lower() in (
            "1", "true", "yes", "on")

    def _pos_int(name, default):
        try:
            value = int(env_map.get(name, "").strip())
        except (TypeError, ValueError):
            return default
        return value if value >= 1 else default

    demo_mode = _truthy("DEMO_MODE")
    config = AppConfig(
        env=env,
        secret=secret,
        trusted_hosts=hosts,
        cookie_secure=is_prod or env_map.get("WEBAPP_COOKIE_SECURE") == "1",
        debug=(not is_prod) and env_map.get("WEBAPP_DEBUG", "1") == "1",
        registration_open=env_map.get("WEBAPP_REGISTRATION_OPEN") == "1",
        web_store_path=Path(env_map.get("WEBAPP_STORE",
                                        "data/webapp.jsonl")),
        fi_store_path=Path(env_map.get("WEBAPP_FI_STORE",
                                       "data/founder_intelligence.jsonl")),
        ci_store_path=Path(env_map.get("WEBAPP_CI_STORE",
                                       "data/company_ingestion.jsonl")),
        bootstrap_email=env_map.get("WEBAPP_BOOTSTRAP_EMAIL", ""),
        bootstrap_password_hash=env_map.get(
            "WEBAPP_BOOTSTRAP_PASSWORD_HASH", ""),
        bootstrap_token=env_map.get("WEBAPP_BOOTSTRAP_TOKEN", ""),
        demo_mode=demo_mode,
        demo_ip_analyses_per_hour=_pos_int(
            "DEMO_MAX_ANALYSES_PER_HOUR", 10),
        demo_session_analyses_per_day=_pos_int(
            "DEMO_MAX_ANALYSES_PER_DAY", 25),
        autorun_sources=env_map.get("WEBAPP_AUTORUN_SOURCES", "1").strip()
        .lower() not in ("0", "false", "no", "off"),
    )
    config.validate()
    return config
