"""First-time onboarding, and the visual contract behind every page.

Two failures from the same tester session. They landed on a company-name box
with no idea what the product was, and several pages had white text on white,
near-invisible headings, and content that looked permanently selected.

The contrast checks here are computed, not eyeballed: WCAG AA is arithmetic on
the two colours, so a stylesheet either passes it or does not.
"""
import io
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def guest(tmp_path):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_no_network, resolver=False)
    c = Client(app)
    c.request("POST", "/demo")
    return c


# --- onboarding ---------------------------------------------------------------
def test_a_first_time_guest_meets_the_product_not_the_methodology(guest):
    """The explainer moved OFF the landing page. A first-time visitor gets the
    promise, the input and an example of the output; the methodology is one
    click away for anyone who wants it."""
    _, _, page = guest.request("GET", "/")
    assert "Before you start" not in page, "methodology is back in front of value"
    assert 'action="/analyze"' in page              # the one thing to do
    # ONE primary call to action. The old page rendered six identical
    # "Got it - start an analysis" buttons because the explainer injection
    # used str.replace on '</section>' with no count.
    # The LABEL is not the invariant -- the COUNT is. The button now reads
    # "Analyse company" because the form takes a company name and no longer
    # demands a website. Pinning the old wording would fail this test for a
    # copy change while still passing if six of the new buttons appeared,
    # which is the defect the assertion was written to catch.
    assert page.count("Analyse company") == 1
    assert 'href="/onboarding"' in page             # still reachable


def test_the_methodology_page_still_tells_a_guest_what_this_is(guest):
    _, _, page = guest.request("GET", "/onboarding")
    assert "Before you start" in page
    for heading in ("What this does", "How it works", "What it does not do",
                    "How to use it"):
        assert heading in page, f"missing: {heading}"


def test_onboarding_explains_the_limits_honestly(guest):
    _, _, page = guest.request("GET", "/onboarding")
    assert "no access to anything inside the company" in page
    assert "private meetings" in page
    assert "hypothesis, not a" in page


def test_onboarding_defines_the_words_that_would_otherwise_be_jargon(guest):
    _, _, page = guest.request("GET", "/onboarding")
    for term in ("Outside-in", "Confidence", "Hypothesis", "Contradiction",
                 "Limited analysis"):
        assert f">{term}<" in page, f"undefined term: {term}"


def test_onboarding_uses_no_internal_terminology(guest):
    _, _, page = guest.request("GET", "/onboarding")
    intro = page.split('class="onboarding"')[1].split("</section>")[0] \
        if 'class="onboarding"' in page else page
    for internal in ("evidence family", "evidence families", "source_class",
                     "ClaimSet", "readiness gate", "ingestion", "pipeline",
                     "synthesis", "corpus", "SEC filing", "EDGAR"):
        assert internal not in intro, f"internal term shown: {internal}"


def test_the_landing_page_has_nothing_to_dismiss(guest):
    """The dismiss flow existed because the explainer was in the way. It is
    not in the way any more."""
    _, _, page = guest.request("GET", "/")
    assert "Got it" not in page
    assert "ob-dismiss" not in page


def test_onboarding_stays_reachable_after_dismissal(guest):
    guest.request("POST", "/onboarding/dismiss", f"csrf={guest.csrf()}")
    status, _, page = guest.request("GET", "/onboarding")
    assert status == "200 OK"
    assert "What this does" in page


def _visible_prose(html):
    """Reader-visible words only — stylesheets and scripts are not prose."""
    stripped = re.sub(r"<(style|script)\b.*?</\1>", " ", html,
                      flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", stripped)


def test_onboarding_is_one_screen_not_a_manual(guest):
    _, _, page = guest.request("GET", "/onboarding")
    assert len(_visible_prose(page).split()) < 400, \
        "onboarding must fit on one screen"


# --- the visual contract -------------------------------------------------------
def _luminance(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    if len(hex_colour) == 3:
        hex_colour = "".join(c * 2 for c in hex_colour)
    channels = []
    for i in (0, 2, 4):
        value = int(hex_colour[i:i + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928
                        else ((value + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# Every foreground/background pair the stylesheets actually put together, in
# both themes. WCAG AA is 4.5:1 for body text and 3:1 for large text.
_LIGHT = {"ink": "#111827", "muted": "#4b5563", "bg": "#ffffff",
          "panel": "#f8fafc", "accent": "#1d4ed8", "accent_ink": "#ffffff"}
_DARK = {"ink": "#f3f4f6", "muted": "#c3cad6", "bg": "#0f141c",
         "panel": "#161c26", "accent": "#7aa2ff", "accent_ink": "#0b1220"}


@pytest.mark.parametrize("theme", [_LIGHT, _DARK], ids=["light", "dark"])
@pytest.mark.parametrize("fg,bg", [("ink", "bg"), ("ink", "panel"),
                                   ("muted", "bg"), ("muted", "panel"),
                                   ("accent", "bg"), ("accent", "panel")])
def test_body_text_meets_wcag_aa(theme, fg, bg):
    ratio = contrast_ratio(theme[fg], theme[bg])
    assert ratio >= 4.5, f"{fg} on {bg} is {ratio:.2f}:1, needs 4.5:1"


@pytest.mark.parametrize("theme", [_LIGHT, _DARK], ids=["light", "dark"])
def test_button_text_meets_wcag_aa(theme):
    ratio = contrast_ratio(theme["accent_ink"], theme["accent"])
    assert ratio >= 4.5, f"button text is {ratio:.2f}:1"


def test_no_colour_is_ever_the_same_as_its_background():
    """White on white is the failure that started this."""
    for theme in (_LIGHT, _DARK):
        for key in ("ink", "muted", "accent"):
            assert theme[key].lower() != theme["bg"].lower()
            assert theme[key].lower() != theme["panel"].lower()


def _get(guest, path, hops=4):
    """GET, following redirects — a reader never sees the 303, they see the
    page it lands on, and that is the page whose styling must hold up."""
    for _ in range(hops):
        status, headers, body = guest.request("GET", path)
        if not status.startswith("30") or "Location" not in headers:
            return body
        path = headers["Location"]
    return body


def _all_styled_pages(guest):
    """Every page a tester actually walks through."""
    pages = {}
    for path in ("/", "/onboarding", "/login"):
        pages[path] = _get(guest, path)
    _, headers, _ = guest.request(
        "POST", "/analyze",
        f"consent=on&csrf={guest.csrf()}&website=https://northwind-demo.example")
    run = headers["Location"].split("/runs/")[1].split("/")[0]
    for suffix in ("", "/brief", "/slides", "/full", "/progress"):
        pages[f"/runs/…{suffix}"] = _get(guest, f"/runs/{run}{suffix}")
    pages["404"] = _get(guest, "/definitely-not-a-route")
    return pages


def test_no_page_ships_a_global_selection_or_focus_rule(guest):
    """Content that looks permanently selected reads as a broken page."""
    for name, body in _all_styled_pages(guest).items():
        assert "::selection" not in body, f"{name} styles ::selection globally"
        assert not re.search(r"\*\s*:focus\s*\{", body), \
            f"{name} has a global focus rule"


def test_every_page_is_styled_not_a_raw_browser_default(guest):
    for name, body in _all_styled_pages(guest).items():
        assert "<style" in body or "class=" in body, f"{name} is unstyled"


def test_every_page_declares_a_mobile_viewport(guest):
    for name, body in _all_styled_pages(guest).items():
        if "<html" not in body:
            continue
        assert "width=device-width" in body, f"{name} has no viewport"


def test_the_reading_surfaces_are_responsive(guest):
    pages = _all_styled_pages(guest)
    for name in ("/runs/…/brief", "/runs/…/slides", "/onboarding"):
        assert "@media" in pages[name], f"{name} has no responsive rules"


def test_focus_is_visible_on_the_interactive_surfaces(guest):
    pages = _all_styled_pages(guest)
    for name in ("/runs/…/brief", "/runs/…/slides"):
        assert "focus-visible" in pages[name], f"{name} has no focus style"


def test_links_are_visually_distinct_from_text(guest):
    _, _, brief = guest.request("GET", "/onboarding")
    assert "text-decoration:underline" in brief.replace(" ", "")


def test_the_presentation_is_print_friendly(guest):
    pages = _all_styled_pages(guest)
    assert "@media print" in pages["/runs/…/slides"]


def test_both_themes_are_styled_never_only_one(guest):
    pages = _all_styled_pages(guest)
    for name in ("/runs/…/brief", "/runs/…/slides", "/onboarding"):
        assert "prefers-color-scheme:dark" in pages[name].replace(" ", ""), \
            f"{name} has no dark theme"


# WHY THE TEST ABOVE PASSED WHILE THE LANDING PAGE WAS UNREADABLE. Every page
# ships `_A11Y_CSS`, and that sheet contains the string
# "prefers-color-scheme:dark" — so asking whether the string is present asks
# nothing about the page's OWN stylesheet. Measured live on preview-v3 at
# c57af3b, in dark mode: `.sample-quote` rendered #1a1a2e on #0f141c (1.08:1),
# `.lede` 1.68:1, and the consent label 1.9:1 — the sentence describing what
# the visitor was consenting to. The floor could not correct them because
# `form.analyze label` and `.sample-quote` outrank its selectors.
#
# So test the property that actually prevents it: a page's own sheet may not
# name a colour, because a colour it names is a colour the dark block cannot
# re-point.

def test_the_landing_sheet_names_no_colour_a_theme_cannot_repoint():
    from intent_engine.founder_intelligence.presentation import _LANDING_CSS
    # `:root{...}` is where a literal belongs: once as the light default, once
    # re-pointed inside the dark block.
    rules = re.sub(r":root\s*\{[^}]*\}", "", _LANDING_CSS)
    leaked = re.findall(r"#[0-9a-fA-F]{3,8}\b", rules)
    assert not leaked, (
        f"landing rules hard-code {sorted(set(leaked))}; dark mode cannot "
        "re-point a literal, so these render at light-mode values on a dark "
        "background")


def test_the_focus_ring_is_repointed_for_dark_not_left_on_the_light_accent():
    """Measured on the deployed /login at b66dbe3: the ring rendered #1d4ed8
    on #0f141c — 2.76:1, under the 3:1 WCAG floor for a non-text indicator, so
    a keyboard user in dark mode could not reliably see where they were."""
    from intent_engine.webapp.app import _A11Y_CSS

    def contrast(hex_a, hex_b):
        def lin(component):
            component /= 255
            return (component / 12.92 if component <= 0.03928
                    else ((component + 0.055) / 1.055) ** 2.4)

        def lum(value):
            r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

        first, second = lum(hex_a), lum(hex_b)
        hi, lo = max(first, second), min(first, second)
        return (hi + 0.05) / (lo + 0.05)

    compact = _A11Y_CSS.replace(" ", "").replace("\n", "")
    dark = compact.split("@media(prefers-color-scheme:dark)", 1)[1]
    assert "focus-visible{outline-color:#7aa2ff}" in dark, \
        "dark mode does not re-point the focus ring"
    assert contrast("#7aa2ff", "#0f141c") >= 3.0
    assert contrast("#1d4ed8", "#0f141c") < 3.0      # the value it replaced


def test_every_panel_that_sets_a_light_background_has_a_dark_counterpart():
    """A background without a colour inherits the dark scheme's near-white.

    Measured live on preview-v3 at 20ffb9c, on the progress page: the stage
    line inside [role=status] rendered at 1.01:1 and the .coverage note at
    1.06:1 — both invisible, on the screen a visitor watches for the whole
    analysis. The generic floor has no rule for these selectors, so the dark
    counterpart has to live beside the light one.
    """
    from intent_engine.founder_intelligence.presentation import _BASE_CSS
    compact = _BASE_CSS.replace(" ", "").replace("\n", "")
    assert "@media(prefers-color-scheme:dark)" in compact, \
        "the base sheet has no dark block"
    light, dark = compact.split("@media(prefers-color-scheme:dark)", 1)
    for selector in ("[role=status]", "[role=alert]", ".coverage",
                     "ul.source-listlilabel"):
        if selector + "{" in light:
            assert selector in dark, (
                f"{selector} sets a light background with no dark counterpart; "
                "its text inherits near-white and disappears")


def test_a_control_border_is_visible_in_dark_mode():
    """WCAG 1.4.11: the boundary that tells a reader where a field IS needs
    3:1, the same as any other non-text UI component.

    Measured live on the deployed landing form at a5e1322, in dark mode: the
    label, the placeholder and the typed text all passed, and the box around
    them rendered #3a4454 on #0f141c — 1.88:1, and 1.74:1 inside a panel. The
    text was readable and you could not see where to type it.
    """
    from intent_engine.founder_intelligence.presentation import _LANDING_CSS
    from intent_engine.webapp.app import _A11Y_CSS

    def contrast(a, b):
        def lin(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        def lum(h):
            r, g, b_ = (int(h[i:i + 2], 16) for i in (1, 3, 5))
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b_)

        x, y = lum(a), lum(b)
        hi, lo = max(x, y), min(x, y)
        return (hi + 0.05) / (lo + 0.05)

    page, panel = "#0f141c", "#161c26"
    for sheet, name in ((_LANDING_CSS, "landing"), (_A11Y_CSS, "floor")):
        compact = sheet.replace(" ", "").replace("\n", "")
        dark = compact.split("@media(prefers-color-scheme:dark)", 1)[1]
        assert "#606e88" in dark, f"{name} sheet has no visible control border"
    assert contrast("#606e88", page) >= 3.0
    assert contrast("#606e88", panel) >= 3.0
    assert contrast("#3a4454", page) < 3.0          # the value it replaced


def test_the_landing_sheet_repoints_its_palette_for_dark():
    from intent_engine.founder_intelligence.presentation import _LANDING_CSS
    compact = _LANDING_CSS.replace(" ", "").replace("\n", "")
    assert "@media(prefers-color-scheme:dark)" in compact, \
        "the landing sheet has no dark block of its own"
    dark = compact.split("@media(prefers-color-scheme:dark)", 1)[1]
    # the text a visitor reads first, and the one they must read to consent
    for token in ("--l-lede:", "--l-label:", "--l-ink:", "--l-field-bg:"):
        assert token in dark, f"dark mode never re-points {token}"


def test_no_page_leaks_an_internal_state_name(guest):
    for name, body in _all_styled_pages(guest).items():
        for internal in ("READY_FOR_FULL_REPORT", "RETRYABLE_EVIDENCE_GAP",
                         "IDENTITY_UNRESOLVED", "UNRECOGNISED",
                         "EVIDENCE_REPORT_READY", "DURABLE_PROVEN",
                         "may_synthesize", "source_class"):
            assert internal not in body, f"{name} leaked {internal}"


def test_the_examples_line_sits_below_the_form_not_above_the_headline(guest):
    """Seen on the deployed page: injected at '<main>', the examples footnote
    rendered above the h1, so the first thing a visitor read was a note about
    examples rather than what the product does."""
    _, _, page = guest.request("GET", "/")
    assert "Not sure where to start" in page
    assert page.index("<h1") < page.index("Not sure where to start"), \
        "the examples line renders above the headline"
    assert page.index('action="/analyze"') < page.index("Not sure where to start")
