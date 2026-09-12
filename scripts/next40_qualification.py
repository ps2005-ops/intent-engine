#!/usr/bin/env python3
"""The next forty, through the public journey, in resumable cohorts (§1-§27).

WHAT THIS IS NOT. It is not a second harness. `public_journey_ten.journey`
carries every instrument correction the previous qualification paid for -- the
lowercase `location` header, the falsy-zero `submit_ack`, the `cso` role id,
per-page duplicate counting, the profile-consistency rule that does not demand
string equality -- and it is reused verbatim. This module adds what forty
companies need that ten did not:

    RESUMABILITY      one row per company on disk; a restart resumes at the
                      first incomplete company rather than re-running forty
    QUOTA             ten analyses per IP per rolling hour is the binding
                      constraint. Not capacity: four concurrent slots exist,
                      but a pipeline cannot spend more than ten an hour, so
                      submitting sequentially and waiting out the window uses
                      the quota optimally AND never manufactures a capacity
                      refusal to report.
    FREE MEASUREMENT  every `/runs/<id>/*` read costs nothing, so discovery
                      state, the history level's own numbers, the X-Ray and
                      the role views are taken on the SAME session inside the
                      one paid run.
    DIFFERENTIATION   each company's decision text is kept so cohorts can be
                      compared for template collapse (§19) without re-running.

WHY SEQUENTIAL IS THE PIPELINE. §4 asks for a pipeline rather than a burst and
warns against faking capacity. With a ten-per-hour IP ceiling the queue is
never the limit: four concurrent analyses would finish in under two minutes and
then wait fifty-eight. Sequential submission is therefore the same throughput
with none of the capacity refusals, and it keeps one failure attributable to
one company.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent

import next40_owner as OWNER                                     # noqa: E402
import public_journey_ten as PJT                                  # noqa: E402
from perf_progressive_matrix import _req, visible                 # noqa: E402

# (n, typed name, entity_id, prefixes a person stops at, category)
FORTY = [
 (1, "Rubrik", "rubrik", ["Rub", "rubrik", "RUBRIK"], "DATA_SECURITY"),
 (2, "Cohesity", "cohesity", ["Coh", "cohesity"], "DATA_SECURITY"),
 (3, "project44", "project44", ["proj", "project44", "Project 44"],
  "SUPPLY_CHAIN"),
 (4, "Kinaxis", "kinaxis", ["Kin", "kinaxis"], "PLANNING"),
 (5, "Alation", "alation", ["Ala", "alation"], "DATA_AI_INFRA"),
 (6, "Workato", "workato", ["Work", "workato"], "AUTOMATION"),
 (7, "Dataminr", "dataminr", ["Datamin", "dataminr"], "EXTERNAL_INTEL"),
 (8, "Adastra", "adastra", ["Adas", "adastra"], "CONSULTING"),
 (9, "HYCU", "hycu", ["HYC", "hycu"], "DATA_SECURITY"),
 (10, "Nasuni", "nasuni", ["Nas", "nasuni"], "DATA_SECURITY"),
 (11, "Dataiku", "dataiku", ["Dataik", "dataiku"], "DATA_AI_INFRA"),
 (12, "Commvault", "commvault", ["Comm", "commvault"], "DATA_SECURITY"),
 (13, "Boomi", "boomi", ["Boo", "boomi"], "AUTOMATION"),
 (14, "SnapLogic", "snaplogic", ["Snap", "snaplogic"], "AUTOMATION"),
 (15, "West Monroe", "west_monroe", ["West", "west monroe"], "CONSULTING"),
 (16, "Guidehouse", "guidehouse", ["Guide", "guidehouse"], "CONSULTING"),
 (17, "Collibra", "collibra", ["Coll", "collibra"], "DATA_AI_INFRA"),
 (18, "Airbyte", "airbyte", ["Airb", "airbyte"], "DATA_AI_INFRA"),
 (19, "OneTrust", "onetrust", ["OneT", "onetrust"], "DATA_AI_INFRA"),
 (20, "Samsara", "samsara", ["Sams", "samsara"], "SUPPLY_CHAIN"),
 (21, "FourKites", "fourkites", ["Four", "fourkites"], "SUPPLY_CHAIN"),
 (22, "Descartes Systems", "descartes", ["Desc", "descartes"],
  "SUPPLY_CHAIN"),
 (23, "o9 Solutions", "o9_solutions", ["o9", "o9 solutions"], "PLANNING"),
 (24, "ThoughtSpot", "thoughtspot", ["Thought", "thoughtspot"], "ANALYTICS"),
 (25, "Starburst", "starburst", ["Starb", "starburst"], "DATA_AI_INFRA"),
 (26, "Dremio", "dremio", ["Drem", "dremio"], "DATA_AI_INFRA"),
 (27, "Denodo", "denodo", ["Deno", "denodo"], "DATA_AI_INFRA"),
 (28, "Geotab", "geotab", ["Geo", "geotab"], "SUPPLY_CHAIN"),
 (29, "Clari", "clari", ["Clar", "clari"], "GTM"),
 (30, "6sense", "6sense", ["6se", "6sense", "6 sense"], "GTM"),
 (31, "Gong", "gong", ["Gon", "gong"], "GTM"),
 (32, "AlphaSense", "alphasense", ["Alpha", "alphasense"], "EXTERNAL_INTEL"),
 (33, "FiscalNote", "fiscalnote", ["Fiscal", "fiscalnote"], "EXTERNAL_INTEL"),
 (34, "Recorded Future", "recorded_future", ["Recorded", "recorded future"],
  "EXTERNAL_INTEL"),
 (35, "Prewave", "prewave", ["Prew", "prewave"], "EXTERNAL_INTEL"),
 (36, "Protiviti", "protiviti", ["Prot", "protiviti"], "CONSULTING"),
 (37, "Credera", "credera", ["Cred", "credera"], "CONSULTING"),
 (38, "Long View Systems", "long_view", ["Long View", "long view systems"],
  "CONSULTING"),
 (39, "Celigo", "celigo", ["Cel", "celigo"], "AUTOMATION"),
 (40, "Fivetran", "fivetran", ["Five", "fivetran", "dbt Labs"],
  "DATA_AI_INFRA"),
]
COHORTS = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41)}
STATE = ROOT / "reports/next40_state.json"

#: The §10 questions, asked of every company. Deliberately NOT company-specific
#: -- the point is whether the ANSWERS are.
QUESTIONS = [
    "What is the most important strategic implication for this company?",
    "What evidence supports it?",
    "What evidence argues against it?",
    "What is the weakest assumption in that reading?",
    "What would change the recommendation or posture?",
    "What should management investigate next?",
]


# --- state ------------------------------------------------------------------

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:                                        # noqa: BLE001
        return {"contract": "next40_state.v1", "rows": {}}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # THE CLAIM IS REFRESHED BY THE WRITE ITSELF, so a runner that is waiting
    # out a quota window keeps its ownership and one that has died loses it.
    OWNER.beat(OWNER.session_id())
    state["owner"] = OWNER.read().get("session")
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(STATE)


def done(row) -> bool:
    """A company is finished when it reached a terminal CLASS on THIS sha."""
    return bool(row) and bool(row.get("final_class")) \
        and row.get("final_class") != "QUOTA_DEFERRED"


# --- the free measurements, taken on the paid session -----------------------

#: What the product's own failure page says. Matched on its sentences, not on
#: a status code: the page answers 200 because it is a real page, and it is the
#: CORRECT page for a company whose sources could not be retrieved.
_COULD_NOT_COMPLETE = "this analysis could not be completed"


def _retrieval_limitation(row, surfaces) -> bool:
    """Is this a correctly-handled retrieval limit rather than a defect? (§8)

    WHY THIS EXISTS AND WHY IT IS NOT A LOOPHOLE. Three of the forty answer
    HTTP 403 from their own domain to every path including robots.txt, and one
    of those files with no regulator anywhere. For that company the product
    CANNOT produce a reading, and the right behaviour is to say so -- §8 names
    that outcome explicitly.

    Scoring it against the full-analysis gates would report a correct refusal
    as a product defect. So the inapplicable gates are neutralised AND
    REPLACED, never merely dropped: a gate set that a bounded run passes by
    having nothing in it would be a test that cannot fail. Every gate below
    has to be earned by something the page actually says.
    """
    intro = visible(surfaces.get("intro", {}).get("html", "") or "")
    result = visible(surfaces.get("result", {}).get("html", "") or "")
    page = (intro + " " + result).lower()
    if _COULD_NOT_COMPLETE not in page:
        return False
    row["bounded_page"] = True
    # THE HONESTY GATES, which are the whole product claim in this state.
    row["gates"]["FAILURE_IS_NAMED"] = True
    row["gates"]["FAILURE_NOT_BLAMED_ON_THE_COMPANY"] = (
        "not evidence that anything is missing in the real world" in page)
    row["gates"]["FAILURE_ASSERTS_NO_READING"] = (
        "we do not invent one" in page)
    row["gates"]["FAILURE_SAYS_WHAT_HAPPENED_TO_EACH_SOURCE"] = (
        "what happened to each source" in page or "what was read" in page)
    row["gates"]["FAILURE_OFFERS_A_RETRY"] = bool(
        re.search(r"try again|retry|add a source|paste", page))
    # The gates a run with no report cannot satisfy, neutralised WITH A REASON
    # recorded beside each one so this can never read as a silent pass.
    row["neutralised_gates"] = {}
    for gate in ("HISTORY_REWIND", "HISTORY_USEFUL", "QA_VALID",
                 "FOLLOWUP_CONTEXT", "EVIDENCE_NO_DUPLICATES",
                 "EVIDENCE_NO_BROKEN_SPANS", "PROFILE_CONSISTENCY",
                 "ROLE_VIEWS", "XRAY_RENDERS"):
        if gate in row["gates"] and not row["gates"][gate]:
            row["neutralised_gates"][gate] = (
                "the run produced no report, so this gate has nothing to "
                "measure; the FAILURE_* gates above are what replace it")
            row["gates"][gate] = True
    return True


def _generalization(run_id, row, surfaces) -> dict:
    """§7. Which force chose this company's decision, and what it was.

    Read from the run's own composed selection where the surface exposes it,
    and from the rendered X-Ray otherwise. Never invented: a company whose
    page does not state its decision gets an empty record, which is the
    honest answer and is what a missing field should look like.
    """
    xray = visible(surfaces.get("xray", {}).get("html", "") or "")
    out = {}
    m = re.search(r"(\b[A-Z][a-z]+(?: [a-z]+)?) decision\b", xray)
    if m:
        out["archetype_label"] = m.group(1)
    q = re.search(r"For [^:]{1,80}:\s*(.{15,200}?\?)", xray)
    if q:
        out["decision_question"] = " ".join(q.group(1).split())
    w = re.findall(r"revenue at a business of this kind moves with "
                   r"([a-z ,]+?)(?:\.|revenue|$)", xray)
    if w:
        out["watch_metrics"] = sorted({x.strip() for x in w if x.strip()})
    why = re.search(r"[Ww]hy this decision\s*(.{20,400}?)(?:\.\s|$)", xray)
    if why:
        out["why_primary_won"] = " ".join(why.group(1).split())[:300]
    # THE CONTRIBUTIONS, READ OFF THE PAGE'S OWN REASON.
    #
    # `/runs/<id>/adaptive.json` does not expose `selection.considered`, so
    # the JSON attempt below returns nothing and `contributions` came back
    # empty on a run whose X-Ray states its reasoning in full. The reason
    # panel is the product's own account of what decided the question, and it
    # names both the force and the terms:
    #
    #   "... is on the list because this company's own record discusses it:
    #    carrier, freight, logistics; ... in 9 distinct terms ...
    #    It was ranked above pricing on the same evidence"
    #
    # Parsed from the RENDERED page, which is also the thing a customer reads,
    # so a claim here cannot outrun what the product actually says.
    # THE WINNER'S OWN REASON, AND NOTHING ELSE ON THE PAGE.
    #
    # The X-Ray states "own record discusses this decision in N distinct
    # terms" for EVERY candidate it weighed, under "Decisions we considered
    # and did not select". Scanning the whole page therefore attributed a
    # REJECTED candidate's evidence to the WINNER: Cohesity's Pricing
    # decision was recorded with three supply-chain terms it never claimed,
    # and HYCU's with the terms of the decision it was ranked above. Five of
    # fourteen cohort-A companies would have been reported evidence-led when
    # the page says the class prior chose them.
    #
    # `<p class="k">Why this decision</p>` is the winner's own anchor in the
    # markup, so the reason is read from there and the search is bounded to it.
    raw = surfaces.get("xray", {}).get("html", "") or ""
    panel = re.search(
        r'<p class="k">Why this decision</p>\s*<p[^>]*>(.*?)</p>', raw,
        re.S)
    why_text = " ".join(visible(panel.group(1)).split()) if panel else ""
    out["why_this_decision"] = why_text
    out["decision_force"] = (
        "POSTURE_LED" if ("which is decided by" in why_text
                          or "operating posture has been identified"
                          in why_text) else
        "ECON_LED" if "conditions reach this business" in why_text else
        "EVIDENCE_LED" if "is not a standing decision for a" in why_text else
        "CLASS_PRIOR_REINFORCED_BY_EVIDENCE"
        if "own record discusses this decision in" in why_text else
        "CLASS_PRIOR_ONLY"
        if "is a standing decision for this business model" in why_text else
        "NO_DECISION")
    terms = re.search(r"own record discusses (?:this decision )?in (\d+) "
                      r"distinct terms? \(([^)]*)\)", why_text)
    contrib = {}
    if terms:
        groups = terms.groups()
        contrib = {
            "evidence": int(groups[0]) if groups[0].isdigit() else None,
            "evidence_terms": [t.strip() for t in groups[-1].split(",")
                               if t.strip()],
            "class_prior_only": False,
        }
    elif "is a standing decision for this business model" in why_text:
        contrib = {"evidence": 0, "evidence_terms": [],
                   "class_prior_only": True}
    if "measured" in why_text and "conditions reach this business" in why_text:
        contrib["econ"] = True
        contrib["class_prior_only"] = False
    if contrib:
        out["contributions"] = contrib
    ranked = re.search(r"ranked above ([a-z ]+?) on the same evidence",
                       why_text)
    if ranked:
        out["ranked_above"] = ranked.group(1).strip()
    # The itemised contributions, where the run exposes them.
    try:
        st, body, _u, _t, _h = _req(
            op_holder[0], f"/runs/{run_id}/adaptive.json", timeout=45) \
            if op_holder else (0, "", "", 0, {})
        data = json.loads(body) if st == 200 else {}
        sel = (data.get("selection") or {}) if isinstance(data, dict) else {}
        considered = sel.get("considered") or []
        if considered:
            out["archetype"] = considered[0].get("archetype")
            if considered[0].get("contributions"):
                out["contributions"] = considered[0]["contributions"]
            out["top_3"] = [c.get("archetype") for c in considered[:3]]
    except Exception:                                        # noqa: BLE001
        pass
    return out


#: Set by `_measure` so `_generalization` can reuse the authenticated session
#: rather than opening one the ownership guard would refuse.
op_holder = []


def _measure(op, run_id, row, surfaces):
    """Everything §10-§19 needs that the ten-company gates did not read."""
    op_holder[:] = [op]
    # --- §14 DISCOVERY. The state is machine-readable on /evidence now, and
    # the prose is kept beside it so a wording change cannot silently pass.
    ev = surfaces.get("evidence", {}).get("html", "") or ""
    m = re.search(r'data-search-state="([^"]*)"', ev)
    origins = re.search(r'data-independent-origins="(\d+)"', ev)
    text = visible(ev)
    row["discovery"] = {
        "search_state": m.group(1) if m else "ATTRIBUTE_ABSENT",
        "independent_origins": int(origins.group(1)) if origins else None,
        "says_no_search": "no discovery run is recorded" in text.lower(),
        "reused": "reused the source list" in text.lower(),
        "hits": (lambda q: int(q.group(1)) if q else None)(
            re.search(r"found (\d+) filing", text)),
        "read_in_full": (lambda q: int(q.group(1)) if q else None)(
            re.search(r"read (\d+) in full", text)),
    }
    # --- §12 HISTORY. The level's OWN numbers, not a guess from the prose.
    hist_html = surfaces.get("history", {}).get("html", "") or ""
    hist = visible(hist_html)
    dates = sorted(set(re.findall(r"\b(20[0-2]\d-[01]\d-[0-3]\d)\b", hist)))
    # EACH LEVEL COUNTS ITS OWN KIND OF RECORD, AND SAYS SO IN ITS OWN WORDS.
    # LEVEL B walks "dated document(s)" -- pages the company published. LEVEL A
    # walks "dated filing(s)" -- a regulator's forms, which is deliberately a
    # different noun (`history_rewind.DatedRecord` exists precisely so an About
    # page is never described as a filing). Matching only the LEVEL B wording
    # read Rubrik's count as null on a page that says 32.
    # EACH LEVEL COUNTS ITS OWN RECORD IN ITS OWN WORDS, and all three must
    # yield §12's DATED_DOCUMENT_COUNT:
    #   A  "32 dated filing(s) span 2024-04-01 to 2026-09-01"
    #   B  "6 dated document(s) span 2026-07-10 to 2026-08-27"
    #   C  "One dated document was retrieved for Alation, Inc."
    # Matching only one of them read two of the three as null on pages that
    # state the number plainly.
    _WORDS = {"no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    spans = re.search(
        r"(\d+) dated (?:document|filing|record)\(s\) span", hist)
    if spans:
        dated_documents = int(spans.group(1))
    else:
        m2 = re.search(
            r"\b(\d+|no|one|two|three|four|five|six|seven|eight|nine|ten) "
            r"dated (?:document|filing|record)s?\b", hist, re.I)
        dated_documents = (
            (int(m2.group(1)) if m2.group(1).isdigit()
             else _WORDS.get(m2.group(1).lower()))
            if m2 else None)
    econ_states = re.findall(r'data-econ-state="([^"]*)"', hist_html)
    row["history"] = {
        "level": row.get("history_level"),
        "dated_documents": dated_documents,
        "earliest": dates[0] if dates else None,
        "latest": dates[-1] if dates else None,
        "financial_series": row.get("history_level") == "A",
        "econ_states": {s: econ_states.count(s) for s in set(econ_states)},
        "economic_links": sum(1 for s in econ_states
                              if s == "ECONOMIC_CONTEXT_LINKED"),
        # THE WALL IS THE SAME WALL, WORDED FOR THE SURFACE IT GUARDS. LEVEL B
        # labels a field "(hindsight, not available then)"; LEVEL A states it
        # about the chart -- "Nothing modelled at a date can see a filing made
        # after it." Checking only the first reported ABSENT on a page whose
        # wall is intact, which would have read as a product defect.
        # A WALL GUARDS A WALK. LEVEL C walks no dates -- it states that the record is
        # too thin to rewind -- so there is no "then" for later evidence to leak into,
        # and reporting ABSENT there would read as a missing guard rather than an
        # inapplicable one.
        "hindsight_wall": ("NOT_APPLICABLE"
                           if row.get("history_level") == "C" else
                           "PRESENT" if any(
            phrase in hist.lower() for phrase in (
                "not available then", "can see a filing made after it",
                "had not happened yet", "after it, because that part"))
            else "ABSENT"),
        "stops": len(econ_states),
        # LEVEL A's evidence is the chart itself: three series and the year
        # selectors a reader can actually move. Recorded so "financial series
        # available" is a measurement rather than an inference from the level.
        "series_lines": sum(1 for m in ("ln-actual", "ln-expect", "ln-counter")
                            if m in hist_html),
        "chart_years": sorted(set(re.findall(r">(20\d\d)<", hist_html))),
        "timeline_points": (lambda m: int(m.group(1)) if m else None)(
            re.search(r"timeline has (\d+) point", hist)),
    }
    # --- §7 the surfaces the ten-company harness did not open.
    #     `result` is the run's OWN page and it is where the economic context
    #     is rendered (`_strategic_run_page` passes `econ=`), so a harness that
    #     reads only /brief and /full measures economic intelligence on two
    #     surfaces that may not carry it.
    for key, path in (("result", f"/runs/{run_id}"),
                      ("xray", f"/runs/{run_id}/xray"),
                      ("slides", f"/runs/{run_id}/slides")):
        st, body, _u, _t, _h = _req(op, path, timeout=90)
        surfaces[key] = {"status": st, "html": body}
        row.setdefault("surface_status", {})[key] = st
    xray = visible(surfaces["xray"]["html"])
    row["xray_chars"] = len(xray)
    row["gates"]["XRAY_RENDERS"] = surfaces["xray"]["status"] < 400
    # --- §10 ECONOMIC INTELLIGENCE: is it about THIS company's engine?
    full = visible(surfaces.get("full", {}).get("html", "") or "")
    brief = visible(surfaces.get("brief", {}).get("html", "") or "")
    result = visible(surfaces.get("result", {}).get("html", "") or "")
    blob = " ".join((result, brief, full, xray))
    row["econ_intel"] = {
        "mentions_transmission": bool(re.search(
            r"transmission|passes through|flows through|exposed to", blob, re.I)),
        "names_a_mechanism": bool(re.search(
            r"because|which means|so that|drives|depends on", blob, re.I)),
        "names_a_falsifier": bool(re.search(
            r"would falsify|would change|argues against|contradict", blob,
            re.I)),
        "chars": len(blob),
    }
    # --- §7 STRATEGIC GENERALIZATION, read off the X-Ray's own panel.
    #     What decided this company's question, itemised, so a cohort can tell
    #     a genuine similarity from the class prior winning again.
    row["generalization"] = _generalization(run_id, row, surfaces)

    # --- §19 the corpus template collapse is measured from. Kept, not judged
    # here: a single company cannot be compared with itself.
    row["decision_text"] = {
        "brief": brief[:6000], "full": full[:9000], "xray": xray[:6000],
    }
    # --- §16 the role views, kept for cross-company comparison
    row["role_text"] = {}
    for role in ("ceo", "cso"):
        st, body, _u, _t, _h = _req(
            op, f"/runs/{run_id}/intro?role={role}", timeout=60)
        row["role_text"][role] = visible(body)[:5000]
    # --- §17 THE CAPTURES, WRITTEN TO DISK RATHER THAN INTO THE STATE FILE.
    # Six surfaces x forty companies is ~10MB of HTML, and a state file that
    # size is re-read and rewritten after every company. The UI matrix reads
    # these files; the state row carries only their names.
    slug = re.sub(r"[^a-z0-9]+", "-", str(row.get("company", "")).lower())
    out = ROOT / "reports/next40_ui"
    out.mkdir(parents=True, exist_ok=True)
    row["capture_files"] = {}
    for key in ("result", "intro", "brief", "full", "history", "evidence",
                "xray", "sources", "story"):
        body = (surfaces.get(key) or {}).get("html")
        if not body:
            continue
        path = out / f"{slug.strip('-')}-{key}.html"
        path.write_text(body)
        row["capture_files"][key] = path.name
    # LAST, because it needs `result` and every surface above it.
    row["retrieval_limited"] = _retrieval_limitation(row, surfaces)


# --- one company ------------------------------------------------------------

def run_one(n, name, entity_id, prefixes, category, sha) -> dict:
    PJT.PREFIXES[name] = prefixes
    PJT.QUESTIONS[:] = QUESTIONS
    began = time.time()
    try:
        row = PJT.journey(name, entity_id, extra=_measure)
    except Exception as exc:                                 # noqa: BLE001
        row = {"company": name, "result": "INSTRUMENT_DEFECT",
               "defects": [{"kind": "INSTRUMENT_DEFECT",
                            "detail": f"{type(exc).__name__}: {exc}"}]}
    row.update(n=n, category=category, live_sha=sha,
               wall_s=round(time.time() - began, 1))
    # §8 the four allowed epistemic outcomes, decided from what the run did
    res = row.get("result")
    if res == "PASS":
        hist = row.get("history_level")
        origins = (row.get("discovery") or {}).get("independent_origins") or 0
        row["final_class"] = (
            "RETRIEVAL_LIMITATION_HANDLED_CORRECTLY"
            if row.get("retrieval_limited") else
            "DECISION_GRADE_READING" if origins > 0 else
            "DEFENSIBLE_ABSTENTION" if hist in ("A", "B") else
            "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY")
    elif res == "INFRASTRUCTURE":
        row["final_class"] = "QUOTA_DEFERRED"
    else:
        row["final_class"] = res or "UNKNOWN"
    return row


def _sha():
    st, body, _u, _t, _h = _req(PJT._opener()[0], "/version")
    try:
        return json.loads(body).get("commit", "")
    except Exception:                                        # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="A", choices=sorted(COHORTS))
    ap.add_argument("--only", type=int, action="append", default=None)
    ap.add_argument("--max", type=int, default=99,
                    help="stop after this many paid analyses this invocation")
    ap.add_argument("--wait-quota", action="store_true",
                    help="on a quota refusal, wait out the window and resume")
    args = ap.parse_args()

    # ONE WRITER. Claimed before anything is read, so a refusal costs nothing
    # and a race cannot start.
    session = OWNER.session_id()
    owner = OWNER.claim(session,
                        force=os.environ.get("NEXT40_FORCE_OWNER") == "1")
    print(f"owner {owner['session']} pid {owner['pid']}"
          + (f" (took over from {owner['previous_session']})"
             if owner.get("previous_session") else ""), flush=True)
    sha = _sha()
    state = load_state()
    state["live_sha"] = sha
    print(f"base {PJT.BASE}\nlive {sha[:12]}\ncohort {args.cohort}", flush=True)

    targets = [r for r in FORTY
               if (args.only and r[0] in args.only)
               or (not args.only and r[0] in COHORTS[args.cohort])]
    spent, deferred = 0, []
    for (n, name, eid, prefixes, category) in targets:
        key = str(n)
        if done(state["rows"].get(key)) and \
                state["rows"][key].get("live_sha") == sha:
            print(f"{n:02d} {name:20s} SKIP (done on this sha)", flush=True)
            continue
        if spent >= args.max:
            deferred.append(name)
            continue
        print(f"\n== {n:02d} {name}", flush=True)
        row = run_one(n, name, eid, prefixes, category, sha)
        # ONLY AN ADMITTED ANALYSIS SPENDS A SLOT. A company refused at the
        # identity gate never reaches `/analyze`, so counting it would make the
        # runner believe the hour's budget was gone when none of it was used --
        # and the dry run against the pre-catalog build did exactly that,
        # reporting spent=2 for two companies that submitted nothing.
        if row.get("run_id"):
            spent += 1
        state["rows"][key] = row
        save_state(state)
        d = row.get("discovery") or {}
        h = row.get("history") or {}
        print(f"   {row['final_class']:38s} core={row.get('core_s')}s "
              f"hist={row.get('history_level','?')}/"
              f"{h.get('dated_documents','?')}doc "
              f"search={d.get('search_state','?')} "
              f"orig={d.get('independent_origins')} "
              f"qa={(row.get('qa') or {}).get('answered','?')}/6", flush=True)
        for defect in (row.get("defects") or ())[:6]:
            print(f"      - {defect['kind']}: {defect['detail'][:140]}",
                  flush=True)
        if row["final_class"] == "QUOTA_DEFERRED":
            if not args.wait_quota:
                print("   quota refused; rerun to resume", flush=True)
                break
            # THE REFUSAL NAMES ITS OWN WINDOW. A blind hour wastes up to
            # fifty-nine minutes per window, and over four windows that is
            # most of an evening; a window read off the page is exact. A
            # minute of slack is added because the limit is a ROLLING hour and
            # the boundary is the first hit, not this one.
            wait = row.get("retry_after_min")
            wait = (int(wait) + 1) if wait else 61
            print(f"   quota refused; the page says {wait - 1} min, "
                  f"waiting {wait}", flush=True)
            time.sleep(60 * wait)
            spent = 0
            # AND RETRY THE COMPANY THAT WAS REFUSED.
            #
            # MEASURED on cohort A: Dataiku hit the ceiling, the runner waited
            # out the window correctly -- and then continued to Commvault,
            # because the `for` loop had already advanced past it. A refusal
            # is not a result, so the company was left QUOTA_DEFERRED and
            # needed a whole second invocation to pick up. `done()` already
            # treats that state as unfinished, which is why nothing was lost;
            # this just stops a wasted pass.
            print(f"   retrying {name} now the window has cleared", flush=True)
            row = run_one(n, name, eid, prefixes, category, sha)
            if row.get("run_id"):
                spent += 1
            state["rows"][key] = row
            save_state(state)
            print(f"   {row['final_class']:38s} core={row.get('core_s')}s "
                  f"hist={row.get('history_level','?')}", flush=True)
    rows = [state["rows"][str(n)] for (n, *_r) in targets
            if str(n) in state["rows"]]
    cores = [r["core_s"] for r in rows if r.get("core_s")]
    passed = sum(1 for r in rows if r.get("result") == "PASS")
    print(f"\nCOHORT {args.cohort}: {passed}/{len(rows)} PASS  "
          f"spent={spent}  deferred={deferred}")
    if cores:
        print(f"CORE p50 {statistics.median(cores):.1f}s  "
              f"p90 {sorted(cores)[max(0,int(len(cores)*0.9)-1)]:.1f}s  "
              f"max {max(cores):.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
