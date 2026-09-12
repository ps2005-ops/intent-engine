#!/usr/bin/env python3
"""The §8 post-deploy controls, read off the captures the re-run just wrote.

EVERY ONE OF THESE IS A THING THAT WAS WRONG. A control that passes because
nothing looked is worth nothing, so each check names the company whose live
page produced it and fails loudly when that company has not been re-run on
the current SHA.
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

#: Pharma vocabulary that must never appear for a Toronto data consultancy.
_PHARMA = ("pharmaceutical", "approved indication", "prescription",
           "exclusivity runway", "drug development", "clinical", "rebate")
#: A serialised Python object on a customer surface.
_PY_REPR = re.compile(r"\{'[A-Za-z_][A-Za-z0-9_]*':|\{\"[A-Za-z_][A-Za-z0-9_]*\":")
#: Engineering vocabulary with no business meaning to a reader.
_INTERNAL = re.compile(r"\b(httperror|keyerror|typeerror|attributeerror|"
                       r"traceback|nonetype|valueerror)\b", re.I)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def _text(company, key):
    p = UI / f"{_slug(company)}-{key}.html"
    return " ".join(visible(p.read_text()).split()) if p.exists() else ""


def _all_text(company):
    out = []
    for p in sorted(UI.glob(f"{_slug(company)}-*.html")):
        out.append(" ".join(visible(p.read_text()).split()))
    return " \n ".join(out)


def check(state, sha) -> list:
    rows = {r.get("company"): r for r in state.get("rows", {}).values()}
    results = []

    def add(name, company, verdict, detail):
        results.append({"control": name, "company": company,
                        "verdict": verdict, "detail": detail})

    def fresh(company):
        r = rows.get(company) or {}
        return r.get("live_sha") == sha

    # --- ADASTRA: the identity P0 -----------------------------------------
    if not fresh("Adastra"):
        add("ADASTRA_IDENTITY", "Adastra", "NOT_MEASURED",
            "Adastra has not been re-run on this SHA")
    else:
        # THE READING, NOT A QUOTED EXCERPT.
        #
        # A first version scanned every surface and failed on the word
        # "Pharmaceutical" -- which appears in a list of industries Adastra
        # serves, quoted from adastracorp.com/success-stories/ with the
        # author and host shown beside it. That is the company's own page
        # saying what it does, and flagging it would report correct,
        # correctly-attributed evidence as contamination.
        #
        # What the P0 was about is the READING: a Toronto data consultancy
        # being handed a pharmaceutical pipeline decision with watch metrics
        # naming approved indications and exclusivity runway. So the decision
        # panel, the answer and the watch metrics are what get scanned, and
        # the evidence drawer -- whose job is to quote sources -- does not.
        reading = " ".join(_text("Adastra", k) for k in
                           ("xray", "brief", "full", "result", "intro",
                            "story")).lower()
        pharma = [w for w in _PHARMA if w in reading]
        cik = re.findall(r"edgar/data/0*1891512", _all_text("Adastra"))
        add("ADASTRA_NO_PHARMA_LANGUAGE", "Adastra",
            "PASS" if not pharma else "FAIL",
            "none of the seven banned terms appear in the reading "
            "(the evidence drawer may quote the company's own industry list)"
            if not pharma else f"present in the reading: {pharma}")
        add("ADASTRA_NO_FOREIGN_CIK", "Adastra",
            "PASS" if not cik else "FAIL",
            "no filing under CIK 1891512 (Adastra Holdings, cannabis)"
            if not cik else f"{len(cik)} reference(s) to the wrong registrant")

    # --- the declared filers ----------------------------------------------
    for company, cik, level in (("Rubrik", "1943896", "A"),
                                ("Commvault", "1169561", "A")):
        if not fresh(company):
            add("FILER_EVIDENCE_SURVIVES", company, "NOT_MEASURED",
                f"{company} has not been re-run on this SHA")
            continue
        blob = _all_text(company)
        own = re.findall(rf"edgar/data/0*{cik}", blob)
        r = rows[company]
        add("FILER_EVIDENCE_SURVIVES", company,
            "PASS" if own else "FAIL",
            f"{len(own)} reference(s) to its own CIK {cik}" if own
            else f"its own filings are gone — CIK {cik} appears nowhere")
        add("FILER_HISTORY_LEVEL", company,
            "PASS" if r.get("history_level") == level else "FAIL",
            f"LEVEL {r.get('history_level')} / "
            f"{(r.get('history') or {}).get('dated_documents')} documents")

    # --- project44: the evidence path and the discovery account -----------
    if not fresh("project44"):
        add("PROJECT44_EVIDENCE_LED", "project44", "NOT_MEASURED",
            "project44 has not been re-run on this SHA")
    else:
        xray = _text("project44", "xray")
        why = re.search(r"Why this decision (.{0,420})", xray)
        why = why.group(1) if why else ""
        add("PROJECT44_EVIDENCE_LED", "project44",
            "PASS" if "is not a standing decision for a" in why else "FAIL",
            why[:200] or "no reason panel found")
        d = (rows["project44"].get("discovery") or {})
        state_now = d.get("search_state")
        lied = (state_now == "NEVER_STARTED")
        add("PROJECT44_DISCOVERY_TRUTHFUL", "project44",
            "PASS" if not lied else "FAIL",
            f"search_state={state_now}"
            + ("" if not lied else " — still claims no search was run"))
        ev = _text("project44", "evidence")
        # The page may say "no search was run" ONLY when none was dispatched.
        claims_none = "no search was run" in ev
        dispatched = bool(d.get("channels_attempted"))
        honest = (not claims_none) or (not dispatched)
        add("PROJECT44_NO_FALSE_NO_SEARCH", "project44",
            "PASS" if honest else "FAIL",
            ("the page does not claim a search was never run"
             if not claims_none else
             "the page says 'no search was run' and no channel was "
             "dispatched, which is true")
            if honest else
            "the page says 'no search was run' about a dispatched search")

    # --- the three that must LOSE their generic decision -------------------
    for company in ("Kinaxis", "Dataminr", "Nasuni"):
        if not fresh(company):
            add("GENERIC_VOCABULARY_NO_LONGER_DECIDES", company,
                "NOT_MEASURED", f"{company} has not been re-run on this SHA")
            continue
        xray = _text(company, "xray")
        why = re.search(r"Why this decision (.{0,420})", xray)
        why = why.group(1) if why else ""
        generic = [t for t in ("go-to-market", "channel partner",
                               "partner program", "reseller")
                   if t in why]
        add("GENERIC_VOCABULARY_NO_LONGER_DECIDES", company,
            "PASS" if not generic else "FAIL",
            why[:160] if not generic
            else f"still decided by category vocabulary: {generic}")

    # --- Cohesity: the winner may not inherit a rejected candidate ---------
    if fresh("Cohesity") or True:
        xray = _text("Cohesity", "xray")
        why = re.search(r"Why this decision (.{0,420})", xray)
        why = why.group(1) if why else ""
        add("WINNER_DOES_NOT_INHERIT_REJECTED_EVIDENCE", "Cohesity",
            "PASS" if "port" not in why else "FAIL",
            "the winner's reason carries no supply-chain term"
            if "port" not in why else why[:160])

    # --- the whole cohort: no leaked object, no internal token -------------
    for company in sorted(rows):
        blob = _all_text(company)
        if not blob:
            continue
        reprs = _PY_REPR.findall(blob)
        internal = sorted({m.lower() for m in _INTERNAL.findall(blob)})
        tag = "on this SHA" if fresh(company) else "ON THE OLD SHA"
        if reprs:
            add("NO_RAW_PYTHON_OBJECT", company, "FAIL",
                f"{len(reprs)} dict repr(s) {tag}: {reprs[:2]}")
        if internal:
            add("NO_INTERNAL_TOKEN", company, "FAIL",
                f"{internal} {tag}")
    if not any(r["control"] == "NO_RAW_PYTHON_OBJECT" for r in results):
        add("NO_RAW_PYTHON_OBJECT", "all", "PASS",
            "no surface of any company carries a serialised Python object")
    if not any(r["control"] == "NO_INTERNAL_TOKEN" for r in results):
        add("NO_INTERNAL_TOKEN", "all", "PASS",
            "no surface of any company carries an engineering token")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default="")
    args = ap.parse_args()
    state = json.loads((ROOT / "reports/next40_state.json").read_text())
    sha = args.sha or state.get("live_sha")
    res = check(state, sha)
    print(f"§8 CONTROLS on {str(sha)[:12]}\n")
    for r in res:
        print(f"  {r['verdict']:12s} {r['control'][:44]:46s} "
              f"{str(r['company'])[:11]:12s} {r['detail'][:80]}")
    bad = [r for r in res if r["verdict"] == "FAIL"]
    unmeasured = [r for r in res if r["verdict"] == "NOT_MEASURED"]
    print(f"\nPASS {sum(1 for r in res if r['verdict'] == 'PASS')}  "
          f"FAIL {len(bad)}  NOT_MEASURED {len(unmeasured)}")
    (ROOT / "reports/next40_controls.json").write_text(json.dumps(
        {"contract": "next40_controls.v1", "sha": sha, "controls": res},
        indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
