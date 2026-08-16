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

## Sweep terms

Re-run before declaring this class closed:

```
readiness  WITHHELD  sufficient  insufficien  evidence_bar
"enough public evidence"  "enough evidence"  view_withheld
"no strategic reading"  should_render  renderable  "supported reading"
```
