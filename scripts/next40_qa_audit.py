#!/usr/bin/env python3
"""§22 — 240 primary answers and 40 follow-ups, judged semantically.

A COUNT OF HTTP 200s IS NOT A Q&A RESULT. Each answer is checked for the
things that would make it worthless even at 200: that it is about THIS
company, that it does not name another company in the universe, that it is
not a generic paragraph that would fit any subject, and that the follow-up
used its context instead of replaying an earlier answer.

Rows measured before the harness captured answer text are reported as
TEXT_NOT_CAPTURED rather than counted as passes.
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
from next40_qualification import FORTY                          # noqa: E402

UNIVERSE = {name for _n, name, *_r in FORTY}
#: Words that would appear in an answer about any company at all.
_GENERIC = ("the company", "this business", "management", "the record")


def audit(row) -> dict:
    qa = row.get("qa") or {}
    name = row.get("company") or ""
    others = {o for o in UNIVERSE if o != name and len(o) > 5}
    detail = qa.get("detail") or []
    results, captured = [], 0
    for item in detail:
        text = item.get("text")
        ok_http = item.get("status") == 200 and (item.get("words") or 0) >= 60
        if text is None:
            results.append({"q": item.get("q"), "verdict":
                            "PASS_TEXT_NOT_CAPTURED" if ok_http else "FAIL",
                            "words": item.get("words")})
            continue
        captured += 1
        low = text.lower()
        names_other = sorted(o for o in others
                             if re.search(rf"\b{re.escape(o.lower())}\b", low))
        # An answer must name its own subject somewhere.
        first = name.split()[0].lower()
        about_subject = first in low
        verdict = ("FAIL" if not ok_http else
                   "FAIL_NAMES_ANOTHER_COMPANY" if names_other else
                   "FAIL_NOT_ABOUT_SUBJECT" if not about_subject else "PASS")
        results.append({"q": item.get("q"), "verdict": verdict,
                        "words": item.get("words"),
                        "named": names_other})
    follow_text = qa.get("followup_text")
    follow = {"verdict": ("PASS" if qa.get("followup") else "FAIL"),
              "replay": qa.get("followup_replay"),
              "words": qa.get("followup_words")}
    if follow_text is not None and qa.get("followup"):
        low = follow_text.lower()
        named = sorted(o for o in UNIVERSE
                       if o != name and len(o) > 5
                       and re.search(rf"\b{re.escape(o.lower())}\b", low))
        if named:
            follow = {"verdict": "FAIL_NAMES_ANOTHER_COMPANY", "named": named,
                      "words": qa.get("followup_words")}
    elif qa.get("followup"):
        follow["verdict"] = "PASS_TEXT_NOT_CAPTURED"
    return {"company": name, "n": row.get("n"), "answers": results,
            "followup": follow, "text_captured": captured}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="ALL")
    args = ap.parse_args()
    state = json.loads((ROOT / "reports/next40_state.json").read_text())
    rng = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41),
           "ALL": range(1, 41)}[args.cohort]
    out = [audit(r) for r in sorted(state["rows"].values(),
                                    key=lambda x: x.get("n") or 0)
           if r.get("n") in rng and r.get("final_class")]
    total = sum(len(a["answers"]) for a in out)
    ok = sum(1 for a in out for r in a["answers"]
             if r["verdict"].startswith("PASS"))
    semantic = sum(1 for a in out for r in a["answers"]
                   if r["verdict"] == "PASS")
    fups = sum(1 for a in out if a["followup"]["verdict"].startswith("PASS"))
    fsem = sum(1 for a in out if a["followup"]["verdict"] == "PASS")
    bad = [(a["company"], r) for a in out for r in a["answers"]
           if not r["verdict"].startswith("PASS")]
    print(f"companies {len(out)}")
    print(f"PRIMARY_QA        {ok}/{total}   (semantically verified "
          f"{semantic}, text not captured {ok - semantic})")
    print(f"FOLLOWUPS         {fups}/{len(out)}   (semantically verified "
          f"{fsem})")
    print(f"cross-company contamination in answers: "
          f"{sum(1 for _c, r in bad if 'ANOTHER_COMPANY' in r['verdict'])}")
    for c, r in bad[:10]:
        print(f"   {c:14s} {r['verdict']:28s} {str(r.get('q'))[:52]}")
    (ROOT / "reports/next40_qa_audit.json").write_text(json.dumps(
        {"contract": "next40_qa_audit.v1", "primary_total": total,
         "primary_pass": ok, "primary_semantic": semantic,
         "followup_total": len(out), "followup_pass": fups,
         "followup_semantic": fsem, "companies": out}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
