# ADR — COMPANY_DEMO_DOSSIER_ARCHITECTURE

**Status:** ACCEPTED (Batch 8)
**Supersedes:** the open fork recorded as FINDING 1 in
[`DOSSIER_CANONICAL_INPUTS.md`](DOSSIER_CANONICAL_INPUTS.md)

---

## The question Batch 7 left open

More than half of what a `CompanyDemoDossier` must show — beliefs, theses,
thesis history, causal questions and results, historical replay, adversary
cases — has **no producer on the founder branch**. It lives in
`intent_engine.market`, a package the founder branch cannot import by design.

Batch 7 stopped rather than guess, and asked: is the dossier a founder-side
index that reports market blocks unavailable-by-architecture, or a third
artifact assembled where both stores are mounted?

## Decision

**`CompanyDemoDossier` is a neutral, versioned, materialized read model
assembled exclusively from serialized snapshot contracts.**

Market and Founder each publish a bounded, sanitized, versioned snapshot of
their own canonical state. A neutral assembler joins those snapshots. It
validates, joins, records availability, references canonical ids, and derives
only *metadata about the join*. It never reasons.

```
  MARKET                                  FOUNDER
  intent_engine.market                    intent_engine.external_intel
        │                                       │
        │ market_demo_snapshot.v1               │ founder_demo_snapshot.v1
        │ (serialized bytes)                    │ (serialized bytes)
        ▼                                       ▼
        └───────────►  intent_engine.demo_dossier  ◄───────────┘
                       (imports NEITHER)
                              │
                              ▼
                     company_demo_dossier.v1
```

The neutral package `intent_engine.demo_dossier` imports nothing from
`intent_engine.market`, and nothing from the founder intelligence packages
(`external_intel`, `business_graph`, `executive`, `webapp`, `company_ingestion`,
`founder_brief`, `research`). A structural guard enforces this by tokenizing
the source rather than grepping it — a comment explaining the rule must not
satisfy the rule.

## What this rejects, explicitly

**OPTION A — Founder imports Market modules.** Rejected. The import boundary is
the only *structural* guarantee that trading internals cannot reach a founder
surface. `strategic_contract.py` states the reason: the moment founder code can
import trading code, the guarantee stops being structural and becomes a promise
about what people will remember not to do.

**OPTION B — Market imports Founder internals.** Rejected for the same reason
in the other direction, plus a second: it would make Market's release cadence
depend on Founder's internal shapes.

**OPTION C — the dossier independently rebuilds intelligence.** Rejected. A
second derivation is a second copy of a rule, and the two drift. This program
has already paid for that: the founder side re-deriving evidence counts from
source rows produced the arithmetic that counted three sites carrying one press
release as three events. The dossier references canonical ids and bounded
projections; it does not recompute a thesis, a recommendation, a causal
standing, a confidence, or a `DecisionImpact`.

**OPTION D — a shared filesystem as an architectural requirement.** Rejected.
A shared disk may be *one transport implementation*. It may not be the semantic
contract. `assemble()` receives snapshot **objects parsed from bytes**; it has
no knowledge of where the bytes came from. The bytes may arrive from a file,
an HTTP POST (`market.dossier_transport` already ships them that way), object
storage, or a test fixture, and the join is identical in all four cases. No
dossier logic may reference an absolute path, a same-process import, or a
shared Python object.

This is what makes the eventual 100-company factory deployable: Market and
Founder can run on different hosts, and a missing Market bridge becomes an
explicit product state rather than an absent product.

## Consequences

### 1. Availability is a first-class reading, never a blank

A snapshot that did not arrive is `UNAVAILABLE` with a reason. It is never
rendered as "the market found nothing", and a `MARKET_UNAVAILABLE` dossier is
never confusable with a company nobody analysed. Batch 7's FINDING 1 recorded
the failure this prevents: 22 published dossiers were silently refused over two
unknown fields, and a refused dossier looked identical to a company never
analysed.

### 2. Unknown fields are tiered, not uniformly fatal

The existing `strategic_contract` fails closed on **every** unknown field, at
any depth. That posture is correct for a payload rendered directly to a founder
— and it is also precisely what kept the bridge silently closed for 22
dossiers, because the producer added `company_display_name` and the consumer
had never heard of it.

The snapshot contracts therefore split the judgement:

| Field class | Unknown field policy |
|---|---|
| security / authority / population / tenancy | **fail closed** — refuse the snapshot |
| everything else | **ignore, and record it** in `unknown_fields` |

An ignored unknown field is counted in telemetry, so a producer that has moved
ahead of a consumer is *visible* rather than silent. Fail-open on a descriptive
field plus a counter beats fail-closed plus a warning log nobody reads.

### 3. The dossier is not an authorization boundary

`FounderDemoSnapshot` is produced **after** `TenantScope` has been applied.
The assembler consumes sanitized references and statuses; it never receives
private graph traversal authority, and it never adopts a `tenant_id` from a
Market snapshot. Market is public-evidence-derived and has no standing to name
a tenant at all.

### 4. `MARKET_FOUNDER_COMBINED_CROSSING` is a separate node

Because the bridge needs shared transport, a free-tier preview cannot prove a
live crossing. The neutral dossier vertical may become LIVE_VERIFIED for the
partial-availability path while the combined crossing stays separately
INSTRUMENTED / BLOCKED_ENVIRONMENT. That distinction is reported, not hidden.

### 5. `DecisionImpact` needs a pair, so versioned persistence is load-bearing

A company's first dossier is structurally `IMPACT_UNMEASURABLE_FIRST_OBSERVATION`.
That is not a retrieval gap; the second run is the fix. Persistence must
therefore version rather than overwrite, and the diff must distinguish
`FIRST_OBSERVATION` from "everything changed".
