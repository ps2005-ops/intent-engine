# Execution checkpoint — V3 continuous economic intelligence

Machine-readable continuation state. A completed slice is a checkpoint, not an
endpoint: this file exists so the mission survives a context boundary instead
of restarting from an audit.

Updated 2026-08-07, wave 6.

## Pinned state

| what | where |
|---|---|
| market runtime | `75681e0` (branch `feat/consumption-telemetry`) |
| founder preview | `a6c8601` (branch `feat/consumption-emitter` → `feat/founder-decision-experience-v3`) |
| production `main` | `119d345` — **untouched, do not target** |
| PAPER | structurally enforced in both launchd plists |
| market suite | 3827 passed / 4 skipped / EXIT=0 |
| founder suite | 4563 passed / 6 skipped / EXIT=0 |

## Completed this mission

| # | slice | commit | evidence it is real |
|---|---|---|---|
| 1 | Belief → graph → founder reasoning | `74f70d0` | founder sentence traces to `ev_6242785c24ff2621` in the ledger |
| 2 | DecisionImpact + before/after harness | `0fde6bc` | 22/22 MEANINGFUL; same-dossier control returns NONE |
| 3 | FounderLearningHealth.v1 | `a6c8601` | reads NOT_LIMITED on the real ledger |
| 4 | Causal episodes + self-test guard | `61e486f` | 10 episodes / 8 subjects; informative 10 → 5 after the guard |
| 5 | Hidden-state binding | `75681e0` | companies_tracked 0 → 16, 54 observations |

## The pattern this mission keeps finding

**A correct module, a call site that never supplies its inputs, and a metric
honestly reporting zero that everyone reads as "nothing has happened yet."**

Three confirmed instances, all shipped and all invisible to a green suite:

1. `learning_cycle.run(observations=)` — never passed. No belief was ever tested.
2. `report.render_report` — dropped `learning_health` from the persisted report.
3. `learning_cycle.run(hidden_states=)` — never passed. `companies_tracked` 0.

Plus two contract breaks of the same family: the founder rejected every dossier
over two unknown fields, and the renderer read every kind of strategic content
except beliefs.

**Before building a subsystem, check whether it already exists and is simply
not wired.** In this codebase that has been true five times out of five.

## Remaining queue, highest value first

1. **Natural scheduled cycle** — fires 20:30 America/Toronto. Verify
   `learning_health` in the DATED report, `observation_binding`,
   `hidden_state_binding`, and that the self-test guard reduced informative
   results on the live ledger.
2. **Strategic interactions** — `strategic_interaction.py` exists; check
   whether it too is unwired before writing anything.
3. **Belief maturity + knowledge decay** — distinguish contradicted from stale.
4. **Value of Information + research priority** — ≥5 real watchlist entries.
5. **Actor-to-actor relationships** — world model has zero; needs evidence, not
   model world knowledge.
6. **Shopify excerpt producer** — SEO meta description outranks body prose.
7. **Adversarial economic suite** — 12 cases.
8. **Break proofs** — 29 listed.
9. **Performance measurement** — no baseline captured this mission.
10. **Brightledger live proof** — preview quota bound.

## Standing rules

- Commit and push every completed slice. A worktree was destroyed mid-session
  once and uncommitted work was lost; it was rebuilt from context, but the
  correct behaviour is to push first.
- Never print a producer's probability as founder confidence. Every market
  belief carries the 0.586 prior a single evidence item opens one at.
- No causal edge is ever `OBSERVED`, and none is promoted by a single test.
- `UNMEASURABLE` is not zero. Absent telemetry and zero utility are opposite
  findings.
