# Executive-quality wave — what was repaired and what was proved

FINAL_DEPLOYED_SHA = `3b6ba34`

## Proved live, on the deployed customer pages

| defect | before | after |
|---|---|---|
| **Business model was the model class** | Adobe, Cloudflare, Microsoft, Salesforce, Shopify shared one **byte-identical** sentence | Cloudflare: "a broad range of services… making them more secure… revenue from **pay-as-you-go and contracted customers**… **usage-based fees**"<br>Microsoft: "an array of services, including **cloud-based solutions that provide customers with AI, software, services, platforms, and content**"<br>Adobe: "**end-to-end professional creative and marketing solutions**; revenue from cloud-enabled subscriptions, **term-based, royalty, and perpetual licenses**" |
| **A filing heading was a competitor** | Goldman: "contested directly by **Banking Supervision and Compensation Practices**" | "contested directly by **brokers and dealers**" |

Zero byte-identical pairs involve any company re-run on a repair SHA. The
remaining 67 of 946 are between companies whose captures predate the fix.

## Repaired, guarded, and NOT yet proved on a page

**Q&A absence.** NIKE and Goldman answer "What should management do?" with
"Do not act on this reading. Re-run once the market engine publishes a
snapshot this side will read." — on companies that composed eleven and five
documents and reached FULL_ANALYSIS. The market bundle covers 26 of 50.

Two mechanisms were repaired and **both shipped inert**:

1. `_standing_of` inferred REFUSED from `availability not in (AVAILABLE,
   STALE)`. Fixed to read the market block's own `REFUSED` state.
2. The narrowing asked `_count(dossier, "evidence")`, which reads
   `market_block.blocks` — empty precisely when no snapshot exists, so the
   condition was circular. Fixed to read the founder block.

Both are unit-tested and break-proved; the live sentence is unchanged after
both. **A third guess is not worth making.** The next step is to instrument
which producer answers that question and what standing it saw — the same
discipline that settled Meta's `compose=1 stored=9` in one run.

## Genuinely absent, verified across every surface of all 50

`adversary` and `impossible_hypothesis` score 0.0 for 44 of 44 measured
companies. The adversary seam was opened this wave — `_adversary` was gated on
`profile.known`, true only inside the curated manifest, so a complete L0/L1/L2
engine ran for nobody — and it is not yet visible on a captured page. The
impossible hypothesis has no producer at all and remains a build.

## Scores

```
EXECUTED 48/50    MECHANICAL_PASS 33/48
CORE_MEAN 8.04    CORE_MIN 0        bar 9.0 / 8.5   -> FAIL
```

The mean is flat against 8.13 because **only three companies were re-run on
the repair SHAs**. The repairs are proved individually on those; the cohort
has not been re-run, so the matrix is not yet evidence about the current
build.

## Performance, adjudicated

Cloudflare, same SHA, same code, same company:

```
local (adequate CPU)      8s to first useful
deployed free instance  110s to first useful      13.75x
```

Per-segment timing during a live analysis showed a dict lookup at 94ms and a
lock acquire in the same band — the container's 100ms CPU-quota period, not a
slow function.

**PERFORMANCE_CLASSIFICATION = BLOCKED_INFRASTRUCTURE_CPU.** The code meets
the ≤30s SLA on adequate CPU. The minimum required deployment class is one
with a full dedicated core and no cgroup quota throttling, plus the
persistent disk the store already needs.
