"""Marketing Plan C3, C6, C7, C8 generators (T017).

Every generator produces DRAFTS ONLY. Each rendered asset carries the
content engine's T:1–T:6 claim-trace table and passes that engine's own
claim audit plus the regime-report language walls — those checks are
imported and reused, never reimplemented here.

C4 (feedback) and C5 (CRM) of the plan are already BUILT (T016 / T014);
this module deliberately contains no second implementation of either.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from intent_engine.core.prediction_ledger import list_predictions
from intent_engine.marketing.records import MarketingError

# src/intent_engine/marketing/generators.py -> repo root is 3 levels up
REPO_ROOT = Path(__file__).resolve().parents[3]


def _content_engine():
    """Load the existing C1 content engine by path (it lives under
    marketing/, outside the src package) — reused, never forked."""
    name = "_marketing_content_engine"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / "marketing" / "content_engine" / "render.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _audit(asset_name: str, text: str) -> None:
    engine = _content_engine()
    violations = engine.audit_predictive_accuracy_claims(text)
    if violations:
        raise MarketingError(
            f"claim audit failed for {asset_name}: {violations} — no "
            "predictive-accuracy claim may enter any asset (A-M5 wall)")
    from intent_engine.core.regime_report import assert_language_walls
    assert_language_walls(text)
    if engine.TRACE_TABLE not in text:
        raise MarketingError(f"{asset_name} is missing the claim-trace table")


def _wrap(asset_name: str, body_lines: list) -> str:
    engine = _content_engine()
    text = "\n".join([engine.DRAFT_BANNER, ""] + body_lines
                     + ["", engine.DISCLAIMER, "", engine.TRACE_TABLE])
    _audit(asset_name, text)
    return text


# --- C3: ledger -> content fan-out -------------------------------------------

C3_ASSET_TYPES = ("markdown_page", "seo_page", "newsletter", "linkedin",
                  "x_thread", "founder_summary", "github_example")


def fan_out_prediction(prediction, *, drafts_root, ledger_path=None) -> dict:
    """One newly recorded prediction -> the full draft set, in an approval
    queue. Idempotent: re-running writes byte-identical files and creates
    no duplicates. The append-only ledger is never touched."""
    out_dir = Path(drafts_root) / "predictions" / prediction.id
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = [
        f"Claim recorded: {prediction.claim_text}",
        f"Stated probability at creation: {prediction.probability:.2f}",
        f"Resolve-by date: {prediction.resolve_by}",
        f"Source: {prediction.source}",
        f"Entity: {prediction.entity_id}",
    ]
    if getattr(prediction, "decision_id", None):
        facts.append(f"Decision record: {prediction.decision_id}")
    context = [
        "",
        "This claim sits on an append-only ledger and will be graded by "
        "code on its resolve-by date. Nothing here is a forecast guarantee, "
        "and no accuracy is claimed (0 resolved is 0 resolved).",
    ]
    written = {}
    for asset in C3_ASSET_TYPES:
        text = _wrap(asset, [f"# Prediction draft — {asset}", ""] + facts
                     + context)
        path = out_dir / f"{asset}.md"
        path.write_text(text)
        written[asset] = path
    return written


# --- C6: commit-triggered content --------------------------------------------

def read_commits(rev_range: str, *, repo_root=None) -> list:
    """Deterministic `git log` walk. Returns [{sha, subject}]."""
    root = Path(repo_root or REPO_ROOT)
    try:
        out = subprocess.run(
            ["git", "log", "--no-merges", "--pretty=%H%x1f%s", rev_range],
            cwd=root, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise MarketingError(f"could not read commit range {rev_range!r}: "
                             f"{type(exc).__name__}") from exc
    commits = []
    for line in out.splitlines():
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            commits.append({"sha": sha[:7], "subject": subject})
    return commits


def drafts_from_commits(commits, *, drafts_root, label: str) -> dict:
    """Changelog + social drafts from a commit range. Facts only: each
    line is a real commit subject; nothing is characterized as an
    improvement, a win, or a performance result."""
    if not commits:
        raise MarketingError("no commits in range — nothing to draft")
    bullets = [f"- `{c['sha']}` {c['subject']}" for c in commits]
    changelog = _wrap("changelog", [f"# Changelog — {label}", ""] + bullets)
    linkedin = _wrap("linkedin", [
        f"What changed in the engine ({label}):", "",
        *bullets[:5], "",
        "Each line is a commit subject from the repository history — "
        "shipped work, described plainly."])
    x_thread = _wrap("x_thread", [
        f"Build log — {label}:", "",
        *[f"{i}. {c['subject']}" for i, c in enumerate(commits[:5], 1)]])
    out_dir = Path(drafts_root) / "commits" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, text in (("changelog", changelog), ("linkedin", linkedin),
                       ("x_thread", x_thread)):
        path = out_dir / f"{name}.md"
        path.write_text(text)
        written[name] = path
    return written


# --- C7: public pages ---------------------------------------------------------

def render_predictions_page(ledger_path, *, analytics_service=None,
                            as_of=None) -> str:
    """Raw ledger rows + the calibration status taken VERBATIM from the
    analytics view. The A-M5 gate text is never re-derived here."""
    rows = list_predictions(path=ledger_path)
    lines = ["# Predictions (live ledger view)", "",
             f"Rows on the ledger: {len(rows)}", ""]
    for p in sorted(rows, key=lambda r: (r.resolve_by, r.id))[:50]:
        outcome = p.outcome or "unresolved"
        lines.append(f"- P={p.probability:.2f} by {p.resolve_by} "
                     f"[{p.source}] — {p.claim_text} ({outcome})")
    lines += ["", "## Calibration status", ""]
    lines += _calibration_lines(analytics_service, as_of)
    return _wrap("predictions_page", lines)


def render_leaderboard_page(ledger_path, *, analytics_service=None,
                            as_of=None) -> str:
    lines = ["# Leaderboard — engine vs baselines", "",
             "Raw resolved counts per source. No ranking is asserted until "
             "the evidence gate below clears.", ""]
    for source in ("premortem", "market", "baseline"):
        rows = list_predictions(path=ledger_path, source=source)
        resolved = [p for p in rows
                    if p.outcome in ("happened", "did_not_happen")]
        lines.append(f"- {source}: {len(rows)} recorded, "
                     f"{len(resolved)} resolved")
    lines += ["", "## Calibration status", ""]
    lines += _calibration_lines(analytics_service, as_of)
    return _wrap("leaderboard_page", lines)


def _calibration_lines(analytics_service, as_of) -> list:
    if analytics_service is None:
        return ["Calibration view unavailable in this render — no analytics "
                "service was supplied. Too few resolved to claim calibration "
                "is the standing position until the gate is shown to clear."]
    metrics = analytics_service.calibration_metrics(as_of=as_of)
    cal = metrics["calibration"]
    status = cal.status if hasattr(cal, "status") else cal["status"]
    lines = [f"Status: {status}"]
    annotations = cal.annotations if hasattr(cal, "annotations") else ()
    lines += [f"- {a}" for a in annotations]
    resolved = metrics["predictions_resolved"]
    total = metrics["predictions_total"]
    lines.append(f"- resolved rows: "
                 f"{resolved.value if hasattr(resolved, 'value') else resolved}"
                 f" of {total.value if hasattr(total, 'value') else total}")
    return lines


def render_mechanism_library_page(library_path=None) -> str:
    """Lists documented mechanisms and their citations. READ-ONLY: the
    frozen library file is opened for reading and never written."""
    import json
    path = Path(library_path or
                REPO_ROOT / "src/intent_engine/core/data/mechanisms.json")
    data = json.loads(path.read_text())
    mechanisms = data if isinstance(data, list) else data.get("mechanisms", [])
    lines = ["# Mechanism library", "",
             f"Documented mechanisms: {len(mechanisms)}", "",
             "Each mechanism carries documented trigger conditions and at "
             "least one cited historical instance. Presence in this library "
             "is not a claim about any future case.", ""]
    for m in mechanisms[:40]:
        name = m.get("name", "(unnamed)")
        tier = m.get("confidence_tier", "unspecified")
        lines.append(f"- **{name}** (documented tier: {tier})")
    return _wrap("mechanism_library_page", lines)


def render_public_pages(ledger_path, *, analytics_service=None, as_of=None,
                        drafts_root=None, library_path=None) -> dict:
    pages = {
        "predictions": render_predictions_page(
            ledger_path, analytics_service=analytics_service, as_of=as_of),
        "leaderboard": render_leaderboard_page(
            ledger_path, analytics_service=analytics_service, as_of=as_of),
        "mechanism_library": render_mechanism_library_page(library_path),
    }
    if drafts_root:
        out_dir = Path(drafts_root) / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, text in pages.items():
            (out_dir / f"{name}.md").write_text(text)
    return pages


# --- C8: public roadmap page --------------------------------------------------

def render_roadmap_page(roadmap_path=None, *, drafts_root=None) -> str:
    """Regenerated from ROADMAP.md through the SAME parser the nightly
    loop uses — no manual duplication of task state anywhere."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pick_next_task import parse_roadmap  # noqa: E402
    path = Path(roadmap_path or REPO_ROOT / "ROADMAP.md")
    tasks = parse_roadmap(path.read_text())
    buckets = {"DONE": [], "IN-PROGRESS": [], "RUNNABLE": [], "NEEDS-SPEC": []}
    for t in tasks:
        buckets.setdefault(t.status, []).append(t)
    lines = ["# Public roadmap", "",
             "Generated from ROADMAP.md by the same parser the nightly loop "
             "uses. Nothing here is maintained by hand.", ""]
    for label, heading in (("DONE", "Done"), ("IN-PROGRESS", "In progress"),
                           ("RUNNABLE", "Next"), ("NEEDS-SPEC", "Ideas")):
        lines += [f"## {heading}", ""]
        entries = sorted(buckets.get(label, []), key=lambda t: t.task_id)
        lines += ([f"- {t.task_id}" for t in entries] if entries
                  else ["- (none)"])
        lines.append("")
    text = _wrap("roadmap_page", lines)
    if drafts_root:
        out_dir = Path(drafts_root) / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "roadmap.md").write_text(text)
    return text
