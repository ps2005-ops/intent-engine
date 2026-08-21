"""Mechanical defects are found by code; judgement is spent on the rest.

Sessions were spent re-reading rendered pages to notice things a regex can
notice: an absence sentence, a raw enum, a trailing ellipsis, a section that
copied its source, two surfaces contradicting each other. Every one of those
is a rule, and a rule that a person applies by eye is a rule that gets
applied inconsistently at the end of a long window.

WHAT THIS DOES NOT DO. It does not judge whether a strategic reading is any
good, whether a board would use it, or whether a chart means anything. Those
need a reader. The point is to arrive at them with the mechanical noise
already cleared.
"""
from __future__ import annotations

import json
import pathlib
import re
from difflib import SequenceMatcher

#: Copy that means the product GAVE UP in front of a chief executive.
FAILURE_LANGUAGE = (
    "analysis failed", "could not be completed", "no result to show",
    "internal failure", "something went wrong", "no result to open",
)
#: Copy that means it bounded itself. NOT the same thing, and the difference
#: is the whole point — a bounded honest answer is a pass, a give-up is not.
ABSENCE_LANGUAGE = (
    "no strategic reading", "not retrieved", "no data available",
    "no estimate retrieved", "nothing found", "unable to determine",
    "no competitor has been selected", "no history available",
    "no market expectation", "no knowledge available", "none available",
)
#: Internal vocabulary that must never reach a reader.
RAW_ENUM = re.compile(
    r"\b(READ_[A-Z_]+|[A-Z]{3,}_[A-Z_]{3,}|UNMEASURED|UNKNOWN_[A-Z_]+)\b")
#: A sentence cut off mid-thought.
ELLIPSIS = re.compile(r"\.\.\.\s*$|…\s*$", re.M)

#: The routes a customer walks, and the ones a score needs.
CUSTOMER_ROUTES = ("intro", "slides", "full", "story", "history", "step6")

#: Where each canonical statement is extracted from, for §20.
CANONICAL = {
    "competitor": re.compile(
        r"contested (?:most )?directly by ([^.]{3,120})", re.I),
    "no_competitor": re.compile(
        r"no competitor has been selected", re.I),
    "central_question": re.compile(
        r"question worth arguing about is ([^?]{10,240}\?)", re.I),
}


#: Two harnesses wrote captures today with different names for the same
#: things. Normalising on READ is cheaper than converting on disk, and it
#: means neither wave has to be re-run to be comparable.
_ROUTE_ALIASES = {"step6": ("step6", "connect"),
                  "connect": ("connect", "step6")}
_MANIFEST_NAMES = ("manifest.json", "run.json")


def _route_text(company_dir: pathlib.Path, name: str) -> str:
    for candidate in _ROUTE_ALIASES.get(name, (name,)):
        body = _read(company_dir / f"{candidate}.txt")
        if body:
            return body
    return ""


def _manifest(company_dir: pathlib.Path) -> dict:
    for name in _MANIFEST_NAMES:
        path = company_dir / name
        if path.exists():
            try:
                return json.loads(_read(path))
            except Exception:                               # noqa: BLE001
                continue
    return {}


def load_qa(company_dir: pathlib.Path) -> list:
    """The ten answers as [{question, answer}], whichever shape was written.

    TWO REAL HARNESSES, TWO SHAPES. One wrote a list of rows with `answer`;
    the other a dict keyed by question with `text`. Normalising on READ is
    the same discipline as the route aliases — a capture that cost eight
    live analyses must never be unreadable because of a key name, and
    hand-authoring a fixture for one shape is how a test comes to assert
    something production does not produce.
    """
    path = company_dir / "qa.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(_read(path))
    except Exception:                                       # noqa: BLE001
        return []
    from intent_engine.pre100.capture import run_is_gone
    rows = []
    if isinstance(raw, dict):
        for question, value in raw.items():
            if isinstance(value, dict):
                rows.append({"question": question,
                             "answer": value.get("answer")
                             or value.get("text") or "",
                             "status": value.get("status")})
            else:
                rows.append({"question": question, "answer": str(value)})
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, dict):
                rows.append({"question": value.get("question", ""),
                             "answer": value.get("answer")
                             or value.get("text") or "",
                             "status": value.get("status")})
    # AN ERROR PAGE IS NOT AN ANSWER. Forty identical "this session does not
    # have an analysis with that id" pages compare as a total collapse, which
    # is the most alarming number a collapse measurement can produce and is
    # entirely an artefact of a lost run.
    live = [r for r in rows if not run_is_gone(r.get("answer") or "")]
    if rows and not live:
        return []
    return live


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text("utf-8")
    except Exception:                                       # noqa: BLE001
        return ""


def _hits(text: str, needles) -> list:
    low = text.lower()
    return sorted({n for n in needles if n in low})


def audit_route(name: str, text: str) -> dict:
    """Every mechanical rule, on one rendered route."""
    return {
        "route": name,
        "chars": len(text),
        "empty": len(text) < 200,
        "failure_language": _hits(text, FAILURE_LANGUAGE),
        "absence_language": _hits(text, ABSENCE_LANGUAGE),
        "raw_enums": sorted(set(RAW_ENUM.findall(text)))[:6],
        "trailing_ellipsis": len(ELLIPSIS.findall(text)),
    }


def canonical_statements(company_dir: pathlib.Path) -> dict:
    """One statement per surface, so contradictions are computed not spotted.

    D17/D25-style defects — a surface asserting what another denies — were
    each found by hand, more than once, after the fact. They are a join of
    two extractions and a comparison.
    """
    out = {}
    for route in CUSTOMER_ROUTES:
        text = _route_text(company_dir, route)
        if not text:
            continue
        row = {}
        match = CANONICAL["competitor"].search(text)
        if match:
            row["competitor"] = match.group(1).strip()[:120]
        if CANONICAL["no_competitor"].search(text):
            row["competitor_denied"] = True
        question = CANONICAL["central_question"].search(text)
        if question:
            row["central_question"] = question.group(1).strip()[:200]
        if row:
            out[route] = row
    for row in load_qa(company_dir):
        if True:
            if "competitor" not in (row.get("question") or "").lower():
                continue
            text = row.get("answer") or ""
            entry = {}
            match = CANONICAL["competitor"].search(text)
            if match:
                entry["competitor"] = match.group(1).strip()[:120]
            if CANONICAL["no_competitor"].search(text):
                entry["competitor_denied"] = True
            if entry:
                out["qa"] = entry
    return out


def contradictions(statements: dict) -> list:
    """A surface naming a rival while another denies one is a contradiction,
    regardless of which is right — they cannot both be shown to a reader."""
    named = [r for r, s in statements.items() if s.get("competitor")]
    denied = [r for r, s in statements.items() if s.get("competitor_denied")]
    out = []
    if named and denied:
        out.append({"kind": "CROSS_SURFACE_CONTRADICTION",
                    "field": "competitor",
                    "named_on": named, "denied_on": denied})
    return out


def audit_company(company_dir: pathlib.Path) -> dict:
    company_dir = pathlib.Path(company_dir)
    manifest = _manifest(company_dir)
    routes = []
    for name in CUSTOMER_ROUTES:
        text = _route_text(company_dir, name)
        if not text and name not in (manifest.get("routes") or {}):
            routes.append({"route": name, "missing": True})
            continue
        routes.append(audit_route(name, text))
    statements = canonical_statements(company_dir)
    flags = []
    for row in routes:
        if row.get("missing"):
            flags.append(f"MISSING_ROUTE:{row['route']}")
        if row.get("empty"):
            flags.append(f"EMPTY:{row['route']}")
        if row.get("failure_language"):
            flags.append(f"FAILURE_LANGUAGE:{row['route']}")
        if row.get("raw_enums"):
            flags.append(f"RAW_ENUM:{row['route']}")
        if row.get("trailing_ellipsis"):
            flags.append(f"ELLIPSIS:{row['route']}")
    found = contradictions(statements)
    flags += [c["kind"] + ":" + c["field"] for c in found]
    return {"company": manifest.get("company") or company_dir.name,
            "deployed_sha": manifest.get("deployed_sha", ""),
            "run_id": manifest.get("run_id", ""),
            "auto_advanced": manifest.get("auto_advanced"),
            "seconds": manifest.get("seconds"),
            "routes": routes, "statements": statements,
            "contradictions": found, "flags": sorted(set(flags))}


# --- §19 template collapse ------------------------------------------------

#: Boilerplate that follows an ANSWER and varies by run rather than by
#: company. Nav words are NOT in here: "next" and "back" are ordinary
#: English, and matching the bare word truncated every answer to
#: "what should we measure " — because the QUESTION contains it. That
#: produced a false 28-of-28 identical, the most dramatic number of the
#: session, from an instrument that had stopped measuring. Fourth instrument
#: error in this programme and the third that pointed the wrong way.
_CHROME = re.compile(
    r"(why this matters|low, by construction"
    r"|what the evidence actually says|ask a follow-up|suggested:)", re.I)


#: A leading word that is also an ordinary word. "alpha" inside "Alphabet
#: Inc." refused whole snapshots once, and "Bank of America" became the term
#: "Bank" — masking that would delete the word from every bank's analysis.
#:
#: LENGTH CANNOT SEPARATE THEM. "Bank" and "Meta" are both four characters
#: and only one is safe, so the rule is a stoplist of generic business nouns
#: rather than a threshold. A name whose first word is on it keeps its
#: longer variants and loses only the bare token.
_MIN_LEADING_TOKEN = 4
_GENERIC_LEADING = frozenset({
    "bank", "first", "national", "general", "american", "united", "standard",
    "global", "international", "pacific", "atlantic", "central", "federal",
    "royal", "public", "premier", "allied", "capital", "trust", "energy",
    "industries", "technologies", "systems", "services", "solutions",
    "digital", "advanced", "new", "north", "south", "east", "west",
})


def name_variants(company: str) -> list:
    """The spellings of a company that must be masked, longest first.

    LONGEST FIRST IS NOT A STYLE CHOICE. Arbitrary iteration order replaced
    "Caterpillar" before "Caterpillar Inc." and left a stray " Inc.", which
    deflated a whole measurement to 0/10.
    """
    base = (company or "").strip()
    if not base:
        return []
    stripped = re.sub(r"[,]?\s+(inc\.?|corporation|corp\.?|co\.?|plc|"
                      r"ltd\.?|limited|company|holdings|group)\s*$", "",
                      base, flags=re.I).strip()
    variants = {base, stripped}
    first = stripped.split()[0] if stripped.split() else ""
    if (len(first) >= _MIN_LEADING_TOKEN
            and first.lower() not in _GENERIC_LEADING):
        variants.add(first)
    return sorted({v for v in variants if len(v) > 2}, key=len, reverse=True)


#: Chrome that appears THROUGHOUT a rendered route: nav, session banner,
#: inlined CSS. Stripped rather than truncated at, because a whole page has
#: many markers and cutting at the first one discards the page.
_PAGE_CHROME = re.compile(
    r"home · your analyses · guest demo session leave demo"
    r"|\.[a-z-]+\{[^}]*\}"
    r"|\bnext\b|\bback\b|\bstep \d\b", re.I)


def normalise(text: str, company: str, *, whole_page: bool = False) -> str:
    """Remove IDENTITY and CHROME. Never strategic nouns.

    Four instruments were tried before one told the truth, and three of the
    four errors were here: naive similarity inflated by shared chrome (0.915);
    masking then testing byte-equality, deflated because chrome AFTER the
    answer differs per run; masking variants in arbitrary order, leaving a
    stray suffix. The fourth gave the FLATTERING answer — a clean 0/10 —
    because "Why this matters" and "Low, by construction" vary by run rather
    than by company, making three identical answers look distinct.

    So: mask longest-variant-first, with word boundaries, and truncate at the
    first chrome marker.
    """
    body = text or ""
    for variant in name_variants(company):
        # Lookarounds, not \b: a variant ending in "." ("Caterpillar Inc.")
        # has no word character at its edge, so \b never matches there and
        # the suffix survives — which is exactly the stray " Inc." that
        # deflated one of the four instruments.
        body = re.sub(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", "<CO>",
                      body, flags=re.I)
    # Page furniture is removed from BOTH shapes. An answer is served on a
    # full page, so it carries the nav banner and the inlined CSS too, and
    # comparing those compares the chrome rather than the answer.
    body = _PAGE_CHROME.sub(" ", body)
    if whole_page:
        # A ROUTE IS NOT AN ANSWER. Truncating a 6,000-character page at its
        # first boilerplate marker compared 454 characters of it and called
        # that a similarity — an instrument that would have reported the
        # opening banner as the whole finding.
        pass
    else:
        marker = _CHROME.search(body)
        # Only a marker with something before it: truncating at position 0
        # leaves an empty string, which compares equal to every other empty
        # string.
        if marker and marker.start() > 0:
            body = body[:marker.start()]
    return re.sub(r"\s+", " ", body).strip().lower()


def similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def collapse_matrix(captures: dict) -> dict:
    """Pairwise similarity per surface, plus identical-answer counts."""
    names = sorted(captures)
    surfaces = {}
    for surface in (*CUSTOMER_ROUTES, "qa"):
        pairs = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ta, tb = captures[a].get(surface), captures[b].get(surface)
                if not ta or not tb:
                    continue
                if surface == "qa":
                    identical = sum(
                        1 for qa, qb in zip(ta, tb)
                        if normalise(qa.get("answer", ""), a)
                        == normalise(qb.get("answer", ""), b))
                    pairs.append({"a": a, "b": b,
                                  "identical_answers": identical,
                                  "of": min(len(ta), len(tb))})
                else:
                    na = normalise(ta, a, whole_page=True)
                    nb = normalise(tb, b, whole_page=True)
                    pairs.append({"a": a, "b": b,
                                  "similarity": similarity(na, nb),
                                  "chars": [len(na), len(nb)]})
        if pairs:
            surfaces[surface] = pairs
    worst = {}
    for surface, pairs in surfaces.items():
        if surface == "qa":
            worst[surface] = max(pairs, key=lambda p: p["identical_answers"])
        else:
            worst[surface] = max(pairs, key=lambda p: p["similarity"])
    return {"pairs": surfaces, "worst": worst}


def audit_batch(capture_root: pathlib.Path) -> dict:
    """One audit over a whole captured wave. This is what Claude reads."""
    capture_root = pathlib.Path(capture_root)
    companies, texts = [], {}
    for company_dir in sorted(p for p in capture_root.iterdir() if p.is_dir()):
        report = audit_company(company_dir)
        companies.append(report)
        name = report["company"]
        bundle = {}
        for route in CUSTOMER_ROUTES:
            body = _route_text(company_dir, route)
            if body:
                bundle[route] = body
        answers = load_qa(company_dir)
        if answers:
            bundle["qa"] = answers
        texts[name] = bundle
    return {"capture_root": str(capture_root),
            "companies": companies,
            "collapse": collapse_matrix(texts) if len(texts) > 1 else {},
            "summary": {
                "captured": len(companies),
                "with_flags": sum(1 for c in companies if c["flags"]),
                "flags": sorted({f.split(":")[0] for c in companies
                                 for f in c["flags"]}),
            }}
