# MORNING HANDOFF — overnight loop 5 (2026-07-22) — T007 single-focus

*Suite at close: **627 passed, 0 failed, 7 deselected (live)**. 1 commit
(`e502f54`) + this handoff. Walls held: no publishing/sending/crontab/
vendor/OAuth/sandbox-live-calls; A-M3 untouched, backtest HELD, enum
frozen, prompts frozen. Process guard honored (explicit suite exit-code
check before the commit). Spend: 0.*

## T007 — final state: PARKED at build time (honest bar conflict)

**Not shipped — and this is a deliberate Honest Park, not a failure to
build.** T007 was approved as specced and I began building it. A bar-(d)
pre-check against the real library — before any committed code — found
that **two approved bars are mutually unsatisfiable on the real data**:

- **Bar (c)** requires the `causal_chain` steps rendered **verbatim**
  (the "rendering, not generation" guarantee).
- **Bar (d)** forbids `buy` / `sell` / `forecast` (etc.) **across the
  whole block**.
- **6 mechanisms** (`margin_collateral_spiral`, `carry_trade_unwind`,
  `money_market_contagion`, `winners_curse_acquisition`,
  `debt_fueled_capacity_race`) use those words inside **verbatim
  third-person descriptions of documented history** — e.g. "…is forced to
  **sell** the underlying asset…". Verbatim (c) necessarily includes them;
  full-block 0-hit (d) forbids them. Both cannot pass on this library.

I did **not** bend either bar to ship my own approved feature (that's the
exact failure mode the discipline guards against), did not reword frozen
mechanism data, and did not gut the feature. I parked and wrote the
decision up.

- **Commit**: `e502f54` (finding doc + ROADMAP → PARKED + trace; no code).
- **The real rendered example you asked for** is in the trace and the
  finding doc — a clean `supply_shock_propagation` `--explain` block
  (conditions + verbatim causal chain + cited precedent + source). It's
  exactly the differentiated artifact intended; only the 6 wall-tripping
  mechanisms are blocked.
- **Bars status**: (a)(b)(c)(e)(f) are all satisfiable and would pass;
  **(d) vs (c) is the sole blocker.** So this is 5/6-clean, one conflict.

## The one decision that unblocks it (docs/T007_PARK_FINDING.md)

Three options, my recommendation first:

1. **(RECOMMENDED) Scope the wall to the system's own voice** — apply
   bar (d) to the system-authored framing lines (headers/labels) and
   **exempt the verbatim causal-chain steps + cited source**, justified
   because bar (c) guarantees those are verbatim quotes of documented
   history, not the system's generated voice — which is what the wall's
   stated intent actually protects. Resolves (c)/(d) without weakening the
   wall's real purpose. It IS a narrowing of bar (d)'s scope, so it's your
   call to ratify — which is why I parked instead of doing it silently.
2. Keep bar (d) whole; drop verbatim causal chains (guts the feature).
3. Reword the 6 causal chains (data change, degrades fidelity).

On your one-word pick I build T007 to green in the next sandbox loop
(0 live calls, one commit, ROADMAP → DONE).

## Deferred to your next message (NOT touched this loop, per T007-only scope)

- **A (T005)**: you reported **both live bars PASS** — the DONE-flip +
  output paste into `overnight_trace.md` is queued for next message.
- **D (citations)**: 9/10 returned 200; the **LTCM Treasury PWG PDF 404**
  → that batch-2 citation needs a swap before batch-2 can merge (Japan IMF
  cleared 200). Not acted on this loop.
- Batch 2/3, Task 5, AP feed, vocab, marketing/outreach — all still
  waiting on your filled selections.

## MY MORNING LIST (in order)

1. **Pick a T007 resolution** (1/2/3 — recommend 1). One word unblocks a
   full green build next loop, no Mac step.
2. **Confirm the T005 DONE-flip** is wanted (both bars passed) so I paste
   your outputs into `overnight_trace.md` and mark it DONE next loop.
3. **Swap the LTCM batch-2 citation** (the 404'd Treasury PWG URL) — give
   me a replacement or say "you pick one," then batch-2 can merge once its
   verdict is in.
4. The still-pending filled selections (batch-2 verdict, Task 5, AP feed,
   vocab, marketing/outreach) whenever you're ready.

## AMBIGUITIES (parked with recommendations, not guessed)

1. **The (c)/(d) bar conflict is a spec defect I introduced last loop**
   when I wrote bar (d) as a blunt full-block grep without anticipating
   verbatim historical prose containing trade verbs. Owning that — the
   fix is option 1, and it's cheap. *Recommendation: ratify option 1.*
2. **I could have shipped option 1 unilaterally** (defensible on the
   wall's intent) but chose to park, because silently narrowing my own
   approved bar to ship my own feature is precisely the discipline being
   tested. *Recommendation: if you'd rather I exercise that judgment
   inline in future when the resolution is this clear-cut, tell me and
   I'll treat "obvious bar-intent-preserving reconciliations" as
   buildable rather than park-worthy — but the conservative default
   served us here.*

## Ready-for-densification flag

**NOT yet** — T007 did not ship clean; it's parked on a one-decision bar
reconciliation. It will be ready-for-densification the loop after you pick
a resolution and it goes green.
