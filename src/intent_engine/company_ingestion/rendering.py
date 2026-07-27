"""Optional, policy-aware rendered-page provider.

Some pages genuinely need JavaScript to produce text. Rendering them is
sometimes the only way to reach an evidence family — but a headless browser is
heavy (memory, CPU, deploy size, flakiness), so it must never be required for
the system to work.

This module defines the PROVIDER INTERFACE plus a no-op default. Browser
rendering is feature-flagged OFF (`BROWSER_RENDERING_ENABLED=0`) and, when
enabled, is bounded by domain policy, timeouts, and a cache. The rest of the
pipeline treats a provider that returns nothing exactly like a page that could
not be read — i.e. an honest failure, never invented content.

Policy is enforced BEFORE any rendering: login pages, authenticated areas,
paywalls, robots-disallowed paths and non-approved hosts are never rendered.
Rendering never bypasses authentication or access controls.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

RENDER_DISABLED = "DISABLED"
RENDER_OK = "OK"
RENDER_POLICY_BLOCKED = "POLICY_BLOCKED"
RENDER_TIMEOUT = "TIMEOUT"
RENDER_FAILED = "FAILED"
RENDER_UNAVAILABLE = "UNAVAILABLE"       # provider enabled but not installed

DEFAULT_RENDER_TIMEOUT_S = 15
MAX_RENDER_PAGES_PER_RUN = 3

# Never render these — they are authenticated, paywalled, or transactional.
_FORBIDDEN_PATH_MARKERS = (
    "/login", "/signin", "/sign-in", "/auth", "/account", "/checkout",
    "/cart", "/subscribe", "/paywall", "/register", "/password",
    "/admin", "/dashboard", "/billing",
)


def rendering_enabled(environ=None) -> bool:
    """OFF unless explicitly enabled. The report must work without it."""
    env = os.environ if environ is None else environ
    return str(env.get("BROWSER_RENDERING_ENABLED", "0")).strip().lower() in (
        "1", "true", "yes", "on")


def render_allowed(url: str, *, robots_disallow=(), approved_hosts=()) -> bool:
    """Policy gate applied BEFORE any rendering is attempted."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if approved_hosts and not any(
            host == h or host.endswith("." + h) for h in approved_hosts):
        return False                     # only sources already in the run
    path = (parsed.path or "/").lower()
    if any(marker in path for marker in _FORBIDDEN_PATH_MARKERS):
        return False                     # authenticated / paywalled surfaces
    for rule in robots_disallow or ():
        if not rule:
            continue
        anchored = rule.endswith("$")
        body = rule[:-1] if anchored else rule
        pattern = "".join(".*" if part == "*" else re.escape(part)
                          for part in re.split(r"(\*)", body))
        if re.match(pattern + ("$" if anchored else ""), path):
            return False                 # robots policy is honoured
    return True


class RenderedPageProvider:
    """Interface. `render(url)` returns {status, html, provenance}."""

    name = "base"

    def render(self, url: str, *, timeout=DEFAULT_RENDER_TIMEOUT_S) -> dict:
        raise NotImplementedError


class NullRenderedPageProvider(RenderedPageProvider):
    """The default: renders nothing, always. No browser, no dependency.

    A caller receiving DISABLED treats the page exactly as unreadable — the
    same honest failure it would record today.
    """

    name = "disabled"

    def render(self, url: str, *, timeout=DEFAULT_RENDER_TIMEOUT_S) -> dict:
        return {"status": RENDER_DISABLED, "html": "",
                "provenance": {"provider": self.name, "url": url}}


class PlaywrightRenderedPageProvider(RenderedPageProvider):
    """Optional Playwright-backed implementation.

    Imported lazily and never required: if Playwright is not installed the
    provider reports UNAVAILABLE rather than raising, so a deployment without
    browsers behaves exactly like the disabled default. Blocks images/media to
    keep memory and time bounded, and closes the browser on every path.
    """

    name = "playwright"

    def __init__(self, *, block_resources=True):
        self.block_resources = block_resources

    def render(self, url: str, *, timeout=DEFAULT_RENDER_TIMEOUT_S) -> dict:
        provenance = {"provider": self.name, "url": url, "timeout_s": timeout}
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"status": RENDER_UNAVAILABLE, "html": "",
                    "provenance": dict(provenance,
                                       reason="playwright is not installed")}
        browser = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                if self.block_resources:
                    context.route(
                        re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|mp4|woff2?)$"),
                        lambda route: route.abort())
                page = context.new_page()
                page.goto(url, timeout=timeout * 1000,
                          wait_until="domcontentloaded")
                html = page.content()
                context.close()
                return {"status": RENDER_OK, "html": html,
                        "provenance": dict(provenance, rendered=True)}
        except Exception as exc:                            # noqa: BLE001
            kind = (RENDER_TIMEOUT if "timeout" in str(exc).lower()
                    else RENDER_FAILED)
            return {"status": kind, "html": "",
                    "provenance": dict(provenance,
                                       reason=type(exc).__name__)}
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:                           # noqa: BLE001
                    pass


def build_provider(environ=None) -> RenderedPageProvider:
    """The provider this deployment should use. Disabled unless flagged on."""
    if not rendering_enabled(environ):
        return NullRenderedPageProvider()
    return PlaywrightRenderedPageProvider()
