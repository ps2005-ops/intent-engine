# Founder Intelligence — continuation

Written at a context handoff. Verified live, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `dcadb1b` verified live |
| **main SHA** | see `git log -1` — one commit ahead, **deploy not yet verified** |
| **Working tree** | clean |
| **`/readyz`** | `degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## Verified live on `dcadb1b`

| layer | anchor present | taxonomy leaks |
|---|---|---|
| `/slides` | yes | **none** |
| `/brief` | yes | `system of record` |
| `/full` | **no** | `system of record`, `tool-to-system-of-record`, `broadening from a focused tool` |

So the shared claim reached the brief, and the full analysis was still
selecting its own thesis from `thesis["view"]`.

## Fixed and pushed (deploy NOT yet verified)

The pattern title reached a reader from **seven** distinct selection points.
Each is now filtered where the visible item is chosen — never globally:

1. `render.py:_central_claim` — the full analysis now opens from the shared
   anchor instead of `thesis["view"]`
2. `render.py:_pattern_block` — printed the library entry's own NAME
   ("Point tool → system of record") plus its generic mechanism text
3. `render.py:_reasoning_block` — "…match the tool-to-system-of-record
   mechanism" is the library describing itself matching
4. `render.py` hypothesis cards — dropped when title AND statement are both
   ontology; the evidence beneath is already shown under Evidence
5. `render.py` questions-for-leadership
6. `render.py` agenda cards + the summary "Likely current discussion" line +
   "What would confirm"
7. `render.py` executive-summary chips (hypothesis titles are pattern names)
   and `brief.py` leadership questions

Local render now shows the full analysis opening on **"Sentry acquired
Codecov."** with all five phrases absent across all three layers, asserted by
27 behavioural tests in `test_sentry_deck_regression.py` that read rendered
output rather than source strings.

## Next task — exact

1. **Deploy and verify.** Re-run Sentry and check `/slides`, `/brief`, `/full`
   for the five phrases (the loop used in this session is in the transcript).
   Do not report Deployment B complete until production output is inspected.
2. **`_brief_page` layout** (`app.py` ~1600) — the claim is shared and clean,
   but the page is still field-shaped cards, not one reading column (Task 6).
3. **`_run_page` layout** (`app.py` ~1180) — same: content is now clean, the
   structure is still a schema dump (Task 5).
4. **Landing examples** — unblocked. "Sentry acquired Codecov." is verified
   live output; use it as a labelled *Example analysis* with the interpretation
   and uncertainty beneath.
5. **Five-company rendered batch incl. mobile** — still never done.

## One thing fixed on the way out

The pre-commit guard blocked this commit with a failure in
`test_marketing_publishing.py` that had nothing to do with the renderers.

`CompanyEvent.content_fingerprint()` excluded `event_id` and `recorded_at` but
kept `occurred_at`, which defaults to the clock at second resolution. Two
identical publishes agreed only while they landed inside the same wall-clock
second; straddle the boundary and the retry was rejected as *"already used for
different content"* — backwards, since a retry is by definition later.

All **twelve** other record types in the codebase already exclude all three,
and `crm/events.py` states the reason outright: *a retry naturally carries a
fresh clock but MUST carry the same facts.* The core envelope was the lone
outlier, contradicting its own docstring.

Every duplicate-publish test in the suite was a coin flip on where the second
boundary fell. `test_a_retry_a_second_later_is_still_the_same_event` now pins
it with explicit timestamps 90 minutes apart, so it fails every time on the
old code rather than one run in a thousand.

## Do not

- Restore the global `_cap()` filter. It stripped honest limitation and
  counter-evidence prose and broke persona cases.
- Import `reads_as_taxonomy` inside a function in `render.py` — it is imported
  at module level there, and a local import shadows it and raises
  `UnboundLocalError` at the other call sites.

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
- `test_product_maturity.py` and `test_product_eval.py` catch over-reach. Run
  them after every narrowing change, before the full suite.
