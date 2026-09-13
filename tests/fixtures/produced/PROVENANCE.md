# Artifacts produced by the real market publisher

These files are **not** hand-written. They were emitted by
`intent_engine.market.strategic_publish.publish` on the market branch, from the
real production learning ledger, and copied here byte for byte.

| field | value |
| --- | --- |
| producer commit | `c5c11623de88277d47d7b8c2a89f1e63e9f54a55` (`feat/market-export-identity`) |
| producer module | `src/intent_engine/market/strategic_publish.py` |
| contract | `strategic_market_intel.v1` |
| session as-of | 2026-08-05 |
| evidence source | `reports/market/learning_ledger.jsonl` from the market runtime worktree |
| trades opened | 0 |

## Why the artifact rather than a fixture

The two ends of this bridge live on **different branches of one repository**
and neither can import the other: the founder branch has
`external_intel/strategic_contract.py` and no `market/` package; the market
branch has `market/strategic_export.py` and no `external_intel/`. So there is
no process in which the producer and the consumer can be called together.

That is exactly the condition under which two hand-written "equivalent"
fixtures drift apart while both suites stay green — which is how the bridge
came to carry zero dossiers with an allowlist enforced at both ends and a full
test suite on each side. Consuming the producer's actual bytes is the only
available proof that the two contracts still agree.

## Regenerating

From the market worktree, run the publisher over a learning session and copy
the emitted files here, then update the commit above. If the founder-side
validator rejects a regenerated artifact, the contracts have diverged and that
is the finding — do not edit the fixture to make the test pass.

## What `stripe.json` is for

It is published under an internal id with no declared display name, so the
founder side cannot find it by company name. It is kept as the negative case:
the identity contract must report that honestly rather than binding it to a
company by proximity.
