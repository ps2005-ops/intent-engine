#!/usr/bin/env python3
"""§44/§45: the artifacts, generated from canonical state.

NOTHING HERE IS TYPED BY HAND. Every count is read from the state file, the
findings ledger, the differentiation measurement, the overlap measurement or
the UI matrix. A total a human typed is a total nobody can check, and the
one thing this report must survive is being checked.

The OLD-40 comparison is computed with ONE INSTRUMENT over BOTH cohorts --
the forty's own word-set overlap script, run here against both sets of
captures -- because a favourable number from a different metric is not a
comparison. Where a V2 field did not exist on the forty, the baseline is
reported as ABSENT rather than as zero.
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

FORTY_UI = pathlib.Path("/Users/prathamsharma/intent-engine-econ/reports/next40_ui")
FORTY_MATRIX = pathlib.Path(
    "/Users/prathamsharma/intent-engine-econ/docs/qualification/"
    "40_company_qualification_matrix.json")
SURFACES = ("intro", "brief", "full", "xray", "history", "evidence")
_NUM = re.compile(r"\b\d[\d,.%$]*\b")
_CHROME = re.compile(r"home · your analyses|guest demo session|leave demo|"
                     r"strategic intelligence|executive x-ray|history rewind|"
                     r"introduction", re.I)


def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", str(n).lower()).strip("-")


def _words(ui, company, key, names):
    p = pathlib.Path(ui) / f"{_slug(company)}-{key}.html"
    if not p.exists():
        return set()
    t = " ".join(visible(p.read_text()).split()).lower()
    t = _CHROME.sub(" ", t)
    for n in sorted(names, key=len, reverse=True):
        if len(n) > 2:
            t = t.replace(n.lower(), " ")
    return set(re.findall(r"[a-z][a-z\-']+", _NUM.sub(" ", t)))


def overlap(ui, companies):
    """The forty's own instrument: word-set Jaccard after normalisation."""
    names, out = set(companies), {}
    for key in SURFACES:
        texts = {c: _words(ui, c, key, names) for c in companies}
        texts = {c: v for c, v in texts.items() if v}
        js = [len(texts[a] & texts[b]) / len(texts[a] | texts[b])
              for a, b in itertools.combinations(sorted(texts), 2)
              if texts[a] or texts[b]]
        out[key] = {"companies": len(texts), "pairs": len(js),
                    "max": round(max(js), 3) if js else 0.0,
                    "ge_098": sum(1 for j in js if j >= 0.98)}
    out["TOTAL"] = {"pairs": sum(v["pairs"] for v in out.values()),
                    "ge_098": sum(v["ge_098"] for v in out.values())}
    return out


#: A run that abstained has no reading to collapse: its page says the record
#: could not be read, and two such pages agreeing is the product being
#: consistent about a real absence.
_ABSTAINED = {"RETRIEVAL_LIMITATION_HANDLED_CORRECTLY",
              "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY",
              "DEFENSIBLE_ABSTENTION"}


def collapses(ui, rows):
    """§37: near-identical pairs, split into EXPLAINED and UNEXPLAINED.

    A shared reading is EXPLAINED when the pages themselves say why they
    agree, and the reason is checkable from the state file rather than from
    the prose:

      * at least one run ABSTAINED -- there is no reading to collapse; or
      * both are at the same HISTORY LEVEL with the same number of dated
        documents, which is what the history surface is a function of. Two
        companies with no regulatory record have the same true history page.

    Everything else is UNEXPLAINED and is reported as a defect, whatever the
    rest of the matrix looks like.
    """
    by = {r["company"]: r for r in rows}
    names = list(by)
    out = {}
    for key in SURFACES:
        texts = {c: _words(ui, c, key, set(names)) for c in names}
        texts = {c: v for c, v in texts.items() if v}
        exp, une, detail = 0, 0, []
        for a, b in itertools.combinations(sorted(texts), 2):
            A, B = texts[a], texts[b]
            if not (A or B):
                continue
            j = len(A & B) / len(A | B)
            if j < 0.98:
                continue
            ra, rb = by[a], by[b]
            why = ""
            if ra.get("final_class") in _ABSTAINED or \
                    rb.get("final_class") in _ABSTAINED:
                why = "at least one run abstained, so there is no reading"
            elif (ra.get("history_level") == rb.get("history_level")
                  and (ra.get("history") or {}).get("dated_documents")
                  == (rb.get("history") or {}).get("dated_documents")):
                why = (f"same history state: level "
                       f"{ra.get('history_level')}, "
                       f"{(ra.get('history') or {}).get('dated_documents')} "
                       f"dated document(s)")
            if why:
                exp += 1
            else:
                une += 1
                detail.append({"a": a, "b": b, "jaccard": round(j, 3)})
        out[key] = {"explained": exp, "unexplained": une,
                    "unexplained_pairs": detail}
    out["UNEXPLAINED_TOTAL"] = sum(v["unexplained"] for v in out.values()
                                   if isinstance(v, dict))
    out["UNEXPLAINED_ON_DECISION_SURFACES"] = sum(
        out[k]["unexplained"] for k in ("intro", "brief", "full", "xray"))
    return out


def main() -> int:
    state = json.loads((ROOT / "reports/asi25_state.json").read_text())
    rows = list(state["rows"].values())
    diff = json.loads((ROOT / "reports/asi25_differentiation.json").read_text())
    found = json.loads((ROOT / "reports/asi25_findings.json").read_text())
    conv = json.loads((ROOT / "reports/asi25_convergence.json").read_text())
    qa = json.loads((ROOT / "reports/asi25_qa_audit.json").read_text())
    ui = json.loads((ROOT / "reports/asi25_ui_widths.json").read_text())
    forty = json.loads(FORTY_MATRIX.read_text())

    names25 = [r["company"] for r in rows]
    names40 = [r["company"] for r in forty["rows"]]
    o25 = overlap(ROOT / "reports/asi25_ui", names25)
    o40 = overlap(FORTY_UI, names40)

    core = sorted(r["core_s"] for r in rows if isinstance(r.get("core_s"),
                                                          (int, float)))
    def pct(xs, p):
        return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1) if xs else None

    f40 = collections.Counter(r.get("decision_force") for r in forty["rows"])
    q40 = collections.Counter(r.get("decision_question")
                              for r in forty["rows"] if r.get("decision_question"))

    out = {
        "contract": "asi25_final.v1",
        "sha": state.get("live_sha"),
        "companies": len(rows),
        "outcomes": dict(collections.Counter(r.get("final_class")
                                             for r in rows)),
        "results": dict(collections.Counter(r.get("result") for r in rows)),
        "qa": {"primary_total": qa["primary_total"],
               "primary_pass": qa["primary_pass"],
               "primary_semantic": qa["primary_semantic"],
               "followup_total": qa["followup_total"],
               "followup_pass": qa["followup_pass"]},
        "performance": {"core_p50": pct(core, 0.50), "core_p90": pct(core, 0.90),
                        "core_max": core[-1] if core else None,
                        "targets": {"p50": 60, "p90": 100, "max": 120},
                        "n": len(core)},
        "ui_matrix": ui.get("totals"),
        "differentiation": {k: diff[k] for k in (
            "decision_force", "grounding_verdict", "distinct_questions",
            "largest_identical_question_group", "rates",
            "differentiation_quality_counts")},
        "convergence": {"classification": conv["classification"],
                        "reason": conv["reason"],
                        "A": conv["A"], "B": conv["B"], "C": conv["C"]},
        "findings": {"total": len(found["findings"]),
                     "by_severity": dict(collections.Counter(
                         f["severity"] for f in found["findings"]))},
        "overlap_one_instrument": {"twenty_five": o25, "forty": o40},
        "collapses": collapses(ROOT / "reports/asi25_ui", rows),
        "abstained": sum(1 for r in rows
                         if r.get("final_class") in _ABSTAINED),
        "old_40_vs_new_25": {
            "instrument": "the forty's own word-set overlap, run over both "
                          "sets of captures in this report",
            "decision_force_40": dict(f40),
            "distinct_questions_40": len(q40),
            "largest_identical_question_group_40": (
                q40.most_common(1)[0][1] if q40 else 0),
            "companies_with_a_question_40": sum(q40.values()),
            "grounded_40": "ABSENT — the field did not exist on the forty",
            "information_priority_40": "ABSENT — the field did not exist",
        },
    }
    p = ROOT / "reports/asi25_final.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in (
        "companies", "results", "qa", "performance", "convergence",
        "findings")}, indent=1)[:1800])
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
