# BATCH 24 — LIVE CUSTOMER PRODUCT COMPLETION

Starting state: founder `84ec6ed` (both branches, and the SHA actually served),
market `9b01ff1`, production `cfd4c3b` untouched.

## LIVE ROUTE GRAPH (§2 — mapped BEFORE any renderer was touched)

Read from `WebApp._route`, not from memory. This is the check whose omission
cost batches 21, 22 and 23.

### CUSTOMER LIVE PATH — reachable from a run a customer just created

| Route | Handler | Canonical object | Renderer |
|---|---|---|---|
| `GET /runs/<id>` | `_run_page` | run report | `founder_brief.render` |
| `GET /runs/<id>/progress` | `_progress` | run state + producers | inline + `hydration` |
| `GET /runs/<id>/brief` | `_executive_brief_page` | `decision_of(report)` | `founder_brief.dossier` |
| `GET /runs/<id>/story` | `_story_page` | `decision_of(report)` | `founder_brief.layers` |
| `GET /runs/<id>/dashboard` | `_intelligence_page` | `decision_of(report)` | `founder_brief.render` |
| `GET /runs/<id>/slides` | `_slides_page` | `decision_of(report)` | `strategic_intelligence.slides` |
| `GET /runs/<id>/full` | `_run_page(layer="full")` | `decision_of(report)` | `founder_brief.deep` |
| `GET /runs/<id>/sources` | `_sources_page` | retrieved documents | inline |
| `GET /runs/<id>/evidence/<c>` | `_evidence` | claim source refs | inline |
| `GET /runs/<id>/xray` | `_run_xray` | `decision_of(report)` | `founder_brief.xray` |
| `POST /runs/<id>/conversation` | `_converse` | run report | CEO Q&A |
| `POST /runs/<id>/{retry,fresh,feedback,share}` | — | run | actions |

`/runs/<id>/xray` is **new in this batch**. Every other row already existed.

### INTERNAL / DEMO-DOSSIER PATH — no live run links here

`/demo-dossiers`, `/demo-dossiers/<c>`, `/demo-dossiers/<c>/{xray,full,deck}`,
`/demo-dossiers/<c>/memory`, `/demo-dossiers/<c>/evidence`,
`/demo-dossiers/telemetry`, `/learning-acceleration`.

Operator-only, login-gated, 404 for a demo guest: `/learning`, `/dashboard`,
`/assistant`, `/status.json`, `/feedback`.

## DEFECTS

### D9 — SEV2, demo-blocking — CLOSED, break-proven

- **Screen:** any completed live run.
- **Customer-visible:** `/runs/<id>/xray` answered `404 Not Found`. The
  Executive X-Ray, the economic-history state and the second-iteration card
  were reachable only at `/demo-dossiers/<company>/xray`.
- **Root cause:** routing, not architecture. Every composed run *already*
  publishes a `CompanyDemoDossier` (`_publish_demo_dossier`, called from
  `_compose`), so the data was never missing — the route and the link were.
- **Fix:** `GET /runs/<id>/xray` → `_run_xray`, projecting the run's OWN
  `decision_of(report)` (not the dossier's separately-composed decision, which
  would have been the second state system §5 forbids). X-Ray added to
  `founder_brief.render._deeper`, the workspace nav.
- **Regression test:** `tests/test_live_run_workspace_is_reachable.py` —
  enumerates links from the rendered page and follows them, so a future
  capability that is built but never linked fails by name.
- **Break proof:** with only the source changes stashed, `/runs/<id>/xray`
  answered `404 Not Found` and both D9 tests went RED for that reason.

### D10 — SEV2 — CLOSED

- **Customer-visible:** "what changed" reported a first reading for every
  company forever, including companies with many stored versions.
- **Root cause:** `DossierStore` had no `previous()` method, and its only
  caller guarded with `hasattr(store, "previous")` — a capability test that
  could only ever answer False. `previous` was therefore always `None` and
  `_what_changed` always took its no-earlier-reading branch. Green forever,
  because `None` is a legal value.
- **Fix:** real `DossierStore.previous(company_id, *, before=…)`, ordered by
  `dossier_version` rather than file position; `hasattr` guard removed.

### D11 — SEV2 — CLOSED

- **Customer-visible:** the second-iteration card rendered its absent state on
  every surface, including the demo X-Ray where it was believed to work.
- **Root cause:** `second_iteration.compare()` had **zero production callers**,
  and `second_iteration` was not a field on `FounderDecision` — so the key was
  never written and could not survive serialization even if it had been. The
  prior reports' "built, unit-proven, off the live path" was half the story:
  the surface was wrong *and* the producer was never called.
- **Fix:** `FounderDecision.second_iteration` field with `as_dict`/`from_dict`
  round-trip; `_second_iteration_delta` composes it on the live run path via
  `_prior_run`, which applies the §17 comparability wall (same canonical
  company, strictly earlier in the owner's ordering, prior produced a report,
  same owner).

### D12 — SEV3 — CLOSED

- A test of mine passed against the pre-fix 404 page — it asserted on body text
  without asserting status first. Fixed by requiring `200` before the body
  assertion. Recorded because it is the same class of defect the file exists to
  catch: a test that cannot fail.

## §7 HYDRATION — wired to the live progress page

`hydration.assess` was built, proven and called by nothing on the customer
path; `/runs/<id>/progress` still showed one lifecycle-derived sentence.
`_hydration_state` now feeds it from producers only (identity, market snapshot,
coverage, discovery, decision) and `_hydration_body` renders the tier table.
Nothing consults a clock. Raw states never reach the sentence.
