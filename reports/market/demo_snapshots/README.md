# Demo market snapshot bundle

WHAT THIS IS. A dated copy of the market engine's published demo snapshots,
committed so a deployed preview has market intelligence to read. The market
engine runs on its own host and writes to its own disk; a Render service
cannot mount that disk (persistent disks attach to exactly one service and
are never shared), so without a bundle the bridge on a preview correctly
reports `MARKET_BRIDGE_MISSING` and the product shows nothing.

WHAT IT IS NOT. A second system of record. Nothing reads this automatically:
`MARKET_SNAPSHOT_ROOT` must name it explicitly, and the bridge has no
fallback that could reach it by accident. That is deliberate -- a silent
fallback to a committed bundle is how a deployment ends up serving months-old
intelligence while reporting itself healthy.

FRESHNESS IS COMPUTED, NOT ASSUMED. The bridge derives staleness from the
newest `evidence_cutoff` inside these files, never from their mtime, so a
redeploy that rewrites every timestamp cannot make this bundle look current.
Past the bounded window it reports `MARKET_BRIDGE_STALE` and the surfaces say
so.

TO REFRESH: run `scripts/republish_demo_snapshots.py --root <market runtime>`
in the market repo, then copy the output here.

    market runtime SHA at bundling: 9b01ff1 (economic state included)
    evidence cutoff:                2026-08-13
    companies:                      26
