#!/usr/bin/env python3
"""§20: every V2 close artifact, generated from canonical state.

NOTHING HERE IS TYPED BY HAND, and nothing here trusts an intermediate
artifact it can compute itself. That second rule is not fastidiousness: at
591041b0 `reports/asi25_differentiation.json` was a SEVENTEEN-company file
left over from a mid-run measurement, and the orchestrator's collection step
copied a fresh result over it only `if not target.exists()`. Every
differentiation headline in the previous close described 17 companies and
was reported as describing 25.

So: the state file is the only input taken on trust, every artifact carries
the row count it was computed from, and this script REFUSES to run if any
input it does read is older than the state file.

TWO INSTRUMENTS, ON PURPOSE
---------------------------
Overlap is reported under the forty's own word-set instrument (numerals
stripped) so the two cohorts are comparable, AND under a stricter one that
keeps numerals. On a decision surface stripping numerals is right -- a
shared number is not a shared argument. On the HISTORY surface it removes
almost all of the content: Okta and Procore read 0.9908 identical with
numerals stripped and 0.6407 with them kept, because the years, the index
values and the base year ARE the page. A >=0.98 reading that survives both
instruments is a finding; one that survives only the looser is an
instrument blind spot, and is reported as such.
"""
from __future__ import annotations

import collections
import itertools
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from public_journey_ten import visible                          # noqa: E402

OUT = ROOT / "docs/qualification"
UI25 = ROOT / "reports/asi25_ui"
FORTY_UI = pathlib.Path("/Users/prathamsharma/intent-engine-econ/reports/next40_ui")
FORTY_MATRIX = pathlib.Path(
    "/Users/prathamsharma/intent-engine-econ/docs/qualification/"
    "40_company_qualification_matrix.json")
SURFACES = ("intro", "brief", "full", "xray", "history", "evidence")
_NUM = re.compile(r"\b\d[\d,.%$]*\b")
_CHROME = re.compile(r"home · your analyses|guest demo session|leave demo|"
                     r"strategic intelligence|executive x-ray|history rewind|"
                     r"introduction", re.I)
ABSTAINED = ("RETRIEVAL_LIMITATION_HANDLED_CORRECTLY",
             "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY",
             "DEFENSIBLE_ABSTENTION")


def slug(n):
    return re.sub(r"[^a-z0-9]+", "-", str(n).lower()).strip("-")


def _tokens(ui, company, key, names, keep_numbers):
    p = pathlib.Path(ui) / f"{slug(company)}-{key}.html"
    if not p.exists():
        return set()
    t = " ".join(visible(p.read_text()).split()).lower()
    t = _CHROME.sub(" ", t)
    for n in sorted(names, key=len, reverse=True):
        if len(n) > 2:
            t = t.replace(n.lower(), " ")
    if keep_numbers:
        return set(re.findall(r"[a-z0-9][a-z0-9\-'.,%$]*", t))
    return set(re.findall(r"[a-z][a-z\-']+", _NUM.sub(" ", t)))


def overlap(ui, names, keep_numbers=False):
    out = {}
    for key in SURFACES:
        texts = {c: _tokens(ui, c, key, set(names), keep_numbers) for c in names}
        texts = {c: v for c, v in texts.items() if v}
        js, near = [], []
        for a, b in itertools.combinations(sorted(texts), 2):
            j = len(texts[a] & texts[b]) / len(texts[a] | texts[b])
            js.append(j)
            if j >= 0.98:
                near.append([a, b, round(j, 4)])
        out[key] = {"companies": len(texts), "pairs": len(js),
                    "mean": round(sum(js) / len(js), 4) if js else 0.0,
                    "max": round(max(js), 4) if js else 0.0,
                    "ge_098": len(near), "near": near}
    out["TOTAL"] = {"pairs": sum(out[k]["pairs"] for k in SURFACES),
                    "ge_098": sum(out[k]["ge_098"] for k in SURFACES)}
    return out


def classify(near_by_surface, by):
    """§37: every near-identical pair, with EVERY reason that applies.

    The abstention clause is checked ALONGSIDE the history clause rather
    than before it. With most of the cohort abstaining, "one of them
    abstained" explains almost any pair by construction, and a
    classification that can only ever fire that clause is close to a
    tautology. The number that carries weight is the last one: pairs where
    NEITHER company abstained -- the only ones where a shared reading would
    be two real decisions collapsing onto each other.
    """
    rows, unexplained = [], 0
    for surface, pairs in near_by_surface.items():
        if surface == "TOTAL":
            continue
        for a, b, j in pairs:
            ra, rb = by[a], by[b]
            aa = ra.get("final_class") in ABSTAINED
            ab = rb.get("final_class") in ABSTAINED
            ha = (ra.get("history") or {}).get("dated_documents")
            hb = (rb.get("history") or {}).get("dated_documents")
            reasons = []
            if aa and ab:
                reasons.append("both runs abstained, so there is no reading "
                               "to collapse")
            elif aa or ab:
                reasons.append("one run abstained, so there is no reading to "
                               "collapse")
            if ra.get("history_level") == rb.get("history_level") and ha == hb:
                reasons.append(f"identical history state: level "
                               f"{ra.get('history_level')}, {ha} dated "
                               f"document(s)")
            if not reasons:
                unexplained += 1
            rows.append({"surface": surface, "a": a, "b": b, "jaccard": j,
                         "reasons": reasons,
                         "neither_abstained": not aa and not ab})
    return {"pairs": rows, "total": len(rows),
            "explained": len(rows) - unexplained,
            "unexplained": unexplained,
            "neither_abstained": sum(1 for r in rows
                                     if r["neither_abstained"])}


# --------------------------------------------------------------- Q&A
CHROME_Q = ("Home · Your analyses · Guest demo session Leave demo",
            "Ask a follow-up", "Your question", "Ask", "Suggested:",
            "What does this company do?", "Why does this matter?",
            "What should I do next?")
CLASSES = (
    ("WHY THIS DECISION", ("decision", "chosen", "selected", "rather")),
    ("WHY THIS COMPANY", ("company", "specific", "generic", "rather")),
    ("SUPPORTING EVIDENCE", ("evidence", "support", "source", "record")),
    ("WHAT CONTRADICTS IT", ("against", "weaken", "contradic", "gap")),
    ("WHAT WOULD CHANGE IT", ("change", "would", "commit", "settle", "posture")),
    ("WHAT TO LEARN NEXT", ("learn", "next", "first", "establish", "priority")),
)


def qa_audit(rows):
    """Status AND semantics. A 200 carrying the right company's furniture is
    the failure this exists to catch.

    A GENERIC LEADING WORD IS NOT A COMPANY NAME. Matching the first token
    case-insensitively reported 36 contaminations, every one of them the
    word "material" inside this product's own sentence "everything rests on
    the company's own material", colliding with Material Security. 36 of 36
    identical is the scorer confessing. A multi-word name must appear in
    full; a single-word name must appear CAPITALISED.
    """
    names = [r["company"] for r in rows]
    out = {"rows": [], "primary_total": 0, "primary_status": 0,
           "primary_semantic": 0, "followup_total": 0, "followup_pass": 0,
           "contamination": []}
    for r in rows:
        comp = r["company"]
        others = [n for n in names if n != comp
                  and n.split()[0].lower() not in comp.lower()]

        def foreign(text):
            hits = []
            for o in others:
                if len(o.split()) > 1:
                    if re.search(rf"\b{re.escape(o)}\b", text, re.I):
                        hits.append(o)
                elif re.search(rf"\b{re.escape(o)}\b", text):
                    hits.append(o)
            return hits

        def body(text, q):
            b = " ".join(str(text or "").split())
            for c in CHROME_Q:
                b = b.replace(c, " ")
            b = b.replace(q, " ")
            for n in range(len(q), 20, -5):
                b = b.replace(q[:n], " ")
            return " ".join(b.split())

        qa = r.get("qa") or {}
        for i, d in enumerate(qa.get("detail", [])):
            label, keys = CLASSES[i] if i < len(CLASSES) else ("?", ())
            q, txt = d.get("q", ""), d.get("text", "") or ""
            b = body(txt, q)
            checks = {
                "STATUS_200": d.get("status") == 200,
                "NAMES_THIS_COMPANY": comp.split()[0].lower() in txt.lower(),
                "ANSWERS_THE_QUESTION": any(k in txt.lower() for k in keys),
                "CARRIES_SUBSTANCE": len(b) >= 200,
                "NO_FOREIGN_SUBJECT": not foreign(b),
            }
            out["primary_total"] += 1
            out["primary_status"] += bool(checks["STATUS_200"])
            ok = all(checks.values())
            out["primary_semantic"] += ok
            out["rows"].append({"company": comp, "class": label, "q": q,
                                "status": d.get("status"),
                                "body_chars": len(b), "checks": checks,
                                "semantic": ok})
        out["followup_total"] += 1
        ftxt = qa.get("followup_text", "") or ""
        fb = body(ftxt, "")
        bad = foreign(fb)
        if bad:
            out["contamination"].append({"company": comp, "foreign": bad})
        ok = bool(qa.get("followup")) and comp.split()[0].lower() in ftxt.lower() \
            and len(fb) >= 150 and not bad
        out["followup_pass"] += ok
    return out


def main() -> int:
    state_p = ROOT / "reports/asi25_state.json"
    state = json.loads(state_p.read_text())
    rows = sorted(state["rows"].values(), key=lambda r: int(r["n"]))
    by = {r["company"]: r for r in rows}
    names = [r["company"] for r in rows]
    n = len(rows)
    smt = state_p.stat().st_mtime

    # --- inputs that must not predate the state file -------------------
    stale = []
    read = {}
    for key, rel in (("ui", "reports/asi25_ui_widths.json"),
                     ("dims", "reports/asi25_ten_dimensions.json"),
                     ("econ", "reports/asi25_econ_chain.json"),
                     ("diff", "reports/asi25_differentiation.json"),
                     ("proofs", "reports/break_proofs_asi2.json")):
        p = ROOT / rel
        if not p.exists():
            stale.append(f"{rel}: MISSING")
            continue
        if p.stat().st_mtime < smt:
            stale.append(f"{rel}: older than the state file")
        read[key] = json.loads(p.read_text())
    if stale:
        print("REFUSING: inputs are not current with canonical state:",
              file=sys.stderr)
        for s in stale:
            print("  " + s, file=sys.stderr)
        return 2

    g = lambda r: r.get("generalization") or {}
    v = lambda r: r.get("v2") or {}
    forty = json.loads(FORTY_MATRIX.read_text())
    f_rows = forty["rows"]

    loose = overlap(UI25, names, keep_numbers=False)
    strict = overlap(UI25, names, keep_numbers=True)
    f_loose = overlap(FORTY_UI, [r["company"] for r in f_rows], False)
    cls_loose = classify({k: loose[k]["near"] for k in SURFACES}, by)
    cls_strict = classify({k: strict[k]["near"] for k in SURFACES}, by)
    qa = qa_audit(rows)

    core = sorted(r["core_s"] for r in rows
                  if isinstance(r.get("core_s"), (int, float)))
    def pct(xs, p):
        return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1) if xs else None

    q25 = collections.Counter(g(r).get("decision_question") for r in rows
                              if g(r).get("decision_question"))
    q40 = collections.Counter(r.get("decision_question") for r in f_rows
                              if r.get("decision_question"))
    arch = collections.Counter(g(r).get("archetype_label") for r in rows
                               if g(r).get("archetype_label"))
    ground = collections.Counter(v(r).get("grounding_verdict") for r in rows)
    force = collections.Counter(g(r).get("decision_force") for r in rows)
    chain = collections.Counter()
    for r in rows:
        e = r.get("econ_intel") or {}
        have = sum(bool(e.get(k)) for k in ("names_a_mechanism",
                                            "names_a_falsifier",
                                            "mentions_transmission"))
        chain["COMPLETE" if have == 3 else
              "PARTIAL" if have == 2 else "BOUNDED"] += 1
    learn = {
        "rehearsal_available": sum(
            1 for r in rows if (r.get("learning_surface") or {}).get("available")),
        "claims_forward": sum(
            1 for r in rows
            if (r.get("learning_surface") or {}).get("claims_forward")),
        "labelled_rehearsal": sum(
            1 for r in rows
            if (r.get("learning_surface") or {}).get("labelled_rehearsal")),
        "says_pre_calibration": sum(
            1 for r in rows
            if (r.get("learning_surface") or {}).get("says_pre_calibration")),
    }
    ip = sum(1 for r in rows if (v(r).get("information_priorities") or 0) > 0)
    GENERIC = ("gather more information", "more research", "further analysis",
               "more data", "additional information")
    ip_spec = sum(1 for r in rows
                  if all(k in (v(r).get("priority_text") or "").lower()
                         for k in ("would change:", "best source:"))
                  and not any(x in (v(r).get("priority_text") or "").lower()
                              for x in GENERIC))

    final = {
        "contract": "asi25_v2_close.v1",
        "sha": state.get("live_sha"),
        "companies": n,
        "rows_measured": n,
        "results": dict(collections.Counter(r.get("result") for r in rows)),
        "final_class": dict(collections.Counter(r.get("final_class")
                                                for r in rows)),
        "abstentions": sum(1 for r in rows
                           if r.get("final_class") in ABSTAINED),
        "non_abstentions": [
            {"company": r["company"], "final_class": r["final_class"],
             "grounding": v(r).get("grounding_verdict"),
             "decision_force": g(r).get("decision_force"),
             "independent_origins":
                 (r.get("discovery") or {}).get("independent_origins")}
            for r in rows if r.get("final_class") not in ABSTAINED],
        "qa": {k: qa[k] for k in ("primary_total", "primary_status",
                                  "primary_semantic", "followup_total",
                                  "followup_pass")},
        "qa_contamination": qa["contamination"],
        "performance": {
            "ack": {"p50": pct(sorted(r["submit_ack_s"] for r in rows), .5),
                    "max": max(r["submit_ack_s"] for r in rows),
                    "target": 2.0},
            "visible": {"p50": pct(sorted(r["visible_progress_s"]
                                          for r in rows), .5),
                        "max": max(r["visible_progress_s"] for r in rows),
                        "target": 3.0},
            "core": {"p50": pct(core, .5), "p90": pct(core, .9),
                     "max": core[-1] if core else None, "n": len(core),
                     "targets": {"p50": 60, "p90": 100, "max": 120}},
            "breaches": [r["company"] for r in rows
                         if isinstance(r.get("core_s"), (int, float))
                         and r["core_s"] > 120],
        },
        "ui_matrix": read["ui"].get("totals"),
        "differentiation": {
            "decision_force": dict(force),
            "grounding_verdict": dict(ground),
            "distinct_questions": len(q25),
            "companies_with_a_question": sum(q25.values()),
            "largest_identical_question_group":
                q25.most_common(1)[0][1] if q25 else 0,
            "question_groups": [[k, c] for k, c in q25.most_common()],
            "decision_domain_diversity": len(arch),
            "archetypes": dict(arch),
            "company_specific_mechanism_rate":
                round(1 - ground.get("NAME_ONLY", 0) / n, 3),
            "genericity_failure_rate": round(ground.get("NAME_ONLY", 0) / n, 3),
            "strategic_delta_changed": sum(1 for r in rows
                                           if v(r).get("delta_stated")),
            "strategic_delta_unchanged": n - sum(1 for r in rows
                                                 if v(r).get("delta_stated")),
            "information_priority_rate": round(ip / n, 3),
            "information_priority_specificity": round(ip_spec / n, 3),
        },
        "economic_chain": dict(chain),
        "learning": learn,
        "history_distribution": dict(collections.Counter(
            r.get("history_level") for r in rows)),
        "discovery_distribution": dict(collections.Counter(
            (r.get("discovery") or {}).get("search_state") for r in rows)),
        "overlap": {
            "instrument_forty_numerals_stripped": {
                "twenty_five": {k: {kk: vv for kk, vv in loose[k].items()
                                    if kk != "near"} for k in SURFACES},
                "forty": {k: {kk: vv for kk, vv in f_loose[k].items()
                              if kk != "near"} for k in SURFACES},
                "twenty_five_total": loose["TOTAL"],
                "forty_total": f_loose["TOTAL"],
            },
            "instrument_strict_numerals_kept": {
                k: {kk: vv for kk, vv in strict[k].items() if kk != "near"}
                for k in SURFACES},
        },
        "collapses": {"under_the_fortys_instrument": cls_loose,
                      "under_the_strict_instrument": cls_strict},
        "old_40_vs_new_25": {
            "instrument": "the forty's own word-set overlap, run here over "
                          "both sets of captures",
            "forty": {
                "companies": len(f_rows),
                "decision_force": dict(collections.Counter(
                    r.get("decision_force") for r in f_rows)),
                "distinct_questions": len(q40),
                "companies_with_a_question": sum(q40.values()),
                "largest_identical_question_group":
                    q40.most_common(1)[0][1] if q40 else 0,
                "history_level": dict(collections.Counter(
                    r.get("history_level") for r in f_rows)),
                "grounding_verdict": "ABSENT — the field did not exist",
                "information_priority": "ABSENT — the field did not exist",
                "archetype_label": "ABSENT — the field did not exist",
            },
        },
        "break_proofs": {"held": read["proofs"]["held"],
                         "total": read["proofs"]["total"]},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "25_company_qualification_matrix.json").write_text(
        json.dumps({"contract": "asi25_matrix.v1", "sha": final["sha"],
                    "companies": n, "rows": rows,
                    "ten_dimensions": read["dims"]}, indent=1))
    (ROOT / "reports/asi25_close.json").write_text(json.dumps(final, indent=1))
    (OUT / "25_company_qa_audit.json").write_text(json.dumps(qa, indent=1))
    print(json.dumps({k: final[k] for k in (
        "companies", "results", "final_class", "abstentions", "qa",
        "performance", "differentiation", "economic_chain", "learning",
        "break_proofs")}, indent=1))
    print(f"\ncollapses (forty's instrument): {cls_loose['total']} near, "
          f"{cls_loose['unexplained']} unexplained, "
          f"{cls_loose['neither_abstained']} between two non-abstainers")
    print(f"collapses (strict instrument) : {cls_strict['total']} near, "
          f"{cls_strict['unexplained']} unexplained, "
          f"{cls_strict['neither_abstained']} between two non-abstainers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
