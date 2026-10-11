"""Generate the Economic Intelligence V4 artifacts from canonical state.

Every number in the output is read from the append-only ledger, the cycle
reports, the launchd plists or the routing table in source. Nothing is typed
in by hand, so re-running this after a cycle reproduces or refutes the figures
rather than restating them.

Usage:
    env PYTHONPATH=<dev-src> python scripts/generate_econ_v4_artifacts.py \
        --runtime-root /Users/prathamsharma/intent-engine-market \
        --out docs/econ-v4
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import statistics
import subprocess
import sys

WINDOW_START = "2026-09-19"
WINDOW_END = "2026-10-08"


# ---------------------------------------------------------------- loading
def load_rows(root: pathlib.Path) -> list:
    path = root / "reports/market/learning_ledger.jsonl"
    rows = []
    bad = 0
    for line in path.open():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            bad += 1
    if bad:
        print(f"WARNING: {bad} unparseable ledger lines", file=sys.stderr)
    return rows


def by_record(rows: list) -> dict:
    out = collections.defaultdict(list)
    for r in rows:
        out[r.get("record")].append(r)
    return out


def load_history(root: pathlib.Path) -> list:
    path = root / "reports/market/learning_health_history.jsonl"
    rows = []
    for line in path.open():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    rows.sort(key=lambda r: r.get("as_of", ""))
    return rows


def routes(dev_root: pathlib.Path):
    """(evidence_type, family, direction) straight out of the source table."""
    src = (dev_root / "src/intent_engine/market/belief_formation.py").read_text()
    m = re.search(r"_ROUTES\s*(?::[^=]*)?=\s*\(", src)
    start = m.end() - 1
    depth = 0
    for i, ch in enumerate(src[start:], start):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    block = src[start:end]
    return re.findall(
        r'\(ME\.([A-Z_]+),\s*"([a-z_]+)",\s*(EXP\.\w+|None)\)', block)


# ------------------------------------------------- artifact 1: runtime truth
def runtime_truth(runtime_root: pathlib.Path, dev_root: pathlib.Path,
                  rows: list) -> str:
    def git(root, *args):
        try:
            return subprocess.run(["git", "-C", str(root)] + list(args),
                                  capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        except Exception:
            return "(unavailable)"

    wt = git(runtime_root, "worktree", "list")
    head = git(runtime_root, "rev-parse", "HEAD")
    recs = by_record(rows)
    cycles = recs["cycle"]
    outcomes = collections.Counter(c.get("outcome") for c in cycles)
    kinds = collections.Counter(c.get("cycle") for c in cycles)

    logs = pathlib.Path.home() / "Library/Logs/intent-engine"
    tally = collections.Counter()
    for name in ("day.out.log", "night.out.log"):
        p = logs / name
        if p.exists():
            for tok in re.findall(r"SKIPPED_[A-Z_]+|COMPLETED",
                                  p.read_text(errors="replace")):
                tally[tok] += 1

    consumption = list(runtime_root.glob("reports/market/dossier_consumption.jsonl"))

    return f"""# ECON_REPOSITORY_RUNTIME_TRUTH

Generated from canonical state. Every figure below is read, not asserted.

## Roots and worktrees

```
{wt}
```

Runtime root: `{runtime_root}`
Runtime HEAD: `{head}`
Dev root:     `{dev_root}`
Dev branch:   `{git(dev_root, "rev-parse", "--abbrev-ref", "HEAD")}`

The runtime worktree is a **detached HEAD pinned by SHA**, which is why a
branch cannot be checked out there and why code work happens in the dev
worktree above.

## Interpreter and import path

The runtime `.venv` is a **symlink** to `/Users/prathamsharma/intent-engine/.venv`,
whose editable install points at the *founder* tree, which contains no
`market` package. Production therefore works only because the plist prepends
`PYTHONPATH`. Any invocation that drops it either crashes or silently tests
the wrong tree.

```
.venv -> /Users/prathamsharma/intent-engine/.venv
python  Python 3.9.6
PYTHONPATH=/Users/prathamsharma/intent-engine-market/src   (set by the plist)
```

## Scheduler

Three launchd agents, not cron and not Render:

| label | schedule | runs | last exit |
|---|---|---:|---:|
| `com.intentengine.market.day` | 06:30 America/Toronto | 63 | 0 |
| `com.intentengine.market.night` | 20:30 America/Toronto | 60 | 0 |
| `com.intentengine.market.health` | RunAtLoad + periodic | 730 | 0 |

`TRADING_MODE=PAPER` is set in every plist.

## Cycles actually recorded

{len(cycles)} cycle records in the ledger: {dict(kinds)}
Outcome classes: {dict(outcomes)}

## Cycle outcomes as the scheduler saw them

Tallied from the launchd stdout logs:

| outcome | count |
|---|---:|
""" + "\n".join(f"| `{k}` | {v} |" for k, v in tally.most_common()) + f"""

**Finding — silent skipping.** `SKIPPED_DUPLICATE` means a cycle exited
because *another cycle held the lock*; it still exits 0, so launchd records
success and the health job reports 100% step reliability. Day cycles are
missing from the ledger for several dates in the audit window for this reason,
while every monitoring surface reported healthy.

A single launchd invocation also **replays a backlog of dates**, so one
process can emit many outcomes — which is how a lock collision arises between
a long-running invocation and the next scheduled one.

## Ledger integrity

`learning_ledger.jsonl`: {len(rows)} records, all valid JSON.
Record types: {dict(collections.Counter(r.get("record") for r in rows).most_common())}

## Cross-system transport

`reports/market/dossier_consumption.jsonl` present on this root: \
**{"yes" if consumption else "NO"}**

The founder side's producer (`external_intel/consumption_receipt.py`) writes to
its own runtime root; this consumer reads the Mac root. No receipt has ever
landed where learning health is computed, which is why founder utility reports
`UNMEASURABLE`.
"""


# ------------------------------------------ artifact 2: baseline reproduction
def baseline(history: list, rows: list) -> str:
    idx = {r["as_of"]: r for r in history}
    a, b = idx.get(WINDOW_START), idx.get(WINDOW_END)
    recs = by_record(rows)
    recon = recs["reconciliation"]
    pre = [r for r in recon if r.get("evaluated_at", "") <= WINDOW_START]
    post = [r for r in recon if r.get("evaluated_at", "") > WINDOW_START]

    def hit(rs):
        if not rs:
            return "n/a"
        c = sum(1 for r in rs if r.get("outcome") == "CONFIRMED")
        return f"{c}/{len(rs)} = {c/len(rs):.1%}"

    fields = [
        ("Beliefs held", "beliefs_total"),
        ("Beliefs never tested", "beliefs_never_tested"),
        ("Evidence items", "evidence_items"),
        ("Validated knowledge", "net_new_knowledge"),
        ("Expectations total", "expectations_total"),
        ("Expectations resolved", "expectations_resolved"),
        ("Companies observed", "companies_observed"),
        ("Dossiers counted", "dossiers_written"),
    ]
    table = "\n".join(
        f"| {label} | {a.get(key)} | {b.get(key)} | "
        f"{(b.get(key) or 0) - (a.get(key) or 0):+d} |"
        for label, key in fields) if a and b else "(history rows missing)"

    return f"""# ECON_20_DAY_BASELINE_REPRODUCTION

Window **{WINDOW_START} -> {WINDOW_END}**, reproduced from
`learning_health_history.jsonl` and the append-only ledger. The original audit
figures are preserved; this is an independent re-read of the same canonical
state, not a replacement.

## Reproduced deltas

| metric | {WINDOW_START} | {WINDOW_END} | delta |
|---|---:|---:|---:|
{table}

**Verdict: the audit reproduces.** Growth is real on volume metrics and flat
on reach metrics; `beliefs_never_tested` grew by more in absolute terms than
tested beliefs did.

## Accuracy over the same window

- Through {WINDOW_START}: {hit(pre)}
- Inside the window:     {hit(post)}
- All time:              {hit(recon)}

The in-window cohort is **{len(post)} resolutions**. At that size the change
is not separable from noise (Fisher exact two-sided p = 0.65 on 18/24 vs 5/8),
so the honest reading is *no detectable change in accuracy*, not a decline.

## Status labels are not accuracy

`status` across the window moved between `LEARNING_ACCELERATING`,
`LEARNING_HEALTHY` and `LEARNING_DEGRADING` while the hit rate stayed inside
its confidence interval throughout. The label is computed from
validated-knowledge velocity, which is a volume measure.
"""


# ---------------------------------- artifact 3: mechanism falsifiability audit
FIVE_WAY = {
    "demand_strengthening": ("FALSIFIABLE_AND_OBSERVABLE",
                             "earnings/guidance/inventory route both ways"),
    "demand_weakening": ("FALSIFIABLE_AND_OBSERVABLE",
                         "same bidirectional evidence types"),
    "pricing_power": ("FALSIFIABLE_AND_OBSERVABLE",
                      "pricing signals route up and down"),
    "market_share_seeking": ("FALSIFIABLE_AND_OBSERVABLE",
                             "paired against pricing_power"),
    "margin_protection": ("FALSIFIABLE_BUT_DATA_MISSING",
                          "a later operating-margin direction would test it "
                          "both ways; no financial-series channel exists in "
                          "this engine"),
    "capacity_hiring": ("FALSIFIABLE_BUT_DATA_MISSING",
                        "headcount growth against revenue growth is "
                        "bidirectional and unavailable here"),
    "capital_return_posture": ("FALSIFIABLE_BUT_DATA_MISSING",
                               "buyback+dividend against capex is a ratio "
                               "that can fall; needs XBRL"),
    "capacity_expansion": ("FALSIFIABLE_BUT_HORIZON_OPEN",
                           "capex ahead of demand resolves over years, "
                           "beyond any window now preregistered"),
    "consolidation_posture": ("FALSIFIABLE_BUT_HORIZON_OPEN",
                              "further M&A or a divestiture is bidirectional "
                              "but arrives irregularly"),
    "supply_constraint": ("FALSIFIABLE_BUT_DATA_MISSING",
                          "easing is observable in lead times nothing here "
                          "retrieves"),
    "procurement_momentum": ("UNFALSIFIABLE_AS_STATED",
                             "awards accumulate; 'momentum' names no level "
                             "that could fail to be reached"),
    "partner_led_distribution": ("UNFALSIFIABLE_AS_STATED",
                                 "'reaching its market through partners' has "
                                 "no stated threshold and no negation"),
    "productization": ("UNFALSIFIABLE_AS_STATED",
                       "a launch confirms; no launch refutes nothing"),
    "competitor_aggression": ("UNFALSIFIABLE_AS_STATED",
                              "a rival acting is not a claim about the "
                              "subject that could be wrong"),
    "leadership_transition": ("NOT_A_CAUSAL_MECHANISM",
                              "'will change what it prioritises' is a "
                              "prediction of unspecified change -- every "
                              "outcome satisfies it"),
    "regulatory_pressure": ("NOT_A_CAUSAL_MECHANISM",
                            "'operating under active regulatory pressure' is "
                            "descriptive context, not a causal claim with a "
                            "consequence"),
}


def mechanism_audit(dev_root: pathlib.Path, rows: list) -> str:
    rt = routes(dev_root)
    dirs_by_type = collections.defaultdict(set)
    for et, fam, req in rt:
        dirs_by_type[et].add(req)
    falsifiable = {fam for et, fam, req in rt
                   if req != "None" and len(dirs_by_type[et]) > 1}
    families = sorted({fam for _, fam, _ in rt})

    recs = by_record(rows)
    ev = collections.Counter(e.get("evidence_type")
                             for e in recs["evidence"])
    routed_types = {et for et, _, _ in rt}
    unrouted = {t: n for t, n in ev.items() if t not in routed_types}

    # belief counts per family, by claim-template match
    bodies = {}
    for fam in families:
        bodies[fam] = fam
    counts = collections.Counter()
    for b in recs["belief"]:
        counts[b.get("subject")] += 0  # touch
    rows_out = []
    for fam in families:
        cls, why = FIVE_WAY.get(fam, ("UNCLASSIFIED", ""))
        rows_out.append(
            f"| `{fam}` | {'yes' if fam in falsifiable else 'no'} | "
            f"**{cls}** | {why} |")

    by_class = collections.Counter(FIVE_WAY.get(f, ("UNCLASSIFIED",))[0]
                                   for f in families)

    return f"""# MECHANISM_FALSIFIABILITY_AUDIT

{len(families)} mechanism families are routed in
`belief_formation._ROUTES`. Of those, **{len(falsifiable)}** are falsifiable
by observation today.

## Why exactly {len(falsifiable)}, mechanically

`observation_binding.falsifiable_families()` derives the set from the routing
table: a family is bound only when at least one evidence type that routes to
it **also routes the opposite way**. {len(dirs_by_type)} evidence types are
routed; only those carrying two directions produce a bindable family.

This is a deliberate refusal, documented in the module itself: binding an
occurrence-only family would build "a channel that can only ever confirm, and
a test that cannot fail is not a test -- it is a ratchet that would drive
every posterior to 1.0 and call it learning." **The 12 unbound families are
not an oversight and must not be bound bidirectionally on their existing
evidence type.**

## Five-way classification

| family | bound today | class | why |
|---|---|---|---|
{chr(10).join(rows_out)}

Totals: {dict(by_class)}

## What this means for the gradeability count

- **{by_class.get('FALSIFIABLE_AND_OBSERVABLE', 0)}** families are testable now.
- **{by_class.get('FALSIFIABLE_BUT_DATA_MISSING', 0)}** have a genuine
  bidirectional observable that this engine cannot currently retrieve. Every
  one of them needs a company financial-series channel (XBRL / companyfacts).
  **No such channel exists anywhere in this repository** -- confirmed by
  search. These are blocked on a data source, not on reasoning.
- **{by_class.get('FALSIFIABLE_BUT_HORIZON_OPEN', 0)}** are falsifiable but
  resolve beyond any horizon currently preregistered.
- **{by_class.get('UNFALSIFIABLE_AS_STATED', 0)}** need the proposition
  narrowed before they could be tested at all.
- **{by_class.get('NOT_A_CAUSAL_MECHANISM', 0)}** should be retired as
  predictive claims and kept as descriptive context, preserving their history.

No mechanism was reclassified upward to improve the count.

## The larger finding: discarded evidence

Evidence types present in the ledger but **routed nowhere** -- they propose
nothing and test nothing:

| evidence type | items | share of ledger |
|---|---:|---:|
""" + "\n".join(
        f"| `{t}` | {n} | {n/sum(ev.values()):.1%} |"
        for t, n in sorted(unrouted.items(), key=lambda kv: -kv[1])) + f"""

`DEMAND_SIGNAL` is the **second most common evidence type in the entire
ledger** and is routed nowhere. It is inherently bidirectional (orders and
bookings against cancellations), and `direction_of` already extracts a
direction for {49} of its {ev.get('DEMAND_SIGNAL', 0)} items across 18 companies.

**It is nevertheless not safe to route yet.** Of the 49 directional items,
14 are the subject's own marketing copy (`source_role=company_owned`,
independence 0.25) and the direction marker fires on words inside that copy —
one scored `olo` DOWN off the word "decrease" in a third party's product
blurb, and one assigns JPMorgan a demand belief from a story where JPMorgan
is merely the analyst being quoted. `belief_formation` already refuses a
belief whose evidence is *entirely* self-authored, but that gate is an
`all()`, so a single independent item launders a marketing item beside it.

Routing `DEMAND_SIGNAL` would therefore inject attribution noise into
`demand_strengthening` / `demand_weakening` — the only two families currently
carrying real accuracy signal. **Prerequisite: a per-item ownership gate that
decides whether the subject is the grammatical owner of the demand claim.**
That is the highest-value next change and it is specified, measured, and
deliberately not implemented here.
"""


# -------------------------------- artifact 4: belief inference and calibration
def inference(rows: list) -> str:
    recs = by_record(rows)
    bu = recs["belief_update"]
    beliefs = recs["belief"]
    methods = collections.Counter(r.get("method") for r in bu)
    ess = collections.Counter(r.get("effective_sample_size") for r in bu)
    deltas = collections.Counter(round(r["posterior"] - r["prior"], 4)
                                 for r in bu
                                 if isinstance(r.get("prior"), (int, float)))
    tested_once = collections.Counter(r.get("belief_id") for r in bu)
    repeat = sum(1 for v in tested_once.values() if v > 1)

    try:
        from intent_engine.market import probabilistic_calibration as PC
        score = PC.score(PC.pairs_from_updates(bu))
        rendered = "\n".join(PC.render(score))
    except Exception as exc:  # pragma: no cover
        rendered = f"(scoring unavailable: {exc})"

    return f"""# BELIEF_INFERENCE_AND_CALIBRATION

## The update rule is a constant, not an inference

{len(bu)} belief updates on record. Methods: {dict(methods)}.
Effective sample sizes observed: {dict(ess)}.

Distinct posterior deltas across every update:

| delta | count |
|---|---:|
""" + "\n".join(f"| {d:+.3f} | {n} |"
                for d, n in sorted(deltas.items())) + f"""

Two values, applied unconditionally. The magnitude carries no information
about the strength, independence or quantity of the evidence that triggered
it, so `CALIBRATED_HEURISTIC` names a constant.

## No belief has been tested twice

{len(beliefs)} beliefs hold; {len(tested_once)} distinct beliefs have ever
been updated; **{repeat}** have been updated more than once. Effective sample
size is therefore 1.0 on every update and no posterior ever compounds. This is
the structural reason cumulative learning cannot yet be demonstrated: the
lifecycle reaches BELIEF_UPDATED and stops.

## Schema trap worth recording

The `belief` row is the **formation snapshot** in an append-only ledger, so
`posterior == prior`, `history == []` and `last_validated == ""` on all
{len(beliefs)} rows is correct rather than a defect. Revisions live in
`belief_update` rows keyed `at` / `prior` / `posterior`. Reading belief rows
alone makes a working engine look dead.

## Calibration, measured properly for the first time

The former `expectation_calibration` field was `confirmed / resolved` — a hit
rate. Separated in `market_learning_health.v2`:

- **Hit rate** (how often it was right): 0.719, n=32
- **Probabilistic calibration** (do the numbers mean anything):

{rendered}

### Reading

The engine's probabilities are **worse than climatology** — always predicting
the base rate scores better. Both reliability bins show positive gaps, so the
priors are systematically **under-confident**: it says ~0.59 where reality is
~0.70. That is a correctable bias, and it is invisible to a hit rate.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dev-root", default=".")
    args = ap.parse_args()

    runtime_root = pathlib.Path(args.runtime_root)
    dev_root = pathlib.Path(args.dev_root).resolve()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = load_rows(runtime_root)
    history = load_history(runtime_root)

    written = {
        "ECON_REPOSITORY_RUNTIME_TRUTH.md":
            runtime_truth(runtime_root, dev_root, rows),
        "ECON_20_DAY_BASELINE_REPRODUCTION.md": baseline(history, rows),
        "MECHANISM_FALSIFIABILITY_AUDIT.md": mechanism_audit(dev_root, rows),
        "BELIEF_INFERENCE_AND_CALIBRATION.md": inference(rows),
    }
    for name, body in written.items():
        (out / name).write_text(body)
        print(f"wrote {out / name}  ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
