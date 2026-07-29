# Founder Intelligence — continuation

Written at a context handoff. Verified live, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `101bf7a` verified live (three layers inspected) |
| **main SHA** | see `git log -1` — one commit ahead (company-name fix), **deploy not yet verified** |
| **Working tree** | clean |
| **`/readyz`** | `degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## What `dcadb1b` looked like (the starting point)

| layer | anchor present | taxonomy leaks |
|---|---|---|
| `/slides` | yes | **none** |
| `/brief` | yes | `system of record` |
| `/full` | **no** | `system of record`, `tool-to-system-of-record`, `broadening from a focused tool` |

So the shared claim reached the brief, and the full analysis was still
selecting its own thesis from `thesis["view"]`.

## Fixed and shipped in `101bf7a`

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

## Deployment B — DONE, verified live on `101bf7a`

Sentry re-run on production, run `01KYNVZG815XHR6DV9NEGTNDYR`:

| layer | leaks | opens on |
|---|---|---|
| `/slides` | **none** | "Sentry acquired Codecov." |
| `/brief` | **none** | "Sentry acquired Codecov." |
| `/full` | **none** | "Sentry acquired Codecov." |

All five phrases absent from all three layers, and the full analysis now
opens on the same claim as the deck. That closes the three-layer programme.

## Found by that inspection — the company had no name

Every layer was headed **"(unnamed company)"** — tab title, `h1`, and the
sentence *"What (unnamed company) does is not described on any page we could
retrieve"* — on a report citing "About Sentry | Sentry" and claiming "Sentry
acquired Codecov."

The landing form asks for a website, not a name, so `company_name` is empty on
essentially every real visit. The name was available twice and used neither
time: `resolve_entity` already ran, and its `profile.legal_name` was computed
and thrown away; failing that, the domain itself carries the name.

Fixed in `_analyze`: resolved legal name first, then `name_from_domain()`
(`sentry.io` → Sentry, `bbc.co.uk` → Bbc, an IP or single label → `""`, and
the "(unnamed company)" wording still stands behind those). A typed name still
wins — the domain is a fallback, never an override.

The whole fixture suite missed this because `_start_real` passes
`company_name=Acme`, which no real form does. **Treat that helper as a liar:
when checking first-visit behaviour, post what the form posts.**

## Next task — exact

1. **`_brief_page` layout** (`app.py` ~1600) — the claim is shared and clean,
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
