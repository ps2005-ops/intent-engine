# Founder Intelligence — continuation

Written at a context handoff. Everything below is verified, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `94f4e18` — verified via `/version` |
| **main SHA** | `94f4e18` (+ this doc) |
| **PR** | none open; `main` auto-deploys |
| **Working tree** | clean |
| **`/readyz`** | `status: degraded` — honest about non-durable storage |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |
| **Smoke token** | not configured — engineering traffic still spends public quota |

## Verified live this round

**Figma, the case that was broken.** `/progress → 303 /slides`
(presentation-first), heading reads **"Limited analysis of Figma"**, 4 usable
sources with the German pages set aside, and the reason is specific rather
than blaming the company: *"Some kinds of evidence are missing, and there are
places left to look."*

**Persistence diagnosed precisely.** `render.yaml` declares a persistent disk
at `/var/data` and sets `RUNTIME_ROOT` to it. The running service reports
`runtime_root: "data"`, `durability: EPHEMERAL_LIKELY` — writing inside the
container, erased on every deploy. **The blueprint is correct and is not what
the live service runs.**

Two halves were ours and are now fixed and deployed:

- `/readyz` reports `status: degraded` in production when storage is not
  durable, with `degraded_reason` naming the fix. **Verified live.** Still
  HTTP 200 — the demo works, it just forgets. Test-mode and genuinely durable
  services are unaffected, so it does not cry wolf.
- `/analyses` no longer promises history it cannot keep: it says the analyses
  are kept only until the next restart.

**Durability is tested at the layer this repo controls:** create an analysis,
destroy and rebuild the application over the same files, and the run, the
history and deterministic reuse are all still there — no duplicated completion
events, no cross-visitor access. Those pass, which locates the defect exactly:
**the code persists correctly; the deployed service is not pointed at the
disk.**

## Next task, in order

1. **Task 6/7 — presentation renderer.** The deterministic path still renders
   the old deck. `build_founder_slides` (`slides.py`) only fires when a
   grounded analysis exists; `build_slides` falls through to the legacy deck
   otherwise. Make one founder-facing presentation contract that both paths
   populate — start at `build_slides` in
   `src/intent_engine/strategic_intelligence/slides.py`.
2. **Task 8 — executive brief.** `_brief_page`, ~`app.py:1600`. Still
   field-by-field.
3. **Task 9 — full analysis.** `_run_page`, ~`app.py:1180`. Still schema-shaped.
4. **Task 10 — landing examples** still Palantir and Shopify
   (`GOLDEN_COMPANIES`, `demo_tiers.py`).
5. **Task 12 — full five-company rendered batch.** Never completed end to end;
   quota cuts it short every time.

## Known unfixed defects

- The "Sources that were read" list on a limited result still shows the
  unreadable German pages without marking them as set aside. They are excluded
  from the counts correctly; the list does not say so.
- Runs still vanish on redeploy in production until the disk is attached.

## Live testing constraints

- Runs do not survive a redeploy (see above), so inspect a run in the session
  that created it, before the next deploy.
- Public demo quota is ~10 analyses/hour/IP and engineering traffic shares it.

## Companies used — rotate away

Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma. Excluded: Chipotle/restaurants, Sony, Palantir, Shopify,
Microsoft, Nintendo.

## Owner actions (exact)

1. **Attach the persistent disk** to `intent-engine-oatc` and set
   `RUNTIME_ROOT=/var/data`. `render.yaml` already declares both; the running
   service is not using them. Until then `/readyz` will keep reporting
   `degraded` and analyses will be lost on every deploy.
2. `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN` (`openssl rand -hex 32`,
   `sync: false`) — unblocks repeated live validation.
3. `ANTHROPIC_API_KEY` — activates grounded reasoning.

## Notes

- Run the suite with the venv on PATH or the pre-commit guard fails:
  `PATH="/Users/prathamsharma/intent-engine/.venv/bin:$PATH" git commit`
- Real-network local reproduction (how the repeated-analysis and Figma defects
  were found; fixture transports hide both): build `AppConfig` with
  `autorun_sources=True` and pass **no** `transport` to `WebApp`.
