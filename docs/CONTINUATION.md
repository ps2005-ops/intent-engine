# Founder Intelligence — continuation

Written at a context handoff. Everything below is verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `68190a1` — verified via `/version` |
| **main SHA** | `68190a1` (+ this doc) |
| **PR** | none open; work goes straight to `main`, which Render auto-deploys |
| **Working tree** | clean |
| **Suite** | 2626 passed, 14 skipped |
| **Worktree** | `scratchpad/si2` on `feat/strategic-intelligence-v2`, tracking main |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` not set (owner) |

## Shipped and verified live this round

**Smoke-test access** (`FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN`, header
`X-Founder-Intelligence-Smoke-Test`, constant-time compare). Consulted in
exactly one place, so a valid token buys the demo quota and nothing else —
tests assert consent, CSRF and run ownership all still hold *with* a valid
token. Absent variable ⇒ mechanism does not exist. Every bypass logs
`internal_smoke_test_rate_limit_bypass_used`, never the token.

**Methodology wall removed.** The landing page injected the whole "Before you
start" explainer above the form, and rendered **six identical CTAs** because
the injection used `.replace('</section>', …)` with no count — `str.replace`
replaces every occurrence and the explainer emits one `</section>` per section.
The explainer now lives only at `/onboarding`; new sessions land on the product.

**Landing page rebuilt** around what the reader gets: a plain promise, two
input boxes with real placeholders, a concrete example of an actual conclusion,
and a short evidence statement. One primary CTA, enforced by a test.

**Two defects found by looking at the deployed page**, both fixed and
redeployed: the examples footnote rendered *above the h1*; and every deck
bullet carried the same retrieval date, reading as chronology that was not
there.

**Live batch, all `303`, no 500s** — the repeated-analysis fix holds across
fresh technology companies:

| Company | Segment |
|---|---|
| Anthropic | AI infrastructure, late-stage private |
| Retool | developer tooling, mid-sized private |
| Wiz | cybersecurity, growth-stage |
| Snowflake | data infrastructure, established public |
| Arm Holdings | semiconductors, major platform |

## Blocked right now — one owner action unblocks it

**Rendered presentation/brief/analysis were NOT inspected for those five.**
The 6th request of the hour hit the demo quota (429) and fell back to the
landing page. This is the third time engineering traffic has exhausted the
public allowance.

The mechanism to fix it is built, tested and deployed. It needs the secret:

> **Owner action:** in the Render dashboard for `intent-engine-oatc`, add env
> var `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` with any long random value
> (`openssl rand -hex 32`), `sync: false`.

Then live batches run with:

```bash
curl -H "X-Founder-Intelligence-Smoke-Test: $TOKEN" ...
```

## Next task, in order

1. **Re-run the five-company batch with the smoke header** and inspect the
   rendered presentation, executive brief, full analysis and sources for each,
   desktop and mobile. This is the step that was cut short.
2. **Task 6 — executive-brief renderer.** Still the old field-serialised
   layout (`_brief_page`, ~`app.py:1600`). Must read as one written argument.
3. **Task 7 — full-analysis renderer** (`_run_page`, ~`app.py:1180`). Single
   reading column, no unanswered headings, one sources section.
4. **Task 5 — presentation narrative.** The founder deck exists
   (`build_founder_slides`, `slides.py`) but only fires when a grounded
   analysis is present; on the deterministic path the old deck still renders.
   Decide what the deterministic deck should say and rebuild it.

## Companies already used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm. Excluded by instruction: Chipotle/restaurants, Sony, Palantir, Shopify,
Microsoft, Nintendo, prior synthetic fixtures.

Note: the product's own prepared examples on the landing page are still
Palantir and Shopify (`GOLDEN_COMPANIES`, `demo_tiers.py`). Worth replacing
with two current technology companies.

## Notes for whoever continues

- Run the suite with the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local reproduction (this is how the repeated-analysis defect was
  found; fixture transports hide it) — construct `AppConfig` with
  `autorun_sources=True` and pass **no** `transport` to `WebApp`.
- After the key is added, verify: `strategic_reasoning: true`, an analyst call
  succeeds, no secret in logs, timeout/fallback understandable, and deck +
  brief + analysis all use grounded output.
