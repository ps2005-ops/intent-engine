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
    )
    config.validate()
    return config
