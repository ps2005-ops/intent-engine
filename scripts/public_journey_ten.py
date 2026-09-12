#!/usr/bin/env python3
"""The exact ten, through the journey a judge actually takes (§K).

WHY THIS EXISTS BESIDE `adaptive_ten_matrix.py`. That harness posts
`company_name` AND `website`, so it proved the analysis works when the
customer already knows the company's URL. Every defect reported from the live
demo happened BEFORE that point: no suggestion appeared for "Highspot", the
submit came back "We could not identify", and the attempt consumed one of the
visitor's ten analyses. A harness that supplies the URL cannot see any of it.

So this one refuses to supply a website. It types a name, reads
`/api/companies`, posts what the combobox posts when a row is picked, and
fails the company if a manual URL would have been required.

WHAT IT MEASURES, per §L:
    identity   suggestion present, correct, first, carries a domain
    runtime    accepted, no unexpected 429, CORE inside the budget
    surfaces   every step renders and says something company-specific
    history    the rewind names the level it can actually deliver
    evidence   no duplicate passages, no broken spans, counterevidence shown
    qa         six questions answered, one contextual follow-up
    role       CEO and Strategy share facts and differ in priority
"""
import argparse
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import perf_progressive_matrix as _PPM                            # noqa: E402
from perf_progressive_matrix import _opener, _req, visible        # noqa: E402

# THE TARGET IS OVERRIDABLE so the same journey can be driven against a local
# instance of the SAME BUILD. The live preview allows ten analyses per IP per
# hour, and spending those ten discovering a bug in this harness is how the
# last two hours went. A local pass validates the instrument for free; the
# live pass is what the qualification actually rests on.
import os                                                         # noqa: E402
if os.environ.get("JOURNEY_BASE"):
    _PPM.BASE = os.environ["JOURNEY_BASE"].rstrip("/")
BASE = _PPM.BASE

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEN = [
    ("Highspot", "highspot"), ("BigID", "bigid"), ("Cyera", "cyera"),
    ("Monte Carlo Data", "monte_carlo_data"), ("Veeam", "veeam"),
    ("Druva", "druva"), ("Slalom", "slalom"),
    ("Sigma Computing", "sigma_computing"), ("ZoomInfo", "zoominfo"),
    ("Point B", "point_b"),
]
#: What a person types on the way to the full name. Autocomplete must work
#: from a PREFIX -- that is the whole feature.
PREFIXES = {
    "Highspot": ["High", "highspot", "HIGHSPOT"],
    "BigID": ["Big", "big id", "BIGID"],
    "Cyera": ["Cye", "cyera", "CYERA"],
    "Monte Carlo Data": ["Monte", "monte carlo", "montecarlo"],
    "Veeam": ["Vee", "veeam", "VEEAM"],
    "Druva": ["Druv", "druva", "DRUVA"],
    "Slalom": ["Slal", "slalom", "SLALOM"],
    "Sigma Computing": ["Sigma", "sigma computing", "SIGMA"],
    "ZoomInfo": ["ZoomI", "zoominfo", "Zoom Info"],
    "Point B": ["Point", "point b", "PointB"],
}
CORE_BUDGET_S = 120
POLL_S = 4.0

QUESTIONS = [
    "What is this company's business model?",
    "Who does it compete with?",
    "What is the biggest risk to this company?",
    "What evidence supports your reading?",
    "What would change your view?",
    "What should a founder take from this?",
]
FOLLOWUP = "Why does that matter?"


def _csrf(html):
    m = re.search(r'name="csrf"[^>]*value="([^"]+)"', html or "")
    return m.group(1) if m else ""


def suggest_live(op, typed):
    """One keystroke's worth of autocomplete. Returns (rows, seconds)."""
    began = time.monotonic()
    st, body, _u, _t, _h = _req(
        op, "/api/companies?q=" + urllib.parse.quote(typed), timeout=30)
    took = time.monotonic() - began
    try:
        rows = json.loads(body).get("companies", [])
    except Exception:                                        # noqa: BLE001
        rows = []
    return rows, took, st


def _sections(html):
    return {h.lower() for h in re.findall(r"<h[12][^>]*>(.*?)</h[12]>",
                                          html or "", re.S | re.I)}


def _quotes(html):
    return [visible(q) for q in
            re.findall(r"<blockquote[^>]*>(.*?)</blockquote>", html or "",
                       re.S | re.I)]


def journey(name, entity_id, *, verbose=True, extra=None) -> dict:
    """`extra(op, run_id, row, surfaces)` runs AFTER the gates are measured and
    BEFORE they are scored, on the SAME authenticated session.

    WHY A HOOK AND NOT A SECOND PASS. `/runs/<id>/*` is ownership-guarded, so a
    follow-up probe from a fresh session is correctly refused -- measured: a
    separate reader got the no-such-run page and reported it as a product
    defect. The expensive half of this function is the analysis, and every
    additional read is free, so a caller that needs more measurements takes
    them here rather than paying for a second run.
    """
    op, _jar = _opener()
    row = {"company": name, "entity_id": entity_id, "defects": [],
           "gates": {}, "autocomplete_ms": [], "result": ""}

    def note(kind, detail):
        row["defects"].append({"kind": kind, "detail": detail})

    def gate(key, ok, detail=""):
        row["gates"][key] = bool(ok)
        if not ok:
            note("PRODUCT_DEFECT", f"{key}: {detail}")

    # --- 1. HOME, as a visitor arrives -------------------------------------
    st, html, _u, _t, _h = _req(op, "/demo")
    token = _csrf(html)
    if not token:
        note("INSTRUMENT_DEFECT", f"no csrf on /demo (status {st})")
        row["result"] = "INSTRUMENT_DEFECT"
        return row

    # --- 2. TYPE THE NAME. Every prefix a person might stop at. -------------
    picked, first_ok = None, True
    for typed in PREFIXES.get(name, [name]) + [name]:
        rows, took, st = suggest_live(op, typed)
        row["autocomplete_ms"].append(round(took * 1000))
        if not rows:
            first_ok = False
            note("PRODUCT_DEFECT",
                 f"autocomplete returned nothing for {typed!r}")
            continue
        top = rows[0]
        if top.get("entity_id") != entity_id:
            # AN EXACT TICKER IS A PRECISE IDENTIFIER, NOT A COLLISION.
            #
            # MEASURED across the forty: eight short prefixes return another
            # company, and every one of them is an exact ticker match --
            # Snap(SNAP), West(WEST), Coll(COLL), Four(FOUR), Drem(DREM),
            # Geo(GEO), Clar(CLAR), Five(FIVE). Somebody typing "GEO"
            # plausibly means The GEO Group, and ranking an exact ticker above
            # a partial name is correct; suppressing it would trade one wrong
            # answer for another.
            #
            # So this is recorded as bounded behaviour WITH THE TICKER AS
            # EVIDENCE, never waived by name. The company must still be found
            # by its own name and longer prefixes, which is what the gate
            # below actually tests -- `picked` is set from any query that
            # resolves correctly.
            ticker = str(top.get("ticker") or "").strip().upper()
            if ticker and ticker == str(typed).strip().upper():
                row.setdefault("bounded_prefixes", []).append(
                    {"typed": typed, "ticker": ticker,
                     "offered": top.get("legal_name")})
                continue
            first_ok = False
            note("PRODUCT_DEFECT",
                 f"{typed!r} offered {top.get('legal_name')!r} first, "
                 f"not {name}")
        elif picked is None:
            picked = top
    gate("AUTOCOMPLETE", first_ok and picked is not None,
         "no query put the right company first")
    if picked is None:
        row["result"] = "PRODUCT_DEFECT"
        return row
    gate("CANONICAL_IDENTITY", bool(picked.get("legal_name")),
         "the suggestion carries no legal name")
    gate("NO_MANUAL_URL", bool(picked.get("domain") or picked.get("cik")),
         "neither a domain nor a CIK -- the visitor would have to type a URL")

    # --- 3. SELECT AND SUBMIT, exactly what the combobox posts --------------
    #     NOTE THE ABSENCE OF `website`. That field is the manual URL this
    #     whole gate exists to make unnecessary; sending it would prove
    #     nothing about the journey the judge takes.
    fields = {
        "csrf": token, "consent": "on",
        "company_name": picked.get("legal_name", ""),
        "suggest_confirmed": picked.get("legal_name", ""),
        "entity_id": picked.get("entity_id", "") or "",
        "suggest_cik": picked.get("cik", "") or "",
        "suggest_ticker": picked.get("ticker", "") or "",
        "suggest_domain": picked.get("domain", "") or "",
        "suggest_country": picked.get("country", "") or "",
    }
    # SUBMIT_ACK IS THE 303, NOT THE PAGE AFTER IT (§9).
    #
    # urllib follows the redirect, so timing `_req` measures the acknowledgement
    # PLUS the first progress render. Those are two different promises -- "we
    # took your request" and "you can see it working" -- and the brief sets
    # different budgets for them (2s and 3s). Measured separately, with a
    # redirect-refusing opener for the first.
    import http.cookiejar as _cj
    import urllib.request as _ur

    class _NoRedirect(_ur.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    began = time.monotonic()
    ack_op = _ur.build_opener(_ur.HTTPCookieProcessor(_jar), _NoRedirect)
    st_ack, _b, _u2, _t2, hdrs = _req(ack_op, "/analyze", fields, timeout=180)
    row["submit_ack_s"] = round(time.monotonic() - began, 2)
    # HTTP HEADER NAMES ARE CASE-INSENSITIVE AND THIS EDGE SENDS LOWERCASE.
    # `dict(e.headers)` preserves the wire spelling, and Render/Cloudflare
    # emit `location` -- so a `.get("Location")` found nothing, the harness
    # reported "submit produced no run (status 303)" for ten successful
    # submissions, and burned an analysis on each one before I caught it.
    location = ""
    for key, value in (hdrs or {}).items():
        if key.lower() == "location":
            location = value
            break
    if st_ack in (302, 303, 307) and "/runs/" in location:
        vis = time.monotonic()
        st, html, url, _t, _h = _req(op, location, timeout=90)
        row["visible_progress_s"] = round(time.monotonic() - vis, 2)
        url = location
    else:
        # No redirect: either a refusal or an error page. Fall through to the
        # existing classification with what the acknowledgement returned.
        st, html, url = st_ack, _b, (BASE + "/analyze")
        row["visible_progress_s"] = None
    row["submit_s"] = round(time.monotonic() - began, 1)
    m = re.search(r"/runs/([A-Za-z0-9]+)", url or "")
    if not m:
        low = visible(html or "").lower()
        if "too many" in low or "limit reached" in low or st == 429:
            note("INFRASTRUCTURE", f"HTTP {st}: demo quota refused the run")
            row["result"] = "INFRASTRUCTURE"
            # THE PAGE STATES ITS OWN RETRY WINDOW, so a caller waits exactly
            # that long instead of guessing an hour. Measured on the live
            # refusal: "You can try again in about 41 minutes."
            _m = re.search(r"try again in (?:about )?(\d+)\s*minute", low)
            row["retry_after_min"] = (
                int(_m.group(1)) if _m else
                1 if "under a minute" in low else None)
        else:
            note("PRODUCT_DEFECT",
                 f"submit produced no run (status {st}): {visible(html)[:180]}")
            row["result"] = "PRODUCT_DEFECT"
        return row
    run_id = m.group(1)
    row["run_id"] = run_id
    gate("ANALYSIS_ACCEPTED", True)
    # `or 99` TURNS A PERFECT SCORE INTO A FAILURE. 0.0 is falsy, so an
    # acknowledgement that came back in under 10ms -- the best possible
    # result -- was read as 99 seconds and failed its own gate. Caught on a
    # local instance where the round trip really is ~0.00s; against the live
    # preview the value is ~0.2s and the bug would have stayed hidden.
    _ack = row.get("submit_ack_s")
    _vis = row.get("visible_progress_s")
    gate("SUBMIT_ACK_2S", _ack is not None and _ack <= 2.0,
         f"acknowledgement took {_ack}s")
    gate("VISIBLE_PROGRESS_3S", _vis is not None and _vis <= 3.0,
         f"first progress render took {_vis}s")
    if verbose:
        print(f"  run {run_id}", flush=True)

    # --- 4. PROGRESS, then CORE --------------------------------------------
    core, spinner_ok = None, True
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
        # Not a spinner that lies -- a spinner that never ends.
        spinner_ok = False
        note("PRODUCT_DEFECT",
             f"no terminal state within {CORE_BUDGET_S}s")
    gate("CORE_WITHIN_120S", core is not None and core <= CORE_BUDGET_S,
         f"CORE took {core}s")
    gate("NO_ENDLESS_SPINNER", spinner_ok, "progress never reached terminal")
    if core is None:
        row["result"] = "PRODUCT_DEFECT"
        return row

    # --- 5. EVERY SURFACE A JUDGE OPENS ------------------------------------
    surfaces = {}
    for key, path in (("intro", f"/runs/{run_id}/intro"),
                      ("brief", f"/runs/{run_id}/brief"),
                      ("full", f"/runs/{run_id}/full"),
                      ("history", f"/runs/{run_id}/history"),
                      ("evidence", f"/runs/{run_id}/evidence"),
                      ("sources", f"/runs/{run_id}/sources"),
                      ("story", f"/runs/{run_id}/story"),
                      ("connect", f"/runs/{run_id}/connect")):
        st, body, _u, _t, _h = _req(op, path, timeout=90)
        surfaces[key] = {"status": st, "html": body}
        if st >= 500:
            note("PRODUCT_DEFECT", f"{key} returned HTTP {st}")
    row["surface_status"] = {k: v["status"] for k, v in surfaces.items()}
    gate("SURFACES_RENDER",
         all(v["status"] < 500 for v in surfaces.values()),
         "a surface returned 5xx")

    # --- 6. HISTORY REWIND: the level must match what is shown -------------
    hist = visible(surfaces["history"]["html"])
    promises_chart = "pick a year" in hist.lower()
    says_no_chart = ("no chart on this page" in hist.lower()
                     or "too thin to rewind" in hist.lower())
    names_simulator = "strategy simulator" in hist.lower()
    level = ("A" if promises_chart and names_simulator else
             "B" if "bounded strategic rewind" in hist.lower() else
             "C" if "does not yet support" in hist.lower() else "?")
    row["history_level"] = level
    # The defect: a page that CALLS itself a simulator and then says it
    # cannot draw one.
    gate("HISTORY_REWIND",
         level in ("A", "B", "C") and not (names_simulator and says_no_chart),
         f"level={level} simulator={names_simulator} no_chart={says_no_chart}")
    gate("HISTORY_USEFUL", len(hist) > 900,
         f"history page carried only {len(hist)} chars of text")

    # --- 7. EVIDENCE: duplicates, broken spans, counterevidence ------------
    # DUPLICATE EVIDENCE IS A PROPERTY OF ONE PAGE.
    #
    # The repair this qualification is checking was PAGE-LEVEL dedup: the
    # same passage must not be printed twice on the page a reader is looking
    # at. Concatenating /evidence and /full and counting repeats across the
    # pair measures something else entirely -- the two surfaces are SUPPOSED
    # to cite the same sources, so every shared citation read as a duplicate
    # and Monte Carlo scored 8 of 9. Counted per page, and the cross-surface
    # figure kept separately because it is informative, not a defect.
    per_page, quotes_all = {}, []
    for key in ("evidence", "full"):
        qs = [q for q in _quotes(surfaces[key]["html"]) if len(q) > 40]
        per_page[key] = len(qs) - len(set(qs))
        quotes_all.extend(qs)
    dupes = sum(per_page.values())
    broken = sum(1 for q in quotes_all
                 if q.startswith(("and ", "but ", "the ", "of ", "to "))
                 or q.endswith((" the", " of", " and", " a", " to")))
    row["evidence"] = {"quotes": len(quotes_all), "duplicates": dupes,
                       "per_page_duplicates": per_page,
                       "shared_across_surfaces":
                           len(quotes_all) - len(set(quotes_all)),
                       "broken_spans": broken}
    gate("EVIDENCE_NO_DUPLICATES", dupes == 0, f"{dupes} duplicated passage(s)")
    gate("EVIDENCE_NO_BROKEN_SPANS", broken == 0, f"{broken} broken span(s)")

    # --- 8. PROFILE CONSISTENCY across surfaces ----------------------------
    #
    # THE PROPERTY IS "NO SURFACE NAMES A DIFFERENT COMPANY", not "every
    # headline is the same string". A first version compared the headlines
    # for equality and reported Veeam as contradictory because /full is
    # headed "Limited analysis of Veeam Software Group GmbH" while /intro is
    # headed "Veeam Software Group GmbH". Those name one company; the second
    # adds an honest qualifier about the evidence. An equality test would
    # flag every bounded run as a contradiction -- inventing a uniform defect
    # out of a correctly-worded page.
    canonical = (picked.get("common_name")
                 or picked.get("legal_name") or name).lower()
    head_word = canonical.split(",")[0].split()[0]
    heads, mismatched = [], []
    for key in ("intro", "brief", "full"):
        m2 = re.search(r"<h1[^>]*>(.*?)</h1>", surfaces[key]["html"],
                       re.S | re.I)
        if not m2:
            continue
        text = visible(m2.group(1)).split("—")[0].strip()
        heads.append(f"{key}:{text}")
        if head_word not in text.lower():
            mismatched.append(f"{key}:{text}")
    row["headline_names"] = heads
    gate("PROFILE_CONSISTENCY", not mismatched,
         f"a surface names a different company: {mismatched}")

    # --- 9. Q&A: six, plus one contextual follow-up ------------------------
    #     THE CANONICAL ROUTE IS /conversation. A first version of this
    #     harness posted to /runs/<id>/ask -- a path the router does not
    #     carry -- and would have reported 0/60 as a product failure.
    answered, qa_detail, answers = 0, [], []
    qtoken = _csrf(surfaces["intro"]["html"]) or token
    for question in QUESTIONS:
        st, body, _u, _t, _h = _req(
            op, f"/runs/{run_id}/conversation",
            {"csrf": qtoken, "question": question}, timeout=120)
        text = visible(body)
        # Words, not characters: the page chrome alone clears a character
        # floor, so a character test would pass on an empty answer.
        ok = st == 200 and len(text.split()) >= 60
        answered += bool(ok)
        answers.append(text)
        qa_detail.append({"q": question, "status": st,
                          "words": len(text.split())})
        qtoken = _csrf(body) or qtoken
    st, body, _u, _t, _h = _req(
        op, f"/runs/{run_id}/conversation",
        {"csrf": qtoken, "question": FOLLOWUP}, timeout=120)
    follow = visible(body)
    # A FOLLOW-UP THAT REPLAYS AN EARLIER ANSWER HAS NOT USED ITS CONTEXT.
    replay = any(a[:400] and a[:400] in follow for a in answers)
    follow_ok = (st == 200 and len(follow.split()) >= 60 and not replay)
    row["qa"] = {"answered": answered, "of": len(QUESTIONS),
                 "followup": follow_ok, "followup_replay": replay,
                 "followup_words": len(follow.split()), "detail": qa_detail}
    gate("QA_VALID", answered == len(QUESTIONS),
         f"{answered}/{len(QUESTIONS)} answered")
    gate("FOLLOWUP_CONTEXT", follow_ok,
         "the follow-up replayed an earlier answer" if replay
         else f"the follow-up was {len(follow.split())} words")

    # --- 10. ROLE VIEWS: same facts, different priority --------------------
    views = {}
    # THE STRATEGY ROLE IS `cso`, NOT "strategy".
    #
    # `_qs_role` accepts any alnum token and `roles.role()` maps an UNKNOWN
    # id to the default -- which is `ceo`. So asking for ?role=strategy
    # silently rendered the CEO view, and this harness reported "CEO and
    # Strategy render identically" for three companies that were in fact
    # never asked for a Strategy view at all. A runner that names a producer
    # field wrongly invents a uniform defect.
    for role in ("ceo", "cso"):
        st, body, _u, _t, _h = _req(op, f"/runs/{run_id}/intro?role={role}",
                                    timeout=60)
        views[role] = visible(body)
    row["role_identical"] = views.get("ceo") == views.get("cso")
    # ROLES DIFFER WHEN THERE IS SOMETHING TO PRIORITISE DIFFERENTLY.
    #
    # A run that correctly abstains has no decision, so a CEO view and a
    # Strategy view of the same abstention SHOULD read the same -- there is
    # no second ordering of nothing. Gating on difference unconditionally
    # asks a bounded page to manufacture a distinction it has no basis for,
    # which is the opposite of what the rest of this qualification checks.
    has_decision = "limited analysis" not in (
        " ".join(row["headline_names"]).lower())
    row["role_gate_applies"] = has_decision
    if has_decision:
        gate("ROLE_VIEWS", not row["role_identical"],
             "CEO and Strategy render identically on a run with a decision")
    else:
        row["gates"]["ROLE_VIEWS"] = True   # bounded run: not applicable

    if extra is not None:
        try:
            extra(op, run_id, row, surfaces)
        except Exception as exc:                             # noqa: BLE001
            # AN INSTRUMENT THAT FAILS MUST NOT FAIL THE COMPANY. A harness
            # bug reported as a product defect is how four analyses were spent
            # on a lowercase header name.
            row.setdefault("instrument_errors", []).append(
                f"{type(exc).__name__}: {exc}")
    failed = [k for k, v in row["gates"].items() if not v]
    row["result"] = "PASS" if not failed else "PRODUCT_DEFECT"
    row["failed_gates"] = failed
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--out", default="reports/public_journey_ten.json")
    args = ap.parse_args()

    st, body, _u, _t, _h = _req(_opener()[0], "/version")
    try:
        version = json.loads(body)
    except Exception:                                        # noqa: BLE001
        version = {}
    print(f"base   {BASE}")
    print(f"live   {version.get('commit','?')[:12]} "
          f"boot={version.get('process',{}).get('boot_id','?')}")

    targets = [(n, e) for n, e in TEN
               if not args.only or n in args.only]
    rows = []
    for name, entity_id in targets:
        print(f"\n== {name}", flush=True)
        try:
            row = journey(name, entity_id)
        except Exception as exc:                             # noqa: BLE001
            row = {"company": name, "result": "INSTRUMENT_DEFECT",
                   "defects": [{"kind": "INSTRUMENT_DEFECT",
                                "detail": f"{type(exc).__name__}: {exc}"}]}
        rows.append(row)
        ms = row.get("autocomplete_ms") or []
        print(f"   {row['result']:16s} core={row.get('core_s')}s "
              f"hist={row.get('history_level','?')} "
              f"qa={(row.get('qa') or {}).get('answered','?')}/6 "
              f"ac_p50={int(statistics.median(ms)) if ms else '-'}ms")
        for d in row.get("defects") or ():
            print(f"      - {d['kind']}: {d['detail'][:150]}")
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"base": BASE, "live_commit": version.get("commit", ""),
             "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
