#!/usr/bin/env python3
"""The twenty-five, through the SAME harness the forty used (§28-§34).

WHY THIS IS NINETY LINES AND NOT SIX HUNDRED
--------------------------------------------
`next40_qualification` carries every instrument correction two qualifications
paid for: the winner-anchored reason panel (five of fourteen companies were
otherwise reported evidence-led on a REJECTED candidate's terms), the three
history wordings, the Level C "no document carried a date" form, the
falsy-zero submit ack, the one-writer claim, the quota arithmetic. A second
harness would re-earn all of it by re-making the mistakes, and the recorded
lesson is that an instrument naming producer fields wrongly invents uniform
defects.

So this module REPLACES THE UNIVERSE AND EXTENDS THE MEASUREMENT, and runs
the same `main()`. The three module constants it rebinds -- the company list,
the cohort ranges, the state path -- are read inside `main()` at call time,
so rebinding them here is not a monkeypatch of behaviour; it is supplying the
arguments the module was always parameterised on.

WHAT IT ADDS
------------
The V2 reasoning objects the forty had no way to produce, read off the pages
a customer actually reads:

    question basis      which slots in the decision question came from THIS
                        company and which from its class
    grounding verdict   GROUNDED / NAME_ONLY / GENERIC -- the name-swap test
    strategic delta     what the class prior alone would have said
    information value   what the page says should be learned next
    learning history    the rehearsal surface, and its refusal reason

Each is parsed from rendered HTML rather than from an internal JSON route,
for the same reason the forty's reason panel was: a claim read off a private
field can outrun what the product actually says to a reader.
"""
from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent

import next40_qualification as Q                              # noqa: E402
from perf_progressive_matrix import _req, visible              # noqa: E402

#: THE FORTY'S MEASUREMENT, BOUND BEFORE ANYTHING REBINDS IT.
#:
#: `main()` sets `Q._measure = _measure` so the journey calls this module's
#: version. Reading `Q._measure` from inside that version then resolves to
#: ITSELF, and the first company recurses until the stack ends. Captured at
#: import time, the original stays reachable.
_FORTY_MEASURE = Q._measure

# (n, typed name, entity_id, prefixes a person stops at, category)
#
# IDENTITY IS CURATED; STRATEGIC OUTPUT IS NOT (§1). The category column is
# an EVALUATION grouping used only to ask whether two companies we consider
# unalike received the same reading. It is never passed to the product and
# never reaches a page: the system derives its own model from evidence, and a
# category that leaked into the reading would be the hard-coding §36 forbids.
TWENTY_FIVE = [
 (1, "Axonius", "axonius", ["Axo", "axonius"], "SECURITY"),
 (2, "Arctic Wolf", "arctic_wolf", ["Arctic", "arctic wolf"], "SECURITY"),
 (3, "Cribl", "cribl", ["Crib", "cribl"], "DATA_CONTEXT"),
 (4, "1Password", "onepassword", ["1Pass", "1password", "1 Password"],
  "IDENTITY"),
 (5, "Illumio", "illumio", ["Illum", "illumio"], "SECURITY"),
 (6, "Abnormal AI", "abnormal_ai", ["Abnormal", "abnormal ai"], "SECURITY"),
 (7, "Netskope", "netskope", ["Netsk", "netskope"], "SECURITY"),
 (8, "Clio", "clio", ["Cli", "clio"], "LEGAL"),
 (9, "Coveo", "coveo", ["Cove", "coveo"], "DATA_CONTEXT"),
 (10, "Procore", "procore", ["Proc", "procore"], "VERTICAL_OPS"),
 (11, "ServiceTitan", "servicetitan", ["Service", "servicetitan"],
  "VERTICAL_OPS"),
 (12, "Motive", "motive", ["Moti", "motive"], "VERTICAL_OPS"),
 (13, "Verkada", "verkada", ["Verk", "verkada"], "PHYSICAL_SECURITY"),
 (14, "Vanta", "vanta", ["Van", "vanta"], "SECURITY"),
 (15, "Snyk", "snyk", ["Sny", "snyk"], "DEV_SUPPLY_CHAIN"),
 (16, "Chainguard", "chainguard", ["Chain", "chainguard"],
  "DEV_SUPPLY_CHAIN"),
 (17, "Island", "island", ["Islan", "island"], "ENTERPRISE_PLATFORM"),
 (18, "NinjaOne", "ninjaone", ["Ninja", "ninjaone"], "ENTERPRISE_PLATFORM"),
 (19, "Huntress", "huntress", ["Hunt", "huntress"], "SECURITY"),
 (20, "Veza", "veza", ["Vez", "veza"], "IDENTITY"),
 (21, "Expel", "expel", ["Expe", "expel"], "SECURITY"),
 (22, "Dragos", "dragos", ["Drag", "dragos"], "SECURITY"),
 (23, "Material Security", "material_security",
  ["Material", "material security"], "SECURITY"),
 (24, "Obsidian Security", "obsidian_security",
  ["Obsidian", "obsidian security"], "SECURITY"),
 (25, "Okta", "okta", ["Okt", "okta"], "IDENTITY"),
]

#: THREE COHORTS, SAME PURPOSE AS THE FORTY'S. A is discovery (new defect
#: classes are expected), B is generalization (new classes here mean A did not
#: find the class, only an instance), C is confirmation (any new class here is
#: a convergence failure and must be reported as one).
COHORTS = {"A": range(1, 10), "B": range(10, 18), "C": range(18, 26)}


# --- the V2 measurement -----------------------------------------------------

def _first(pattern, text, group=1, flags=re.S):
    m = re.search(pattern, text, flags)
    return " ".join(m.group(group).split()) if m else ""


def _section(html, heading):
    """The body of one X-Ray section, by its heading. Bounded on purpose.

    Scanning the whole page attributed a REJECTED candidate's evidence to the
    winner on five of fourteen companies in the forty. The same mistake is
    available here for every panel, so every read below is anchored.
    """
    m = re.search(
        r"<h2[^>]*>\s*" + re.escape(heading) + r".*?</h2>(.*?)(?=<h2|</main>)",
        html, re.S | re.I)
    return m.group(1) if m else ""


def _v2(op, run_id, row, surfaces):
    """Everything §17 needs that the forty's harness could not read."""
    raw = surfaces.get("xray", {}).get("html", "") or ""
    why_company = visible(_section(raw, "Why this reading is this company"))
    to_learn = visible(_section(raw, "What we would have to learn next"))

    low = why_company.lower()
    if "this reading is this company" in low and "not yet" not in low:
        verdict = "GROUNDED"
    elif "not yet this company" in low:
        verdict = "NAME_ONLY"
    elif why_company.strip():
        verdict = "STATED_UNMEASURED"
    else:
        verdict = "PANEL_ABSENT"

    row["v2"] = {
        "grounding_verdict": verdict,
        "why_company_chars": len(why_company),
        # The two sentences that carry the claim, kept verbatim so a cohort
        # can compare them for collapse exactly as it compares questions.
        "grounding_reason": _first(r"(?:company&rsquo;s\.|company's\.)\s*(.{20,400}?)(?:\s{2,}|$)",
                                   why_company) or why_company[:400],
        "measured_in": _first(r"question is measured in ([^,]{2,60}), which is",
                              why_company),
        "quoted_itself": "It said so itself" in why_company,
        "prior_question": _first(
            r"the question would have been:\s*[“\"](.{15,300}?)[”\"]",
            why_company),
        "delta_stated": bool(re.search(
            r"measured in this company's own terms|Nothing this company "
            r"published changed the decision|moved the decision to",
            why_company, re.I)),
        "information_priorities": len(re.findall(
            r"(HIGH|MEDIUM|LOW) value", to_learn)),
        "priority_text": to_learn[:1500],
        "asks_for_billing_unit": "one unit of its revenue" in to_learn,
    }

    # --- §27 the learning surface, and its honest refusal.
    st, body, _u, _t, _h = _req(op, f"/runs/{run_id}/learning", timeout=90)
    surfaces["learning"] = {"status": st, "html": body}
    row.setdefault("surface_status", {})["learning"] = st
    text = visible(body)
    row["learning_surface"] = {
        "status": st,
        "available": "No rehearsal" not in text,
        "labelled_rehearsal": "HISTORICAL REHEARSAL" in text,
        "says_pre_calibration": "pre-calibration" in text.lower(),
        "claims_forward": bool(re.search(r"real forward|forward calibration",
                                         text, re.I)
                               and "NOT FORWARD" not in text),
        "change_type": _first(r"What changed\s*([a-z ]{3,40})", text),
        "refused": _first(r"No rehearsal\s*(.{20,300}?)(?:A rehearsal needs|$)",
                          text),
        "chars": len(text),
    }
    row["decision_text"]["why_company"] = why_company[:4000]
    row["decision_text"]["learning"] = text[:4000]

    slug = re.sub(r"[^a-z0-9]+", "-", str(row.get("company", "")).lower())
    out = ROOT / "reports/asi25_ui"
    out.mkdir(parents=True, exist_ok=True)
    for key in ("result", "intro", "brief", "full", "history", "evidence",
                "xray", "sources", "story", "learning"):
        html = (surfaces.get(key) or {}).get("html")
        if not html:
            continue
        path = out / f"{slug.strip('-')}-{key}.html"
        path.write_text(html)
        row.setdefault("capture_files", {})[key] = path.name


def _measure(op, run_id, row, surfaces):
    """The forty's measurement, then the V2 measurement on top of it."""
    _FORTY_MEASURE(op, run_id, row, surfaces)
    try:
        _v2(op, run_id, row, surfaces)
    except Exception as exc:                                 # noqa: BLE001
        # AN INSTRUMENT FAULT IS NOT A PRODUCT FINDING. A blank cell that
        # cannot say why costs a whole re-run to explain.
        row["v2"] = {"instrument_error": f"{type(exc).__name__}: {exc}"}


#: §32's six, asked of every company. Deliberately NOT company-specific --
#: the point is whether the ANSWERS are.
#:
#: TWO OF THEM ARE NEW. The forty asked "what is the most important strategic
#: implication" and "what is the weakest assumption"; neither could reach the
#: V2 objects, because neither existed. "Why THIS decision" and "why THIS
#: company" are the two questions the frozen 40 could answer truthfully and
#: identically for twenty-two companies at once, so they are exactly the two
#: worth asking a live system.
QUESTIONS = [
    "Why was this decision selected for this company rather than another?",
    "Why is this reading specific to this company rather than to any "
    "company like it?",
    "What evidence supports this reading?",
    "What evidence argues against it?",
    "What would change the recommendation or posture?",
    "What should management learn next, and why that first?",
]


def main() -> int:
    Q.FORTY = TWENTY_FIVE
    Q.QUESTIONS = QUESTIONS
    Q.COHORTS = COHORTS
    Q.STATE = ROOT / "reports/asi25_state.json"
    Q.UI = ROOT / "reports/asi25_ui"
    Q._measure = _measure
    return Q.main()


if __name__ == "__main__":
    raise SystemExit(main())
