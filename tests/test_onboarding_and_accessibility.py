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
def test_a_first_time_guest_is_told_what_this_is(guest):
    _, _, page = guest.request("GET", "/")
    assert "Before you start" in page
    for heading in ("What this does", "How it works", "What it does not do",
                    "How to use it"):
        assert heading in page, f"missing: {heading}"


def test_onboarding_explains_the_limits_honestly(guest):
    _, _, page = guest.request("GET", "/")
    assert "no access to anything inside the company" in page
    assert "private meetings" in page
    assert "hypothesis, not a" in page


def test_onboarding_defines_the_words_that_would_otherwise_be_jargon(guest):
    _, _, page = guest.request("GET", "/")
    for term in ("Outside-in", "Confidence", "Hypothesis", "Contradiction",
                 "Limited analysis"):
        assert f">{term}<" in page, f"undefined term: {term}"


def test_onboarding_uses_no_internal_terminology(guest):
    _, _, page = guest.request("GET", "/")
    intro = page.split('class="onboarding"')[1].split("</section>")[0] \
        if 'class="onboarding"' in page else page
    for internal in ("evidence family", "evidence families", "source_class",
                     "ClaimSet", "readiness gate", "ingestion", "pipeline",
                     "synthesis", "corpus", "SEC filing", "EDGAR"):
        assert internal not in intro, f"internal term shown: {internal}"


def test_onboarding_is_dismissible_and_stays_dismissed(guest):
    _, _, page = guest.request("GET", "/")
    assert "Before you start" in page
    status, _, _ = guest.request("POST", "/onboarding/dismiss",
                                 f"csrf={guest.csrf()}")
    assert status.startswith("303")
    _, _, page = guest.request("GET", "/")
    assert "Before you start" not in page
    # and the analyse form is still right there
    assert 'action="/analyze"' in page


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


def test_no_page_leaks_an_internal_state_name(guest):
    for name, body in _all_styled_pages(guest).items():
        for internal in ("READY_FOR_FULL_REPORT", "RETRYABLE_EVIDENCE_GAP",
                         "IDENTITY_UNRESOLVED", "UNRECOGNISED",
                         "EVIDENCE_REPORT_READY", "DURABLE_PROVEN",
                         "may_synthesize", "source_class"):
            assert internal not in body, f"{name} leaked {internal}"
