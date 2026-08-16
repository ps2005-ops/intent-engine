# Every site that decides "is there a supported reading?"

Four instances of one defect appeared before this register existed: D13 (the
X-Ray rendered empty), the permanent INCOMPARABLE second look, D17 (X-Ray vs
brief vs deck), and D22 (a routing gate). Each was fixed where it was found,
and the next one appeared one layer away. This file exists so the fifth is
found by reading rather than by a customer.

**The rule.** Only `intent_engine.executive.contract` decides whether a
supported executive reading exists. A site may still decide whether *its own
subsection* has data.

**What the contract does NOT govern** — these keep their own typed states and
must not be collapsed into one boolean:

- whether causal magnitude is measurable (`causal_status`)
- whether history replay is valid (`economic_history.state`)
- whether independent corroboration exists (independence rows)
- whether an evidence family is empty (`evidence_families`)
- whether a deck slide is supported (`deck_is_presentable`, per-slide bullets)

## Register

| Site | Type | Verdict source | Status |
|---|---|---|---|
| `founder_brief/xray.py::render` | RENDERING | `_executive_read(dossier)` standing | canonical — this is the reading |
| `founder_brief/dossier.py::render_decision_lead` | RENDERING | contract (`reading_exists`) | MIGRATED (D17) |
| `founder_brief/narrative.py::_executive_answer` | RENDERING | contract | MIGRATED (D17) |
| `strategic_intelligence/slides.py::build_slides` view slide | RENDERING | contract + `thesis["view_withheld"]` | MIGRATED (D17) |
| `webapp/app.py::_insufficient_evidence_page` | ROUTING SINK | contract | MIGRATED (D22) — all three refusing routes funnel here |
| `webapp/app.py::_run_page` (3 call sites) | ROUTING | `avail`/`layer` → the sink above | inherits the sink's verdict |
| `webapp/app.py::_slides_page` | ROUTING | `avail["slides_ready"]` → redirects to `_run_page` | inherits |
| `webapp/app.py::_failed_run_page` | ROUTING | `run_state` terminal + no report | JUSTIFIED — a run that retrieved nothing is a different fact from a run with no reading |
| `founder_brief/build.py::classify_mode` | RENDERING | evidence counts | JUSTIFIED — selects depth of prose, not whether a reading exists |
| `slides.py::deck_is_presentable` | RENDERING | per-slide bullet support | JUSTIFIED — §5, a slide-level question |
| `founder_brief/qa.py::answer` (line ~108) | RENDERING | `brief.withheld` | **NOT MIGRATED — D25**, found live on `8f2ea0c` |

## Sweep terms

Re-run before declaring this class closed:

```
readiness  WITHHELD  sufficient  insufficien  evidence_bar
"enough public evidence"  "enough evidence"  view_withheld
"no strategic reading"  should_render  renderable  "supported reading"
```


## D25 — the fifth site, found live after this register was written

CEO Q&A on run `01M04MYF6XCFAC7C2SM1QK9YVB` (Cloudflare, `8f2ea0c`):

- X-Ray: "Supported in direction, not in size · Pricing decision"
- Brief: "A supported reading of Cloudflare, Inc. exists…"
- **Q&A: "I am not going to give you a strategic read on this company,
  because the public evidence does not support one — the same reason the
  summary above withheld it."**

The last clause is the tell: it cites a refusal the summary no longer makes.
`founder_brief/qa.py::answer` gates on `brief.withheld`, which is derived from
the run's own evidence, not from the contract.

**This register did not prevent it, and that is the lesson.** Q&A was named in
the sweep's search scope but never given a row, so it was searched for and not
recorded — the register only protects sites it lists. Any future sweep must
end by enumerating rows against the route table, not against memory of what
was looked at.

Fix (next batch, bounded): pass the contract into `qa.answer` and gate the
refusal on `contract.reading_exists` rather than `brief.withheld`, exactly as
`render_decision_lead` now does. The Q&A may still explain what this run could
not establish.
