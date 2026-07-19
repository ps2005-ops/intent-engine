# T007 — PARKED at build time: bars (c) and (d) are mutually unsatisfiable on the real library

*2026-07-22 build loop. T007 was APPROVED and I began building it. During
the bar-(d) pre-check against real data — BEFORE writing any committed
code — I found that two of the six approved bars cannot both hold on the
real 20-mechanism library. Per park-don't-improvise (and "a staged-at-gate
morning with Honest Parks beats a finished morning with crossed walls"), I
am PARKING rather than quietly bending either bar to ship. No code was
committed; suite stays green at 627. This needs one founder decision to
unblock — it is a spec-reconciliation, not a rebuild.*

## The conflict, precisely

- **Bar (c) — causal-chain fidelity**: "every stored `causal_chain` step
  appears **verbatim**, no paraphrase/invention/drop." This is the
  "rendering not generation" guarantee — the whole point of the feature.
- **Bar (d) — language walls**: "0-hit greps for … `sell` … `buy` …
  `forecast` … **across every mechanism's block**."

Six real mechanisms have `causal_chain` steps that use `buy` / `sell` /
`forecast` to **describe documented historical behavior in the third
person**. Rendering them verbatim (bar c) necessarily puts those words in
the block, which bar (d) forbids. The two bars cannot both pass on this
data:

| Mechanism | Verbatim causal-chain phrase | Trips |
|---|---|---|
| `margin_collateral_spiral` | "…is forced to **sell** the underlying asset…" | `\bsell\b` |
| `carry_trade_unwind` | "…**buy** back the funding currency…" / "unwind (**sell** the target-currency asset)" | `\bbuy\b`, `\bsell\b` |
| `money_market_contagion` | "…funds industry-wide to **sell** holdings…" | `\bsell\b` |
| `winners_curse_acquisition` | "…acquisition currency to **buy** a large target…" | `\bbuy\b` |
| `debt_fueled_capacity_race` | "…each **forecast** continued demand growth…" | `\bforecast\b` |

None of these is the system advising a trade or making a forecast — they
are **verbatim descriptions of what economic actors did in the documented
pattern**. But a blunt full-block grep (correctly blunt, by design) cannot
distinguish third-person history from first-person advice.

## Why I did not just pick a side

- **Weakening bar (d)** to let these through would be exactly the
  self-serving, post-hoc bar-softening the discipline forbids — I wrote
  bar (d) as a full-block grep last loop; changing it now to ship my own
  approved feature is not my call to make unilaterally.
- **Rewording the 6 causal chains** is a mechanism-data change, out of
  scope this loop (T007-only; batch/data work frozen) and touches content
  that should not be edited to satisfy a renderer.
- **Dropping the causal chain** from the block guts the feature (and fails
  bars (a)/(c) coverage) — the causal chain *is* the explanation depth.

So the honest outcome is: PARK, report, and let you choose the
reconciliation.

## Real rendered example (what the feature produces — clean mechanism)

Generated deterministically from the real `supply_shock_propagation` entry
(this one has no wall-tripping words, so it shows the intended output
cleanly):

    Why this may be in play — Supply-shock propagation (well_documented)
      Conditions present in your situation:
        - concentrated_supplier_base
        - few_dominant_competitors
      How it unfolds (documented pattern):
        1. A small number of suppliers account for most of an industry's critical input
        2. An external shock (natural disaster, geopolitical disruption, demand spike
           elsewhere) removes capacity from that supplier base
        3. Buyers relying on just-in-time inventory have no slack to absorb the gap
        4. Production halts cascade downstream faster than new supply can be qualified or built
        5. Recovery lags the shock by quarters to years because building new supplier capacity is slow
      Historical precedent: 2020-2023 global semiconductor chip shortage (automotive sector) (2021)
      Source: https://en.wikipedia.org/wiki/2020%E2%80%932023_global_chip_shortage ; https://www.clevelandfed.org/publications/economic-commentary/2021/ec-202117-semiconductor-shortages-vehicle-production-prices

This is precisely the differentiated artifact the feature is for. The only
blocker is that the 6 mechanisms above can't render this way under bar (d)
as written.

## Three resolutions — your pick (one decision unblocks the build)

1. **(RECOMMENDED) Scope the wall to the system's own voice.** Apply the
   language wall (existing + new terms) to the **system-authored framing
   lines only** (the "Why this may be in play" header, the "Conditions
   present" label, section text) and **exempt the verbatim `causal_chain`
   steps and the cited `source`**, on the principled ground that bar (c)
   guarantees those are *verbatim quotes of documented history*, not the
   system's generated voice — which is exactly what the wall's stated
   intent protects ("structural reads, never predictions **in the system's
   voice**"). This resolves (c)/(d) without weakening the wall's real
   purpose. It is a narrowing of bar (d)'s scope, so it needs your
   ratification — which is why I parked instead of doing it myself.

2. **Keep bar (d) whole; drop verbatim causal chains from the block.**
   Render only conditions + cited instance (no "how it unfolds" steps).
   Ships under the literal bars, but removes the explanation depth that is
   the feature's entire point. Not recommended.

3. **Reword the 6 causal chains** to avoid buy/sell/forecast (e.g.
   "offload" / "projected"). A mechanism-data change, separate from T007,
   and it degrades fidelity to how these patterns are normally described.
   Not recommended.

## What happens on your pick

- Option 1: I build T007 with the wall scoped to system-framing lines,
  keep all six bars' INTENT (bar (d) becomes "0 forbidden terms in
  system-authored lines"; bars a/b/c/e/f unchanged), ship green in one
  sandbox loop, one commit, real example in the trace, ROADMAP → DONE.
- Option 2 or 3: I build the reduced/ reworded version accordingly.

Until then T007 is **PARKED — bar reconciliation pending** in ROADMAP,
not DONE.
