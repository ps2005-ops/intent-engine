# CompanyDemoDossier — canonical input map

Batch 7 §3's prerequisite, produced as read-only discovery. **No aggregator was
built.** This exists so the session that builds one does not have to rediscover
where truth lives, and does not invent a producer for a field that has none.

Read the two findings at the bottom before designing the contract. The first
one changes the shape of the whole node.

---

## The table

`UNAVAILABLE` means: no canonical producer exists on the founder branch today.
§3 says mark it and do not manufacture one. It is not a defect and it is not a
licence to compute the field locally.

| DOSSIER FIELD | CANONICAL PRODUCER | STORE | READER |
|---|---|---|---|
| company identity | `company_ingestion.entities.resolve_choice` (`EntityResolution`) | `data/entity_graph.db` | `WebApp._analyze` (app.py:1355) resolves before any work |
| run / analysis id | `WebApp._analyze` | `webapp.store.WebStore` (append-only), `owner_of(run_id)` | `ci.store.for_run(run_id)` |
| evidence / observations | `company_ingestion.service` | company-ingestion store, per run | `ci.store.for_run` |
| evidence trust + event identity | `external_intel.evidence_trust` (`Event`, `Trust`, `read`, `as_read_by`) | in the analysis report block | `evidence_trust.read(block)` |
| **evidence independence** | **UNAVAILABLE** | — | — |
| source families / health | `research.sources`, `research.records` | research store | `research.service` |
| coverage state | `external_intel.coverage_state` (`classify`, `baseline`, `Coverage`) | derived per analysis | `coverage_state.classify(intel)` |
| standing ceiling | `external_intel.standing_ceiling` + `coverage_state.ceiling_for` | derived | consumed by every surface |
| economic / macro exposure | `external_intel.macro_exposure`, `macro_contract` | analysis report | `external_intel.pack` |
| market context | `external_intel.market_contract`, `market_producer` | analysis report | `external_intel.pack` |
| **beliefs, belief maturity** | `intent_engine.market.belief_formation`, `belief_maturity`, `beliefs` | **MARKET repo** | via bridge only — see FINDING 1 |
| **theses, revision history** | market-side | **MARKET repo** | via bridge only |
| **causal question / method / result / refusal** | `market.causal*`, `causal_question`, `causal_diagnostics` | **MARKET repo** | via bridge only |
| **historical replay episodes** | `market.causal_episodes` | **MARKET repo**, 13/40 | via bridge only |
| **adversary cases / strategic response** | `market.adversary_case`, `actor_response_memory` | **MARKET repo** | via bridge only |
| strategic market intel (the bridge) | market `strategic_export` | **a file on disk** | `external_intel.strategic_contract` (`SCHEMA_VERSION = strategic_market_intel.v1`, `MAX_AGE_DAYS = 21`) |
| internal business graph | `business_graph.internal` private node constructors | `business_graph.private_store.PrivateGraphStore`, tenant-partitioned | `graph.read(scope=...)` |
| internal impact | `external_intel.internal_impact.assess_internal_impact` | derived per request | `webapp.internal_view.answer` |
| TenantScope | `core.tenant.establish` / `webapp.tenancy.scope_for_session` | `tenant_directory.jsonl`, audited | `scope_for_session` |
| Living Decision Records | `executive.living_decision` (`open_decision`, `revise`) | `LivingDecisionStore`, tenant-partitioned jsonl | `open_decisions`, `awaiting_information`, `what_changed` |
| Minimum Data Requests | `external_intel.minimum_data_request.route` | `DataRequestStore` (`*.mdr.jsonl`), tenant-partitioned | `requests(scope=)`, `/decisions` dereferences |
| Minimum Viable Experiments | `minimum_data_request.design_experiment` | `DataRequestStore` (`*.mve.jsonl`) | `experiments(scope=)` |
| DecisionImpact | `external_intel.decision_impact` (`compare_field`, `materiality_of`, `DecisionImpact`) | derived from a run pair | needs TWO runs — see §16's `IMPACT_UNMEASURABLE` |
| learning health / funnel | `external_intel.founder_learning_health.assess(root)` | consumption-receipt ledger (`consumption_receipt.LEDGER_PATH`) | `assess`, `bottleneck_of` |
| consumption receipts | `external_intel.consumption_receipt.emit` | ledger jsonl under root | `read_events(root)` |
| tenant receipts (audit) | `webapp.tenancy.receipt_for` | `tenant_receipts.jsonl` | `app._tenant_receipts.all()` |
| MDR telemetry | `minimum_data_request.MDRTelemetry.of` | in-memory on `WebApp`, exposed at `?format=json` | `app._mdr_telemetry` |
| prose dossier (existing) | `founder_brief.dossier` (`Passage`, `Dossier`) | derived from the report dict | `founder_brief.render` |
| CEO answers | `external_intel.ceo_answers` | derived | presenter |
| **UI visual / a11y verification** | **UNAVAILABLE** | — | §17: `VISUAL_UNMEASURED`, never `PASS` |
| **cohort assignment** | **UNAVAILABLE** | — | no manifest exists yet |

---

## FINDING 1 — the dossier spans two repositories, and the seam between them
## is a file

More than half of §8–§12's blocks (beliefs, theses, causal, historical replay,
adversary) have **no producer on the founder branch**. They live in
`intent_engine.market`, which the founder branch *cannot import by design*:

> "The producer lives in a package this one CANNOT IMPORT. `intent_engine.market`
> does not exist on this branch, and must not: the moment founder code can
> import trading code, the guarantee stops being structural and starts being a
> promise about what people will remember not to do."
> — `external_intel/strategic_contract.py`

The only crossing is `strategic_market_intel.v1`: a file the market side writes
and the founder side re-validates against its own allowlist, with
`MAX_AGE_DAYS = 21`. On most runs it returns `available: False`, and that is
the honest state.

**Three consequences for the contract, all of which must be decided before any
code is written:**

1. A founder-side `CompanyDemoDossier` cannot populate the belief, causal,
   historical or adversary blocks from canonical producers. It can only
   reference what the bridge payload happens to carry. Every one of those
   blocks needs a first-class `*_UNAVAILABLE` reading that is reached on the
   *normal* path, not on an error path.
2. This program has already shipped the failure mode once — recorded as
   *"Bridge never opened: all 22 dossiers silently refused over two unknown
   fields; a refused dossier looks identical to a company never analysed."*
   A dossier that cannot distinguish `BRIDGE_REFUSED` from
   `BRIDGE_ABSENT` from `COMPANY_NOT_ANALYSED` will reproduce it at
   100-company scale, where nobody will read 100 of them by hand.
3. Also recorded: *"Bridge needs a shared disk — the dossier handoff is a file,
   so no free-tier preview can ever show a live crossing."* §33's
   LIVE_VERIFIED bar therefore cannot include a live bridge crossing on the
   preview deployment. Either the live proof runs both sides on one disk, or
   the bridge blocks are proven `UNAVAILABLE` live and the crossing is proven
   separately.

**The design question the next session must answer first:** is
`CompanyDemoDossier` a founder-side index that reports the market blocks as
unavailable-by-architecture, or a third artifact assembled where both stores
are mounted? §2 says it must reference and never re-derive — which is exactly
what makes this a fork in the road rather than an implementation detail.

## FINDING 2 — DecisionImpact needs a run pair, so a first analysis is
## structurally `IMPACT_UNMEASURABLE`

`decision_impact.compare_field(impact_type, before, after)` is a comparison.
A company's first dossier has no `before`. §16 already anticipates this
(`IMPACT_UNMEASURABLE` when only `FIRST_OBSERVATION` exists) — worth noting
that it is not a data gap that better retrieval fixes, it is the second run.
That makes §21's dossier diff and §20's versioned persistence load-bearing for
§16, not merely nice for the second 100-company pass.

## FINDING 3 — no company manifest exists, and the closest candidate is small

`scripts/v11_real_company_acceptance.py::COMPANIES` is a dict keyed by domain.
It is an acceptance fixture, not a universe, and §34 is explicit that it must
not be silently declared the canonical 100. No other company list was found
under `data/` (which holds only `entity_graph.db`) or `docs/`.

## Vocabulary already canonical — reuse, do not restate

- coverage: `NEVER_ANALYSED, PRIOR_ONLY, HYDRATING, PARTIALLY_OBSERVED, OBSERVED, DEGRADED` (`coverage_state.COVERAGE_STATES`) — §5's readiness model should extend or map onto this rather than introduce a parallel scale.
- internal impact: `INTERNAL_IMPACT_IDENTIFIED, NO_INTERNAL_IMPACT, INTERNAL_LINK_WITHOUT_METRIC, INTERNAL_DATA_UNAVAILABLE`, with `NOT_A_NEGATIVE` exported so a surface asserts against the set (`internal_impact.py`) — §13 and §26's missing-vs-zero control are already enforceable here.
- sensitivity: `internal, confidential, restricted` (`business_graph.internal.SENSITIVITIES`), plus `public` added by `minimum_data_request.PRIVACY_CLASSES`.
- population: `SYNTHETIC_ENTERPRISE, REAL_ENTERPRISE` with `refuse_mixed_population` raising on a join — §27's requirement is already implemented; consume it.
- request ladder: `NO_REQUEST_DATA_SUFFICIENT, NO_REQUEST_NO_DECISION_VALUE, MDR_ISSUED, MVE_PROPOSED, UNRESOLVABLE, BREADTH_REFUSED`, with `NO_ASK_STATES` exported.
