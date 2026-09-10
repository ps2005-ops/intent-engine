#!/usr/bin/env python3
"""The adaptive-intelligence qualification, against the DEPLOYED service.

ONE SESSION PER COMPANY, HELD OPEN, and the real guest form. `/analyze` is
posted with exactly the fields the browser posts -- csrf, company, website,
consent -- because sending less than the real form does is bypassing the
customer flow just as surely as calling an internal function would be.

WHAT IS RECORDED, and why each one is here:

    identity            the canonical company, read off the rendered page
    profile             business model, its source, and its specificity
    lens                primary, secondary, confidence, and the refusals
    decision map        count, top domain, top priority, and the components
    causal chain        nodes, evidence coverage, generic links
    differentiation     what carried it, and whether it was flagged
    q&a                 six questions through the canonical route, with a
                        follow-up that depends on the previous answer
    roles               CEO and Strategy, same facts, different order
    latency             CORE, and the full surface sweep

EVERY ROW IS PERSISTED THE MOMENT IT IS PRODUCED. A wave that dies on company
seven must not lose companies one to six -- and a matrix that can only be read
after it finishes is a matrix nobody watches.

DEFECTS ARE CLASSIFIED, NOT COUNTED. PRODUCT_DEFECT, INSTRUMENT_DEFECT,
INFRASTRUCTURE, EXPECTED_ABSTENTION and DATA_LIMITATION call for four
different responses and one of them is "nothing".
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from perf_progressive_matrix import BASE, _opener, _req, visible  # noqa: E402

#: The exact ten. Not replaceable because evidence is difficult -- that is the
#: thing being measured.
TEN = (
    ("Highspot", "https://www.highspot.com"),
    ("BigID", "https://bigid.com"),
    ("Cyera", "https://www.cyera.com"),
    ("Monte Carlo Data", "https://www.montecarlodata.com"),
    ("Veeam", "https://www.veeam.com"),
    ("Druva", "https://www.druva.com"),
    ("Slalom", "https://www.slalom.com"),
    ("Sigma Computing", "https://www.sigmacomputing.com"),
    ("ZoomInfo", "https://www.zoominfo.com"),
    ("Point B", "https://pointb.com"),
)

#: §13. SEMANTIC EXPECTATIONS, NOT TEMPLATES. These are what the matrix
#: CHECKS, never what the product is told. A company that lands elsewhere is
#: examined rather than corrected.
EXPECTED_LENS = {
    "Highspot": {"revenue_gtm"},
    "BigID": {"data_security_governance", "enterprise_data_ai"},
    "Cyera": {"data_security_governance", "enterprise_data_ai"},
    "Monte Carlo Data": {"data_infrastructure", "enterprise_data_ai"},
    "Veeam": {"enterprise_data_ai", "data_security_governance"},
    "Druva": {"enterprise_data_ai", "data_security_governance"},
    "Slalom": {"consulting_portfolio"},
    "Sigma Computing": {"data_infrastructure", "enterprise_data_ai"},
    "ZoomInfo": {"revenue_gtm", "market_competitive"},
    "Point B": {"consulting_portfolio"},
}

QUESTIONS = (
    "Why does this matter for this company specifically?",
    "What evidence most supports this reading?",
    "What would have to be true for this to be wrong?",
    "What should management monitor next?",
    "Which decision here is the most urgent, and why that one?",
    "What is the biggest uncertainty in this analysis?",
)
FOLLOW_UP = "Of those, which would you look at first, and why that one?"

#: Anything on a customer surface that is us talking to ourselves.
LEAKS = ("validation manifest", "PROFILE_SPARSE", "PROFILE_PARTIAL",
         "SUBJECT_EVIDENCE", "CLASS_PRIOR", "NOT_ESTABLISHED",
         "SUBSCRIPTION_SOFTWARE", "PEOPLE_OR_ROUTE_BASED_SERVICES",
         "LENS_AND_EXPOSURE", "ResultState.", "business_model_class",
         "None", "UNKNOWN", "Traceback", "Internal Server Error")

POLL_S = 2.0
CORE_BUDGET_S = 300.0


def _csrf(html):
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html or "")
    return m.group(1) if m else ""


def _leaks_in(text: str):
    """Raw internals on a customer surface.

    "None" and "UNKNOWN" are deliberately in the list and deliberately
    word-bounded: they are the two that reach a page through an unset field
    rather than through a deliberate sentence, and a substring match on them
    fires on "nonetheless" and on "unknowns", which is how a leak detector
    becomes something nobody reads.
    """
    found = []
    for token in LEAKS:
        if re.search(r"\b" + re.escape(token) + r"\b", text):
            found.append(token)
    return found


def qualify(name, domain, *, with_qa=True, verbose=True) -> dict:
    op, _jar = _opener()
    row = {"company": name, "domain": domain, "result": "", "defects": [],
           "instrument_notes": []}

    def note(kind, detail):
        row["defects"].append({"kind": kind, "detail": detail})

    st, html, _u, _t, _h = _req(op, "/demo")
    token = _csrf(html)
    if not token:
        note("INSTRUMENT_DEFECT", f"no csrf on /demo (status {st})")
        row["result"] = "INSTRUMENT_DEFECT"
        return row

    began = time.monotonic()
    fields = {"csrf": token, "company": name, "consent": "on"}
    if domain:
        fields["website"] = domain
    st, html, url, _t, _h = _req(op, "/analyze", fields, timeout=180)
    m = re.search(r"/runs/([A-Za-z0-9]+)", url or "")
    if not m:
        low = visible(html or "").lower()
        kind = ("INFRASTRUCTURE" if "too many" in low or st in (429, 502, 503)
                else "PRODUCT_DEFECT")
        note(kind, f"submit did not produce a run (status {st}): "
                   f"{visible(html)[:200]}")
        row["result"] = kind
        return row
    run_id = m.group(1)
    row["run_id"] = run_id
    if verbose:
        print(f"  run {run_id}", flush=True)

    core = None
    while time.monotonic() - began < CORE_BUDGET_S:
        st, body, _u, _t, _h = _req(op, f"/runs/{run_id}/progress.json",
                                    timeout=45)
        try:
            js = json.loads(body)
        except Exception:                                    # noqa: BLE001
            js = {}
        if js.get("opens_result") or js.get("terminal"):
            core = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    row["core_s"] = core
    if core is None:
        note("INFRASTRUCTURE", f"no terminal state within {CORE_BUDGET_S}s")
        row["result"] = "INFRASTRUCTURE"
        return row

    # --- the adaptive telemetry, which is what the gates are read from ----
    st, body, _u, _t, _h = _req(op, f"/runs/{run_id}/adaptive.json",
                                timeout=90)
    try:
        tel = json.loads(body)
    except Exception:                                        # noqa: BLE001
        tel = {}
        note("INSTRUMENT_DEFECT",
             f"adaptive.json unreadable (status {st}): {body[:160]}")
    row["telemetry"] = tel

    row["resolved_identity"] = tel.get("company", "")
    row["business_model"] = tel.get("business_model", "")
    row["profile_source"] = tel.get("company_profile_source", "")
    row["specificity"] = tel.get("company_specificity_score", 0.0)
    row["primary_lens"] = tel.get("primary_lens", "")
    row["secondary_lenses"] = tel.get("secondary_lenses", [])
    row["lens_confidence"] = tel.get("lens_confidence", "")
    row["decision_opportunity_count"] = tel.get("decision_opportunity_count", 0)
    row["top_decision_domain"] = tel.get("top_decision_domain", "")
    row["top_decision_priority"] = tel.get("top_decision_priority", 0.0)
    row["causal_chain_nodes"] = tel.get("causal_chain_nodes", 0)
    row["causal_evidence_coverage"] = tel.get(
        "causal_chain_evidence_coverage", 0.0)
    row["genericity_flags"] = tel.get("genericity_flags", 0)
    row["differentiation_carried_by"] = tel.get(
        "differentiation_carried_by", [])
    row["abstention_reason"] = tel.get("abstention_reason", "")
    for err in (tel.get("errors") or []):
        note("PRODUCT_DEFECT", f"adaptive producer failed: {err}")

    # --- the surfaces, read as a customer reads them ----------------------
    pages = {}
    for suffix in ("/intro", "/brief", "/full", "/xray", "/evidence",
                   "/answer"):
        st, body, _u, dt, _h = _req(op, f"/runs/{run_id}{suffix}", timeout=90)
        key = suffix.strip("/")
        pages[key] = body or ""
        row[f"{key}_status"] = st
        row[f"{key}_chars"] = len(body or "")
        if st != 200:
            note("PRODUCT_DEFECT", f"{suffix} answered {st}")
    row["surface_s"] = round(time.monotonic() - began, 1)

    intro = pages.get("intro", "")
    intro_text = visible(intro)
    row["intro_words"] = len(intro_text.split())

    # identity, read off the page rather than off our own telemetry
    row["identity_on_page"] = bool(
        re.search(re.escape(name.split()[0]), intro_text, re.I))
    if not row["identity_on_page"]:
        note("PRODUCT_DEFECT", "the company name does not appear on /intro")

    leaks = _leaks_in(intro_text)
    row["leaks"] = leaks
    if leaks:
        note("PRODUCT_DEFECT", f"raw internals on /intro: {leaks}")

    # the sections this phase exists to put there
    row["has_why_different"] = "Why this analysis is different" in intro
    row["has_lens_block"] = "The lens this analysis is using" in intro
    row["has_decision_map"] = ("Where better intelligence could change a "
                               "decision") in intro
    row["has_causal_chain"] = "From the change to the decision" in intro
    row["has_role_switch"] = "Read this as" in intro
    row["has_value_block"] = "Where Intent Engine could create value" in intro
    for key, label in (("has_why_different", "why-this-company"),
                       ("has_lens_block", "lens block"),
                       ("has_decision_map", "decision map"),
                       ("has_causal_chain", "causal chain"),
                       ("has_role_switch", "role switch"),
                       ("has_value_block", "value block")):
        if not row[key]:
            note("PRODUCT_DEFECT", f"{label} missing from /intro")

    # the headline is the company AND the lens, not a product name
    row["headline_is_generic"] = "Economic Decision Intelligence" in intro
    if row["headline_is_generic"]:
        note("PRODUCT_DEFECT", "the generic product title is still the "
                               "page's headline")

    # §13 expectation -- CHECKED, never told to the product
    expected = EXPECTED_LENS.get(name, set())
    row["lens_matches_expectation"] = (row["primary_lens"] in expected
                                       or row["primary_lens"] == "")
    if row["primary_lens"] and not row["lens_matches_expectation"]:
        note("DATA_LIMITATION",
             f"lens {row['primary_lens']} outside the expected set "
             f"{sorted(expected)} -- examine rather than correct")
    if not row["primary_lens"]:
        note("EXPECTED_ABSTENTION",
             f"no lens selected: {tel.get('lens_selection_reasons', '')[:200]}")

    # --- the two live role views: same facts, different order -------------
    role_pages = {}
    for role in ("ceo", "cso"):
        st, body, _u, _t, _h = _req(
            op, f"/runs/{run_id}/intro?role={role}", timeout=90)
        role_pages[role] = body or ""
        row[f"role_{role}_status"] = st
        if st != 200:
            note("PRODUCT_DEFECT", f"/intro?role={role} answered {st}")
    if all(role_pages.get(r) for r in ("ceo", "cso")):
        ceo_t, cso_t = (visible(role_pages["ceo"]),
                        visible(role_pages["cso"]))
        row["role_views_differ"] = ceo_t != cso_t
        # SAME FACTS. The company's own self-description, the selected lens
        # and the top decision must be word-identical in both.
        anchors = [a for a in (tel.get("primary_lens_name", ""),
                               tel.get("top_decision_domain", ""),
                               tel.get("customer_job", "")[:60]) if a]
        row["role_facts_identical"] = all(
            (a in ceo_t) == (a in cso_t) for a in anchors)
        if not row["role_views_differ"]:
            note("PRODUCT_DEFECT", "CEO and Strategy render identically")
        if not row["role_facts_identical"]:
            note("PRODUCT_DEFECT",
                 "a fact appears under one role and not the other")

    # --- Q&A through the canonical route, with a dependent follow-up ------
    if with_qa:
        answers, csrf = [], _csrf(intro)
        for question in QUESTIONS:
            st, body, _u, _t, _h = _req(
                op, f"/runs/{run_id}/conversation",
                {"csrf": csrf, "question": question}, timeout=120)
            text = visible(body)
            csrf = _csrf(body) or csrf
            answers.append({"q": question, "status": st,
                            "words": len(text.split()),
                            "text": text[:1400]})
        st, body, _u, _t, _h = _req(
            op, f"/runs/{run_id}/conversation",
            {"csrf": csrf, "question": FOLLOW_UP}, timeout=120)
        follow = visible(body)
        row["qa"] = answers
        row["qa_ok"] = sum(1 for a in answers
                           if a["status"] == 200 and a["words"] >= 60)
        row["qa_company_specific"] = sum(
            1 for a in answers
            if re.search(re.escape(name.split()[0]), a["text"], re.I))
        # a follow-up that repeats a previous answer verbatim has not used
        # the context it was given
        row["followup_words"] = len(follow.split())
        row["followup_is_replay"] = any(
            a["text"][:400] and a["text"][:400] in follow for a in answers)
        row["followup_pass"] = (row["followup_words"] >= 60
                                and not row["followup_is_replay"])
        if row["qa_ok"] < len(QUESTIONS):
            note("PRODUCT_DEFECT",
                 f"{len(QUESTIONS) - row['qa_ok']} of {len(QUESTIONS)} "
                 f"answers were short or errored")
        if not row["followup_pass"]:
            note("PRODUCT_DEFECT",
                 "the follow-up replayed a previous answer or was empty"
                 if row["followup_is_replay"] else "the follow-up was empty")

    product = [d for d in row["defects"] if d["kind"] == "PRODUCT_DEFECT"]
    row["result"] = ("PASS" if not product else "PRODUCT_DEFECT")
    if not product and not row["primary_lens"]:
        row["result"] = "DEFENSIBLE_ABSTENTION"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-qa", action="store_true")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="seconds to wait between companies (demo quota is "
                         "10 analyses per IP per rolling hour)")
    a = ap.parse_args()

    cohort = [(n, d) for n, d in TEN
              if not a.only or a.only.lower() in n.lower()]
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)

    st, body, _u, _t, _h = _req(_opener()[0], "/version")
    try:
        version = json.loads(body)
    except Exception:                                        # noqa: BLE001
        version = {"raw": body[:200]}
    print(f"base    {BASE}")
    print(f"live    {version.get('commit', '?')}")
    print(f"cohort  {len(cohort)}\n")

    rows = []
    for index, (name, domain) in enumerate(cohort, start=1):
        print(f"[{index}/{len(cohort)}] {name}", flush=True)
        began = time.monotonic()
        try:
            row = qualify(name, domain, with_qa=not a.no_qa)
        except Exception as exc:                             # noqa: BLE001
            row = {"company": name, "domain": domain,
                   "result": "INSTRUMENT_DEFECT",
                   "defects": [{"kind": "INSTRUMENT_DEFECT",
                                "detail": f"{type(exc).__name__}: {exc}"}]}
        row["wall_s"] = round(time.monotonic() - began, 1)
        rows.append(row)
        # PERSISTED IMMEDIATELY. A wave that dies on company seven must not
        # lose one to six.
        out.write_text(json.dumps(
            {"base": BASE, "live_commit": version.get("commit", ""),
             "rows": rows}, indent=2))
        print(f"      {row['result']:22s} lens={row.get('primary_lens', '-')}"
              f" model={row.get('business_model', '-')}"
              f" spec={row.get('specificity', 0)}"
              f" core={row.get('core_s', '-')}s"
              f" defects={len(row.get('defects', []))}", flush=True)
        if a.pace and index < len(cohort):
            time.sleep(a.pace)

    cores = [r["core_s"] for r in rows if r.get("core_s")]
    passed = sum(1 for r in rows if r["result"] in
                 ("PASS", "DEFENSIBLE_ABSTENTION"))
    lenses = {r.get("primary_lens") for r in rows if r.get("primary_lens")}
    print(f"\n{passed}/{len(rows)} passed or defensibly abstained")
    print(f"{len(lenses)} distinct primary lenses across {len(rows)} companies")
    if cores:
        print(f"CORE p50 {statistics.median(cores):.1f}s  "
              f"max {max(cores):.1f}s")
    print(f"written {out}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
