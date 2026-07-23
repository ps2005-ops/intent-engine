"""V1.0.1 Early-Access Readiness — the web layer over Founder Intelligence.

New infrastructure (server, auth, sessions, CSRF, sharing, config), held
to full engineering discipline. It composes the frozen T023.5 product and
computes no intelligence.
"""
from intent_engine.webapp.app import WebApp, make_server
from intent_engine.webapp.auth import (
    AuthService, PASSWORD_RESET_STATUS, hash_password, verify_password,
)
from intent_engine.webapp.config import (
    AppConfig, ConfigError, ENVIRONMENTS, from_env,
)
from intent_engine.webapp.records import WebAppError, WebEvent
from intent_engine.webapp.sharing import DEFAULT_SHARE_TTL_SECONDS, SharingService
from intent_engine.webapp.store import (
    DEFAULT_WEB_PATH, WebAppCorruptLogError, WebStore,
)

__all__ = [
    "AppConfig", "AuthService", "ConfigError", "DEFAULT_SHARE_TTL_SECONDS",
    "DEFAULT_WEB_PATH", "ENVIRONMENTS", "PASSWORD_RESET_STATUS",
    "SharingService", "WebApp", "WebAppCorruptLogError", "WebAppError",
    "WebEvent", "WebStore", "from_env", "hash_password", "make_server",
    "verify_password",
]
