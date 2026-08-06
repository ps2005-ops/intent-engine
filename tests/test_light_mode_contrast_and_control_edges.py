"""Light mode is a shipped theme, not the absence of dark mode.

The landing sheet was audited once, for dark, and the audit re-pointed the
variables without re-measuring the light literals they were extracted from.
Three of them shipped under the floor for a year of commits because every
check we had either looked at dark, or looked at a hard-coded copy of the
palette rather than the palette itself.

So these tests read the tokens out of `_LANDING_CSS` at runtime. A dict of
colours copied into a test file cannot fail when production drifts away from
it — it can only fail when someone remembers to update both, which is exactly
the seam that let this through.
"""
import re

import pytest

from intent_engine.founder_intelligence.presentation import _LANDING_CSS
from intent_engine.webapp.app import _A11Y_CSS

_DARK_AT = "@media(prefers-color-scheme:dark)"


def _lin(v):
    v /= 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _lum(hex_colour):
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    x, y = _lum(a), _lum(b)
    hi, lo = max(x, y), min(x, y)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(compact_sheet, *, dark):
    """The `--l-*` custom properties production actually declares.

    Everything before the dark media query is the light theme; everything
    inside it is the re-pointed dark theme.
    """
    head, _, tail = compact_sheet.partition(_DARK_AT)
    region = tail if dark else head
    return dict(re.findall(r"(--l-[a-z-]+):(#[0-9a-fA-F]{3,6})", region))


_COMPACT = _LANDING_CSS.replace(" ", "").replace("\n", "")
_LIGHT_TOKENS = _tokens(_COMPACT, dark=False)
_DARK_TOKENS = _tokens(_COMPACT, dark=True)

# The canvas each theme resolves to. Light is the UA default: `body` sets no
# background of its own, which is fine — but it means a probe that treats an
# unset background as black will invert every ratio it computes, and one did.
_LIGHT_CANVAS = "#ffffff"
_DARK_CANVAS = "#0f141c"

# Which floor applies to each token, and what it sits on. `--l-place` is the
# placeholder *inside* the field, so it is measured against the field fill,
# not the page.
_TEXT_TOKENS = ["--l-ink", "--l-muted", "--l-lede", "--l-label",
                "--l-faint", "--l-head"]


def test_the_light_palette_is_actually_parsed_not_assumed():
    """If this breaks, every other test in the file is measuring nothing."""
    assert _LIGHT_TOKENS, "no light tokens parsed out of _LANDING_CSS"
    assert _DARK_TOKENS, "no dark tokens parsed out of _LANDING_CSS"
    for name in _TEXT_TOKENS + ["--l-place", "--l-field-line", "--l-field-bg"]:
        assert name in _LIGHT_TOKENS, f"{name} vanished from the light theme"
        assert name in _DARK_TOKENS, f"{name} vanished from the dark theme"


@pytest.mark.parametrize("token", _TEXT_TOKENS)
def test_light_body_text_meets_wcag_aa(token):
    """#77778f on white is 4.36:1 — the section labels ("What comes back",
    "Where it comes from") at 12.8px/600, which is normal text, not large."""
    ratio = contrast(_LIGHT_TOKENS[token], _LIGHT_CANVAS)
    assert ratio >= 4.5, f"{token} is {ratio:.2f}:1 on the light canvas"


@pytest.mark.parametrize("token", _TEXT_TOKENS)
def test_dark_body_text_meets_wcag_aa(token):
    ratio = contrast(_DARK_TOKENS[token], _DARK_CANVAS)
    assert ratio >= 4.5, f"{token} is {ratio:.2f}:1 on the dark canvas"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_placeholder_is_readable_against_the_field_it_sits_in(dark):
    """#9a9ab0 on #fff is 2.75:1. Measuring it against the page instead of the
    field would have been the wrong surface even if it had passed."""
    toks = _DARK_TOKENS if dark else _LIGHT_TOKENS
    ratio = contrast(toks["--l-place"], toks["--l-field-bg"])
    assert ratio >= 4.5, f"placeholder is {ratio:.2f}:1 inside the field"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_field_border_is_visible_in_both_themes(dark):
    """WCAG 1.4.11. Dark got this fix at a5e1322 (#3a4454 -> #606e88); light
    kept #d5d5e2 at 1.45:1 — the box around the input you are told to type in.
    """
    toks = _DARK_TOKENS if dark else _LIGHT_TOKENS
    canvas = _DARK_CANVAS if dark else _LIGHT_CANVAS
    line, field = toks["--l-field-line"], toks["--l-field-bg"]
    assert contrast(line, canvas) >= 3.0, \
        f"field border is {contrast(line, canvas):.2f}:1 on the page"
    assert contrast(line, field) >= 3.0, \
        f"field border is {contrast(line, field):.2f}:1 against its own fill"


def test_the_light_theme_was_not_fixed_by_flattening_it_to_greyscale():
    """The page has a deliberate cool cast. Darkening a token is the fix;
    turning it neutral is a different design, silently applied."""
    for token in ("--l-head", "--l-place", "--l-field-line"):
        h = _LIGHT_TOKENS[token].lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        assert b > r, f"{token} lost its cool cast: #{h}"


# --- the seam: a colour with no width -------------------------------------
def _dark_floor():
    compact = _A11Y_CSS.replace(" ", "").replace("\n", "")
    return compact.partition(_DARK_AT)[2]


def test_the_dark_control_rule_sets_a_border_width_not_only_a_colour():
    """`border-color:#606e88` painted nothing on any <button>, because
    `presentation._BASE_CSS` ships a global `button{border:0}` that zeroes the
    width. The colour was declared, correct, tested for — and invisible.

    A rule that names a colour for a boundary must also give that boundary a
    width, or it is describing something the reader never sees.
    """
    dark = _dark_floor()
    assert "border-color:#606e88" in dark
    assert "border-width:1px" in dark, \
        "the dark control border has a colour but no width to draw it with"
    assert "border-style:solid" in dark


def test_checkboxes_keep_their_native_boundary():
    """`color-scheme:dark` already gives them one. An author border makes the
    engine drop native rendering, which costs the tick as well."""
    dark = _dark_floor()
    # `_dark_floor` has had every space stripped, so the selector is matched
    # in that same compacted form.
    assert ":rootinput:not([type=checkbox]):not([type=radio])" in dark


def test_text_styled_buttons_do_not_become_flat_boxes_in_dark():
    """`nav button` and `button.linkish` are transparent on purpose so they
    read as links. The blanket dark fill outranked them and made each a
    #1b2230 rectangle at 1.16:1 against the page — not a link, and not a
    button you can see."""
    dark = _dark_floor()
    assert ":rootnavbutton" in dark
    assert ":rootbutton.linkish" in dark
    assert "background:transparent" in dark


def test_the_shared_shell_field_border_is_visible_too():
    """Fixing one stylesheet says nothing about the other.

    The landing sheet's border was corrected first. `_BASE_CSS` — the shell
    every OTHER surface uses, so login, the follow-up question box on a
    result, and the add-a-source form — still carried #cfd0dc at 1.53:1, and
    it took a live sweep of a deployed result page to find it. Parsed out of
    the sheet for the same reason as everything else here.
    """
    from intent_engine.founder_intelligence.presentation import _BASE_CSS
    compact = _BASE_CSS.replace(" ", "").replace("\n", "")
    # the shared field rule, up to the end of its declaration block
    block = compact.split("input:not([type]),textarea,select{", 1)[1]
    block = block.split("}", 1)[0]
    found = re.search(r"border:1pxsolid(#[0-9a-fA-F]{3,6})", block)
    assert found, f"shared field rule declares no border colour: {block[:120]}"
    colour = found.group(1)
    ratio = contrast(colour, _LIGHT_CANVAS)
    assert ratio >= 3.0, \
        f"shared field border {colour} is {ratio:.2f}:1 on the white field"


def test_the_shared_shell_focus_ring_is_visible():
    """The ring is the only thing telling a keyboard user where they are."""
    from intent_engine.founder_intelligence.presentation import _BASE_CSS
    compact = _BASE_CSS.replace(" ", "").replace("\n", "")
    found = re.search(r"outline:2pxsolid(#[0-9a-fA-F]{3,6})", compact)
    assert found, "shared shell declares no focus outline colour"
    ratio = contrast(found.group(1), _LIGHT_CANVAS)
    assert ratio >= 3.0, f"focus ring is {ratio:.2f}:1"


def test_a_flat_dark_button_fill_would_not_pass_on_its_own():
    """Why the border is load-bearing rather than decorative: the fill the
    dark floor gives a button is nearly the page colour."""
    assert contrast("#1b2230", _DARK_CANVAS) < 3.0
    assert contrast("#606e88", _DARK_CANVAS) >= 3.0
