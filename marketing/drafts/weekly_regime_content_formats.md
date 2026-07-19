# Weekly regime-read content formats — DRAFT (deliverable c)

*Formats derived from the real weekly report; every example below uses
ONLY the real 2026-07-17 run's content. Nothing scheduled or posted —
these are format proposals for per-item approval. Claim-trace shared with
landing_page_copy.md (T:1–T:6); the no-accuracy-claim rule applies to
every post, every week.*

## Format A — "The Regime, Plainly" (LinkedIn/X long-post, weekly)

Structure: 1 regime state line → 1 honest-uncertainty line → 1 mechanism
read (or the none-matched line) → claims-on-record with P values →
standing disclaimer.

Example (real 2026-07-17 content):
> **This week's structural read:** yield curve not inverted, SPY within
> 1% of its highs. Credit spreads, CPI trend, and unemployment momentum:
> UNAVAILABLE this run — our data guard found no verified number, so we
> make no claim.
> **Mechanisms in play: none matched.** The signal genuinely didn't clear
> any documented mechanism's triggers — so the system said nothing. That
> restraint is tested, not accidental.
> **On the record this week:** curve stays above +0.30pp by Oct 16
> (P=0.72) · SPY back within 1% of highs by Sep 15 (P=0.58) ·
> unemployment under 5% through Q3 (P=0.65). All graded automatically
> against FRED/Tiingo; misses stay on the ledger.
> *We don't claim predictive accuracy — 0 predictions resolved so far.
> The ledger speaks as it fills.*

## Format B — "One Mechanism, One Precedent" (evergreen educational)

One library mechanism per post: name, causal chain in 3 plain sentences,
the cited historical instance, and "what would have to be true in YOUR
market for this to matter." Sourced 1:1 from mechanisms.json entries (all
citations named). Batch-1 additions (pending founder approval) would feed
this format 3 new posts.

## Format C — "Resolution Day" (event-driven, starts late Aug 2026)

When a ledgered prediction resolves: the original claim + P, the outcome,
the Brier component, running counts. **Hard rule: publishes hits AND
misses mechanically — the format is the ledger row, so cherry-picking is
structurally impossible. Until ≥30 resolved + founder review, every post
carries "too few resolutions to claim calibration."**

## Cadence + pipeline

Weekly A (after the Monday report), 1-2 B per week (evergreen queue),
C as resolutions land. All drafts → founder per-item approval →
publer_pipeline.py (dry-run until you flip PUBLISHING_ENABLED).
