"""Discovery and measurement ask the same question -- "is this text about the
company?" -- and must use one definition of the names it goes by.

MEASURED 2026-11-28 (prospect-98 w6): discovery verified three articles about
Wiz; the independence count then called all three "never names the company",
because measurement built its terms from "Wiz, Inc." and drops a bare
three-letter name as a collision risk.
"""
import inspect

from intent_engine.company_ingestion import independence as IND
from intent_engine.company_ingestion.entities import press_names

TEXT = ("Wiz said on Tuesday that its cloud security platform now integrates with the "
        "agent framework, giving customers runtime protection. Wiz expects the release to "
        "reach most customers this quarter, the company said in a statement.")


def test_a_curated_domain_yields_its_common_name_and_never_a_short_word():
    assert press_names("https://wiz.io")[0] == "Wiz"
    name, aliases = press_names("https://safe.security")
    assert name == "SAFE" and "safe" not in [a.lower() for a in aliases]
    assert press_names("https://unregistered.example") == ("", ())


def test_the_count_recognises_a_short_name_once_identity_is_settled():
    doc = {"final_url": "https://siliconangle.com/2026/11/19/wiz-x", "source_class": "independent_reporting",
           "text_content": TEXT}
    bare = IND.assess([doc], subject_domain="wiz.io", subject_name="Wiz, Inc.")
    pn, pa = press_names("https://wiz.io")
    named = IND.assess([doc], subject_domain="wiz.io", subject_name="Wiz, Inc.", aliases=(pn, *pa))
    assert not any(r["independence_bearing"] for r in bare["rows"])
    assert any(r["independence_bearing"] for r in named["rows"])


def test_discovery_and_the_dossier_both_call_the_one_definition():
    from intent_engine.company_ingestion import service as SVC
    from intent_engine.webapp.app import WebApp
    code = lambda f: "\n".join(l for l in inspect.getsource(f).split("\n") if not l.strip().startswith("#"))
    svc = next(v for v in vars(SVC).values() if isinstance(v, type) and hasattr(v, "_independent_reporting_candidates"))
    assert "press_names(" in code(svc._independent_reporting_candidates)
    pub = code(WebApp._publish_demo_dossier)
    assert "_press_names(" in pub and pub.count("aliases=_press") >= 2
