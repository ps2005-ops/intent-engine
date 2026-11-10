"""Text we did not write may not push a phone screen sideways (§17).

MEASURED on Workato at 375px, cohort A, on 1b0d803c: `/full` reported 22px of
horizontal overflow (7px at 390px, none at desktop widths). The cause was a
single evidence quote containing

    HRMarketingITSalesFinanceProductEngineering.

-- forty-four characters with no space, which is Workato's own navigation menu
scraped without separators. `<q>` had no wrapping rule, so the token could not
break and the quote ran 22px past the viewport.

This is not a Workato problem. Every one of the forty draws its quotes from
pages this product does not control, and a menu rendered without separators is
an ordinary thing for a site to do. The rule already existed for the two other
places untrusted text lands -- inline `<code>` on the retrieval-failure page,
and long URLs -- and a quote is the third and the most common.
"""
from __future__ import annotations

import re



def _chrome_css() -> str:
    """The module's own source, read whole.

    A first version sliced from the FIRST "<style>" and measured a different
    stylesheet entirely -- app.py emits several. Reading the module is the
    honest way to ask "does this rule ship", and it cannot silently point at
    the wrong block.
    """
    import inspect

    import intent_engine.webapp.app as A
    return inspect.getsource(A)


def test_a_quote_wraps_a_token_it_cannot_break():
    css = _chrome_css()
    rule = re.search(r"q,blockquote\{([^}]*)\}", css)
    assert rule, ("<q> and <blockquote> carry text this product did not write "
                  "and have no wrapping rule, so one unbreakable token widens "
                  "the page")
    body = rule.group(1)
    assert "overflow-wrap:anywhere" in body, body
    assert "word-break:break-word" in body, body


def test_the_rule_still_covers_code_and_links():
    """POSITIVE CONTROL. The quote rule must be ADDED to the existing ones,
    not substituted for them: the retrieval-failure page's inline <code> and
    long URLs were the first two surfaces this defect appeared on."""
    css = _chrome_css()
    assert re.search(r"code,\.src,\.prov\{[^}]*overflow-wrap:anywhere", css)
    assert re.search(r"a\[href\]\{[^}]*overflow-wrap:anywhere", css)


def test_ordinary_prose_is_not_broken_mid_word():
    """`anywhere` breaks a token ONLY when it cannot fit, which is why it is
    used instead of `break-all`. A rule that hyphenated ordinary sentences
    would trade an overflow for an unreadable page."""
    css = _chrome_css()
    assert "break-all" not in css, (
        "break-all breaks every long word, not only the ones that do not fit")
