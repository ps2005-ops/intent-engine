# Founder Intelligence — continuation

Written at a context handoff. Verified live, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `4292db7` — verified via `/version` |
| **main SHA** | `4292db7` + this doc |
| **Working tree** | clean |
| **`/readyz`** | `degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## Shipped and verified live

The Sentry defect is fixed on production:

| | |
|---|---|
| before | "broadening from a focused tool toward being the place a team's work is stored" |
| after | **"Sentry acquired Codecov."** cited to *Sentry Acquires Codecov \| Sentry* |

Live checks on the deployed deck: `broadening from a focused tool` **absent**,
`tool-to-system-of-record` **absent**, `analysis version` **absent**,
presentation-first intact (`/progress → 303 /slides`), confidence screen intact.

**The governing rule**, implemented in `select_founder_claim_anchor()`
(`strategic_intelligence/concrete.py`) and independently tested: only replace
the fallback when a real reported ACTION exists — not an observation count, a
source count, a pattern, or the company name in a title.

Two ways I got that rule wrong and fixed, both caught by fixtures:

- A pricing **page** is not an action. Matching it handed the takeover to the
  adversarial fixture (`Hostile Co pricing`) and dropped it to
  `FAILED_PRODUCT_QUALITY`. Only a reported pricing **change** counts now.
- Title Case capitalises every word, so shape cannot tell "Codecov" from
  "Acquires". The first cut produced "Sentry acquired codecov". The default is
  now PRESERVE; only words positively recognised as ordinary English are
  lowered.

Thin/adversarial preservation is asserted **at the gate**, not inferred from
text: bloom_dental, hostile_co and a development-free commerce fixture all
return `{}`. `test_product_maturity` and `test_product_eval` unchanged and green.

## The one defect this round did NOT fix

`system of record` still reaches the reader, on the **"What to watch, and what
to ask"** screen:

> "Customers describing it as a companion to a system of record rather than the
> record itself."

That is the pattern's `falsification_questions[0]`, rendered by the `watch`
screen in `build_founder_slides` (`slides.py`). It survives because taxonomy
filtering is applied only at claim construction — deliberately, since the
previous global filter in `_cap()` stripped honest limitation and
counter-evidence prose and broke several persona cases.

**Next exact task:** filter taxonomy from the `watch` screen's bullets in
`build_founder_slides` (questions and `what_to_watch` only), leaving the
counterargument screen and the limitation/confidence prose untouched. Then
re-run `test_product_maturity.py` and `test_product_eval.py` — they are what
catch over-reach — and re-run Sentry live.

## Then

- Executive brief (`_brief_page`, ~`app.py:1600`) — still field-shaped; should
  open from the same selected anchor rather than regenerating a claim
- Full analysis (`_run_page`, ~`app.py:1180`) — still schema-shaped
- Landing examples still Palantir/Shopify (`GOLDEN_COMPANIES`, `demo_tiers.py`).
  Now unblocked: "Sentry acquired Codecov." is verified live output.
- Five-company rendered batch incl. mobile — still never completed
- Scorecard floor is 5 meaningful slides (`product_eval/scorecard.py`); an
  honest short deck can trip it. Task 9 asked for coverage-based
  presentability rather than raw count — not done.

## Companies used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma, Sentry.

## Constraints

- Runs do not survive a redeploy (ephemeral storage) — inspect in the session
  that created the run.
- Public demo quota ~10 analyses/hour/IP, shared with engineering traffic.

## Owner actions

1. Attach the Render disk, set `RUNTIME_ROOT=/var/data`.
2. `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` (`openssl rand -hex 32`).
3. `ANTHROPIC_API_KEY` — grounded reasoning is off, so the deterministic path
   IS the product.

## Notes

- Suite needs the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local run: `AppConfig(autorun_sources=True)`, **no** `transport`.
