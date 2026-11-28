"""The exposure map connects a measured variable to a relationship the
company's OWN material states -- never a class default, never a size."""
import inspect

from intent_engine.executive import exposure_map as XM

USAGE = ("Pinecone is priced pay-as-you-go: usage-based billing means you pay per query "
         "and per gigabyte stored, with no minimum commitment for serverless indexes. " * 3)
CONSULT = ("Improving is a consulting firm whose consultants and engineers deliver work "
           "from nearshore delivery centers across the Americas for enterprise clients. " * 3)


def test_an_exposure_needs_the_companys_own_words_and_quotes_them():
    m = XM.build([USAGE], business_model_class="SUBSCRIPTION_SOFTWARE")
    x = next(e for e in m["exposures"] if e["key"] == "usage_priced_compute")
    assert len(x["phrases"]) >= 2 and x["evidence"] and "usage-based" in x["evidence"][0]
    assert x["measurement"] == XM.UNMEASURED          # no cloud-spend series exists here


def test_measured_only_when_the_run_measures_that_channel():
    a = XM.build([CONSULT], business_model_class="PEOPLE_OR_ROUTE_BASED_SERVICES")
    b = XM.build([CONSULT], business_model_class="PEOPLE_OR_ROUTE_BASED_SERVICES",
                 measured_channels=("US:LABOR",))
    la = next(e for e in a["exposures"] if e["key"] == "delivery_labour")
    lb = next(e for e in b["exposures"] if e["key"] == "delivery_labour")
    assert la["measurement"] == XM.UNMEASURED and lb["measurement"] == XM.MEASURED


def test_one_use_case_post_is_not_a_customer_domain():
    blog = ("Our guide shows how a supply chain team can use the database to map "
            "suppliers and procurement risk. " * 3)
    m = XM.build([blog], business_model_class="SUBSCRIPTION_SOFTWARE")
    assert "customer_procurement_budgets" not in [e["key"] for e in m["exposures"]]


def test_labour_exposure_is_not_read_off_a_software_careers_page():
    careers = "We are hiring engineers and consultants to join our talent community. " * 5
    m = XM.build([careers], business_model_class="SUBSCRIPTION_SOFTWARE")
    assert "delivery_labour" not in [e["key"] for e in m["exposures"]]


def test_nothing_is_estimated():
    m = XM.build([USAGE, CONSULT], business_model_class="SUBSCRIPTION_SOFTWARE")
    flat = repr(m).lower()
    for word in ("coefficient", "elasticity", "probability", "%"):
        assert word not in flat


class _Store:
    def __init__(self, docs):
        self.docs = docs

    def retrieved(self, run_id):
        return self.docs


def _stub(docs, cls="PEOPLE_OR_ROUTE_BASED_SERVICES", ids=("US:LABOR",)):
    from types import SimpleNamespace as NS
    from intent_engine.webapp.app import WebApp
    stub = NS(ci=NS(store=_Store(docs)), _EXPOSURE_OWN_CLASSES=WebApp._EXPOSURE_OWN_CLASSES,
              _canonical_selection=lambda run_id, name="", domain="": NS(profile=NS(business_model_class=cls)),
              _founder_economy=lambda run_id: {"ids": list(ids)})
    return lambda name: WebApp._exposure_section(stub, "r1", name=name, domain="x.example")


def test_the_section_renders_the_companys_own_sentence_and_the_measured_channel():
    render = _stub([{"source_class": "company_owned", "text_content": CONSULT},
                    {"source_class": "independent_reporting", "text_content": USAGE}])
    html = render("Improving")
    assert "How economic conditions reach Improving" in html
    assert "nearshore delivery centers" in html and "measured by this engine" in html
    assert "usage-based" not in html          # a third party's text is never the company's exposure


def test_no_evidence_says_so_without_claiming_insulation():
    html = _stub([{"source_class": "company_owned", "text_content": "Welcome. " * 50}])("Acme")
    assert 'data-exposure-state="NO_EXPOSURE_EVIDENCED"' in html and "not a finding" in html


def test_the_xray_and_full_analysis_render_it():
    from intent_engine.webapp.app import WebApp
    code = lambda f: "\n".join(l for l in inspect.getsource(f).split("\n") if not l.strip().startswith("#"))
    x = code(WebApp._run_xray)
    assert "exposure = self._exposure_section(run_id" in x
    assert 'body.replace("</main>", exposure + "</main>", 1)' in x
    assert "{self._exposure_section(run_id" in code(WebApp._strategic_run_page)
