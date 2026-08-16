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
| `founder_brief/qa.py::answer` → `_converse` | RENDERING | contract | MIGRATED (D25) |
| `webapp/app.py::_run_xray` | RENDERING | `_executive_read(dossier)` | CANONICAL_CONTRACT — this composes the reading the contract reports |
| `webapp/app.py::_executive_brief_page` | RENDERING | contract via `render_decision_lead` | MIGRATED (D17) |
| `webapp/app.py::_story_page` | RENDERING | `founder_brief/layers.py` `if not k:` (line ~810) | **NOT MIGRATED — D26**, gated on `brief.key_insight`, same shape as D25 |
| `webapp/app.py::_intelligence_page` | RENDERING | `founder_brief/layers.py` `if not k:` | **NOT MIGRATED — D26** (measured live: does not deny) |
| `webapp/app.py::_run_evidence` | RENDERING | `_evidence_screen` — independence/relevance as the bridge published them | JUSTIFIED — states why each SOURCE counts, never whether a reading exists; it deliberately does not re-decide independence, because two opinions about one document is how the drawer and the count start disagreeing |

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


## D26 — sites six and seven, found by the completeness gate

`test_every_strategic_surface_is_declared_in_the_verdict_register` walks the
dispatch table and demands a register row per strategic surface. On its FIRST
run it named five undeclared surfaces, two of which are genuine gaps:
`_story_page` and `_intelligence_page` both render through
`founder_brief/layers.py`, whose withheld branch gates on `brief.key_insight`
— the same field Q&A used, and the same shape as D25.

This is the gate working as intended. Five instances of this class were found
by customers reading live pages; the sixth and seventh were found by a test,
before deploy, in the first minute it existed.

Their customer-visible wording is softer than Q&A's ("The public evidence
describes what this company does, but none of it supports a strategic view"),
so whether it reads as a contradiction is being verified live rather than
assumed. Status is recorded as NOT MIGRATED either way, because the verdict is
demonstrably not contract-owned.
