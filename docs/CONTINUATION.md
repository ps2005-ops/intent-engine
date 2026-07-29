# Founder Intelligence — continuation

Written at a context handoff. Verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `62661cd`. `e0283ce` + this work pushed, deploy unverified |
| **main SHA** | see `git log -1` |
| **Working tree** | clean |
| **`/readyz`** | `degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## The finding that matters this round

Sentry's live run **retrieved a page titled "Sentry Acquires Codecov"** — a
named acquisition, the hardest fact in the run. The presentation discarded it
and opened with:

> "broadening from a focused tool toward being the place a team's work is
> stored"

which is the `tool_to_system_of_record` scaffold and reads identically for
Notion, Linear or Atlassian. **A real fact was thrown away for a pattern
title.** That is the defect, located precisely.

## Landed: `strategic_intelligence/concrete.py` (+22 tests)

Standalone, green, **not yet wired in**:

- `concrete_developments()` — ranks observations by how hard the fact is
  (acquisition > funding > launch > pricing > partnership > leadership). On
  Sentry's real evidence it returns the Codecov acquisition first.
- `descriptive_subjects()` — page subjects with the "| Company" suffix stripped
- `reads_as_taxonomy()` — detects ontology vocabulary, normalising hyphens so
  `tool-to-system-of-record` is caught as well as `system of record`
- both accept observation records **and** serialised dicts

## What I tried, and why it is not in the tree

I wired this into `founder_view_from_report()` and got the right headline live
in a local render:

> **The insight** — "Sentry Acquires Codecov."

But two things broke and I reverted rather than leave them:

1. **A global taxonomy filter in `_cap()` was too blunt.** Applied to every
   bullet it also stripped honest limitation and counter-evidence prose that
   legitimately names the mechanism being doubted; several persona cases lost
   the answers they depend on.
2. **Taking the deck over without a concrete fact broke thin/adversarial
   cases.** `bloom_dental` and `hostile_co` began scoring
   `FAILED_PRODUCT_QUALITY`. Falling back when no development is found did not
   fix it on its own, and I ran out of context to finish properly.

`git reset --hard origin/main` restored green (2,668 → now 2,690 passing).

## Next task — exact

In `slides.py`, `founder_view_from_report()`:

1. Take the deck over **only when `concrete_developments()` is non-empty.**
   Leave every other run on its current path.
2. Build the headline with `_fact_sentence()`-style logic: strip the
   `| Company` suffix and state the development. Do **not** use
   `thesis["transition"]`.
3. Put the pattern reading in the paragraph **only if**
   `reads_as_taxonomy()` is false for it; otherwise carry the other concrete
   developments and stop. Saying less is correct — a reader can check "Sentry
   Acquires Codecov" against the world and cannot check "becoming the place a
   team's work is stored".
4. Apply the taxonomy filter **at claim construction only**, never in `_cap()`.
5. `_lower_first()` must not lowercase a proper noun, or you get "A plausible
   reading is that sentry appears to be…".
6. Re-run `tests/test_product_maturity.py` and `tests/test_product_eval.py`
   after every step — they are the ones that catch over-reach.

## Then

- Executive brief (`_brief_page`, ~`app.py:1600`) — still field-shaped
- Full analysis (`_run_page`, ~`app.py:1180`) — still schema-shaped
- Landing examples still Palantir/Shopify (`GOLDEN_COMPANIES`, `demo_tiers.py`)
- Five-company rendered batch incl. mobile — never completed

## Companies used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma, Sentry. Excluded: Chipotle/restaurants, Sony, Palantir, Shopify,
Microsoft, Nintendo.

## Constraints

- Runs do not survive a redeploy (ephemeral storage) — inspect in the session
  that created the run.
- Public demo quota ~10 analyses/hour/IP, shared with engineering traffic.

## Owner actions

1. Attach the Render disk, set `RUNTIME_ROOT=/var/data` (`render.yaml` declares
   both; the service is not using them).
2. `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` (`openssl rand -hex 32`).
3. `ANTHROPIC_API_KEY` — with grounded reasoning off, the deterministic path
   IS the product, which is why the above matters.

## Notes

- Suite needs the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local run: `AppConfig(autorun_sources=True)`, **no** `transport`.
