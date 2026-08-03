"""A bounded result must still be about the company the founder asked for.

MEASURED on the deployed preview (2026-08-02, commit bbd8588), running Tesla
end to end as a guest:

  /runs/<id>            ->  "Limited analysis of Tesla"      (names it)
  /runs/<id>/dashboard  ->  "This company — intelligence"    (does not)

Tesla's own site refused automated access (HTTP 401/403 on www.tesla.com and
17 more), leaving one usable SEC exhibit -- so no strategic report was built.
That is the LIMITED path, and it is the path these tests must drive.

The cause was a name-resolution chain that consulted the identity record, the
report and the result, but not the run's own metadata -- the one source that
is always set, because it is what the founder typed. On a limited run the
first three are empty, so every company collapsed onto the placeholder and
three unrelated companies rendered the same page.

WHY THIS FILE DRIVES A THIN TRANSPORT: an earlier version of this gate used
the ordinary fixture transport, which retrieves enough to build a report.
`report["company_name"]` then resolved the name at link three and the broken
link was never reached -- the gate passed with the fix reverted, which is to
say it proved nothing. `_one_thin_filing` reproduces the live condition: every
page refuses automation except a single procedural filing.
"""
import email
import re
import urllib.error

import pytest

from tests.test_insufficient_evidence_page import Client
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

LAYERS = ("", "/dashboard", "/story", "/brief")

# Three companies whose evidence DIFFERS, because that is the real case the
# gate exists for. Tesla and NVIDIA did not merely have different names on the
# preview -- they had different filings and different page counts (the limited
# page rendered 250 words against 329) and STILL produced byte-identical
# dashboards. A fixture where all three retrieve the same thing could only
# ever prove that the name was substituted, which is the weaker claim.
PROFILES = {
    "Vantorix": ("Form 6-K (2026-05-14)", 1),
    "Quellmar": ("Annual report on Form 20-F (2026-03-02)", 2),
    "Brimsdale": ("Notice of annual general meeting (2026-06-30)", 1),
}
COMPANIES = tuple(PROFILES)


def _thin_transport(company):
    """Everything refuses automation except this company's own filing(s).

    Reproduces the live Tesla condition -- www.tesla.com returned 401/403 on
    every page and only SEC exhibits could be read -- while giving each
    company a distinguishable footing.
    """
    title, count = PROFILES[company]

    def transport(url, timeout):
        readable = [f"/about"] + [f"/filing-{i}" for i in range(1, count)]
        if any(url.rstrip("/").endswith(p) for p in readable):
            body = (f"<html><head><title>{title}</title></head><body>"
                    f"<p>Report furnished pursuant to the rules of the "
                    f"Exchange Act. This report is incorporated by reference "
                    f"into the registration statements of the registrant."
                    f"</p></body></html>").encode()
            return (200, {"content-type": "text/html"}, body, False)
        raise urllib.error.HTTPError(url, 403, "forbidden",
                                     email.message_from_string(""), None)
    return transport


def _limited_run(tmp_path, company):
    """A finished run with no strategic report -- the live bounded case."""
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_thin_transport(company), resolver=False)
    client = Client(app)
    client.request("POST", "/demo")
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={company}"
        f"&website=https://{company.lower()}.example")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    # The premise of this file: if a report got built, the thin transport
    # stopped reproducing the live condition and every assertion below is
    # testing the wrong path.
    assert app._results[run_id]["strategic_report"] is None, (
        "transport retrieved too much -- this is no longer the limited path")
    return client, run_id


def _text(html):
    html = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


@pytest.mark.parametrize("layer", LAYERS)
def test_unrelated_companies_never_render_identical_founder_text(tmp_path,
                                                                 layer):
    """The release gate. Identical text across unrelated companies means the
    page is about no one."""
    rendered = {}
    for company in COMPANIES:
        client, run_id = _limited_run(tmp_path / company, company)
        _, _, html = client.request("GET", f"/runs/{run_id}{layer}")
        rendered[company] = _text(html)
    bodies = list(rendered.values())
    assert len(set(bodies)) == len(bodies), (
        f"{layer or '/(brief)'} rendered identical text for unrelated "
        f"companies: {sorted(rendered)}")


@pytest.mark.parametrize("layer", LAYERS)
def test_bounded_pages_differ_by_more_than_the_company_name(tmp_path, layer):
    """MATERIALLY identical is the thing being gated, not textually identical.

    Substituting the name into a constant makes two pages differ by one word
    while still telling the founder nothing about their company -- it would
    satisfy a naive inequality check and leave the defect in place. So the
    name is masked out and what remains must still differ.
    """
    stripped = {}
    for company in COMPANIES:
        client, run_id = _limited_run(tmp_path / company, company)
        _, _, html = client.request("GET", f"/runs/{run_id}{layer}")
        body = _text(html).replace(company, "<NAME>")
        stripped[company] = body.replace(company.lower(), "<name>")
    bodies = list(stripped.values())
    assert len(set(bodies)) == len(bodies), (
        f"{layer or '/(brief)'} differs only by the company name -- the page "
        f"is a constant with a name substituted into it")


@pytest.mark.parametrize("layer", LAYERS)
def test_every_founder_layer_names_the_company(tmp_path, layer):
    """"This company" is what the identical pages were headed. A bounded
    result may say little, but it must say who it is about."""
    client, run_id = _limited_run(tmp_path, "Vantorix")
    _, _, html = client.request("GET", f"/runs/{run_id}{layer}")
    body = _text(html)
    assert "Vantorix" in body, f"{layer or '/(brief)'} never names the company"
    assert "This company —" not in body, "placeholder heading survived"
