#!/usr/bin/env python3
"""The §11 frozen invariants, evaluated per cohort from what was measured.

WHY THESE AND NOT THE GATES. The per-company gates catch BROKEN. Cohort A
established that the expensive defects are the ones where every affected
company PASSES -- seven companies sharing one decision, a repair that shipped
inert, a cannabis filing read as a consultancy's evidence. Those are
properties of the SET, or of a seam, and an invariant is how a later cohort
answers "did that generalize?" without re-deriving the argument.

HELD / FAILED / N/A, and N/A is a real answer: I03 cannot be tested by a
cohort with no SEC filer in it, and reporting it as HELD would be a test that
cannot fail.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
from public_journey_ten import visible                           # noqa: E402

UI = ROOT / "reports/next40_ui"
RANGES = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41),
          "ALL": range(1, 41)}


def _cap(slug, key):
    p = UI / f"{slug}-{key}.html"
    return p.read_text() if p.exists() else ""


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


#: Structural invariants: properties of the CODE, not of a company. Asserted
#: by naming the test that pins each one, so an invariant cannot be reported
#: as held because no company happened to exercise it.
_BY_TEST = {
    "I02": "tests/test_a_curated_non_filer_is_never_fuzzy_resolved.py",
    "I03": "tests/test_a_curated_non_filer_is_never_fuzzy_resolved.py"
           "::test_a_curated_filer_still_retrieves_its_own_filings",
    "I08": "tests/test_the_xray_composer_sees_the_company_record.py",
    "I21": "tests/test_category_vocabulary_is_not_a_decision.py",
    "I22": "tests/test_a_stop_teaches_something_of_its_own.py",
}


def _run_tests(target: str) -> tuple:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         target], cwd=ROOT, capture_output=True, text=True)
    tail = [l for l in proc.stdout.splitlines() if l.strip()][-1:] or [""]
    return proc.returncode == 0, tail[0][:120]


def evaluate(rows, *, with_tests=True) -> list:
    """Each invariant, with the evidence that decided it."""
    out = []

    def add(iid, name, verdict, evidence):
        out.append({"id": iid, "invariant": name, "verdict": verdict,
                    "evidence": evidence})

    live = [r for r in rows if r.get("decision_question")]

    # I01 canonical identity stable
    bad = [r["company"] for r in rows
           if not r.get("primary_lens") or not r.get("company")]
    add("I01", "canonical identity stable",
        "HELD" if not bad else "FAILED",
        f"{len(rows) - len(bad)}/{len(rows)} carry a canonical name and a "
        f"selected lens" + (f"; missing: {bad}" if bad else ""))

    # I04 foreign evidence never enters the company record. Measured on the
    # SOURCES the run actually read, host by host.
    foreign = []
    for r in rows:
        html = _cap(_slug(r["company"]), "sources") or \
            _cap(_slug(r["company"]), "evidence")
        for m in re.finditer(r"sec\.gov/Archives/edgar/data/(\d+)", html):
            cik = m.group(1).lstrip("0")
            own = str(r.get("subject_cik") or "").lstrip("0")
            if own and cik != own:
                foreign.append(f"{r['company']}:{cik}")
    add("I04", "foreign evidence never enters the company record",
        "HELD" if not foreign else "FAILED",
        "no filing under another registrant's CIK appears in any company's "
        "sources" if not foreign else f"found: {foreign[:5]}")

    # I05 company evidence can outrank the class prior
    led = [r["company"] for r in live if r["decision_force"] == "EVIDENCE_LED"]
    add("I05", "company evidence can outrank the class prior",
        "HELD" if led else ("FAILED" if live else "N/A"),
        f"{len(led)} of {len(live)} decisions were selected off-menu by the "
        f"company's own record: {led}" if led else
        "no company in this cohort reached an off-menu decision, so the path "
        "is unproven here")

    # I06 the class prior remains available for a sparse record
    prior = [r["company"] for r in live
             if r["decision_force"] in ("CLASS_PRIOR_ONLY",
                                        "CLASS_PRIOR_REINFORCED_BY_EVIDENCE")]
    add("I06", "the class prior remains available for a sparse record",
        "HELD" if prior else ("N/A" if not live else "FAILED"),
        f"{len(prior)} of {len(live)} decisions still rest on the standing "
        f"menu, which is the fallback an evidence-poor company needs")

    # I07 the reason states the force that selected the decision
    unstated = [r["company"] for r in live
                if r["decision_force"] == "UNCLASSIFIED" or not r.get("why")]
    add("I07", "the decision reason states the force that selected it",
        "HELD" if not unstated else "FAILED",
        f"{len(live) - len(unstated)}/{len(live)} name their own basis in the "
        f"X-Ray's reason panel" + (f"; silent: {unstated}" if unstated else ""))

    # I09 history level matches the dated evidence actually retrieved
    mismatch = []
    for r in rows:
        lvl, docs = r.get("history_level"), r.get("history_documents")
        if lvl == "C" and (docs or 0) > 1:
            mismatch.append(f"{r['company']}:C/{docs}")
        if lvl in ("A", "B") and (docs or 0) < 2:
            mismatch.append(f"{r['company']}:{lvl}/{docs}")
    add("I09", "history level matches the dated evidence retrieved",
        "HELD" if not mismatch else "FAILED",
        "every level is consistent with its own document count"
        if not mismatch else f"inconsistent: {mismatch}")

    # I10 economic linkage exists only where supported
    over = [r["company"] for r in rows
            if (r.get("economic_links") or 0) > (r.get("stops") or 0)]
    add("I10", "economic linkage exists only where supported",
        "HELD" if not over else "FAILED",
        f"linked stops never exceed walked stops across {len(rows)} companies"
        if not over else f"over-claimed: {over}")

    # I11 the discovery state survives reuse
    lost = [r["company"] for r in rows
            if r.get("discovery_reused") and
            r.get("discovery_state") == "NEVER_STARTED"]
    reused = [r["company"] for r in rows if r.get("discovery_reused")]
    add("I11", "the discovery state survives reuse",
        "HELD" if reused and not lost else ("N/A" if not reused else "FAILED"),
        f"{len(reused)} company/ies reused a source list and none reported "
        f"NEVER_STARTED: {reused}" if reused else
        "no company in this cohort reused a source list")

    # I12 provenance remains subject-correct
    wrong = [r["company"] for r in rows
             if r.get("provenance_status") != "SUBJECT_CORRECT"]
    add("I12", "provenance remains subject-correct",
        "HELD" if not wrong else "FAILED",
        f"{len(rows) - len(wrong)}/{len(rows)}" +
        (f"; wrong subject: {wrong}" if wrong else ""))

    # I13 evidence cannot widen the responsive UI. Read from the §17 scan,
    # which measured every surface -- not from the analysis row, which never
    # carried this field and therefore reported a comfortable zero.
    try:
        idx = json.loads((UI / "index.json").read_text())
    except Exception:                                        # noqa: BLE001
        idx = {}
    widths = [(v.get("longest_token") or 0, c, k)
              for c, row in idx.items() if c in {r["company"] for r in rows}
              for k, v in (row.get("text") or {}).items()]
    widest = max(widths, default=(0, "", ""))
    add("I13", "evidence cannot widen the responsive UI",
        "HELD" if widths and widest[0] <= 120 else
        ("N/A" if not widths else "FAILED"),
        f"longest unbreakable token across "
        f"{len(widths)} surfaces is {widest[0]} chars "
        f"({widest[1]}{widest[2] and '/' + widest[2]}); the quote rule wraps "
        f"at any length" if widths else
        "the §17 scan has not been run for these companies")

    # I14/I15 Q&A and follow-up
    qa_bad = [r["company"] for r in rows if (r.get("qa_answered") or 0) < 6]
    add("I14", "Q&A answers the current company and the current run",
        "HELD" if not qa_bad else "FAILED",
        f"{sum(r.get('qa_answered') or 0 for r in rows)}/{6 * len(rows)} "
        f"answered" + (f"; short: {qa_bad}" if qa_bad else ""))
    fu_bad = [r["company"] for r in rows if not r.get("followup")]
    add("I15", "a follow-up preserves its context",
        "HELD" if not fu_bad else "FAILED",
        f"{len(rows) - len(fu_bad)}/{len(rows)}" +
        (f"; lost: {fu_bad}" if fu_bad else ""))

    # I16 role views share canonical facts
    role_bad = [r["company"] for r in rows
                if r.get("role_consistency") != "CONSISTENT"]
    add("I16", "role views share canonical facts",
        "HELD" if not role_bad else "FAILED",
        f"{len(rows) - len(role_bad)}/{len(rows)}" +
        (f"; contradicting: {role_bad}" if role_bad else ""))

    # I17 the terminal state is bounded.
    #
    # BOUNDEDNESS IS NOT THE EPISTEMIC OUTCOME, and conflating them reported
    # Adastra as unbounded because it missed a 3s LATENCY gate on a run that
    # completed and rendered a full reading. What this invariant is for is
    # the run that never ends: a stale spinner, or a surface that never
    # answers. The epistemic distribution is reported separately.
    spinning = [r["company"] for r in rows
                if (idx.get(r["company"], {}).get("text") or {})
                and any(v.get("stale_spinner")
                        for v in idx[r["company"]]["text"].values())]
    stuck = [r["company"] for r in rows
             if not (r.get("decision_question") or r.get("outcome"))]
    add("I17", "the terminal state is bounded",
        "HELD" if not spinning and not stuck else "FAILED",
        f"{len(rows)}/{len(rows)} runs reached a terminal page with no stale "
        f"spinner on any surface" if not spinning and not stuck else
        f"spinning: {spinning}; stuck: {stuck}")
    epistemic = [r["company"] for r in rows
                 if r.get("outcome") not in (
                     "DECISION_GRADE_READING", "DEFENSIBLE_ABSTENTION",
                     "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY",
                     "RETRIEVAL_LIMITATION_HANDLED_CORRECTLY")]
    add("I17b", "every run lands on one of the four allowed outcomes",
        "HELD" if not epistemic else "FAILED",
        f"{len(rows) - len(epistemic)}/{len(rows)}" +
        (f"; other: {epistemic}" if epistemic else ""))

    # I18 abstention remains possible
    abst = [r["company"] for r in rows
            if r.get("outcome") in ("DEFENSIBLE_ABSTENTION",
                                    "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY")]
    add("I18", "abstention remains possible",
        "HELD" if abst else "FAILED",
        f"{len(abst)}/{len(rows)} abstained rather than manufacturing a "
        f"reading, which is what shows the system is selective")

    # I19 no false precision
    loud = []
    for r in rows:
        if r.get("independent_origins") == 0 and \
                r.get("outcome") == "DECISION_GRADE_READING":
            loud.append(r["company"])
    add("I19", "no false precision",
        "HELD" if not loud else "FAILED",
        "no company claimed a decision-grade reading without an independent "
        "origin" if not loud else f"over-claimed: {loud}")

    # I20 no cross-company or cross-session contamination
    leaked = []
    names = {r["company"] for r in rows}
    for r in rows:
        body = visible(_cap(_slug(r["company"]), "xray"))
        for other in names:
            if other != r["company"] and len(other) > 5 and \
                    re.search(rf"\b{re.escape(other)}\b", body):
                leaked.append(f"{r['company']}<-{other}")
    add("I20", "no cross-company or cross-session contamination",
        "HELD" if not leaked else "FAILED",
        "no company's X-Ray names another company in the cohort"
        if not leaked else f"named: {sorted(set(leaked))[:6]}")

    # The structural ones, asserted by their own tests.
    for iid, target in sorted(_BY_TEST.items()):
        name = {"I02": "a curated non-filer cannot fuzzy-resolve into "
                       "another registrant",
                "I03": "a legitimate filer keeps its correct SEC evidence",
                "I08": "every decision composer receives the canonical "
                       "evidence inputs",
                "I21": "category vocabulary alone cannot manufacture "
                       "decision specificity",
                "I22": "sibling rendering branches obey the same semantic "
                       "invariant"}[iid]
        if not with_tests:
            add(iid, name, "NOT_RUN", f"pinned by {target}")
            continue
        ok, tail = _run_tests(target)
        add(iid, name, "HELD" if ok else "FAILED", f"{target} — {tail}")
    return sorted(out, key=lambda x: x["id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="A")
    ap.add_argument("--analysis", default="reports/next40_analysis.json")
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    a = json.loads((ROOT / args.analysis).read_text())
    rows = [r for r in a["rows"] if r["n"] in RANGES[args.cohort]]
    res = evaluate(rows, with_tests=not args.no_tests)
    print(f"COHORT {args.cohort}  {len(rows)} companies  sha "
          f"{str(a.get('sha'))[:12]}\n")
    for r in res:
        print(f"{r['id']}  {r['verdict']:8s} {r['invariant'][:52]:54s}")
        print(f"           {r['evidence'][:150]}")
    held = sum(1 for r in res if r["verdict"] == "HELD")
    failed = [r["id"] for r in res if r["verdict"] == "FAILED"]
    na = [r["id"] for r in res if r["verdict"] in ("N/A", "NOT_RUN")]
    print(f"\nHELD {held}/{len(res)}   FAILED {failed or 'none'}   "
          f"N/A {na or 'none'}")
    out = args.out or f"reports/next40_invariants_{args.cohort}.json"
    (ROOT / out).write_text(json.dumps(
        {"contract": "next40_invariants.v1", "cohort": args.cohort,
         "sha": a.get("sha"), "invariants": res}, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
