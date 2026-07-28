# Founder Intelligence — continuation

Written at a context handoff. Everything below is verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `a72e13e` (verified). `29a6fe0` pushed, deploy not yet confirmed |
| **main SHA** | `29a6fe0` |
| **PR** | none open; `main` auto-deploys |
| **Working tree** | clean |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |
| **Smoke token** | not configured — engineering traffic still spends public quota |

## Shipped this round, verified live

**Operations console was a guest surface.** Any anonymous guest who typed
`/dashboard` saw missing-credential names (`TIINGO_API_KEY`, `FRED_API_KEY`),
the full deployed commit, scheduler state and `status.json`. The gate asked
only whether a session existed — a demo session is a session. Now 404 for
guests on `/dashboard`, `/learning`, `/assistant`; logged-out users still
redirect to `/login`. **Verified live: 404 on all three.**

**Runs were unfindable.** No index, no history; closing the tab lost the
result. `runs_owned_by()` already existed and nothing called it. Added
`/analyses`, linked from the nav only when the session has runs. One guest
cannot see another's.

**The Figma failure — two real defects, both generalisable.** Production said
*"Not enough public evidence for Figma"* directly above *"8 usable source(s)"*
across four families. Cause: discovery walked into Figma's **German** blog
(`Tag: Fallstudie`, `Tag: Produktupdates`); those pages counted as usable,
dragged the readable share under 0.6, and voided a run whose four English
sources were fine.

- discovery now drops locale-prefixed translations (`/de/`, `/pt_BR/`,
  `/zh-hans/`), with an exclusion list so `/in/`, `/is/`, `/api/` are never
  mistaken for locales;
- readiness now judges on documents it can **read**, setting the rest aside and
  reporting `set_aside_unreadable`, instead of counting them and then refusing.

**Verified live before → after:** `/slides` used to bounce to `/full` with
"not enough public evidence, full stop". Now `/progress → 303 /slides`
(presentation-first restored), 8 → 4 usable sources, and the reason is
specific: *"Some kinds of evidence are missing, and there are places left to
look… customers, use cases or partnerships."*

**Heading no longer contradicts the body.** "Not enough public evidence for X"
blamed the company while the body said the search was incomplete. Now
"Limited analysis of X".

## Next task, in order

1. **Confirm `29a6fe0` deployed**, then re-run Figma and check the heading.
2. **Task 5 — presentation narrative.** `/slides` now renders, but the
   deterministic deck is still the old one; `build_founder_slides` only fires
   when a grounded analysis exists. Decide what the deterministic deck says.
3. **Task 5/6 — brief and full-analysis renderers.** Still field-serialised
   (`_brief_page` ~`app.py:1600`, `_run_page` ~`app.py:1180`).
4. **Task 9 — landing examples** are still Palantir and Shopify
   (`GOLDEN_COMPANIES`, `demo_tiers.py`). Replace with current tech companies.
5. **Full five-company batch with rendered inspection** — still not done end to
   end; quota keeps cutting it short.

## Live testing constraint

Runs do **not** survive a redeploy: Render storage is `EPHEMERAL_LIKELY`, so
`/analyses` is empty after each deploy and earlier runs are unrecoverable.
Inspect a run in the same session that created it, before the next deploy.

## Companies used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma. Excluded: Chipotle/restaurants, Sony, Palantir, Shopify,
Microsoft, Nintendo.

## Owner actions

1. `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` (`openssl rand -hex 32`,
   `sync: false`) — unblocks repeated live validation without spending the
   public quota. Mechanism is built, tested and deployed.
2. `ANTHROPIC_API_KEY` — switches `strategic_reasoning` to true and activates
   the grounded analyst.

## Notes

- Run the suite with the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local reproduction (how the repeated-analysis and Figma defects
  were found; fixture transports hide both): build `AppConfig` with
  `autorun_sources=True` and pass **no** `transport` to `WebApp`.
