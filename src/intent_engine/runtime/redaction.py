"""Secret redaction for persisted error strings.

The market-data fetchers pass credentials as URL query params
(`token=`, `api_key=`). A `requests` exception embeds the request URL, so an
un-sanitized error string could carry a live secret into the append-only
event log, the status files, and the dashboard — all durable and
human-visible. Every boundary that PERSISTS an error string routes it
through `redact_secrets` first.

Two layers of defence:
  1. redact the actual configured secret VALUES (we know them from the env);
  2. redact credential-shaped query params / headers even if the value is
     one we don't know (belt and suspenders).
"""
from __future__ import annotations

import os
import re

# env vars whose live values must never appear in a persisted string
_SECRET_ENV_VARS = (
    "TIINGO_API_KEY", "FRED_API_KEY", "ANTHROPIC_API_KEY", "PUBLER_API_KEY",
    "WEBAPP_SECRET",
)

_REDACTED = "***REDACTED***"

# credential-shaped key/value pairs: token=..., api_key: ..., ?key=..., etc.
_PARAM_RE = re.compile(
    r"(?i)\b(token|api[_-]?key|apikey|secret|password|passwd|key)"
    r"([=:]\s*)([^&\s\"']+)")
# space-separated bearer tokens: "Bearer eyJ...", "authorization: bearer ..."
_BEARER_RE = re.compile(r"(?i)\bbearer\s+([^&\s\"']+)")


def redact_secrets(text) -> str:
    if text is None:
        return ""
    s = str(text)
    # 1) known live values (exact string of a configured secret)
    for var in _SECRET_ENV_VARS:
        val = os.environ.get(var)
        if val and val.strip():
            s = s.replace(val, _REDACTED)
    # 2) credential-shaped tokens, regardless of whether we know the value
    s = _BEARER_RE.sub(f"Bearer {_REDACTED}", s)
    s = _PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", s)
    return s
