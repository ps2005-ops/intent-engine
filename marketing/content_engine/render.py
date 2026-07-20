"""C1 (PLAN_2026-07-21 / MARKETING_PLAN_V2 §1): the content engine.

One analysis object -> many assets, all DRAFTS into an approval queue.

- ContentSource is a normalized record parsed from a production weekly
  regime report .txt (already language-walled at generation time). The
  parser is REUSED from scripts/render_founder_report.py — one parser,
  one truth; a report that script would refuse to render is refused here
  for the same reason (parse-park, never guess).
- Every renderer is a pure function source -> markdown string. No fact
  appears in any asset that is not in the source object; everything else
  is fixed template prose.
- Every asset carries the claim-trace table (T:1–T:6, from
  marketing/drafts/landing_page_copy.md) and the honesty markers.
- Every asset is audited: zero predictive-accuracy claims (the outreach
  checklist rule, implemented as code) + the engine's language walls.
- Zero network. Zero model calls. Zero publishes: write_drafts() writes
  files under marketing/content_engine/drafts/<date>/ and nothing else.
  Publishing remains publer_pipeline.py, dry-run gated, per-item approval.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_ROOT = Path(__file__).resolve().parent / "drafts"

# --- reuse the founder-report parser (one parser, one truth) ----------------

def _load_founder_report_module():
    spec = importlib.util.spec_from_file_location(
        "_render_founder_report", REPO_ROOT / "scripts" / "render_founder_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_frr = _load_founder_report_module()
parse_report = _frr.parse_report

sys.path.insert(0, str(REPO_ROOT / "src"))
from intent_engine.core.regime_report import assert_language_walls  # noqa: E402


# --- the normalized source object -------------------------------------------

class ContentSource(BaseModel):
    snapshot_date: str
    rows: List[dict]            # {label, value, prov}
    mechanisms: List[str]
    none_matched: bool
    gaps: List[str]
    predictions: List[dict]     # {p, by, claim}
    no_predictions: bool
    calibration: List[str]

    @classmethod
    def from_report_text(cls, text: str) -> "ContentSource":
        parsed = parse_report(text)
        return cls(**parsed)

    @classmethod
    def from_report_path(cls, path) -> "ContentSource":
        return cls.from_report_text(Path(path).read_text())


# --- claim audit (outreach checklist rule, as code) -------------------------
# The only performance statement permitted anywhere is the explicit
# disclaimer that no accuracy is claimed (approval_checklist_template.md).

ALLOWED_DISCLAIMERS = [
    "no accuracy is claimed",
    "no accuracy claimed",
    "no accuracy claim",
    "not a claim of accuracy",
    "too few resolved to claim calibration",
    "isn't a track record",
    "is not a track record",
]

FORBIDDEN_CLAIM_PATTERNS = [
    "accura",              # accuracy/accurate/accurately as a positive claim
    "track record",
    "hit rate",
    "win rate",
    "success rate",
    "correctly predicted",
    "correctly called",
    "proven",
    "% right",
    "beats the market",
]


def audit_predictive_accuracy_claims(text: str) -> List[str]:
    """Return the forbidden patterns present after removing the approved
    disclaimers. Empty list == pass."""
    lowered = text.lower()
    for allowed in ALLOWED_DISCLAIMERS:
        lowered = lowered.replace(allowed, " ")
    return [p for p in FORBIDDEN_CLAIM_PATTERNS if p in lowered]


# --- shared fixed blocks ----------------------------------------------------

TRACE_TABLE = """\
## Claim-trace table (T:1–T:6 — required on every asset; not for publication)

| Trace | Claim | Grounds (gate-passed capability / ledgered fact) |
|---|---|---|
| T:1 | extraction restraint, closed taxonomy | Task 3 reliability gate (5x3 protocol) + v2 rerun PASS 2026-07-18; closed TriggerCondition enum, schema-enforced |
| T:2 | "says so when none match" | deterministic matcher returns empty on no overlap (match_mechanisms, tested); "correct silence" bar in gate + T005 bar (b) |
| T:3 | documented library, named sources, deterministic match | mechanisms.json: every historical_instance carries a real citation; matcher is zero-LLM code |
| T:4 | UNAVAILABLE labels, loud DATA GAPS | regime_report rendering + 2026-07-18 gap-rule amendment (render_data_gaps_section), both tested |
| T:5 | append-only ledger, code-graded | prediction_ledger.py append-only convention; resolve_prediction computes Brier in code |
| T:6 | no accuracy claim, public-as-it-accumulates | A-M5 ≥30-resolved wall + founder calibration review; ledger 0 resolved (ledgered fact) |
"""

DISCLAIMER = (
    "Every probability here is on an append-only ledger, graded by code "
    "against real data on its resolve-by date. Nothing has resolved yet, so "
    "no accuracy is claimed — publishing a prediction is not a claim of accuracy."
)

DRAFT_BANNER = (
    "<!-- DRAFT — approval queue item. Not published. Publishing requires "
    "per-item founder approval + PUBLISHING_ENABLED (publer_pipeline.py). -->"
)


def _snapshot_lines(src: ContentSource) -> List[str]:
    out = []
    for r in src.rows:
        v = "UNAVAILABLE — no verified number this run, so no claim is made" \
            if r["value"] == "unavailable" else r["value"]
        prov = f"  [{r['prov']}]" if r["prov"] else ""
        out.append(f"- **{r['label']}**: {v}{prov}")
    return out


def _mechanism_block(src: ContentSource) -> List[str]:
    if src.none_matched:
        return ["**NONE MATCHED** — and that's the finding. The available signal "
                "didn't clear any documented mechanism's trigger conditions, so the "
                "system says nothing rather than forcing a story."]
    return [f"- {m}" for m in src.mechanisms]


def _prediction_block(src: ContentSource) -> List[str]:
    if src.no_predictions:
        return ["None recorded this run."]
    return [f"- P={p['p']} by {p['by']}: {p['claim']}" for p in src.predictions]


def _gaps_block(src: ContentSource) -> List[str]:
    if src.gaps:
        return ["Genuine data gaps this run — excluded from every number above, "
                "never papered over:"] + [f"- {g}" for g in src.gaps]
    return ["No genuine data gaps detected this run."]


# --- renderers (pure functions; template prose fixed, facts from source) ----

def render_website_article(src: ContentSource) -> str:
    lines = [DRAFT_BANNER,
             f"# Structural Regime Read — {src.snapshot_date}",
             "",
             "*Every number carries its source and date. What we can't verify, "
             "we say we can't verify.*",
             "",
             "## Where the regime stands", ""]
    lines += _snapshot_lines(src)
    lines += ["", "## Structural mechanisms in play", ""]
    lines += _mechanism_block(src)
    lines += ["", "## Claims on the record", ""]
    lines += _prediction_block(src)
    lines += ["", "## Data gaps", ""]
    lines += _gaps_block(src)
    lines += ["", "## Ledger status", "", DISCLAIMER, "", "---", "", TRACE_TABLE]
    return "\n".join(lines)


def render_linkedin_post(src: ContentSource) -> str:
    n_unavail = sum(1 for r in src.rows if r["value"] == "unavailable")
    mech_line = ("Structural mechanisms matched this week: none — and the system "
                 "says so plainly instead of forcing a story."
                 if src.none_matched else
                 f"Structural mechanisms matched this week: {len(src.mechanisms)}.")
    lines = [DRAFT_BANNER,
             f"Weekly structural regime read, {src.snapshot_date}.",
             "",
             mech_line,
             ""]
    if n_unavail:
        lines += [f"{n_unavail} of {len(src.rows)} indicator series were unavailable "
                  "this run — they're labeled UNAVAILABLE, not papered over.", ""]
    if not src.no_predictions:
        lines += [f"{len(src.predictions)} resolvable prediction(s) went on the "
                  "append-only ledger, e.g.:", ""]
        p = src.predictions[0]
        lines += [f'"P={p["p"]} by {p["by"]}: {p["claim"]}"', ""]
    lines += [DISCLAIMER, "", "---", "", TRACE_TABLE]
    return "\n".join(lines)


def render_x_thread(src: ContentSource) -> str:
    lines = [DRAFT_BANNER,
             f"1/ Structural regime read, {src.snapshot_date}. "
             "Every number sourced and dated; every claim on an append-only ledger.",
             ""]
    n = 2
    for r in src.rows:
        v = "UNAVAILABLE (no verified number, so no claim)" \
            if r["value"] == "unavailable" else r["value"]
        prov = f" [{r['prov']}]" if r["prov"] else ""
        lines += [f"{n}/ {r['label']}: {v}{prov}", ""]
        n += 1
    if src.none_matched:
        lines += [f"{n}/ Mechanisms matched: NONE — the system stays silent on "
                  "thin evidence rather than forcing a narrative.", ""]
        n += 1
    for p in src.predictions:
        lines += [f"{n}/ On the record: P={p['p']} by {p['by']} — {p['claim']}", ""]
        n += 1
    lines += [f"{n}/ {DISCLAIMER}", "", "---", "", TRACE_TABLE]
    return "\n".join(lines)


def render_newsletter(src: ContentSource) -> str:
    lines = [DRAFT_BANNER,
             f"Subject: Structural regime read — {src.snapshot_date}",
             "",
             "This is the weekly read: real data, deterministic indicators, a "
             "mechanism check against documented historical episodes, and "
             "probabilistic claims recorded to a public append-only ledger.",
             "",
             "REGIME SNAPSHOT", ""]
    lines += _snapshot_lines(src)
    lines += ["", "MECHANISMS", ""]
    lines += _mechanism_block(src)
    lines += ["", "ON THE RECORD THIS WEEK", ""]
    lines += _prediction_block(src)
    lines += ["", "DATA GAPS", ""]
    lines += _gaps_block(src)
    lines += ["", DISCLAIMER, "", "---", "", TRACE_TABLE]
    return "\n".join(lines)


def render_founder_email(src: ContentSource) -> str:
    lines = [DRAFT_BANNER,
             f"Subject: Your structural regime read, {src.snapshot_date}",
             "",
             "Here's this week's read — two minutes, no narrative padding.",
             "",
             "Where the regime stands:", ""]
    lines += _snapshot_lines(src)
    lines += ["", "Mechanisms:", ""]
    lines += _mechanism_block(src)
    lines += ["", "Claims we put on the record (graded by code, not by us):", ""]
    lines += _prediction_block(src)
    lines += ["", DISCLAIMER,
              "",
              "Reply with what was wrong or what surprised you — that feedback "
              "goes straight into the loop.",
              "", "---", "", TRACE_TABLE]
    return "\n".join(lines)


RENDERERS: Dict[str, Callable[[ContentSource], str]] = {
    "website_article": render_website_article,
    "linkedin_post": render_linkedin_post,
    "x_thread": render_x_thread,
    "newsletter": render_newsletter,
    "founder_email": render_founder_email,
}


def render_all(src: ContentSource) -> Dict[str, str]:
    """source -> {asset_type: draft}. Audits every draft before returning."""
    drafts = {}
    for asset_type, fn in RENDERERS.items():
        draft = fn(src)
        violations = audit_predictive_accuracy_claims(draft)
        if violations:
            raise ValueError(
                f"Claim audit failed for {asset_type}: {violations} — no "
                "predictive-accuracy claim may enter any asset (A-M5 wall).")
        assert_language_walls(draft)
        if TRACE_TABLE not in draft:
            raise ValueError(f"{asset_type} draft is missing the claim-trace table.")
        drafts[asset_type] = draft
    return drafts


def write_drafts(src: ContentSource, drafts_root: Optional[Path] = None) -> List[Path]:
    """Write all drafts to the approval queue. Never publishes anything."""
    root = Path(drafts_root) if drafts_root else DRAFTS_ROOT
    out_dir = root / src.snapshot_date
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for asset_type, draft in render_all(src).items():
        p = out_dir / f"{asset_type}.md"
        p.write_text(draft)
        written.append(p)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True,
                    help="Production weekly regime report .txt")
    ap.add_argument("--drafts-root", default=None)
    args = ap.parse_args(argv)
    src = ContentSource.from_report_path(args.input)
    for p in write_drafts(src, Path(args.drafts_root) if args.drafts_root else None):
        print(f"draft queued (NOT published): {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
