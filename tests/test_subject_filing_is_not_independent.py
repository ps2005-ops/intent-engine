"""A company's own 10-K does not corroborate the company.

THE MEASURED DEFECT. On the deployed preview at `4a90ad2`, Cloudflare's
dossier published:

    independent_origins:  ["sec.gov/filer/1477333", "sec.gov/filer/1816554"]
    corroboration_state:  INDEPENDENTLY_CORROBORATED
    plain_statement:      "11 document(s) support this view, representing
                           two independent origin(s)."

CIK 1477333 is Cloudflare, Inc. itself. The product was telling a buyer that
the subject's own annual report independently corroborated the subject.

`_vantage` checked the VENUE before the AUTHOR: a 10-K is hosted by the SEC,
so `_is_primary_filing` matched and the row became
REGULATOR_OR_PRIMARY_FILING, which is independence-bearing. The module's own
rule says the opposite -- "a company self-report is the subject speaking about
itself, so it can never corroborate itself" -- and `third_party_filings`
already refuses the subject's filings at DISCOVERY time for exactly this
reason. The measurement stage was simply never given a subject to compare
against.

THE NEGATIVE CONTROLS ARE THE POINT. Demoting the subject's filing is only
correct if a DIFFERENT registrant's filing still counts. An over-broad fix
here deletes real independent observations, which is the failure this module
exists to prevent, pointing the other way.
"""
from intent_engine.company_ingestion.independence import (
    COMPANY_SELF_REPORT, INDEPENDENT_EXTERNAL_SOURCE, INDEPENDENCE_BEARING,
    INDEPENDENTLY_CORROBORATED, PARTIALLY_INDEPENDENT,
    REGULATOR_OR_PRIMARY_FILING, assess, classify, subject_authored,
)

SUBJECT_CIK = "0001477333"          # Cloudflare, Inc.
OTHER_CIK = "0001816554"            # a different registrant
SUBJECT_DOMAIN = "cloudflare.com"


def _edgar(cik, name="doc"):
    return (f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/"
            f"000123/{name}.htm")


def _doc(url, source_class, words, digest):
    # THE TEXT MATTERS NOW. Independence says whose voice this is; relevance
    # says whether the voice discussed Cloudflare. A fixture whose body never
    # names the company is correctly IRRELEVANT and would not be counted, so
    # these bodies say something about the subject on purpose.
    body = (f"{words}. We compete with Cloudflare for edge security customers, "
            f"and pricing pressure from Cloudflare affected our renewal "
            f"revenue this year. ") * 8
    return {"final_url": url, "source_class": source_class,
            "filing": "sec.gov" in url, "content_hash": digest,
            "text_content": body}


SUBJECT_SITE = _doc(f"https://www.{SUBJECT_DOMAIN}/pricing",
                    "company_owned", "pricing enterprise plans teams", "a")
SUBJECT_FILING = _doc(_edgar(SUBJECT_CIK, "net-10k"), "investor_material",
                      "annual report risk factors network", "b")
OTHER_FILING = _doc(_edgar(OTHER_CIK, "evk-10k"), "competitor",
                    "unrelated holdings business description", "c")

SUBJECT = dict(subject_filers=(SUBJECT_CIK,), subject_domain=SUBJECT_DOMAIN)


# --- the defect --------------------------------------------------------------

def test_the_subjects_own_filing_is_a_self_report():
    rows = {r["origin_family"]: r for r in
            classify([SUBJECT_SITE, SUBJECT_FILING, OTHER_FILING], **SUBJECT)}
    own = rows[f"sec.gov/filer/{SUBJECT_CIK.lstrip('0')}"]
    assert own["lineage"] == COMPANY_SELF_REPORT
    assert own["independence_bearing"] is False


def test_the_subjects_own_filing_no_longer_corroborates_it():
    """Two rows, both written by the subject. That is one voice, not two."""
    out = assess([SUBJECT_SITE, SUBJECT_FILING], **SUBJECT)
    assert out["independent_evidence_count"] == 0
    assert out["corroboration_state"] != INDEPENDENTLY_CORROBORATED


def test_the_live_cloudflare_shape_drops_to_partially_independent():
    """The exact live combination: the company's site, the company's own
    10-K, and one genuine third-party filing. One outside vantage point."""
    docs = [SUBJECT_SITE, SUBJECT_FILING, OTHER_FILING]
    assert assess(docs)["corroboration_state"] == INDEPENDENTLY_CORROBORATED
    out = assess(docs, **SUBJECT)
    assert out["corroboration_state"] == PARTIALLY_INDEPENDENT
    assert out["independent_evidence_count"] == 1


# --- the negative controls ---------------------------------------------------

def test_a_different_registrants_filing_is_still_independent():
    """THE CONTROL THAT MATTERS. If this breaks, the fix has deleted real
    independent evidence rather than removed a false claim."""
    rows = {r["origin_family"]: r for r in
            classify([SUBJECT_FILING, OTHER_FILING], **SUBJECT)}
    other = rows[f"sec.gov/filer/{OTHER_CIK.lstrip('0')}"]
    assert other["lineage"] == INDEPENDENT_EXTERNAL_SOURCE
    assert other["independent_voice"] is True
    assert other["independence_bearing"] is True


def test_two_third_party_filings_still_corroborate():
    third = _doc(_edgar("0000320193", "aapl-10k"), "customer_voice",
                 "supplier arrangements and vendor commitments", "d")
    out = assess([SUBJECT_FILING, OTHER_FILING, third], **SUBJECT)
    assert out["corroboration_state"] == INDEPENDENTLY_CORROBORATED
    assert out["independent_evidence_count"] == 2


def test_without_a_subject_the_previous_behaviour_is_unchanged():
    """A caller that cannot say who the subject is gets an unverified count,
    not a silently altered one. Guessing that an unrecognised filer is the
    subject would delete outside observations wholesale."""
    rows = {r["origin_family"]: r for r in
            classify([SUBJECT_FILING, OTHER_FILING])}
    own = rows[f"sec.gov/filer/{SUBJECT_CIK.lstrip('0')}"]
    assert own["lineage"] == REGULATOR_OR_PRIMARY_FILING
    assert own["independence_bearing"] is True


def test_an_unknown_filer_is_not_assumed_to_be_the_subject():
    unknown = _doc(_edgar("0000999999", "x"), "competitor",
                   "some other registrant entirely", "e")
    rows = {r["origin_family"]: r for r in classify([unknown], **SUBJECT)}
    # ITS VOICE is independent -- that is what this test is about. Whether it
    # also COUNTS now depends on relevance, which is a different axis.
    assert rows["sec.gov/filer/999999"]["independent_voice"] is True


# --- identification ----------------------------------------------------------

def test_cik_padding_does_not_defeat_the_match():
    """The manifest writes `0001477333`; the EDGAR path writes `1477333`."""
    for spelling in ("1477333", "0001477333", "  0001477333 "):
        assert subject_authored(SUBJECT_FILING, subject_filers=(spelling,))


def test_a_subdomain_of_the_subject_is_still_the_subject():
    blog = _doc(f"https://blog.{SUBJECT_DOMAIN}/post", "company_owned",
                "product announcement", "f")
    assert subject_authored(blog, subject_domain=SUBJECT_DOMAIN)


def test_a_company_whose_domain_merely_ends_similarly_is_not_the_subject():
    """`notcloudflare.com` is a different company. Substring walls have
    refused real companies here before."""
    other = _doc("https://notcloudflare.com/post", "company_owned",
                 "unrelated", "g")
    assert not subject_authored(other, subject_domain=SUBJECT_DOMAIN)


def test_an_empty_subject_identifies_nothing():
    assert not subject_authored(SUBJECT_FILING, subject_filers=("",),
                                subject_domain="")


def test_self_report_is_never_independence_bearing():
    """The invariant the whole fix rests on, asserted directly rather than
    inferred from the cases above."""
    assert COMPANY_SELF_REPORT not in INDEPENDENCE_BEARING


# --- the transport, which is where the first repair actually failed ----------

def test_an_empty_subject_is_a_no_op_which_is_how_the_first_repair_shipped():
    """THE REGRESSION THIS FILE NOW EXISTS FOR, SECOND TIME.

    The first repair read `meta["cik"]` directly. A run started from a
    WEBSITE carries no CIK -- the ordinary case -- so the filter received
    `("",)`, identified nothing, and the live claim did not change even
    though the deployed build contained the fix and every unit test passed.

    This pins the no-op explicitly, so the fact that an empty subject
    changes nothing is a stated property rather than a silent one.
    """
    docs = [SUBJECT_SITE, SUBJECT_FILING, OTHER_FILING]
    empty = assess(docs, subject_filers=("",), subject_domain="")
    assert empty["corroboration_state"] == INDEPENDENTLY_CORROBORATED
    assert empty["independent_evidence_count"] == 2


def test_a_website_run_still_identifies_the_subject(monkeypatch):
    """PRODUCER -> TRANSPORT -> MEASUREMENT, over the shape production uses.

    `run_meta` for a website entry has a company name and no CIK. The
    service must still produce a subject, by the same fallback filing
    discovery has always used.
    """
    from intent_engine.company_ingestion import service as svc

    resolver = svc.CompanyIngestionService.subject_cik
    meta = {"company_name": "Cloudflare", "domain": SUBJECT_DOMAIN, "cik": ""}

    monkeypatch.setattr(
        "intent_engine.company_ingestion.edgar.resolve_cik",
        lambda name, **kw: {"cik": SUBJECT_CIK} if "cloudflare" in
        str(name).lower() else None)

    class _Svc:
        transport = None
        resolver = None
    got = resolver(_Svc(), meta)
    assert got == SUBJECT_CIK

    # and that subject, fed forward, is what demotes the filing
    out = assess([SUBJECT_SITE, SUBJECT_FILING, OTHER_FILING],
                 subject_filers=(got,), subject_domain=meta["domain"])
    assert out["corroboration_state"] == PARTIALLY_INDEPENDENT


def test_a_recorded_cik_is_preferred_over_a_fuzzy_name_lookup(monkeypatch):
    """Re-resolving by name could return a DIFFERENT registrant, which would
    exclude that company's filings as "the subject's own" and keep the real
    subject's as third-party -- the attribution error inverted."""
    from intent_engine.company_ingestion import service as svc

    called = []
    monkeypatch.setattr(
        "intent_engine.company_ingestion.edgar.resolve_cik",
        lambda name, **kw: called.append(name) or {"cik": "0000000001"})

    class _Svc:
        transport = None
        resolver = None
    got = svc.CompanyIngestionService.subject_cik(
        _Svc(), {"company_name": "Cloudflare", "cik": SUBJECT_CIK})
    assert got == SUBJECT_CIK
    assert not called, "a recorded CIK must not trigger a name lookup"


# --- the call site -----------------------------------------------------------

def test_production_actually_passes_the_subject_to_assess():
    """A FIX WITH NO CALLER IS NOT A FIX.

    Every test above passes with the production call site reverted to
    `assess(rows)` -- verified by mutation. The parameter defaults to empty
    for callers that cannot identify the subject, which is right, and which
    means the one caller that CAN must be pinned separately or the whole
    repair silently reverts to a capability nobody invokes.

    Read from the AST rather than by grep: a grep matches the comment
    explaining the call as readily as the call.
    """
    import ast
    import pathlib

    import intent_engine.webapp.app as app_module

    source = pathlib.Path(app_module.__file__).read_text("utf-8")
    tree = ast.parse(source)

    # The module is imported under a local alias; find it rather than assume
    # one, so renaming the alias fails loudly here instead of quietly
    # disarming the check. Other `.assess(` calls in this file belong to
    # unrelated modules (decision impact, the market bridge) and matching on
    # the method name alone would police them too.
    aliases = {
        alias.asname or alias.name.rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "independence"
    }
    assert aliases, "the webapp no longer imports the independence module"

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "assess"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in aliases
    ]
    assert calls, "the webapp never assesses independence at all"
    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "subject_filers" in passed and "subject_domain" in passed, (
            "an independence assessment in the webapp does not identify the "
            "subject, so the company's own filings will corroborate it")
        # AND IT MUST RESOLVE, NOT JUST READ. Passing `meta.get("cik")`
        # satisfies the check above and identifies nothing on a website run,
        # which is exactly how the first repair shipped inert.
        filers = next(kw.value for kw in call.keywords
                      if kw.arg == "subject_filers")
        resolved = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subject_cik"
            for node in ast.walk(filers))
        assert resolved, (
            "subject_filers is not resolved through `subject_cik`; a run "
            "started from a website carries no CIK and the filter will be "
            "empty")
