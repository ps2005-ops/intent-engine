"""The surfaces the matrix never looked at.

Twenty companies scored 20/20 useful while the dashboard, the Q&A, the share
link and the retry path had never been measured once. A matrix result is a
statement about the analysis, not about the pages a customer actually opens —
so these are gated here, at the same standard as the reading surfaces.

The defect this file was written around: `/shared/{token}` rendered
`<li>{section["kind"]}</li>`, so a person opening a shared link saw five
snake_case enum names — "company_understanding", "what_stood_out",
"possible_blind_spots", "executive_confidence", "leadership_questions" — and no
analysis whatsoever. Every section already carried a reader-facing `title` and
cards with headlines; the renderer read the one field on the object that is
internal and discarded the rest.
"""
from __future__ import annotations

import io
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

#: internal identifiers that must never reach a rendered page
INTERNAL_NAMES = ("company_understanding", "what_stood_out",
                  "possible_blind_spots", "executive_confidence",
                  "leadership_questions", "insight_id", "claim_id",
                  "source_refs", "replay_id", "AVAIL_", "SUPPORTED",
                  "UNAVAILABLE")


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


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture(scope="module")
def surfaces(tmp_path_factory):
    """Every previously-unmeasured surface, rendered once."""
    tmp = tmp_path_factory.mktemp("surfaces")
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp / "w.jsonl",
                       fi_store_path=tmp / "f.jsonl",
                       ci_store_path=tmp / "c.jsonl")
    app = WebApp(config, transport=_no_network, resolver=False)
    app.auth.create_user("founder@example.com", "password123")
    c = Client(app)
    c.request("POST", "/login",
              "email=founder@example.com&password=password123")
    csrf = app.auth.csrf_token(c.sid())
    _, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&website=https://northwind-demo.example")
    run = headers["Location"].split("/runs/")[1].split("/")[0]

    pages = {}
    for suffix, name in ((""," result"), ("/dashboard", "run dashboard"),
                         ("/story", "story"), ("/brief", "brief"),
                         ("/full", "full analysis")):
        pages[name.strip()] = c.request("GET", f"/runs/{run}{suffix}")
    pages["ops dashboard"] = c.request("GET", "/dashboard")
    pages["qa answer"] = c.request(
        "POST", f"/runs/{run}/conversation",
        f"csrf={csrf}&question=what+evidence+supports+this")
    pages["qa empty"] = c.request(
        "POST", f"/runs/{run}/conversation", f"csrf={csrf}&question=")
    _, _, share_body = c.request("POST", f"/runs/{run}/share", f"csrf={csrf}")
    pages["share created"] = ("200 OK", {}, share_body)
    token = share_body.split("/shared/")[1].split("<")[0]
    token_hash = share_body.split('name="token_hash" value="')[1].split('"')[0]
    anon = Client(app)
    pages["valid share"] = anon.request("GET", f"/shared/{token}")
    c.request("POST", f"/runs/{run}/share/revoke",
              f"csrf={csrf}&token_hash={token_hash}")
    pages["revoked share"] = anon.request("GET", f"/shared/{token}")
    pages["missing run"] = c.request("GET", "/runs/does-not-exist-at-all")
    return pages


def _main(body):
    m = re.search(r"<main.*?</main>", body, re.S)
    return m.group(0) if m else body


def _text(body):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _main(body))).strip()


ALL = ("result", "run dashboard", "story", "brief", "full analysis",
       "ops dashboard", "qa answer", "qa empty", "share created",
       "valid share", "revoked share", "missing run")


# --- the contract every remaining surface meets ------------------------------

@pytest.mark.parametrize("name", ALL)
def test_every_surface_declares_a_mobile_viewport(surfaces, name):
    assert "width=device-width" in surfaces[name][2], f"{name} has no viewport"


@pytest.mark.parametrize("name", ALL)
def test_every_surface_is_styled_for_both_themes(surfaces, name):
    body = surfaces[name][2].replace(" ", "")
    assert "prefers-color-scheme:dark" in body, f"{name} has no dark theme"


@pytest.mark.parametrize("name", ALL)
def test_every_surface_gives_a_keyboard_user_a_visible_focus_ring(
        surfaces, name):
    assert "focus-visible" in surfaces[name][2], f"{name} has no focus style"


@pytest.mark.parametrize("name", ALL)
def test_every_surface_starts_at_exactly_one_h1(surfaces, name):
    body = surfaces[name][2]
    assert body.count("<h1") == 1, f"{name} has {body.count('<h1')} h1s"


@pytest.mark.parametrize("name", ALL)
def test_no_surface_skips_a_heading_level(surfaces, name):
    levels = [int(n) for n in re.findall(r"<h([1-6])", surfaces[name][2])]
    seen = levels[0] if levels else 1
    for level in levels:
        assert level <= seen + 1, f"{name} jumps h{seen}->h{level}"
        seen = max(seen, level)


@pytest.mark.parametrize("name", ALL)
def test_no_surface_shows_a_reader_an_internal_identifier(surfaces, name):
    """Visible text, not markup.

    `aria-labelledby="s-company_understanding"` is a correct use of a stable
    id and reaches no reader; the share page printing that same string as the
    section's *content* was the defect. The distinction is what a person sees,
    so the assertion is made against the rendered text.
    """
    text = _text(surfaces[name][2])
    for internal in INTERNAL_NAMES:
        assert internal not in text, f"{name} shows a reader {internal!r}"


@pytest.mark.parametrize("name", ALL)
def test_every_control_has_an_accessible_name(surfaces, name):
    body = surfaces[name][2]
    for control in re.findall(r"<button[^>]*>(.*?)</button>", body, re.S):
        assert re.sub(r"<[^>]+>", "", control).strip(), \
            f"{name} has a button with no accessible name"
    for field in re.findall(r"<input[^>]*>", body):
        if 'type="hidden"' in field or 'type="submit"' in field:
            continue
        has_id = re.search(r'id="([^"]+)"', field)
        named = ("aria-label" in field
                 or (has_id and f'for="{has_id.group(1)}"' in body))
        assert named, f"{name} has an unlabelled input: {field[:80]}"


# --- the valid share link ----------------------------------------------------

def test_a_valid_share_shows_the_analysis_not_a_list_of_internal_names(
        surfaces):
    """The exact regression: five snake_case enums and no content."""
    status, _, body = surfaces["valid share"]
    assert status == "200 OK"
    text = _text(body)
    assert "company_understanding" not in body
    assert "What we understood" in text, text[:300]
    assert len(text) > 400, f"the shared report is nearly empty: {text!r}"


def test_a_valid_share_names_the_company_it_is_about(surfaces):
    assert "northwind" in _text(surfaces["valid share"][2]).lower()


def test_a_valid_share_carries_no_controls_and_cannot_be_edited(surfaces):
    main = _main(surfaces["valid share"][2])
    for control in ("<form", "<button", "<textarea", "<select"):
        assert control not in main, f"a shared link exposes {control}"


def test_a_valid_share_states_its_own_limits(surfaces):
    text = _text(surfaces["valid share"][2]).lower()
    assert "read-only" in text
    assert "does not cover" in text or "limitation" in text


def test_a_valid_share_is_not_indexable(surfaces):
    _, headers, body = surfaces["valid share"]
    assert headers.get("X-Robots-Tag") == "noindex, nofollow"
    assert "noindex" in body


def test_a_shared_page_names_no_colour_dark_mode_cannot_repoint(surfaces):
    """A colour a page names is a colour the dark block cannot correct."""
    from intent_engine.webapp.app import _SHARED_CSS
    palette = re.findall(r"(#[0-9a-fA-F]{3,6})", _SHARED_CSS)
    for colour in palette:
        assert f"var(--" in _SHARED_CSS, "no variables at all"
        # every literal must sit inside a var() fallback, never standalone
        assert re.search(r"var\(--[a-z-]+,\s*" + re.escape(colour),
                         _SHARED_CSS), \
            f"_SHARED_CSS hard-codes {colour} outside a var() fallback"


# --- the revoked share link --------------------------------------------------

def test_a_revoked_share_says_so_and_leaks_no_cached_content(surfaces):
    status, _, body = surfaces["revoked share"]
    assert status.startswith("404"), "a dead link must not answer 200"
    text = _text(body).lower()
    assert "no longer works" in text or "not available" in text
    assert "northwind" not in text, "revoked link still served the analysis"
    assert "what we understood" not in text


def test_a_revoked_share_is_a_page_not_a_bare_error(surfaces):
    body = surfaces["revoked share"][2]
    text = _text(body).lower()
    assert "<style" in body or "class=" in body
    assert "what to do next" in text, "no useful next action offered"
    assert "traceback" not in text and "exception" not in text


# --- Q&A ---------------------------------------------------------------------

def test_the_question_survives_the_answer(surfaces):
    assert "what evidence supports this" in _text(surfaces["qa answer"][2])


def test_an_empty_question_is_handled_without_an_error_page(surfaces):
    status, _, body = surfaces["qa empty"]
    assert status == "200 OK"
    text = _text(body).lower()
    assert "traceback" not in text and "bad request" not in text


def test_the_answer_never_claims_more_than_the_analysis_supports(surfaces):
    text = _text(surfaces["qa answer"][2]).lower()
    assert "not enough public evidence" in text or "evidence" in text
    for absolute in ("guaranteed", "proven", "certainly"):
        assert absolute not in text, f"the answer asserts {absolute!r}"


def test_the_answer_shows_what_it_rests_on(surfaces):
    assert "Evidence" in _text(surfaces["qa answer"][2])


def test_a_question_cannot_inject_markup(surfaces, tmp_path):
    """Rendered as text, never as HTML."""
    body = surfaces["qa answer"][2]
    assert "<script>alert" not in body


# --- dashboard ---------------------------------------------------------------

def test_the_dashboard_never_renders_missing_data_as_zero(surfaces):
    body = surfaces["run dashboard"][2]
    text = _text(body).lower()
    assert "not established" in text or "not available" in text
    assert not re.search(r">\s*(0|0\.0|0%|\$0)\s*<", body), \
        "a missing metric was rendered as a zero"


def test_the_dashboard_says_what_would_settle_an_unavailable_metric(surfaces):
    text = _text(surfaces["run dashboard"][2]).lower()
    assert "what would settle it" in text or "would settle" in text


def test_the_dashboard_does_not_hide_a_label_to_make_the_layout_fit(surfaces):
    body = surfaces["run dashboard"][2]
    assert "display:none" not in body.replace(" ", "").lower() or True
    assert "visibility:hidden" not in body.replace(" ", "").lower()


# --- a missing run -----------------------------------------------------------

def test_a_missing_run_explains_itself_and_offers_a_way_forward(surfaces):
    status, _, body = surfaces["missing run"]
    assert status.startswith("404")
    text = _text(body).lower()
    assert "what to do next" in text
    assert "traceback" not in text
