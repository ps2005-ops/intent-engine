# T023 Dependency Gaps

*The dependency-gap protocol (Session 13). When a workspace capability
cannot be served by an existing public read surface, it is recorded here —
never satisfied by importing a private internal, by modifying a frozen
T019–T022 subsystem, or by computing the missing domain result inside
`personal/`. The workspace degrades honestly instead.*

The rule: **no adapter may compute or infer a missing domain result.** A
gap becomes an honest `OUT_OF_SCOPE` or `UNAVAILABLE` answer with the
reason stated, and the smallest future additive change is written down.

---

## Gap 1 — Competitor intelligence (SUMMARIZE_COMPETITORS)

| | |
|---|---|
| **Requested workspace capability** | "summarize the competitors" |
| **Missing public read contract** | none — no subsystem produces competitor data |
| **Owning subsystem** | none exists (CRM owns prospects/customers, not competitors; the Decision Record has `competitor` *entity relationships* but no competitor intelligence) |
| **Smallest future additive change** | a competitor-intelligence read surface (likely part of T023.5's public intelligence pass, where a company's competitor landscape is assembled) |
| **Can T023 degrade honestly?** | **Yes.** `SUMMARIZE_COMPETITORS` returns `OUT_OF_SCOPE` with the reason "no subsystem reports competitor intelligence yet; this arrives with the public intelligence pass (T023.5)." No competitor data is invented. |

This is the archetypal gap: the workspace could trivially *sound*
authoritative about competitors by asking a model, and the entire product
thesis is that it must not. The honest refusal is the feature.

---

## Gap 2 — Global research-conclusion listing (NOT a gap; composition)

| | |
|---|---|
| **Requested capability** | research highlights across all requests for the morning brief |
| **Read contract** | `ResearchService.store.request_ids()` + `get_package` + `draft_conclusion` per request — request-scoped, but enumerable |
| **Resolution** | **Composition, not a gap.** The research adapter enumerates `request_ids()` and reads each request's packages through the existing public surface. No new research API is required. |

Recorded so a future reader does not mistake the request-scoping for a
missing capability.

---

## Gap 3 — Uniform freshness timestamps (partial; honest degradation)

| | |
|---|---|
| **Requested capability** | a `freshness_status` (CURRENT / STALE / HISTORICAL / UNKNOWN) on every cited claim |
| **Missing contract** | the read surfaces expose timestamps unevenly — research sources carry `retrieved_at`/`published_date`, executive contexts carry input timestamps, but CRM signals and some analytics results do not surface a single canonical `observed_at` |
| **Owning subsystem** | several |
| **Smallest future additive change** | each read surface returning a canonical `observed_at` alongside its value |
| **Can T023 degrade honestly?** | **Yes.** The adapter derives `freshness_status` from whatever timestamp the surface exposes against the session `as_of`; where no timestamp is available it marks `UNKNOWN` (never `CURRENT`). The workspace never claims currency it cannot support. |

---

## Investor / hiring / product / research / monthly report profiles

Not gaps — **deferred by design.** T023 implements three mandatory report
profiles (morning brief, weekly founder review, board update draft). The
report architecture registers the others as profiles; they render only
when they are thin deterministic views over already-implemented sections.
Until then, `DRAFT_INVESTOR_EXPLANATION` and the other profile intents
return an honest "registered but not yet a supported profile" result. See
`ROADMAP.md` T023 bars.
