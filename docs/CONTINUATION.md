# Founder Intelligence — continuation

Written at a context handoff. Everything below is verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `62661cd` — verified. A newer commit is pushed and awaiting deploy |
| **main SHA** | see `git log -1` (slide build-version removal + this doc) |
| **Working tree** | clean |
| **`/readyz`** | `status: degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## Shipped this round

**One founder-facing product.** Which presentation a visitor saw used to
depend on whether an API key was configured. Grounded runs rendered the founder
deck; every other run — which in production is every run — rendered a deck
opening with `"{company} in one minute"` and closing on `"Key strategic
signals"`.

`founder_view_from_report()` (`slides.py`) adapts a deterministic report into
the same contract the grounded path fills; `build_slides` routes both through
one renderer. The deterministic path deliberately fills fewer fields — it
cannot honestly reconstruct a business model or predict a competitor — so those
screens are omitted rather than padded.

**Verified live on Sentry** (fresh company), presentation-first, 6 screens:

> **The insight** — "Sentry appears to be broadening from a focused tool toward
> being the place a team's work is stored, which raises switching cost and
> blunts the original product's sharpness."
> Then: Why this matters now · The decision · Why this could be wrong ·
> What to watch · How far to trust this

**Three things the rebuild taught, each fixed:**
- the tension had no screen after the five-questions rebuild — restored
- confidence vanished; the persona eval caught it (17 cases, "unanswered: how
  confident to be") — the closing screen now says how far to trust the reading
- the eval harness mapped questions to the OLD slide ids, so it scored a
  product that had been replaced rather than one that regressed — it now
  accepts both vocabularies, because thin reports still fall back to the
  legacy deck

**Source states corrected.** "Sources that were read" listed pages that were
fetched but unreadable. Now "Sources used" and "Sources found but not used"
with the reason in plain words.

## The honest weakness — read this first

The renderer is now good. **The deterministic content is still scaffold
prose.** From the live Sentry run:

> "broadening from a focused tool toward being the place a team's work is
> stored" — the `tool_to_system_of_record` scaffold
> "The trade-off: how much to invest ahead of the transition" — generic

This is the same genericity problem earlier programmes fixed for the grounded
path. The presentation layer now shows it clearly instead of burying it. **The
next real quality step is either grounded reasoning (owner: API key) or making
the deterministic path lead with company-specific evidence rather than pattern
titles.**

## Next task, in order

1. **Deploy and verify** the pending commit; re-run Sentry.
2. **Task 7 — executive brief.** `_brief_page`, ~`app.py:1600`, still
   field-by-field. Should read as one argument.
3. **Task 8 — full analysis.** `_run_page`, ~`app.py:1180`, still schema-shaped.
4. **Task 11 — landing examples** still Palantir/Shopify
   (`GOLDEN_COMPANIES`, `demo_tiers.py`).
5. **Task 13 — five-company rendered batch**, incl. mobile. Never completed.
6. Deterministic content quality (see above).

## Companies used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma, Sentry. Excluded: Chipotle/restaurants, Sony, Palantir, Shopify,
Microsoft, Nintendo.

## Constraints

- Runs do not survive a redeploy (ephemeral storage) — inspect a run in the
  session that created it, before the next deploy.
- Public demo quota ~10 analyses/hour/IP, shared with engineering traffic.

## Owner actions (unchanged)

1. Attach the Render persistent disk and set `RUNTIME_ROOT=/var/data`
   (`render.yaml` already declares both; the service is not using them).
2. `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` (`openssl rand -hex 32`).
3. `ANTHROPIC_API_KEY`.

## Notes

- Suite needs the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local reproduction: `AppConfig(autorun_sources=True)` and pass
  **no** `transport` to `WebApp`.
