"""Deployable version identity.

`/version` (webapp) reads this so a deployed instance is identifiable — the
"is the deployed commit the tested commit?" question the acceptance
criteria require. The commit is read from the environment the platform
actually deploys on (Render sets RENDER_GIT_COMMIT); WEBAPP_COMMIT is an
explicit override for other hosts. Never guessed: unknown is reported as
"unknown", not fabricated. No secret is ever read or exposed here.
"""
from __future__ import annotations

import os

# Bumped when the platform's runtime contract changes. Distinct from the
# event schema version (events/envelope.COMPANY_EVENT_SCHEMA_VERSION).
APP_VERSION = "1.4.0-unified-learning-runtime"


def deployed_commit() -> str:
    for var in ("WEBAPP_COMMIT", "RENDER_GIT_COMMIT", "SOURCE_VERSION"):
        val = os.environ.get(var)
        if val:
            return val
    return "unknown"


def version_info() -> dict:
    return {"app_version": APP_VERSION, "commit": deployed_commit()}
