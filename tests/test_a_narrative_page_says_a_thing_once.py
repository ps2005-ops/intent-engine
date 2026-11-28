"""A narrative page says a thing once (prospect-98 w4: 52 of 70 companies
repeated prose on a page, from a dozen producers)."""
import inspect

from intent_engine.webapp import app as A

S1 = "The reading below is selected from the published record alone, so it does not use the business model."
S2 = "Companies that sell software and deliver it as a service genuinely are both, and picking one decides."
NEW = "This sentence is new on the page and is long enough to count as a substantive sentence."


def _page(body):
    return f"<!doctype html><html><head><style>p{{}}</style></head><body><main>{body}</main></body></html>"


def test_a_repeated_paragraph_and_list_item_are_dropped():
    out = A.say_once(_page(f"<p>{S1}</p><ul><li>{S1}</li></ul><p>{S2}</p><p>{S2}</p>"))
    assert out.count(S1) == 1 and out.count(S2) == 1


def test_a_plain_paragraph_keeps_its_new_sentence():
    out = A.say_once(_page(f"<p>{S1}</p><p>{NEW} {S1}</p>"))
    assert NEW in out and out.count(S1) == 1


def test_markup_is_never_cut_and_short_furniture_repeats():
    linked = f'<p>{S1} See <a href="/x">the source</a>.</p>'
    out = A.say_once(_page(f"<p>{S1}</p>{linked}<p>Independent voice: no</p><p>Independent voice: no</p>"))
    assert 'href="/x"' in out and out.count("Independent voice: no") == 2


def test_scripts_and_styles_are_untouched():
    out = A.say_once(_page(f"<p>{S1}</p><script>var s = '{S1}';</script>"))
    assert out.count(S1) == 2


def test_the_report_wrapper_applies_it_and_spares_the_evidence_page():
    src = "\n".join(l for l in inspect.getsource(A.WebApp._with_ask).split("\n")
                    if not l.strip().startswith("#"))
    assert "self._said_once(response)" in src
    assert 'data-search-state=' in src
