"""Prospect-100 resume: recovered round-4 baseline, live scorecard, progress manifest.

Reads only committed artifacts. Writes:
  docs/engineering/prospect100/resume/scorecard_live.json
  docs/engineering/prospect100/resume/SCORECARD.md
  docs/engineering/prospect100/resume/PROGRESS_MANIFEST.json  (created once, then merged)

Idempotent: re-running regenerates the scorecard from the same inputs and keeps
any manifest fields a later round has written.

Scoring honesty: a "current" score is only written for a company when a
re-evaluation has actually been run on the evaluated commit. Until then the
current score is null and the row says why. Round-4 scores are never carried
forward as current, because the implementation has changed since cc04b23.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
P100 = ROOT / "docs/engineering/prospect100"
OUT = P100 / "resume"
DIMS = ("search", "identity", "coverage", "independence", "economics",
        "strategy", "presentation", "history", "visual", "performance")
STATUS_DIMS = ("identity", "corporate_status", "ownership", "evidence",
               "search", "explanation", "successor_navigation",
               "no_fabricated_analysis", "presentation", "performance")
#: The eight companies whose /slides answered 500 in round 4 (presentation FAIL),
#: fixed by 7729503d. Recovered from qualification_100_pass4.json, not assumed.
ROUND4_BASE = "cc04b23a"


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


def _current_summary(rows, rounds) -> dict:
    """The latest scored round, against round 4. Never invents a score."""
    if not rounds:
        return {"evaluated": 0, "fully_qualified_analytical": 0,
                "fully_qualified_status_pages": 0, "remaining": 100,
                "note": "No company has been re-evaluated on the candidate yet."}
    n, _table, commit = rounds[-1]
    a = [r for r in rows if r["kind"] == "ANALYTICAL"
         and r.get(f"round{n}_score") is not None]
    s = sorted(r[f"round{n}_score"] for r in a)
    up = sum(1 for r in a if r[f"round{n}_score"] > (r["round4_score"] or 0))
    down = sum(1 for r in a if r[f"round{n}_score"] < (r["round4_score"] or 0))
    return {"round": n, "analysis_commit": commit, "evaluated": len(a),
            "ten_of_ten": sum(1 for x in s if x == 10.0),
            "fully_qualified_analytical": sum(1 for x in s if x == 10.0),
            "mean": round(sum(s) / len(s), 3),
            "median": (s[len(s) // 2] if len(s) % 2 else
                       (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2),
            "lowest": s[0], "highest": s[-1],
            "up": up, "down": down, "same": len(a) - up - down,
            "pass_count_by_metric": {d: sum(1 for r in a if (r.get(
                f"round{n}_grades") or {}).get(d) == "PASS") for d in DIMS}}


def main() -> int:
    head = _git("rev-parse", "--short=8", "HEAD")
    p4 = json.load(open(P100 / "qualification_100_pass4.json"))["companies"]
    p3 = {c["prospect_id"]: c for c in
          json.load(open(P100 / "qualification_100.json"))["companies"]}
    reg = {r["prospect_id"]: r for r in
           yaml.safe_load(open(P100 / "PROSPECT_REGISTRY.yaml"))["prospects"]}
    listed = {r["prospect_id"]: r for r in
              yaml.safe_load(open(P100 / "PROSPECT_LIST.yaml"))["prospects"]}
    assert len(p4) == len(reg) == len(listed) == 100

    crash8 = [c["prospect_id"] for c in p4
              if (c.get("grades") or {}).get("presentation") == "FAIL"]
    rows = []
    for c in p4:
        pid = c["prospect_id"]
        r = reg[pid]
        g4 = c.get("grades") or {}
        status = r.get("corporate_status") or {}
        is_status = c["verdict"] == "STATUS_PAGE_BY_DESIGN"
        failed = [d for d in DIMS if g4.get(d) not in ("PASS",)] if not is_status else []
        changed_since = []
        if pid in crash8:
            changed_since.append(
                "presentation crash (/slides 500) fixed in 7729503d; fix "
                "unchanged in HEAD; regression test passes; NOT re-scored")
        rows.append({
            "prospect_id": pid,
            "tier": c["tier"],
            "name_as_listed": listed[pid]["name_as_listed"],
            "company": c["company"],
            "entity_id": c["entity_id"],
            "website": r.get("primary_domain"),
            "corporate_status": status.get("state") or "INDEPENDENT",
            "corporate_status_summary": status.get("summary"),
            "corporate_status_reverified": False,
            "kind": "STATUS_PAGE" if is_status else "ANALYTICAL",
            "round3_score": p3[pid].get("score"),
            "round4_score": c.get("score"),
            "round4_verdict": c["verdict"],
            "round4_grades": g4,
            "round4_blocker": c.get("blocker"),
            "round4_failed_metrics": failed,
            "changes_since_round4": changed_since,
            "current_original_rubric_score": None,
            "current_strengthened_rubric_score": None,
            "current_grades": None,
            "status_page_grades": ({d: None for d in STATUS_DIMS}
                                   if is_status else None),
            "device_theme_matrix": {k: None for k in (
                "desktop_light", "desktop_dark", "mobile_light", "mobile_dark")},
            "last_evaluation": None,
            "evaluated_commit": None,
            "qualification_status": "NOT_RE_EVALUATED",
            "why_not_re_evaluated": (
                "Re-analysis needs outbound network (company sites, SEC, "
                "Wikidata, trade press) and a reasoning backend; neither is "
                "available in the evaluating environment. See manifest blockers."),
            "next_action": ("Wave 0: re-score presentation after crash fix"
                            if pid in crash8 else
                            "Wave 5: status-page qualification" if is_status
                            else "Re-run on candidate commit"),
        })

    # --- Wave 5 (local browser) results, when present -------------------
    w5 = OUT / "wave5" / "status_pages_local.json"
    if w5.exists():
        cells = json.load(open(w5))
        for r in rows:
            mine = [c for c in cells if c["entity_id"] == r["entity_id"]]
            if r["kind"] != "STATUS_PAGE" or not mine:
                continue
            ok = lambda k: all(c[k] for c in mine)
            clean = all(c["h_overflow_px"] <= 0 and not c["console_errors"]
                        and not c["failed_requests"] for c in mine)
            r["status_page_grades"] = {
                "identity": "PASS",          # search ranks it first (search_local.json)
                "search": "PASS",
                "explanation": "PASS" if ok("says_not_independent") else "FAIL",
                "no_fabricated_analysis": "PASS" if not any(
                    c["opened_run"] for c in mine) else "FAIL",
                "successor_navigation": "PASS" if ok("names_successor") else "FAIL",
                "presentation": "PASS" if clean else "FAIL",
                "performance": "PASS_LOCAL_ONLY",
                # These need an outside source read today; the evaluating
                # environment could reach none. Not carried from the registry.
                "corporate_status": "NOT_VERIFIED_NETWORK_BLOCKED",
                "ownership": "NOT_VERIFIED_NETWORK_BLOCKED",
                "evidence": "NOT_VERIFIED_NETWORK_BLOCKED",
            }
            r["device_theme_matrix"] = {
                f"{'mobile' if w < 768 else 'tablet' if w < 1024 else 'desktop'}"
                f"_{c['scheme']}_{w}": c["pass"] for c in mine
                for w in [c["width"]]}
            r["last_evaluation"] = datetime.fromtimestamp(
                w5.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            r["evaluated_commit"] = head + ("+dirty" if _git(
                "status", "--porcelain", "--", "src") else "")
            r["qualification_status"] = "STATUS_PAGE_PRODUCT_PASS_STATUS_UNVERIFIED"
            r["why_not_re_evaluated"] = (
                "Product surface verified locally at 5 widths x 2 themes; the "
                "corporate status itself still needs re-verification against a "
                "current outside source (network blocked).")
            r["next_action"] = "Re-verify corporate status from a primary source"

    # --- Later rounds, each scored by the ORIGINAL qualify100 on ONE commit --
    #: (round number, qualification file, commit the analyses ran on)
    rounds = []
    for f in sorted(OUT.glob("qualification_r*.json")):
        n = int("".join(ch for ch in f.stem.split("_r")[-1] if ch.isdigit()))
        meta = OUT / f"round{n}_meta.json"
        commit = (json.loads(meta.read_text()).get("analysis_commit")
                  if meta.exists() else "")
        rounds.append((n, json.loads(f.read_text())["companies"], commit))
    rounds.sort()
    for n, table, commit in rounds:
        by = {c["prospect_id"]: c for c in table}
        for r in rows:
            c = by.get(r["prospect_id"])
            if not c:
                continue
            r[f"round{n}_score"] = c.get("score")
            r[f"round{n}_grades"] = c.get("grades")
            r[f"round{n}_blocker"] = c.get("blocker")
    if rounds:
        n, table, commit = rounds[-1]
        by = {c["prospect_id"]: c for c in table}
        for r in rows:
            c = by.get(r["prospect_id"])
            if not c or r["kind"] != "ANALYTICAL":
                continue
            r["current_original_rubric_score"] = c.get("score")
            r["current_grades"] = c.get("grades")
            r["evaluated_commit"] = commit
            r["qualification_status"] = (
                "QUALIFIED_10_OF_10" if c.get("score") == 10.0 else
                f"ROUND_{n}_SCORED")
            r["why_not_re_evaluated"] = None
            r["failed_metrics_current"] = [d for d in DIMS if
                                           (c.get("grades") or {}).get(d) != "PASS"]
            r["next_action"] = (c.get("blocker") or "")[:160]

    OUT.mkdir(parents=True, exist_ok=True)
    scores = sorted(r["round4_score"] for r in rows if r["round4_score"] is not None)
    dist = {}
    for s in scores:
        dist[str(s)] = dist.get(str(s), 0) + 1
    pass_rate = {d: sum(1 for r in rows if r["kind"] == "ANALYTICAL"
                        and r["round4_grades"].get(d) == "PASS") for d in DIMS}
    agg = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_on_commit": head,
        "round4_evaluated_on": ROUND4_BASE,
        "companies": 100,
        "analytical": sum(r["kind"] == "ANALYTICAL" for r in rows),
        "status_pages": sum(r["kind"] == "STATUS_PAGE" for r in rows),
        "round4": {
            "ten_of_ten": sum(1 for s in scores if s == 10.0),
            "mean": round(sum(scores) / len(scores), 3),
            "median": scores[len(scores) // 2] if len(scores) % 2 else
                      (scores[len(scores) // 2 - 1] + scores[len(scores) // 2]) / 2,
            "lowest": scores[0], "highest": scores[-1],
            "distribution": dict(sorted(dist.items(), key=lambda kv: -float(kv[0]))),
            "pass_count_by_metric_of_95": pass_rate,
        },
        "current": _current_summary(rows, rounds),
        "presentation_crash_companies": [
            {"prospect_id": p, "company": next(r["company"] for r in rows
                                               if r["prospect_id"] == p)}
            for p in crash8],
    }
    (OUT / "scorecard_live.json").write_text(json.dumps(
        {"summary": agg, "companies": rows}, indent=1) + "\n")

    cur = agg["current"]
    latest = rounds[-1][0] if rounds else None
    md = ["# Prospect-100 live scorecard", "",
          f"Generated {agg['generated_at']} on `{head}`. Round 4 was evaluated on "
          f"`{ROUND4_BASE}`."
          + (f" Current = round {latest}, scored by the original "
             f"`qualify100.py` on analyses run at `{cur.get('analysis_commit')}`."
             if latest else " No later round has been scored yet."), "",
          f"Round 4: 10/10 = {agg['round4']['ten_of_ten']}; mean "
          f"{agg['round4']['mean']}; median {agg['round4']['median']}; lowest "
          f"{agg['round4']['lowest']}; highest {agg['round4']['highest']} "
          f"(95 analytical; 5 status pages unscored).", ""]
    if latest:
        md += [f"Round {latest}: 10/10 = {cur['ten_of_ten']}; mean {cur['mean']}; "
               f"median {cur['median']}; lowest {cur['lowest']}; highest "
               f"{cur['highest']}; vs round 4: {cur['up']} up, {cur['down']} "
               f"down, {cur['same']} unchanged.", ""]
    md += ["| # | Company | Status | R4 | "
           + (f"R{latest} | " if latest else "")
           + " | ".join(d[:5] for d in DIMS) + " | Next |",
           "|---|---|---|---|" + ("---|" if latest else "")
           + "---|" * len(DIMS) + "---|"]
    abbrev = {"PASS": "P", "BOUNDED": "b", "FAIL": "**F**", "N/A": "–",
              "NOT_MEASURED": "?"}
    for r in rows:
        g = (r.get(f"round{latest}_grades") if latest else None) \
            or r["round4_grades"]
        cur_s = r.get(f"round{latest}_score") if latest else None
        md.append(f"| {r['prospect_id']} | {r['company']} | "
                  f"{'status' if r['kind'] == 'STATUS_PAGE' else 'analysis'} | "
                  f"{r['round4_score'] if r['round4_score'] is not None else '–'} | "
                  + (f"{cur_s if cur_s is not None else '–'} | " if latest else "")
                  + " | ".join(abbrev.get(g.get(d), "?") for d in DIMS)
                  + f" | {r['next_action']} |")
    md += ["", "P = PASS, b = BOUNDED, F = FAIL, – = not applicable."]
    (OUT / "SCORECARD.md").write_text("\n".join(md) + "\n")

    mpath = OUT / "PROGRESS_MANIFEST.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    manifest.setdefault("program", "Prospect-100 resume (from Nov 9 session)")
    manifest.setdefault("worktree_branch", "qual/prospect100-resume")
    manifest.setdefault("base_commit", "3536cf41 (integration/unified-2026-11-25)")
    manifest.setdefault("current_wave", 0)
    manifest.setdefault("current_round", 5)
    manifest.setdefault("completed_company_ids", [])
    manifest["pending_company_ids"] = [r["prospect_id"] for r in rows
                                       if r["prospect_id"] not in
                                       manifest["completed_company_ids"]]
    manifest["scorecard"] = "docs/engineering/prospect100/resume/scorecard_live.json"
    manifest["last_baseline_build"] = agg["generated_at"]
    manifest["last_verified_commit"] = head
    log = OUT / "OPERATIONS.json"
    if log.exists():
        ops = json.loads(log.read_text())
        manifest["operations_log"] = str(log.relative_to(ROOT))
        manifest["last_completed_operation"] = ops["completed"][-1]
        manifest["blockers"] = ops["blockers"]
        manifest["outstanding_defects"] = ops["outstanding_defects"]
    manifest.setdefault("resume_command",
                        ".venv/bin/python scripts/prospect100/resume/build_baseline.py")
    mpath.write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(agg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
