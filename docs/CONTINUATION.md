# Founder Intelligence — continuation

Written at a context handoff. Everything below is verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `ac7aada` — verified via `/version` |
| **main SHA** | `ac7aada` — deployed and in sync |
| **Public URL** | https://intent-engine-oatc.onrender.com |
| **Open PR** | none — [#13](https://github.com/ps2005-ops/intent-engine/pull/13) merged |
| **Working tree** | clean |
| **Suite** | 2611 passed, 14 skipped |
| **Worktree** | `scratchpad/si2` on `feat/strategic-intelligence-v2`, tracking main |

## Done and verified live

**The repeated-analysis 500 is fixed.** Three separate anonymous visitors
analysed the same company (Linear) on production: `303`, `303`, `303`.

Two layers, both fixed:

1. `complete:{run_id}` idempotency key collided when the same company was
   re-analysed with different limitations. Key now carries a payload digest.
2. The real one: run identity is deterministic per company + evidence +
   pipeline version, so a second caller derived the same id and **re-executed
   the write path against a terminal run** —
   `fi.section_assembled on a terminal run (COMPLETE)`.
   `run()` now resolves run state first: COMPLETE/PARTIAL recomposes in memory
   and appends nothing; FAILED/REJECTED refuses plainly; otherwise normal.

Reuse is safe structurally: the result is a pure function of the arguments
(`_assemble_sections` reads only its parameters), which is the same premise
that makes the id deterministic.

Real-network verification with a persistent store — the condition that hid this
from 2,600 tests:

```
visitor 1: 303  sections=12  completed=1
visitor 2: 303  sections=12  completed=1
visitor 3: 303  sections=12  completed=1
```

Also live-verified earlier: no login dead end (`303` to the run + `HttpOnly;
SameSite=Lax; Secure` session), presentation-first (`/progress` → `303
/slides`), and `/readyz` reporting `capabilities.strategic_reasoning`.

## Blocked right now — do this first

**The per-IP demo quota blocks live validation.** Engineering traffic consumes
the same allowance as user traffic; repeated smoke runs return `429`. This
stopped rendered-page verification twice.

Implement **Task 6** before resuming the UI loop, or every batch stalls:

- add a smoke-test path that does not consume public quota
- prefer: a config-gated token checked in `_demo_rate_limited`
  (`src/intent_engine/webapp/app.py:501`), read from an env var, absent by
  default, with an audit log line on every bypass
- do **not** disable public limiting, embed the secret client-side, or make the
  bypass discoverable

## Then resume the loop

**Task 8 UI defects, none started**, in impact order:

1. Methodology wall on the primary journey, with **six identical "Got it —
   start an analysis" buttons** (`_onboarding`, `app.py:352`)
2. Landing page does not show a concrete example of the value
3. Old executive-brief renderer (`_brief_page`, ~`app.py:1579`)
4. Old full-analysis renderer (`_run_page`, ~`app.py:1159`)
5. Brief/analysis do not use the grounded company model the deck uses
6. Empty and sparse one-sentence cards
7. Mobile readability unverified

Per batch: deploy → confirm SHA → 5 fresh technology companies → inspect
rendered pages in a browser → screenshot → rank defects → fix root causes →
regression tests → redeploy → re-run failures + unrelated cases.

Companies used so far (rotate away from these): Vercel, Datadog, Ramp, Linear,
Cloudflare. Excluded by instruction: Chipotle, restaurants, Sony, Palantir,
Shopify, Microsoft, Nintendo, prior synthetic fixtures.

## Useful commands

```bash
# real-network repeated-analysis reproduction (the one that found layer 2)
cd scratchpad/si2 && .venv/bin/python -c "..."   # see git log for ac7aada
```

Run the suite with the venv on PATH or the pre-commit guard fails:
`PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`

## Owner-only

`ANTHROPIC_API_KEY` is not set in Render, so the grounded analyst is dark and
`/readyz` reports `strategic_reasoning: false`. Everything else — retrieval,
stability, UI, deployment — proceeds without it. After it is added, verify:
`strategic_reasoning: true`, an analyst call succeeds, no secret is logged,
timeout/fallback is understandable, and the deck/brief/analysis use grounded
output.
