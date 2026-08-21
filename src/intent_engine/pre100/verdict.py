"""PASS or FAIL for one captured company, and WHY. The acceptance instrument.

WHY IT IS BEING REWRITTEN
-------------------------
The previous instrument decided whether a company had been analysed by
searching the rendered `/full` page for the literal string "Limited
analysis". Meta Platforms rendered

    "Analysis could not be completed"

which is a different sentence, so Meta scored a PASS on two deployed builds
while a customer was being told one of the most heavily documented companies
in the world could not be analysed. The intelligence-quality score taken with
that instrument is void.

The lesson is NOT "add the other string".

    HTTP 200 is not success.
    A non-empty page is not success.
    A route existing is not success.
    TERMINAL is not success.

An instrument that infers an outcome from prose has to know every sentence the
product can write, and it silently stops working the day someone edits copy.
So the service now STATES its outcome (`X-Analysis-Outcome`, produced once by
`WebApp.analysis_outcome`) and this reads that. Prose checks remain, but only
as CORROBORATION -- and a disagreement between the stated outcome and the
rendered page is itself a defect, because that disagreement is what the Meta
run actually was.

WHAT A PASS REQUIRES
--------------------
All of: the right company, a customer-readable outcome appropriate to that
company, real content on every customer surface, no failure page, no
unexpected bounded page, no raw internals, no lost run, no redirect loop, and
ten Q&A answers that are answers.
"""
from __future__ import annotations

import json
import pathlib
import re

from intent_engine.pre100 import audit as A
from intent_engine.webapp import outcome as O

#: A dataclass or namedtuple that reached a reader.
#:
#: CASE-INSENSITIVE, AND POSITIVELY CONTROLLED IN THE TESTS. The first
#: version of this pattern was lowercase-only and reported zero leaks across
#: eleven companies whose answers demonstrably contain "MarketBelief(
#: belief_id=" -- the eye that found the defect and the regex that counted it
#: were reading different text. A baseline of zero would have made the repair
#: look unnecessary and its reproof meaningless.
REPR = re.compile(r"\b[A-Za-z_]+\((?:[a-z_]+=)")

#: The surfaces a customer walks. `run` is the screen `/runs/<id>` lands on.
REQUIRED_ROUTES = ("run", "intro", "slides", "full", "story", "history",
                   "connect")

#: Below this a "page" is chrome. Meta's `/full` failure page was 755
#: characters; its intro on the same run was 6,008.
THIN = 1200

#: The number of board questions every company is asked.
QUESTIONS = 10


def _fail(code: str, detail: str = "") -> dict:
    return {"code": code, "detail": detail}


def expected_full(manifest: dict) -> bool:
    """Should this company be expected to yield the WHOLE product?

    Derived from observable characteristics -- a registrant CIK, an official
    domain -- and never from a list of company names. A hard-coded exception
    for Meta would pass Meta and keep failing Microsoft.
    """
    return bool(manifest.get("cik") or manifest.get("entry_domain"))


def verdict(company_dir) -> dict:
    """Everything known about one captured company, and the verdict."""
    company_dir = pathlib.Path(company_dir)
    manifest = A._manifest(company_dir)
    company = manifest.get("company") or company_dir.name
    routes = manifest.get("routes") or {}
    stated = manifest.get("outcome") or ""
    failures: list = []

    # --- did the run even end where a customer can read it? ---------------
    status = manifest.get("status") or ""
    if status != "READY":
        failures.append(_fail("RUN_NOT_READY", status or "no status"))
    if manifest.get("run_lost_after_routes"):
        failures.append(_fail("LOST_RUN", "run vanished mid-capture"))
    if any(not s.get("text") and str(s.get("status", "")).startswith("30")
           for s in (manifest.get("progress") or [])):
        failures.append(_fail("REDIRECT_LOOP", "progress redirected to itself"))

    # --- the stated outcome ----------------------------------------------
    if stated and stated not in O.OUTCOMES:
        failures.append(_fail("UNNAMED_OUTCOME", stated))
    if manifest.get("outcome_disagreement"):
        # THE META DEFECT, AS A FIELD. One run, seven surfaces, two stories.
        failures.append(_fail("OUTCOME_DISAGREEMENT",
                              ", ".join(manifest["outcome_disagreement"])))
    if stated and stated not in O.SUCCESSFUL:
        if expected_full(manifest) and stated == O.TRUE_EVIDENCE_SCARCITY:
            # §6. For an information-rich registrant a bounded page is not
            # honest degradation, it is a false statement about the company.
            failures.append(_fail("FALSE_SCARCITY", stated))
        elif stated in O.OPERATIONAL_FAILURE:
            failures.append(_fail("OPERATIONAL_FAILURE", stated))
        elif stated == O.WORKING:
            failures.append(_fail("NEVER_SETTLED", stated))

    # --- what the pages actually say -------------------------------------
    audited = A.audit_company(company_dir)
    by_route = {row["route"]: row for row in audited["routes"]}
    for name in REQUIRED_ROUTES:
        alias = "step6" if name == "connect" else name
        row = by_route.get(alias) or by_route.get(name)
        chars = (routes.get(name) or {}).get("chars")
        if row is None and chars is None:
            failures.append(_fail("MISSING_ROUTE", name))
            continue
        size = chars if chars is not None else (row or {}).get("chars", 0)
        if size < THIN:
            failures.append(_fail("THIN_ROUTE", f"{name}={size} chars"))
        if row and row.get("failure_language"):
            failures.append(_fail("FAILURE_PAGE",
                                  f"{name}: {row['failure_language'][0]}"))
        if row and row.get("raw_enums"):
            failures.append(_fail("RAW_ENUM", f"{name}: {row['raw_enums'][0]}"))

    # A STATED SUCCESS OVER A FAILURE PAGE IS ITSELF A DEFECT, and it is the
    # only check that can catch the next Meta if the producer is ever wrong.
    prose_failed = any(row.get("failure_language")
                       for row in audited["routes"] if not row.get("missing"))
    if stated in O.SUCCESSFUL and prose_failed:
        failures.append(_fail("STATED_SUCCESS_OVER_FAILURE_PAGE", stated))

    # --- identity ---------------------------------------------------------
    named = _identity(company_dir, company)
    if named is False:
        failures.append(_fail("WRONG_IDENTITY",
                              "the company is not named on its own intro"))

    # --- Q&A --------------------------------------------------------------
    qa = _qa_rows(company_dir)
    if len(qa) < QUESTIONS:
        failures.append(_fail("QA_INCOMPLETE", f"{len(qa)}/{QUESTIONS}"))
    leaks = [r for r in qa if REPR.search(r.get("answer") or "")]
    if leaks:
        failures.append(_fail("RAW_REPR_IN_QA", f"{len(leaks)} of {len(qa)}"))
    distinct = A.within_company_distinctness(qa, company)
    if qa and distinct["distinct"] <= max(1, distinct["answers"] // 3):
        failures.append(_fail("QA_COLLAPSE",
                              f"{distinct['distinct']}/{distinct['answers']}"))

    return {"company": company,
            "deployed_sha": manifest.get("deployed_sha", ""),
            "outcome": stated,
            "outcome_by_route": manifest.get("outcome_by_route") or {},
            "seconds": manifest.get("seconds"),
            "first_useful": manifest.get("first_useful"),
            "qa_answers": len(qa),
            "flags": audited["flags"],
            "contradictions": audited["contradictions"],
            "failures": failures,
            "passed": not failures}


def _identity(company_dir: pathlib.Path, company: str):
    """Is the subject named on its own intro? None when there is no intro."""
    text = A._route_text(company_dir, "intro") or \
        A._route_text(company_dir, "run")
    if not text:
        return None
    variants = A.name_variants(company)
    low = text.lower()
    return any(v.lower() in low for v in variants if len(v) >= 4)


def _qa_rows(company_dir: pathlib.Path) -> list:
    path = pathlib.Path(company_dir) / "qa.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text("utf-8"))
    except Exception:                                       # noqa: BLE001
        return []
    rows = raw if isinstance(raw, list) else [
        dict(v, question=k) if isinstance(v, dict) else
        {"question": k, "answer": str(v)} for k, v in raw.items()]
    return [r for r in rows if isinstance(r, dict)]


def verdict_batch(capture_root) -> dict:
    """Every company captured on one SHA."""
    root = pathlib.Path(capture_root)
    rows = [verdict(d) for d in sorted(root.iterdir())
            if d.is_dir() and (d / "manifest.json").exists()]
    return {"companies": rows,
            "total": len(rows),
            "passed": sum(1 for r in rows if r["passed"]),
            "by_outcome": _tally(r["outcome"] for r in rows),
            "by_failure": _tally(f["code"] for r in rows
                                 for f in r["failures"])}


def _tally(values) -> dict:
    out: dict = {}
    for value in values:
        out[value or "(none)"] = out.get(value or "(none)", 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
