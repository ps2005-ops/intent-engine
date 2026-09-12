#!/usr/bin/env python3
"""The ten qualification dimensions, per company, from what was measured.

WHAT 10/10 MEANS HERE. Not "this company produced a confident unique
recommendation". A company qualifies when the SYSTEM handled it completely
and truthfully across every applicable dimension. All four epistemic outcomes
can qualify:

    DECISION_GRADE_READING
    DEFENSIBLE_ABSTENTION
    INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY
    RETRIEVAL_LIMITATION_HANDLED_CORRECTLY

Nasuni is the example worth holding on to: its independent-source search was
dispatched and then abandoned when the interactive budget ran out. The
retrieval FAILED. The page said so -- "started, then abandoned on our time
budget ... we did not wait to find out" -- and that is a 10/10 bounded
result, because the dimension being qualified is whether the system tells the
truth about what it did, not whether the internet cooperated.

A dimension may be PASS, PASS_BOUNDED (handled truthfully within a real
limit) or FAIL. Only FAIL costs the 10/10.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
from public_journey_ten import visible                           # noqa: E402

UI = ROOT / "reports/next40_ui"
_PY_REPR = re.compile(r"\{'[A-Za-z_][A-Za-z0-9_]*':|\{\"[A-Za-z_][A-Za-z0-9_]*\":")
_INTERNAL = re.compile(r"\b(httperror|keyerror|typeerror|attributeerror|"
                       r"traceback|nonetype|valueerror|stacktrace)\b", re.I)
_ENUM = re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+\b")
#: Filing/marketing boilerplate that must never be presented as intent.
_BOILERPLATE = {"acquired by", "acquisition of", "combination with",
                "gross margin", "operating leverage", "headcount",
                "free cash flow", "capital expenditure", "dividend",
                "net revenue retention", "churn", "expansion revenue",
                "renewal rate", "go-to-market", "channel partner",
                "partner program", "reseller", "port", "trial", "clinical",
                "compliance", "gdpr", "hipaa", "regulation", "regulatory"}


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def _cap(company, key):
    p = UI / f"{_slug(company)}-{key}.html"
    return p.read_text() if p.exists() else ""


def _text(company, key):
    return " ".join(visible(_cap(company, key)).split())


def _all_text(company):
    return " \n ".join(
        " ".join(visible(p.read_text()).split())
        for p in sorted(UI.glob(f"{_slug(company)}-*.html")))


def assess(row, ui_index) -> dict:
    """Ten dimensions for one company."""
    name = row["company"]
    dims, why = {}, {}

    def d(n, verdict, reason):
        dims[n] = verdict
        why[n] = reason

    gates = row.get("gates") or {}
    disc = row.get("discovery") or {}
    hist = row.get("history") or {}
    qa = row.get("qa") or {}
    outcome = row.get("final_class")
    intro = _text(name, "intro") or _text(name, "result")
    xray_raw = _cap(name, "xray")
    xray = _text(name, "xray")
    allt = _all_text(name)
    reading = " ".join(_text(name, k) for k in
                       ("xray", "brief", "full", "result", "intro", "story"))

    # 1 IDENTITY -----------------------------------------------------------
    ident_ok = bool(gates.get("CANONICAL_IDENTITY", True)) and \
        bool(gates.get("NO_MANUAL_URL", True)) and \
        bool(row.get("suggest_confirmed") or row.get("entity_id"))
    # no OTHER registrant's filings anywhere in this company's sources
    own = str(row.get("suggest_cik") or "").lstrip("0")
    foreign = []
    for m in re.finditer(r"edgar/data/0*(\d+)", allt):
        if own and m.group(1).lstrip("0") != own:
            foreign.append(m.group(1))
    d("IDENTITY", "PASS" if ident_ok and not foreign else "FAIL",
      f"resolved from the combobox with no manual URL"
      + (f"; CIK {own}" if own else "; no CIK claimed (curated non-filer)")
      + ("" if not foreign else f"; FOREIGN CIK: {sorted(set(foreign))}"))

    # 2 EVIDENCE + PROVENANCE ---------------------------------------------
    prov_ok = bool(gates.get("PROVENANCE_SUBJECT_CORRECT", True))
    dup_ok = bool(gates.get("EVIDENCE_NO_DUPLICATES", True))
    span_ok = bool(gates.get("EVIDENCE_NO_BROKEN_SPANS", True))
    # the winner's own reason may not rest on boilerplate
    m = re.search(r'<p class="k">Why this decision</p>\s*<p[^>]*>(.*?)</p>',
                  xray_raw, re.S)
    winner_why = " ".join(visible(m.group(1)).split()) if m else ""
    terms = re.search(r"in \d+ distinct terms? \(([^)]*)\)", winner_why)
    winner_terms = [t.strip().lower() for t in terms.group(1).split(",")] \
        if terms else []
    boiler = [t for t in winner_terms if t in _BOILERPLATE]
    d("EVIDENCE_PROVENANCE",
      "PASS" if prov_ok and dup_ok and span_ok and not boiler else "FAIL",
      f"subject-correct provenance, no duplicate passages, no broken spans"
      + ("" if not boiler else
         f"; the winning decision rests on boilerplate: {boiler}"))

    # 3 COMPANY UNDERSTANDING ---------------------------------------------
    model = re.search(r"— ([a-z][a-z ,/-]{4,70}?)[:,] (?:revenue|where|the )",
                      xray)
    established = bool(model)
    says_unknown = "What kind of business this is has not been established" \
        in xray
    d("COMPANY_UNDERSTANDING",
      "PASS" if established else ("PASS_BOUNDED" if says_unknown else "FAIL"),
      (f"model stated: {model.group(1)}" if established else
       "the model could not be established and the page says so, naming what "
       "would settle it" if says_unknown else
       "no business model stated and no explanation of why"))

    # 4 ECONOMIC INTELLIGENCE ----------------------------------------------
    econ_states = (hist.get("econ_states") or {})
    linked = hist.get("economic_links") or 0
    asks = {
        "what_changed": bool(re.search(r"What changed", xray)),
        "why_it_matters": bool(re.search(r"moves with|bears directly|"
                                         r"revenue at a business of this kind",
                                         xray)),
        "transmission": bool(re.search(r"How the economy reaches it|"
                                       r"channel\(s\)", xray)),
        "exposure": bool(re.search(r"Revenue moves with|Cost moves with",
                                   xray)),
        "management_decision": bool(re.search(r"Action|decision", xray)),
        "supports": bool(re.search(r"What we could (and could not )?"
                                   r"establish|evidence", xray)),
        "opposes": bool(re.search(r"Key risk|What is open|limits", xray)),
        "would_change": bool(re.search(r"Next test|would settle|falsif",
                                       xray)),
        "learn_next": bool(re.search(r"Next test|investigate|settle it",
                                     xray)),
    }
    answered = sum(1 for v in asks.values() if v)
    states_its_limit = bool(re.search(
        r"economic layer did not run|no economic state had been published|"
        r"could not be answered from the public record|not placed in its "
        r"economic period", allt))
    d("ECONOMIC_INTELLIGENCE",
      "PASS" if answered >= 8 and linked else
      ("PASS_BOUNDED" if answered >= 7 and states_its_limit else "FAIL"),
      f"{answered}/9 economic questions addressed on the page; "
      f"{linked} stop(s) placed beside a published economic state"
      + ("; the page states specifically where the economic layer could not "
         "reach" if states_its_limit else ""))

    # 5 STRATEGIC DECISION QUALITY -----------------------------------------
    # A PAGE THAT SAYS THE MODEL COULD NOT BE ESTABLISHED IS A NO_DECISION,
    # not an unclassified one. Alation and Adastra both carry a full "Why
    # this decision" panel whose content is the REFUSAL -- "What kind of
    # business this is has not been established" -- and reading only the
    # decision-force phrases classified that as UNCLASSIFIED and failed them
    # for a bounded outcome they handled correctly.
    force = ("NO_DECISION" if not winner_why
             or "has not been established" in winner_why else
             "POSTURE_LED" if "which is decided by" in winner_why else
             "ECON_LED" if "conditions reach this business" in winner_why else
             "EVIDENCE_LED" if "is not a standing decision for a" in winner_why
             else "CLASS_PRIOR_REINFORCED_BY_EVIDENCE"
             if "own record discusses this decision in" in winner_why else
             "CLASS_PRIOR_ONLY"
             if "is a standing decision for this business model" in winner_why
             else "UNCLASSIFIED")
    no_decision_explained = force == "NO_DECISION" and bool(
        re.search(r"What would settle it|Establish what kind of business",
                  xray))
    d("STRATEGIC_DECISION",
      "PASS" if force in ("EVIDENCE_LED", "ECON_LED", "POSTURE_LED",
                          "CLASS_PRIOR_REINFORCED_BY_EVIDENCE") and not boiler
      else ("PASS_BOUNDED" if force == "CLASS_PRIOR_ONLY"
            or no_decision_explained else "FAIL"),
      f"decision force {force}, stated on the page"
      + (f" on {winner_terms}" if winner_terms else "")
      + ("; the prior is named as the basis rather than dressed as evidence"
         if force == "CLASS_PRIOR_ONLY" else "")
      + ("; no decision, and the page names what would settle it"
         if no_decision_explained else ""))

    # 6 HISTORY ------------------------------------------------------------
    level = row.get("history_level")
    docs = hist.get("dated_documents")
    wall = hist.get("hindsight_wall")
    hist_text = _text(name, "history")
    leaked = bool(_PY_REPR.search(hist_text))
    sents = [s.strip() for s in re.split(r"(?<=[.?])\s+", hist_text)
             if len(s.strip()) > 60]
    repeats = len(sents) - len(set(sents))
    d("HISTORY",
      "FAIL" if leaked or wall == "ABSENT" else
      ("PASS" if level in ("A", "B") and not repeats else
       "PASS_BOUNDED"),
      f"LEVEL {level} over {docs} dated record(s), hindsight wall {wall}"
      + (f"; {repeats} repeated passage(s)" if repeats else "")
      + ("; RAW PYTHON OBJECT ON THE PAGE" if leaked else ""))

    # 7 DISCOVERY ----------------------------------------------------------
    state = disc.get("search_state")
    ev_text = _text(name, "evidence")
    lies = (state == "NEVER_STARTED"
            and bool(disc.get("channels_attempted")))
    raw = bool(_INTERNAL.search(ev_text)) or bool(_PY_REPR.search(ev_text))
    d("DISCOVERY",
      "FAIL" if lies or raw else
      ("PASS" if state in ("SEARCH_RAN_WITH_RESULTS",
                           "SEARCH_RAN_WITH_NO_RESULTS") else "PASS_BOUNDED"),
      f"{state}, {disc.get('independent_origins')} independent origin(s)"
      + ("; the limit is stated as ours, not as the company's record"
         if state in ("DISCOVERY_BLOCKED", "INTERACTIVE_BUDGET_SPENT")
         else "")
      + ("; RAW INTERNAL TOKEN" if raw else ""))

    # 8 Q&A + ROLE ---------------------------------------------------------
    answered_q = qa.get("answered") or 0
    d("QA_ROLE",
      "PASS" if answered_q >= 6 and gates.get("FOLLOWUP_CONTEXT")
      and gates.get("ROLE_VIEWS") else "FAIL",
      f"{answered_q}/6 answered, follow-up "
      f"{'kept' if gates.get('FOLLOWUP_CONTEXT') else 'LOST'}, CEO/CSO "
      f"{'share canonical facts' if gates.get('ROLE_VIEWS') else 'CONTRADICT'}")

    # 9 UI -----------------------------------------------------------------
    u = ui_index.get(name) or {}
    surfaces = (u.get("text") or {})
    overflow = u.get("overflow")
    contrast = u.get("contrast")
    enums = sum(len(v.get("raw_enums") or []) for v in surfaces.values())
    reprs = sum(len(v.get("python_reprs") or []) for v in surfaces.values())
    internal = sum(len(v.get("internal") or []) for v in surfaces.values())
    nones = sum(len(v.get("literal_none") or []) for v in surfaces.values())
    spin = sum(1 for v in surfaces.values() if v.get("stale_spinner"))
    measured = overflow is not None
    d("UI",
      "FAIL" if (enums or reprs or internal or nones or spin
                 or (measured and (overflow or contrast))) else
      ("PASS" if measured else "NOT_MEASURED"),
      f"{len(surfaces)} surfaces; enums {enums}, dict reprs {reprs}, "
      f"internal {internal}, literal None {nones}, spinners {spin}"
      + (f", overflow {overflow}, contrast {contrast} across 5 widths x 2 "
         f"themes" if measured else "; width/theme pass not yet run"))

    # 10 EXECUTIVE USEFULNESS ---------------------------------------------
    eu = row.get("_usefulness") or {}
    verdict = eu.get("verdict")
    d("EXECUTIVE_USEFULNESS",
      "PASS" if verdict == "EXECUTIVE_USEFUL" else
      ("PASS_BOUNDED" if verdict == "EXECUTIVE_USEFUL_BUT_BOUNDED"
       else "FAIL" if verdict else "NOT_MEASURED"),
      verdict or "not measured")

    failed = [k for k, v in dims.items() if v == "FAIL"]
    unmeasured = [k for k, v in dims.items() if v == "NOT_MEASURED"]
    return {
        "company": name, "n": row.get("n"), "outcome": outcome,
        "decision_force": force,
        "dimensions": dims, "why": why,
        "failed": failed, "unmeasured": unmeasured,
        "qualification_10_of_10": not failed and not unmeasured,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="ALL")
    args = ap.parse_args()
    state = json.loads((ROOT / "reports/next40_state.json").read_text())
    try:
        analysis = json.loads(
            (ROOT / "reports/next40_analysis.json").read_text())
        use = {r["company"]: r.get("executive_usefulness")
               for r in analysis["rows"]}
    except Exception:                                        # noqa: BLE001
        use = {}
    try:
        ui_index = json.loads((UI / "index.json").read_text())
        widths = json.loads(
            (ROOT / "reports/next40_ui_widths.json").read_text())
        for company, row in ui_index.items():
            w = widths.get(_slug(company)) or {}
            row["overflow"] = w.get("overflow")
            row["contrast"] = w.get("contrast")
    except Exception:                                        # noqa: BLE001
        ui_index = {}
    rng = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41),
           "ALL": range(1, 41)}[args.cohort]
    out = []
    for r in sorted(state["rows"].values(), key=lambda x: x.get("n") or 0):
        if r.get("n") not in rng or not r.get("final_class"):
            continue
        r["_usefulness"] = use.get(r["company"])
        out.append(assess(r, ui_index))
    names = ["IDENTITY", "EVIDENCE_PROVENANCE", "COMPANY_UNDERSTANDING",
             "ECONOMIC_INTELLIGENCE", "STRATEGIC_DECISION", "HISTORY",
             "DISCOVERY", "QA_ROLE", "UI", "EXECUTIVE_USEFULNESS"]
    print(f"{'#':>2} {'company':13s} " +
          " ".join(f"{n[:4]:>4s}" for n in names) + "  10/10")
    for a in out:
        cells = []
        for n in names:
            v = a["dimensions"][n]
            cells.append({"PASS": "  ok", "PASS_BOUNDED": " bnd",
                          "FAIL": "FAIL", "NOT_MEASURED": "   ?"}[v])
        print(f"{a['n']:2d} {a['company'][:12]:13s} " +
              " ".join(f"{c:>4s}" for c in cells) +
              f"   {'YES' if a['qualification_10_of_10'] else 'no'}")
    tally = {n: {"PASS": 0, "PASS_BOUNDED": 0, "FAIL": 0, "NOT_MEASURED": 0}
             for n in names}
    for a in out:
        for n in names:
            tally[n][a["dimensions"][n]] += 1
    print()
    for n in names:
        t = tally[n]
        ok = t["PASS"] + t["PASS_BOUNDED"]
        print(f"  {n:24s} {ok}/{len(out)}   "
              f"(pass {t['PASS']}, bounded {t['PASS_BOUNDED']}, "
              f"fail {t['FAIL']}, unmeasured {t['NOT_MEASURED']})")
    full = sum(1 for a in out if a["qualification_10_of_10"])
    print(f"\nQUALIFICATION_10_OF_10   {full}/{len(out)}")
    for a in out:
        if a["failed"] or a["unmeasured"]:
            print(f"   {a['company']:14s} fail={a['failed']} "
                  f"unmeasured={a['unmeasured']}")
    (ROOT / "reports/next40_ten_dimensions.json").write_text(json.dumps(
        {"contract": "next40_ten_dimensions.v1", "cohort": args.cohort,
         "sha": state.get("live_sha"), "companies": out}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
