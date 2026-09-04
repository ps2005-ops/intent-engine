"""The final PRE-Strategic-100 proof: ten UNSEEN companies, full UI journey.

WHY THESE TEN AND NOT THE FROZEN FIFTY. The 50-company cohort has been run
repeatedly and the acquisition repairs were developed against it, so another
pass mostly answers "can it repeat what we debugged it on?". These ten have
never been a run subject in ANY repo artifact -- verified against the 50 in
`docs/execution/v5/pre100_50` and the 63 in the harnesses -- so they answer
the question Strategic-100 actually depends on: does it GENERALISE?

WHAT IS MEASURED. Not "did a route return 200". The complete journey a judge
would take: submit, watch a truthful waiting page with a real clock, reach a
substantial report, inspect its evidence and provenance, interrogate it, and
never see a spinner that does not end or a company that is not theirs.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://intent-engine-preview-bridge.onrender.com"
POLL_S = 3.0
SUBMIT_TIMEOUT = 300
PAGE_TIMEOUT = 90

#: The sentence ResultState.DEEP_PENDING renders on the brief. Its
#: ABSENCE is DEEP_READY -- read from the served page rather than from
#: a header the harness would have had to ask the product to add.
DEEP_PENDING_MARK = "deeper strategic review is still"

#: Never a run subject in any repo artifact. See PART 18 audit.
TEN = [
    ("Synopsys", "synopsys.com", "technology / EDA"),
    ("Emerson Electric", "emerson.com", "industrial"),
    ("Lowe's Companies", "lowes.com", "consumer / retail"),
    ("BlackRock", "blackrock.com", "financial services"),
    ("Amgen", "amgen.com", "healthcare / biotech"),
    ("SLB", "slb.com", "energy services"),
    ("T-Mobile US", "t-mobile.com", "communications"),
    ("Old Dominion Freight Line", "odfl.com", "transportation"),
    ("Novartis", "novartis.com", "international (20-F)"),
    ("Sprouts Farmers Market", "sprouts.com", "small-cap / sparse"),
]

QUESTIONS = [
    "What is the most important strategic implication?",
    "What is the strongest evidence supporting that?",
    "What is the strongest argument against this conclusion?",
    "What would make this recommendation wrong?",
    "What should management monitor next?",
]
FOLLOW_UP = "Why does that matter most for this company specifically?"

#: Internal vocabulary that must never reach a reader.
LEAK_PATTERNS = (
    r"\bREADY_FOR_[A-Z_]+\b", r"\bINSUFFICIENT_EVIDENCE\b",
    r"\bRETRYABLE_EVIDENCE_GAP\b", r"\bIDENTITY_UNRESOLVED\b",
    r"\bEVIDENCE_[A-Z_]{3,}\b", r"\bSOURCE_DIVERSITY_[A-Z_]+\b",
    r"\bEXTERNAL_[A-Z_]{3,}\b", r"\bCAPACITY_EXCEEDED\b",
    r"\bNOT_ABSTAINED\b", r"\bcandidate_id\b", r"\bsource_id\b",
    r"\bcompany_ingestion\b", r"\bTraceback\b",
)
#: Other companies heavily exercised earlier; none may appear as the SUBJECT
#: of one of these ten reports.
FOREIGN = ("NVIDIA", "Meta Platforms", "Netflix", "Caterpillar",
           "Goldman Sachs", "Johnson & Johnson", "Deere", "Chevron",
           "Eli Lilly", "Ford Motor")


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler), jar


def _req(op, path, fields=None, timeout=PAGE_TIMEOUT):
    data = urllib.parse.urlencode(fields).encode() if fields else None
    headers = {"User-Agent": "final-ten/1"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    began = time.monotonic()
    try:
        with op.open(req, timeout=timeout) as r:
            return (r.status, r.read().decode("utf-8", "replace"), r.geturl(),
                    time.monotonic() - began)
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode("utf-8", "replace"), BASE + path,
                time.monotonic() - began)
    except Exception as e:                                   # noqa: BLE001
        return (0, f"{type(e).__name__}: {e}", BASE + path,
                time.monotonic() - began)


def visible(html: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", s).split())


def leaks(text: str) -> list:
    found = []
    for pat in LEAK_PATTERNS:
        m = re.search(pat, text)
        if m:
            found.append(m.group(0))
    return sorted(set(found))


def _names(text: str, company: str) -> bool:
    """Does this page name the company it is about?

    Compared against the CANONICAL identity that was submitted, and with no
    minimum token length. The first version required tokens longer than three
    characters, which for "SLB" left NO tokens at all -- so `any([])` returned
    False and a page that said "Slb Limited" three times was reported as not
    naming its own company. Two of that row's defects were this rule.
    """
    haystack = (text or "").lower()
    tokens = [t for t in str(company or "").replace(",", " ").split()
              if len(t) >= 2 and t.lower() not in
              ("inc", "inc.", "corp", "corp.", "ltd", "ltd.", "the", "co",
               "company", "limited", "group", "holdings", "plc", "&")]
    if not tokens:
        tokens = [str(company or "").strip()]
    return any(t.lower() in haystack for t in tokens if t)


def _answer_excerpt(answer_text: str, brief_text: str) -> str:
    """What the ANSWER added, with the surrounding page chrome removed.

    The conversation route re-renders the whole brief with the answer on it,
    so `len(html)` measures the report and not the reply. Subtracting the
    brief's own sentences leaves the part that was written for the question.
    """
    known = set()
    for sentence in re.split(r"(?<=[.!?])\s+", brief_text):
        cleaned = sentence.strip()
        if len(cleaned) > 25:
            known.add(cleaned)
    fresh = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer_text)
             if len(s.strip()) > 25 and s.strip() not in known]
    return " ".join(fresh)[:1400]


def journey(name, domain, sector, *, budget_s=300.0) -> dict:
    op, _ = _opener()
    row = {"company": name, "domain": domain, "sector": sector,
           "defects": [], "error": ""}
    st, entry, _u, _d = _req(op, "/demo")
    csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)

    # --- SELECT FROM SUGGESTIONS, as the customer does ---------------------
    #
    # Submitting name+website directly would skip the exact step where the
    # wrong-company failure lives. The UI queries `/api/companies` as the
    # customer types, and `confirm()` binds the CHOSEN row's canonical
    # identity into hidden fields; this reproduces that, so the identity
    # invariant (chosen -> analysed -> reported -> answered) is actually
    # exercised rather than assumed.
    # ENOUGH CHARACTERS TO BE A REAL QUERY. `name.split()[0][:5]` gave "old"
    # for Old Dominion Freight Line -- three characters, which returned five
    # unrelated "Old ..." registrants. A customer types more than one word
    # before expecting the right answer, and the product does return exactly
    # "Old Dominion Freight Line, Inc." for "Old D".
    typed = name.lower()[:6].strip()
    t0 = time.monotonic()
    st_s, sug, _u, _d = _req(op, "/api/companies?q=" + urllib.parse.quote(typed))
    row["suggest_ms"] = int((time.monotonic() - t0) * 1000)
    row["typed_prefix"] = typed
    chosen = None
    try:
        companies = json.loads(sug).get("companies", []) if st_s == 200 else []
    except Exception:                                        # noqa: BLE001
        companies = []
    row["suggestions"] = [c.get("legal_name") for c in companies[:5]]

    # PICK THE INTENDED COMPANY, NOT THE FIRST LOOSE MATCH.
    #
    # This took the first suggestion whose name contained the target's FIRST
    # WORD. For "Old Dominion Freight Line" that word is "old", so it selected
    # "Old QVC Group, Inc." and the whole row analysed the wrong company --
    # not a product failure (the identity chain held perfectly: Old QVC was
    # chosen, submitted, analysed and reported consistently) but a harness one
    # that invalidates the row.
    #
    # Now scored by how much of the INTENDED name a suggestion actually
    # covers, and a suggestion that covers almost none of it is refused
    # outright rather than accepted as the best of a bad list.
    def _overlap(legal_name: str) -> float:
        want = {w for w in re.split(r"[^a-z0-9]+", name.lower())
                if len(w) > 2 and w not in ("inc", "the", "com", "ltd")}
        got = {w for w in re.split(r"[^a-z0-9]+", (legal_name or "").lower())
               if w}
        return len(want & got) / max(1, len(want))

    scored = sorted(((_overlap(c.get("legal_name") or ""), c)
                     for c in companies), key=lambda pair: -pair[0])
    if scored and scored[0][0] >= 0.5:
        chosen = scored[0][1]
    row["match_score"] = round(scored[0][0], 2) if scored else 0.0
    row["autocomplete_found"] = chosen is not None
    row["chosen_identity"] = (chosen or {}).get("legal_name")

    # ASSERT THE IDENTITY, THEN SUBMIT -- NEVER THE OTHER WAY ROUND.
    #
    # This used to fall through to a raw name+website submit whenever no
    # suggestion scored, which spends one of ten hourly analyses on a run
    # whose identity was never bound by the product. The row that comes back
    # is then unreadable: a wrong company looks exactly like a product
    # defect, and the quota is gone either way. A harness that cannot name
    # the entity it selected has failed, and says so instead.
    if chosen is None:
        row["result"] = "HARNESS_ERROR"
        row["error"] = (f"no suggestion covered {name!r}: best overlap "
                        f"{row['match_score']} across {row['suggestions']}")
        return row

    fields = {"consent": "on", "company_name": name,
              "website": f"https://{domain}"}
    if chosen:
        # EXACTLY WHAT `confirm()` WRITES, AND IT USED TO WRITE THREE OF SEVEN.
        #
        # `autocomplete.js: confirm(row)` sets id, cik, tk, dm, ct and ok --
        # and `ok` (`suggest_confirmed`) is the field the server checks before
        # it will honour ANY of the others: `confirmed == company_name` gates
        # the whole confirmed-pick branch, and that branch is the only thing
        # that sets `filer_cik`.
        #
        # This harness sent entity_id, company_name and website. So every
        # analysis it has ever driven fell THROUGH the confirmed-pick branch
        # and opened with cik="", while a real customer picking the same row
        # opens with 60667. Read live from the deployed form after a keyboard
        # selection of "Lowes Companies Inc": suggest_cik=60667,
        # suggest_ticker=LOW, suggest_confirmed="Lowes Companies Inc".
        #
        # That is not a small fidelity gap. An empty CIK is precisely the
        # condition that leaves the business-model gate at UNKNOWN, so the
        # thesis collapse this qualification exists to re-measure was, in
        # part, produced by the instrument. `pre100/capture.py` already sends
        # these; this harness did not, and nothing compared them.
        if chosen.get("entity_id"):
            fields["entity_id"] = chosen["entity_id"]
        if chosen.get("legal_name"):
            fields["company_name"] = chosen["legal_name"]
            fields["suggest_confirmed"] = chosen["legal_name"]
        for key, field in (("cik", "suggest_cik"),
                           ("ticker", "suggest_ticker"),
                           ("domain", "suggest_domain"),
                           ("country", "suggest_country")):
            if chosen.get(key):
                fields[field] = str(chosen[key])
        if chosen.get("domain"):
            fields["website"] = f"https://{chosen['domain']}"
    if csrf:
        fields["csrf"] = csrf.group(1)
    row["submitted_company"] = fields["company_name"]
    row["submitted_cik"] = fields.get("suggest_cik", "")
    row["confirmed_pick"] = bool(fields.get("suggest_confirmed"))

    began = time.monotonic()
    st, body, url, submit_s = _req(op, "/analyze", fields,
                                   timeout=SUBMIT_TIMEOUT)
    row["submit_ack_s"] = round(submit_s, 2)
    row["analyze_status"] = st
    if st in (429, 503):
        row["result"] = "QUOTA" if st == 429 else "CAPACITY_REFUSED"
        row["error"] = visible(body)[:140]
        return row
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        row["result"] = "NO_RUN"
        row["error"] = visible(body)[:200]
        return row
    run_id = row["run_id"] = m.group(1)

    # --- the waiting page --------------------------------------------------
    seen_timer, seen_eta, stages, ui_timer = False, False, [], None
    while time.monotonic() - began < budget_s:
        st, page, url, _d = _req(op, f"/runs/{run_id}/progress", timeout=60)
        if 'id="pg-timer"' in page:
            seen_timer = True
            mt = re.search(r'id="pg-timer"[^>]*>([^<]+)<', page)
            if mt:
                ui_timer = mt.group(1).strip()
        text = visible(page)
        if "finish within two minutes" in text or "longer than usual" in text:
            seen_eta = True
        for label in ("Identifying the company", "Reading current company",
                      "Connecting macro", "Mapping competitors",
                      "Stress-testing", "Building the executive"):
            if label in text and label not in stages:
                stages.append(label)
        if "/progress" not in url and st == 200:
            row["core_ready_s"] = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    row["timer_shown"] = seen_timer
    row["eta_shown"] = seen_eta
    row["stages_seen"] = stages
    row["ui_timer_at_core"] = ui_timer
    if row.get("core_ready_s") is None:
        row["result"] = "NO_TERMINAL"
        row["defects"].append("no terminal outcome within budget")
        return row

    # --- WAIT FOR THE DEEP READING BEFORE ASKING ANYTHING ------------------
    #
    # CORE_READY is when the analysis becomes OPENABLE, not when it is
    # finished: the deeper strategic review continues behind it, and until it
    # lands the brief has no key insight, so `founder_brief.qa` withholds
    # every strategic answer by contract.
    #
    # Asking at CORE therefore measures a half-built analysis. It produced a
    # "70% of answers are refusals" reading across ten companies that was
    # entirely an artifact of asking too early -- the same run answered
    # "Whether a supply commitment should be treated as fixed or
    # renegotiable" once DEEP had merged, 16 seconds later.
    #
    # The marker is the sentence DEEP_PENDING renders; its ABSENCE is
    # DEEP_READY. Bounded, and a run that never finishes is recorded rather
    # than waited on forever.
    deep_ready_s = None
    brief = ""
    while time.monotonic() - began < budget_s:
        st, brief, _u, page_open = _req(op, f"/runs/{run_id}/brief", timeout=90)
        if st == 200 and len(brief) > 2000 and \
                DEEP_PENDING_MARK not in visible(brief).lower():
            deep_ready_s = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    row["deep_ready_s"] = deep_ready_s
    # CORE_READY answers "may this be opened"; STRATEGIC_QA_READY answers
    # "may this be interrogated". Reporting the second as the first is how
    # DEEP latency was once charged to CORE.
    row["strategic_qa_ready_s"] = deep_ready_s
    if deep_ready_s is None:
        row["defects"].append(
            "the deeper strategic review never merged within the budget")

    # --- the report --------------------------------------------------------
    st, brief, _u, page_open = _req(op, f"/runs/{run_id}/brief", timeout=90)
    row["page_open_s"] = round(page_open, 2)
    row["brief_chars"] = len(brief)
    btext = brief_text = visible(brief)
    row["leaks"] = leaks(btext)
    if row["leaks"]:
        row["defects"].append(f"internal vocabulary on the brief: {row['leaks']}")
    row["names_company"] = _names(btext, row.get("submitted_company") or name)
    if not row["names_company"]:
        row["defects"].append("the report does not name the company")
    foreign = [c for c in FOREIGN
               if c.lower() in btext.lower() and c.lower() not in name.lower()]
    row["foreign_companies"] = foreign
    row["spinner_after_terminal"] = 'id="pg-timer"' in brief
    if row["spinner_after_terminal"]:
        row["defects"].append("a running clock remains after the terminal state")

    # --- telemetry: evidence, roles, provenance ----------------------------
    st, tel, _u, _d = _req(op, f"/runs/{run_id}/telemetry", timeout=60)
    if st == 200:
        try:
            data = json.loads(tel)
            roles = data.get("evidence_roles") or {}
            row["documents"] = roles.get("documents")
            row["roles_filled"] = roles.get("filled")
            row["roles_missing"] = roles.get("missing")
            row["families"] = roles.get("families")
            row["sources"] = data.get("sources")
            row["abstention"] = (data.get("abstention") or {}).get("reason")
            mem = data.get("acquisition_memory") or {}
            row["memory_skips"] = (mem.get("skipped_known_failure", 0)
                                   + mem.get("skipped_host_open", 0))
            row["cache_hits"] = (data.get("filing_cache")
                                 or {}).get("CACHE_HIT")
            # THE THESIS AUDIT. Same-thesis is allowed; UNEXPLAINED
            # same-thesis is not, and the two are distinguishable only if the
            # run says which classification it was given and which readings
            # survived it.
            audit = data.get("thesis") or {}
            row["business_model"] = audit.get("business_model")
            row["eligible_patterns"] = audit.get("eligible_pattern_ids")
            row["excluded_patterns"] = audit.get("excluded_pattern_ids")
            row["chosen_pattern"] = audit.get("chosen_pattern")
            row["headline_thesis"] = audit.get("chosen_thesis")
            row["mechanism"] = audit.get("company_specific_mechanism")
            row["thesis_alternative"] = audit.get("alternative")
            row["reason_chosen"] = audit.get("reason_chosen")
            row["thesis_evidence"] = audit.get("supporting_evidence")
            row["reasoning_provenance"] = audit.get("reasoning_provenance")
            if audit.get("business_model") == "UNKNOWN":
                row["defects"].append(
                    "the pattern gate was never told what kind of business "
                    "this is (UNKNOWN takes the whole library)")
        except Exception:                                    # noqa: BLE001
            row["defects"].append("telemetry unreadable")

    # --- evidence / provenance surface -------------------------------------
    st, ev, _u, _d = _req(op, f"/runs/{run_id}/evidence", timeout=60)
    row["evidence_page"] = st
    etext = visible(ev) if st == 200 else ""
    row["provenance_has_sources"] = bool(
        re.search(r"sec\.gov|Archives|10-K|20-F|filing", etext, re.I))
    if st == 200 and not row["provenance_has_sources"]:
        row["defects"].append("evidence page names no identifiable source")

    # --- Q&A ---------------------------------------------------------------
    csrf2 = re.search(r'name="csrf"\s+value="([^"]+)"', brief)
    token = csrf2.group(1) if csrf2 else (csrf.group(1) if csrf else "")
    answers = []
    for q in QUESTIONS + [FOLLOW_UP]:
        st, ans, _u, dt = _req(op, f"/runs/{run_id}/conversation",
                               {"csrf": token, "question": q}, timeout=120)
        atext = visible(ans)
        # The answer is whatever the page gained beyond the brief's chrome.
        # THE ANSWER ITSELF IS KEPT, NOT JUST A COUNT.
        #
        # "6/6 answered" is not a quality measurement: a generic LLM bolted to
        # the bottom of a report answers 6/6 too. The text is retained so the
        # depth standard can be judged against what was actually said --
        # whether the answer names THIS company's mechanism, cites evidence
        # from THIS run, and states uncertainty where the evidence is thin.
        answers.append({
            "q": q, "status": st, "chars": len(ans),
            "leaks": leaks(atext),
            "names_company": _names(
                atext, row.get("submitted_company") or name),
            "seconds": round(dt, 1),
            "answer_text": _answer_excerpt(atext, brief_text),
        })
    row["qa"] = answers
    ok_qa = [a for a in answers
             if a["status"] == 200 and not a["leaks"] and a["names_company"]]
    row["qa_ok"] = f"{len(ok_qa)}/{len(answers)}"
    if len(ok_qa) < len(answers):
        row["defects"].append(f"Q&A weak: {row['qa_ok']}")

    row["result"] = ("FULL_REPORT" if row["brief_chars"] >= 30000
                     else "BOUNDED_ABSTENTION")
    return row


#: PUNCTUATION IS A REAL CUSTOMER INPUT. "Lowe\'s" broke identity binding
#: once already, and a prefix proof costs no analysis quota -- only
#: `/api/companies` is touched, so this runs before the cohort rather than
#: instead of a row in it.
PREFIX_PROOFS = [
    ("Lowe\'s Companies", ["lowe", "lowe\'s", "Lowe\'s Companies"]),
    ("Old Dominion Freight Line", ["old d", "old dominion"]),
    ("T-Mobile US", ["t-mob", "t-mobile"]),
    ("SLB", ["slb"]),
]


def autocomplete_proof() -> list:
    """Does the deployed product resolve the INTENDED company from what a
    customer actually types? Suggestions only -- no analysis is spent."""
    op, _ = _opener()
    _req(op, "/demo")
    out = []
    for intended, prefixes in PREFIX_PROOFS:
        for typed in prefixes:
            t0 = time.monotonic()
            st, body, _u, _d = _req(
                op, "/api/companies?q=" + urllib.parse.quote(typed))
            ms = int((time.monotonic() - t0) * 1000)
            try:
                companies = json.loads(body).get("companies", []) \
                    if st == 200 else []
            except Exception:                                # noqa: BLE001
                companies = []
            want = {w for w in re.split(r"[^a-z0-9]+", intended.lower())
                    if len(w) > 2 and w not in ("inc", "the", "com", "ltd")}
            best, best_name = 0.0, ""
            for c in companies:
                got = {w for w in re.split(
                    r"[^a-z0-9]+", (c.get("legal_name") or "").lower()) if w}
                score = len(want & got) / max(1, len(want))
                if score > best:
                    best, best_name = score, c.get("legal_name") or ""
            out.append({"intended": intended, "typed": typed, "status": st,
                        "ms": ms, "results": len(companies),
                        "best_match": best_name, "score": round(best, 2),
                        "resolves": best >= 0.5})
            print(f"  {typed:<24} {ms:>5}ms  {len(companies):>2} results  "
                  f"{'OK ' if best >= 0.5 else 'MISS'}  {best_name}",
                  flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace", type=float, default=400.0)
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    # `--only synopsys,emerson,blackrock,slb` runs the focused proof that
    # must pass BEFORE the ten are spent. One prefix could never express it,
    # and spending ten analyses to prove four is how an hourly quota is lost.
    wanted = [w.strip().lower() for w in args.only.split(",") if w.strip()]
    cohort = [c for c in TEN if not wanted
              or any(c[0].lower().startswith(w) for w in wanted)]
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, began = [], time.monotonic()
    print(f"FINAL TEN — live UI qualification against {BASE}\n")
    print("AUTOCOMPLETE PREFIX PROOF (no analysis spent)")
    proofs = autocomplete_proof()
    misses = [p for p in proofs if not p["resolves"]]
    print(f"  -> {len(proofs) - len(misses)}/{len(proofs)} resolve"
          + (f"; MISSES {[(p['typed']) for p in misses]}" if misses else "")
          + "\n", flush=True)
    out.with_name(out.stem + "_autocomplete.json").write_text(
        json.dumps(proofs, indent=2), "utf-8")
    for i, (name, domain, sector) in enumerate(cohort, 1):
        started = time.monotonic()
        row = journey(name, domain, sector, budget_s=args.budget)
        row["index"] = i
        rows.append(row)
        out.write_text(json.dumps(rows, indent=2), "utf-8")
        print(f"[{i:>2}/{len(cohort)}] {name[:26]:<27}"
              f"ack={str(row.get('submit_ack_s')):>6} "
              f"core={str(row.get('core_ready_s')):>6} "
              f"timer={str(row.get('ui_timer_at_core')):>6} "
              f"{row.get('result',''):<18} docs={row.get('documents')} "
              f"qa={row.get('qa_ok')} "
              f"defects={len(row.get('defects', []))} "
              f"({(time.monotonic()-began)/60:.0f}m)", flush=True)
        for d in row.get("defects", []):
            print(f"        ! {d}", flush=True)
        if i < len(cohort):
            rest = args.pace - (time.monotonic() - started)
            if rest > 0:
                time.sleep(rest)
    full = sum(1 for r in rows if r.get("result") == "FULL_REPORT")
    clean = sum(1 for r in rows if not r.get("defects"))
    print(f"\n  FULL_REPORT {full}/{len(rows)}   defect-free {clean}/{len(rows)}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
