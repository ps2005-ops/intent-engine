# AgentOS Extraction — Architectural Diff Report (T022)

*Written 2026-07-21 at the close of Session 12. This is the audit trail
the T022 brief requires: proof that the session **simplified** the
repository by extracting proven duplication, rather than moving code around
or inventing abstractions. Companion to `docs/COMPANY_OS.md` Part 2
(AgentOS) — this file records the extraction; that file records the
architecture.*

---

## 1. The extraction audit table

Nothing entered AgentOS without appearing, byte-for-byte, in all three
production agents. Every shape is classified **extracted**, **intentionally
duplicated**, or **intentionally left local**, with the reason.

| Shape | T019 Research | T020 Product | T021 Executive | Decision |
|---|---|---|---|---|
| Append-only store mechanics (flock, fsync, parse cache, idempotency, `read_all`, `find_by_idempotency_key`, `append`) | ✓ identical | ✓ identical | ✓ identical | **EXTRACTED** → `agentos/append_only.py`; the three stores subclass it |
| `_stable_id(key)` | ✓ identical | ✓ identical | ✓ identical | **EXTRACTED** → `agentos/identity.stable_id` |
| `scan_banned_language` word-boundary + phrase matcher | ✓ (own terms) | ✓ (own terms) | ✓ (own terms) | **EXTRACTED** → `agentos/language_wall`; vocabulary passed in |
| `model_provenance` shape `{prompt_version, model_version, …}` | ✓ (extraction_module) | ✓ (authority) | ✓ (authority) | **EXTRACTED** → `agentos/model_boundary.model_provenance`; third key preserved per agent |
| Recursive `find_forbidden_fields` scan | flat forbidden-set (source-anchored) | ✓ identical | ✓ identical | **EXTRACTED** (product+executive) → `agentos/model_boundary`; research's flat wall left local (below) |
| Store / Index / Consumer / Snapshot / Replayable shape | ✓ | ✓ | ✓ | **EXTRACTED as PROTOCOLS** → `agentos/contracts.py`; structural, no forced inheritance |
| Company-event consumer framework (drain, replay, checkpoints, dead letters) | uses `events/` | uses `events/` | uses `events/` | **ALREADY SHARED** since T013 — nothing to extract; the per-agent consumers are thin adapters |
| Snapshot payloads | domain | domain | domain | **LEFT LOCAL** (contract only); payloads are domain-specific |
| Index implementations (Evidence / Problem / Opportunity / Decision) | domain | domain | domain | **LEFT LOCAL**; four different memories, unifying them would be invention |
| Model-boundary exception (`ExtractionRejected` / `ModelOverreach`) | subclass of `ResearchError` | subclass of `ProductError` | subclass of `ExecutiveError` | **LEFT LOCAL**; a shared base would force multiple inheritance and change catchability |
| Research's model WALL (locatability + URL regex + flat forbidden set) | ✓ | — | — | **LEFT LOCAL**; a different, stricter, source-anchored operation, not the same rule |
| Scoring / readiness / conflicts / debt / portfolios / graphs / Decision Context | domain | domain | domain | **FORBIDDEN from the kernel**; domain intelligence, not infrastructure |

---

## 2. Which duplicated implementations were removed

- **The append-only store body**, held in three byte-identical copies.
  The agent store files went from **338 lines to 123** (research 107→36,
  product 117→45, executive 114→42) — **215 lines of triplicated
  infrastructure eliminated**, replaced by one `AppendOnlyStore`
  (~135 lines) in the kernel. Each agent store now contains only its
  domain query methods (`for_request`, `for_proposal`, `for_candidate`, …).
- **The `scan_banned_language` loop** — three ~10-line copies collapsed to
  one matcher plus three one-line delegations.
- **`find_forbidden_fields`** — two byte-identical ~15-line copies
  (product, executive) collapsed to one kernel scan plus two one-line
  delegations.
- **`_stable_id`** — three copies collapsed to one.
- **The model-provenance dict** — three inline constructions collapsed to
  one builder.

Net: roughly **~250 lines of duplicated infrastructure removed from the
three agents**, replaced by a single implementation each.

---

## 3. Which abstractions were intentionally NOT extracted, and why

- **The company-event consumer framework** — already shared in
  `events/consumer.py` since T013. Extracting it into AgentOS would have
  been moving already-shared code for the sake of a file name.
- **The index implementations** — the Evidence, Problem, Opportunity, and
  Decision Indexes share a *shape* (`build_index(rows)` /
  `assert_invariants()` / `lineage()`) but nothing of their content.
  Unifying four different memories would be inventing an abstraction over
  things that are only superficially alike. The shape is a **protocol**;
  the code stays in the agents.
- **Snapshot payloads** — the envelope (id, versions, as_of, watermarks,
  reproducibility) is shared and recorded as a contract; the payloads are
  domain-specific and stay local, exactly as the brief required.
- **Research's model wall** — a source-anchored check (a claim must be
  locatable in its registered source; a URL in claim text is rejected)
  that is genuinely a different, stricter operation than scanning a
  drafted prose payload for leaked identifiers. Only its provenance shape
  was shared.
- **The model-boundary exceptions** — each subclasses its own agent's
  error type so a caller catching `ResearchError` still catches a research
  model rejection. A shared base would change that.
- **The T013–T018 subsystem stores** (events, crm, knowledge, marketing,
  growth) — **out of the three-agent extraction scope.** Some carry
  genuine variations (the event bus's checkpoints and dead letters,
  growth's namespacing that rejects cross-namespace rows); all are stable
  code that the zero-regression rule says not to disturb for no in-scope
  benefit. Migrating them onto `AppendOnlyStore` is a clean, separate
  follow-up, deliberately not done here.
- **All domain intelligence** — scoring, the six readiness dimensions, the
  conflict taxonomy, every debt vocabulary, both portfolios, every graph,
  and the Decision Context. A test (`test_domain_concepts_never_entered_the_kernel`)
  fails if any of these appears in the kernel.

---

## 4. Which public APIs changed

**None.** Every agent's public surface — `ResearchService`,
`ProductService`, `ExecutiveService`, their store classes, their
`scan_banned_language` / `find_forbidden_fields` functions, their
corruption-error types — keeps the same name, signature, and behaviour.
The corruption errors now subclass the kernel's `CorruptLogError` instead
of `RuntimeError` directly, but `CorruptLogError` **is** a `RuntimeError`,
so any caller catching `ResearchCorruptLogError` (or `RuntimeError`) is
unaffected. The `_stable_id` and `scan_banned_language` delegations are
internal; their outputs are byte-identical.

---

## 5. Which tests prove behaviour remained identical

- **The full offline suite passed byte-for-byte before and after**: 1421
  passing before the extraction, 1448 after — and the +27 are **only** the
  new kernel tests. No existing test changed its expectation. (One
  documentation-only line changed: `test_pick_next_task`'s queue assertion
  moved `{T022}` → `{T023}`, the once-per-session promotion marker.)
- **`test_agentos_kernel.py`** (27 tests) proves the extraction directly:
  the three stores subclass the kernel and carry no append-only mechanics
  of their own; the matcher preserves word boundaries (`provenance` ≠
  `proven`); the recursive scan catches a nested forbidden field (the T020
  bug that motivated one shared implementation); the four indexes and
  three consumers satisfy their protocols; the registry lists exactly
  three agents and imports no domain module; no domain concept entered the
  kernel; a store rebuilds byte-identically through the kernel; and a
  cross-agent golden path runs with the kernel in the path and no
  behavioural change.
- **Every T019/T020/T021 end-to-end test still passes unchanged** — the
  replay, snapshot, lineage, and CLI behaviours those suites assert are
  the zero-regression proof.

---

## 6. The zero-regression rule (standing)

> Every replay, snapshot, index, lineage query, and CLI output produced
> before T022 remains semantically identical after extraction.

Held. The kernel is infrastructure, not intelligence: it changed how the
three agents are *built*, and nothing about what they *do*.
