"""A publisher's hyperlink to the company's verified domain anchors a short,
ambiguous name. MEASURED 2026-11-28 (prospect-98 w4): Wiz read as having no
outside coverage because the press never prints "wiz.io" in running text."""
from intent_engine.company_ingestion import independent_reporting as IR


def test_a_link_to_the_domain_anchors():
    assert IR.links_to_domain('<p>by <a href="https://www.wiz.io/blog/x">Wiz</a></p>', "wiz.io")
    assert IR.links_to_domain("<a href='//wiz.io'>Wiz</a>", "wiz.io")


def test_a_namesake_or_lookalike_domain_does_not():
    assert not IR.links_to_domain('<a href="https://www.wizconnected.com">WiZ</a>', "wiz.io")
    assert not IR.links_to_domain('<a href="https://notwiz.io/">x</a>', "wiz.io")
    assert not IR.links_to_domain('wiz.io mentioned in text only', "wiz.io")


class _Robots:
    def allows(self, url):
        return True


def _verify(body):
    report = {"rejection_reasons": IR._Counter(), "candidates_fetched": 0}
    fetch = lambda url, mimes: {"ok": True, "body": body, "final_url": url}
    got = IR.verify({"url": "https://siliconangle.com/2026/11/19/wiz-story", "publisher": "SiliconANGLE"},
                    company="Wiz", domain="wiz.io", aliases=("Wiz, Inc.",), fetch=fetch,
                    robots=_Robots(), report=report)
    return got, report


_TEXT = ("<p>Wiz said on Tuesday that its cloud security platform now integrates with the agent "
         "framework. Wiz, which Google acquired this year, said customers can scan agents. "
         "Wiz researchers added that the integration covers runtime and posture.</p>")


def test_the_verifier_admits_a_linked_article_and_refuses_an_unlinked_one():
    linked, _ = _verify("<html><body>" + _TEXT.replace("Wiz said", '<a href="https://www.wiz.io/">Wiz</a> said', 1) + "</body></html>")
    unlinked, report = _verify("<html><body>" + _TEXT + "</body></html>")
    assert linked is not None and linked["source_class"] == "independent_reporting"
    assert unlinked is None and report["rejection_reasons"]["AMBIGUOUS_NAME_NO_IDENTITY_ANCHOR"] == 1
