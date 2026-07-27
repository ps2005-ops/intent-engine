"""Optional rendered-page provider contract.

Browser rendering must never be REQUIRED: these tests run with no browser
installed and prove the default is a no-op, the policy gate refuses
authenticated/paywalled/disallowed pages before anything is rendered, and an
unavailable or timing-out provider degrades to an honest failure rather than
inventing content.
"""
from intent_engine.company_ingestion.rendering import (
    DEFAULT_RENDER_TIMEOUT_S, NullRenderedPageProvider,
    PlaywrightRenderedPageProvider, RENDER_DISABLED, RENDER_FAILED,
    RENDER_OK, RENDER_TIMEOUT, RENDER_UNAVAILABLE, build_provider,
    render_allowed, rendering_enabled,
)


# --- feature flag -----------------------------------------------------------

def test_rendering_is_disabled_by_default():
    assert rendering_enabled({}) is False
    assert rendering_enabled({"BROWSER_RENDERING_ENABLED": "0"}) is False
    assert isinstance(build_provider({}), NullRenderedPageProvider)


def test_rendering_enabled_only_when_explicitly_flagged():
    assert rendering_enabled({"BROWSER_RENDERING_ENABLED": "1"})
    assert rendering_enabled({"BROWSER_RENDERING_ENABLED": "true"})
    provider = build_provider({"BROWSER_RENDERING_ENABLED": "1"})
    assert isinstance(provider, PlaywrightRenderedPageProvider)


def test_disabled_provider_renders_nothing_and_never_raises():
    result = NullRenderedPageProvider().render("https://x.com/page")
    assert result["status"] == RENDER_DISABLED
    assert result["html"] == ""
    assert result["provenance"]["provider"] == "disabled"


# --- policy gate ------------------------------------------------------------

def test_policy_refuses_authenticated_and_paywalled_pages():
    for path in ("/login", "/signin", "/account/settings", "/checkout",
                 "/subscribe", "/admin/users", "/billing"):
        assert not render_allowed(f"https://x.com{path}"), path


def test_policy_refuses_non_http_and_unknown_hosts():
    assert not render_allowed("file:///etc/passwd")
    assert not render_allowed("javascript:alert(1)")
    assert not render_allowed("https://evil.com/page",
                              approved_hosts=("x.com",))
    assert render_allowed("https://x.com/products",
                          approved_hosts=("x.com",))
    assert render_allowed("https://www.x.com/products",
                          approved_hosts=("x.com",))


def test_policy_honours_robots_disallow():
    rules = ["/private", "*/internal", "/tmp$"]
    assert not render_allowed("https://x.com/private/deck", robots_disallow=rules)
    assert not render_allowed("https://x.com/a/internal", robots_disallow=rules)
    assert not render_allowed("https://x.com/tmp", robots_disallow=rules)
    assert render_allowed("https://x.com/products", robots_disallow=rules)


def test_policy_allows_an_ordinary_public_product_page():
    assert render_allowed("https://x.com/platform/overview")


# --- provider behaviour without a browser -----------------------------------

def test_playwright_provider_reports_unavailable_without_browser(monkeypatch):
    """No browser installed must NOT be an exception — it degrades."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = PlaywrightRenderedPageProvider().render("https://x.com/p")
    assert result["status"] == RENDER_UNAVAILABLE
    assert result["html"] == ""
    assert "not installed" in result["provenance"]["reason"]


def test_provider_results_carry_provenance():
    result = NullRenderedPageProvider().render("https://x.com/p")
    assert result["provenance"]["url"] == "https://x.com/p"


def test_render_outcomes_are_typed_not_generic():
    """Distinct failure modes must remain distinguishable."""
    assert len({RENDER_OK, RENDER_DISABLED, RENDER_TIMEOUT, RENDER_FAILED,
                RENDER_UNAVAILABLE}) == 5
    assert DEFAULT_RENDER_TIMEOUT_S > 0
