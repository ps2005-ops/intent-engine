#!/usr/bin/env python3
"""The canonical qualification matrix, re-derived from the captures (§2-§3).

WHY THIS EXISTS RATHER THAN THE RUNNER'S OWN `generalization` RECORD. The
runner scraped the X-Ray for "own record discusses this decision in N distinct
terms" -- and the X-Ray states that sentence for EVERY candidate it weighed,
under "Decisions we considered and did not select". So the scrape attributed a
REJECTED candidate's evidence to the WINNER: Cohesity's Pricing decision was
recorded as carrying three supply-chain terms it never claimed, and HYCU's as
carrying the regulatory terms of the decision it was ranked above.

The winner's reason has its own anchor in the markup -- `<p class="k">Why this
decision</p>` followed by its paragraph -- and that anchor is what this module
reads. One decision, one reason, one evidence list.

TWO AXES, NOT ONE FLAG. "Which force selected this decision" and "did the
evidence change the decision" are different questions, and one status answering
both hides the interesting case: SALES_MOTION is ON the subscription-software
menu, so a company whose record moves it above PRICING is reported by the page
as a standing decision -- while the evidence is what actually chose it. So
FORCE is what the page says, and CHANGED compares the winner against what the
class prior alone would have picked (the first archetype on the model's menu).
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
from public_journey_ten import visible                           # noqa: E402

UI = ROOT / "reports/next40_ui"

#: The first archetype on each model class's standing menu: what the class
#: prior alone would choose for a company of this kind, with no evidence, no
#: measured channel and no posture. Read from the profile tables rather than
#: assumed, so a menu reordering cannot silently invalidate this column.
def _prior_first() -> dict:
    src = (ROOT / "src/intent_engine/executive/company_profile.py").read_text()
    out = {}
    for m in re.finditer(r'\n    "([A-Z_]+)": \{', src):
        blk = src[m.end():m.end() + 3000]
        a = re.search(r'"archetypes": \(([^)]*)\)', blk)
        if a:
            first = [x.strip().strip('"') for x in a.group(1).split(",")
                     if x.strip()]
            if first:
                out[m.group(1)] = first[0]
    return out


_CHROME = set(
    "the a an and or of to in for on with by is are was were be been this "
    "that it its as at from not no any all we our you your they their what "
    "which who when how why if then than so such more most less least "
    "company companies business evidence analysis reading decision strategic "
    "strategy management page pages document documents source sources date "
    "dated published retrieved record records level question".split())


def _words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _CHROME}


def _cap(slug, key):
    p = UI / f"{slug}-{key}.html"
    return p.read_text() if p.exists() else ""


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


# --- the winner's own panel -------------------------------------------------

def _why_block(html: str) -> str:
    """The WINNING decision's reason, and nothing else on the page."""
    m = re.search(r'<p class="k">Why this decision</p>\s*<p[^>]*>(.*?)</p>',
                  html, re.S)
    return " ".join(visible(m.group(1)).split()) if m else ""


def _considered(html: str):
    """The rejected candidates, each with its own rationale (§P1-6)."""
    m = re.search(r"Decisions we considered and did not select(.*?)"
                  r"(?:<h2|</main|Ask a follow-up)", html, re.S)
    if not m:
        return []
    seg = m.group(1)
    out = []
    for row in re.finditer(r"<p[^>]*>(.*?)</p>\s*<p[^>]*>(.*?)</p>", seg,
                           re.S):
        label = " ".join(visible(row.group(1)).split())
        why = " ".join(visible(row.group(2)).split())
        if label and why:
            out.append({"archetype": label, "why": why})
    return out


_TERMS = re.compile(r"own record discusses this decision in (\d+) distinct "
                    r"terms? \(([^)]*)\)")


def _force(why: str, has_decision: bool):
    if not has_decision:
        return "NO_DECISION"
    if "which is decided by" in why or "operating posture has been identified" \
            in why:
        return "POSTURE_LED"
    if "conditions reach this business" in why:
        return "ECON_LED"
    off_menu = "is not a standing decision for a" in why
    if off_menu:
        return "EVIDENCE_LED"
    if _TERMS.search(why):
        return "CLASS_PRIOR_REINFORCED_BY_EVIDENCE"
    if "is a standing decision for this business model" in why:
        return "CLASS_PRIOR_ONLY"
    return "UNCLASSIFIED"


def _dated_documents(row, slug):
    """The count the history page states, including the LEVEL C zero.

    The runner recorded None where the page says "No document retrieved for X
    carried a date" -- a real number, stated plainly, read as a missing
    measurement.
    """
    h = row.get("history") or {}
    known = h.get("dated_documents")
    if known is not None:
        return known
    text = " ".join(visible(_cap(slug, "history")).split())
    if re.search(r"No document retrieved for .{0,90}?carried a date", text):
        return 0
    m = re.search(r"(\d+) dated (?:document|filing|record)", text)
    return int(m.group(1)) if m else None


def analyse(row, priors) -> dict:
    slug = _slug(row.get("company"))
    xray = _cap(slug, "xray")
    intro = visible(_cap(slug, "intro") or _cap(slug, "result"))
    xtext = " ".join(visible(xray).split())
    why = _why_block(xray)

    lab = re.search(r"([A-Z][a-z]+(?: [a-z]+)*) decision For ", xtext)
    q = re.search(r"For [^:]{1,80}:\s*(.{15,220}?\?)", xtext)
    # The model is stated after the SECOND "<Name> —", and its clause ends
    # with a colon for some classes and a comma for others -- matching only
    # the colon read a stated model as absent on Dataiku's page.
    bm = re.search(r"— ([a-z][a-z ,/-]{4,70}?)[:,] (?:revenue|where|the )",
                   xtext)
    # THE LENS FROM THE TITLE, not from the prose. "Introduction <Name> <LENS>"
    # has no delimiter between the name and the lens, so a prose match ate the
    # company name's first character into the lens.
    lens = re.search(r"<title>[^<—]*—\s*([^<]{3,80})</title>",
                     _cap(slug, "intro") or _cap(slug, "result"))
    lens2 = re.search(r"Also reading through ([^.]{3,70})\.", intro)
    terms = _TERMS.search(why)
    ranked = re.search(r"ranked above ([a-z ]+?) on the same evidence", why)
    has_decision = bool(lab and q)
    force = _force(why, has_decision)
    model_class = (row.get("profile_model_class") or "").upper()
    if not model_class:
        # The page states the model in English; map it back to the class whose
        # menu decides the prior, which is what the CHANGED column compares to.
        english = (bm.group(1) if bm else "").lower()
        model_class = ("SUBSCRIPTION_SOFTWARE"
                       if "subscription" in english or "software" in english
                       else "PEOPLE_OR_ROUTE_BASED_SERVICES"
                       if "people" in english or "route" in english
                       or "services" in english else "")
    prior_first = priors.get(model_class, "")
    arch = (lab.group(1) if lab else "")
    changed = None
    if has_decision and prior_first:
        changed = (arch.upper().replace(" ", "_") != prior_first)
    g = row.get("gates") or {}
    d = row.get("discovery") or {}
    h = row.get("history") or {}
    qa = row.get("qa") or {}
    return {
        "n": row.get("n"), "company": row.get("company"),
        "category": row.get("category"), "outcome": row.get("final_class"),
        # Carried so every downstream reader can tell a run that produced no
        # report from one that produced a thin one. Without it, four separate
        # checks marked a correct refusal as a failure.
        "bounded_page": bool(row.get("bounded_page")),
        "live_sha": row.get("live_sha"),
        "failed_gates": row.get("failed_gates") or [],
        "ack_s": row.get("submit_ack_s"), "visible_s":
            row.get("visible_progress_s"), "core_s": row.get("core_s"),
        "history_level": row.get("history_level"),
        "history_documents": _dated_documents(row, slug),
        "hindsight_wall": h.get("hindsight_wall"),
        "economic_links": h.get("economic_links"),
        "stops": h.get("stops"),
        "discovery_state": d.get("search_state"),
        "independent_origins": d.get("independent_origins"),
        "discovery_reused": d.get("reused"),
        "business_model": bm.group(1) if bm else None,
        "model_class": model_class or None,
        "primary_lens": (lens.group(1).replace("&amp;", "&").strip()
                         if lens else None),
        "secondary_lens": (lens2.group(1).strip() if lens2 else None),
        "decision_archetype": arch or None,
        "decision_question": " ".join(q.group(1).split()) if q else None,
        "decision_force": force,
        "class_prior_alone_would_choose": prior_first or None,
        "evidence_changed_decision": changed,
        "evidence_term_count": int(terms.group(1)) if terms else (
            0 if has_decision else None),
        "evidence_terms": ([t.strip() for t in terms.group(2).split(",")
                            if t.strip()] if terms else []),
        "ranked_above": ranked.group(1).strip() if ranked else None,
        "why": why,
        "considered": _considered(xray),
        "provenance_status": ("SUBJECT_CORRECT"
                              if g.get("PROVENANCE_SUBJECT_CORRECT", True)
                              else "WRONG_SUBJECT"),
        "duplicate_status": ("NONE" if g.get("EVIDENCE_NO_DUPLICATES")
                             else "PRESENT"),
        "broken_span_status": ("NONE" if g.get("EVIDENCE_NO_BROKEN_SPANS")
                              else "PRESENT"),
        "profile_consistency": ("CONSISTENT" if g.get("PROFILE_CONSISTENCY")
                                else "CONTRADICTION"),
        "qa_answered": qa.get("answered"), "qa_total": 6,
        "followup": bool(g.get("FOLLOWUP_CONTEXT")),
        "role_consistency": ("CONSISTENT" if g.get("ROLE_VIEWS") else "FAIL"),
        "xray_text": xtext,
        "neutralised_gates": sorted((row.get("neutralised_gates") or {})),
        "gates_passed": sum(1 for v in g.values() if v),
        "gates_total": len(g),
    }


def cohort(rows):
    """§3. The cohort-level generalization numbers, with the mechanism."""
    live = [r for r in rows if r["decision_question"]]
    qs, arcs = {}, {}
    for r in live:
        qs.setdefault(r["decision_question"], []).append(r["company"])
        arcs.setdefault(r["decision_archetype"], []).append(r["company"])
    ov = []
    for a, b in itertools.combinations(sorted(rows, key=lambda r: r["n"]), 2):
        wa, wb = _words(a["xray_text"]), _words(b["xray_text"])
        if wa and wb:
            ov.append({"jaccard": round(len(wa & wb) / len(wa | wb), 3),
                       "a": a["company"], "b": b["company"],
                       "same_category": a["category"] == b["category"],
                       "same_question": (a["decision_question"]
                                         == b["decision_question"])})
    ov.sort(key=lambda x: -x["jaccard"])
    cross = [o for o in ov if not o["same_category"]]
    forces = {}
    for r in rows:
        forces[r["decision_force"]] = forces.get(r["decision_force"], 0) + 1
    shared = {q: c for q, c in qs.items() if len(c) > 1}
    return {
        "companies": len(rows), "with_decision": len(live),
        "distinct_decision_archetypes": len(arcs),
        "distinct_decision_questions": len(qs),
        "archetypes": {k: v for k, v in sorted(arcs.items())},
        "questions": {k: v for k, v in sorted(qs.items())},
        "shared_questions": shared,
        "force_distribution": dict(sorted(forces.items())),
        "evidence_changed_decision": sum(1 for r in rows
                                         if r["evidence_changed_decision"]),
        "max_xray_overlap": ov[0]["jaccard"] if ov else None,
        "max_cross_category_overlap": cross[0]["jaccard"] if cross else None,
        "top_overlaps": ov[:8],
        "discovery_distribution": _count(rows, "discovery_state"),
        "history_distribution": _count(rows, "history_level"),
        "outcome_distribution": _count(rows, "outcome"),
        "core_p50": _pct([r["core_s"] for r in rows], 50),
        "core_p90": _pct([r["core_s"] for r in rows], 90),
        "core_max": max([r["core_s"] for r in rows if r["core_s"]] or [0]),
        "ack_p50": _pct([r["ack_s"] for r in rows], 50),
        "ack_p90": _pct([r["ack_s"] for r in rows], 90),
        "visible_p50": _pct([r["visible_s"] for r in rows], 50),
        "visible_p90": _pct([r["visible_s"] for r in rows], 90),
        "qa_pass": sum(r["qa_answered"] or 0 for r in rows),
        "qa_total": 6 * len(rows),
        "followups": sum(1 for r in rows if r["followup"]),
    }


def _count(rows, key):
    out = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return dict(sorted(out.items()))


def _pct(vals, p):
    v = sorted(x for x in vals if x)
    if not v:
        return None
    return round(v[min(len(v) - 1, max(0, int(len(v) * p / 100) - (p == 50)))]
                 if p != 50 else statistics.median(v), 2)



# --- §3 explained similarity vs unexplained collapse ------------------------

_NORM_CHROME = re.compile(
    r"home · your analyses|guest demo session|leave demo|strategic "
    r"intelligence|executive x-ray|history rewind|introduction", re.I)


def _norm_bag(company):
    """The substance of a company's X-Ray, with the trivia removed."""
    p = UI / f"{_slug(company)}-xray.html"
    if not p.exists():
        return set()
    text = " ".join(visible(p.read_text()).split()).lower()
    text = _NORM_CHROME.sub(" ", text)
    for part in re.split(r"[^a-z0-9]+", company.lower()):
        if len(part) > 2:
            text = text.replace(part, " ")
    text = re.sub(r"\b(inc|llc|ltd|corp|corporation|nv|lp|plc)\b", " ", text)
    text = re.sub(r"\d[\d,.%$-]*", " ", text)
    return {w for w in re.findall(r"[a-z]{4,}", text)}


def _identical_pairs(companies, floor=0.98):
    """Pairs whose readings are the same reading, not merely alike."""
    bags = {c: _norm_bag(c) for c in companies}
    bags = {c: b for c, b in bags.items() if len(b) > 40}
    out = []
    for a, b in itertools.combinations(sorted(bags), 2):
        j = len(bags[a] & bags[b]) / max(1, len(bags[a] | bags[b]))
        if j >= floor:
            out.append((round(j, 3), a, b))
    out.sort(reverse=True)
    return out


def classify_similarity(rows, question, companies) -> dict:
    """Why these companies share a question, and whether that is honest.

    NOT A SCORE. A lower overlap number with no mechanism behind it is the
    same defect wearing different clothes, so each shared question is
    classified by what the PAGE says decided it:

      EXPLAINED   the companies share a business-model class AND the page
                  states the basis for each -- including the honest case
                  where an evidence-poor company falls back to the class
                  prior and the page says so
      UNEXPLAINED the companies do NOT share a class, or the evidence that
                  supposedly distinguished them is the same vocabulary for
                  all of them, which is a class prior with extra steps
    """
    by = {r["company"]: r for r in rows}
    mine = [by[c] for c in companies if c in by]
    classes = {r["model_class"] for r in mine}
    forces = {r["decision_force"] for r in mine}
    termsets = [frozenset(t.lower() for t in (r["evidence_terms"] or []))
                for r in mine if r["evidence_terms"]]
    evidence_led = [r for r in mine
                    if r["decision_force"] in
                    ("EVIDENCE_LED", "CLASS_PRIOR_REINFORCED_BY_EVIDENCE")]
    shared_terms = (set.intersection(*[set(t) for t in termsets])
                    if termsets and all(termsets) else set())
    reason, verdict = "", "EXPLAINED_SIMILARITY"
    if len(classes) > 1:
        verdict = "UNEXPLAINED_COLLAPSE"
        reason = (f"companies of different business-model classes "
                  f"({', '.join(sorted(str(c) for c in classes))}) were "
                  f"handed one question")
    elif len(evidence_led) > 1 and shared_terms:
        verdict = "UNEXPLAINED_COLLAPSE"
        reason = (f"{len(evidence_led)} companies were said to be "
                  f"evidence-led and their records share the term(s) "
                  f"{', '.join(sorted(shared_terms))} — the same vocabulary "
                  f"justifying the same question for different companies, "
                  f"which is a class prior with extra steps")
    elif forces == {"CLASS_PRIOR_ONLY"}:
        reason = ("every company here is evidence-poor and the page states "
                  "the class prior as its basis, which is the fallback the "
                  "brief asked to preserve")
    else:
        reason = ("one business-model class, and the page states a basis for "
                  "each: "
                  + "; ".join(f"{r['company']}={r['decision_force']}"
                              + (f" on {', '.join(r['evidence_terms'])}"
                                 if r["evidence_terms"] else "")
                              for r in mine))
    # EXPLAINED IS ABOUT WHY THEY SHARE A QUESTION. IT IS NOT A CLAIM THAT
    # THE REST OF THE READING DIFFERS.
    #
    # MEASURED across the forty, after normalising away company name, legal
    # suffixes, dates, numbers and demo chrome: several X-Ray pairs score a
    # Jaccard of 1.000 — Airbyte and Clari, Airbyte and SnapLogic, Dremio and
    # Recorded Future. Those are not similar pages, they are the same page
    # with a different name in it. The similarity is honestly EXPLAINED (one
    # business model, an evidence-poor record, and the page says the class
    # prior chose the question) and the reading is still not company-specific.
    #
    # Reporting only EXPLAINED would let a reader infer differentiation that
    # is not there, so the identical case is named separately.
    identical = _identical_pairs(companies)
    if verdict == "EXPLAINED_SIMILARITY" and identical:
        verdict = "EXPLAINED_QUESTION_IDENTICAL_READING"
        reason += (f". But their readings are not merely similar: "
                   f"{len(identical)} pair(s) score >= 0.98 substantive "
                   f"overlap after the company name, dates and numbers are "
                   f"removed — e.g. "
                   + "; ".join(f"{a} / {b} at {j}"
                               for j, a, b in identical[:3])
                   + ". The question is explained; the reading is not "
                     "company-specific")
    return {"question": question, "companies": list(companies),
            "verdict": verdict, "reason": reason,
            "identical_pairs": identical,
            "model_classes": sorted(str(c) for c in classes),
            "forces": sorted(forces),
            "shared_evidence_terms": sorted(shared_terms)}


# --- §16 executive usefulness ----------------------------------------------

def executive_usefulness(r) -> dict:
    """Useful to a decision-maker, useful but bounded, or not useful.

    NO INVENTED NUMBER. Each verdict names the properties that produced it,
    and every property is something measured elsewhere in this row.
    """
    strengths, limits, blockers = [], [], []
    if r["decision_question"]:
        strengths.append("states one decision in the business's own variables")
    else:
        limits.append("states no decision: the business model could not be "
                      "established from the public record")
    if r["decision_force"] == "EVIDENCE_LED":
        strengths.append(
            f"the decision came from the company's own record "
            f"({r['evidence_term_count']} terms: "
            f"{', '.join(r['evidence_terms'])}) and outranked the class prior")
    elif r["decision_force"] == "CLASS_PRIOR_REINFORCED_BY_EVIDENCE":
        strengths.append(
            f"the class prior is corroborated by the company's own record "
            f"({r['evidence_term_count']} terms)")
    elif r["decision_force"] == "CLASS_PRIOR_ONLY":
        limits.append("the decision is the standing question for the business "
                      "model with nothing company-specific behind it, and the "
                      "page says so")
    if r["independent_origins"]:
        strengths.append(f"{r['independent_origins']} independent origin(s) "
                         f"corroborate the reading")
    else:
        limits.append("no independent origin: direction is better founded "
                      "than magnitude, which the page states")
    if r["history_level"] == "A":
        strengths.append(f"a financial series over {r['history_documents']} "
                         f"dated filings")
    elif r["history_level"] == "B":
        strengths.append(f"{r['history_documents']} dated documents walked in "
                         f"order with a hindsight wall "
                         f"{str(r['hindsight_wall']).lower()}")
    else:
        limits.append("too thin a dated record to rewind")
    if r["discovery_state"] == "NEVER_STARTED":
        limits.append("the page claims no search was run over a search that "
                       "was dispatched and abandoned")
    # THE ONE THING THAT MAKES A READING NOT USEFUL RATHER THAN BOUNDED: the
    # economics are the wrong economics, so every variable in the question is
    # the wrong variable.
    if r["model_class"] == "PEOPLE_OR_ROUTE_BASED_SERVICES" and \
            "software" in str(r["primary_lens"] or "").lower() + \
            str(r["category"] or "").lower():
        blockers.append("classified as a people-or-route services business, "
                        "so the decision is posed in billable-headcount "
                        "variables a software company does not have")
    if blockers:
        verdict = "NOT_EXECUTIVE_USEFUL"
    elif not r["decision_question"]:
        verdict = "EXECUTIVE_USEFUL_BUT_BOUNDED"
    elif r["decision_force"] in ("EVIDENCE_LED",
                                 "CLASS_PRIOR_REINFORCED_BY_EVIDENCE") \
            and r["history_level"] in ("A", "B"):
        verdict = "EXECUTIVE_USEFUL"
    else:
        verdict = "EXECUTIVE_USEFUL_BUT_BOUNDED"
    return {"verdict": verdict, "strengths": strengths, "limits": limits,
            "blockers": blockers}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="A")
    ap.add_argument("--out", default="reports/next40_analysis.json")
    args = ap.parse_args()
    state = json.loads((ROOT / "reports/next40_state.json").read_text())
    priors = _prior_first()
    rng = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41),
           "ALL": range(1, 41)}[args.cohort]
    rows = [analyse(r, priors) for r in state["rows"].values()
            if r.get("n") in rng and r.get("final_class")
            and r["final_class"] != "QUOTA_DEFERRED"]
    rows.sort(key=lambda r: r["n"])
    summary = cohort(rows)
    summary["similarities"] = [
        classify_similarity(rows, q, c)
        for q, c in summary["shared_questions"].items()]
    summary["explained_high_similarities"] = sum(
        1 for s in summary["similarities"]
        if s["verdict"] == "EXPLAINED_SIMILARITY")
    summary["unexplained_template_collapses"] = sum(
        1 for s in summary["similarities"]
        if s["verdict"] == "UNEXPLAINED_COLLAPSE")
    summary["explained_but_identical_readings"] = sum(
        1 for s in summary["similarities"]
        if s["verdict"] == "EXPLAINED_QUESTION_IDENTICAL_READING")
    summary["identical_reading_pairs"] = sum(
        len(s.get("identical_pairs") or ()) for s in summary["similarities"])
    for r in rows:
        r["executive_usefulness"] = executive_usefulness(r)
        r.pop("xray_text", None)
    summary["executive_usefulness"] = _count(
        [{"v": r["executive_usefulness"]["verdict"]} for r in rows], "v")
    out = {"contract": "next40_analysis.v1", "cohort": args.cohort,
           "sha": state.get("live_sha"), "summary": summary, "rows": rows}
    (ROOT / args.out).write_text(json.dumps(out, indent=1))
    print(f"cohort {args.cohort}  sha {str(state.get('live_sha'))[:12]}  "
          f"{len(rows)} companies\n")
    print(f"{'#':>2} {'company':13s} {'archetype':20s} {'force':38s} "
          f"{'ev':>3} chg")
    for r in rows:
        print(f"{r['n']:2d} {str(r['company'])[:12]:13s} "
              f"{str(r['decision_archetype'])[:19]:20s} "
              f"{r['decision_force']:38s} {str(r['evidence_term_count']):>3} "
              f"{'' if r['evidence_changed_decision'] is None else ('YES' if r['evidence_changed_decision'] else 'no')}")
    s = summary
    print(f"\nDISTINCT_DECISION_ARCHETYPES  {s['distinct_decision_archetypes']}"
          f" / {s['with_decision']}")
    print(f"DISTINCT_DECISION_QUESTIONS   {s['distinct_decision_questions']}"
          f" / {s['with_decision']}")
    print(f"EVIDENCE_CHANGED_DECISION     {s['evidence_changed_decision']}"
          f" / {s['with_decision']}")
    for k, v in s["force_distribution"].items():
        print(f"  {k:40s} {v}")
    print(f"MAX_XRAY_OVERLAP              {s['max_xray_overlap']}")
    print(f"MAX_CROSS_CATEGORY_OVERLAP    {s['max_cross_category_overlap']}")
    print("\nshared questions:")
    for sim in s["similarities"]:
        print(f"  {len(sim['companies'])}x  {sim['question'][:66]}")
        print(f"      {', '.join(sim['companies'])}")
        print(f"      {sim['verdict']}: {sim['reason'][:200]}")
    print(f"\nEXPLAINED_HIGH_SIMILARITIES     "
          f"{s['explained_high_similarities']}")
    print(f"UNEXPLAINED_TEMPLATE_COLLAPSES  "
          f"{s['unexplained_template_collapses']}")
    print("\nEXECUTIVE USEFULNESS")
    for k, v in s["executive_usefulness"].items():
        print(f"  {k:34s} {v}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
