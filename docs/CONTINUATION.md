# Founder Intelligence — continuation

Written at a context handoff. Verified live, not assumed.

> ## ✅ Founder Intelligence is complete
>
> The demo-perfection milestone finished at **`91113fa`** on
> `feat/strategic-intelligence-v2`. Suite: **2809 passed, 14 skipped**.
> Five fresh companies validated end to end, 15 layer-views clean of every
> leak class, no page repeating a text block. Mobile inspected at 375×812.
>
> **Read [`LAUNCH_READINESS.md`](LAUNCH_READINESS.md) first** — it carries the
> architecture summary, what changed, the demo checklist, the five-company and
> mobile validation, known limitations, owner actions and the roadmap.
>
> **Not deployed.** Production is still on the previously verified SHA. Merging
> and deploying `91113fa`, then re-running the demo checklist against
> production, is the one remaining step and it is an owner action.
>
> Everything below this box is the record of how the product got here. It is
> history, not a task list.

## State

| | |
|---|---|
| **Milestone head** | `91113fa` — demo perfection complete, **not deployed** |
| **Deployed SHA** | `101bf7a` verified live (three layers inspected) — now well behind |
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
opens on the same claim as the deck.

**That was true for Sentry and not in general.** Sentry has a concrete fact
("acquired Codecov"), so its deck is built by the founder path. Running four
more companies showed the OTHER deck — the fallback for a company with real
evidence and nothing concrete — was never filtered at all.

## The fallback deck — measured on five companies at `f1d350c`

| company | `/slides` | `/brief` | `/full` |
|---|---|---|---|
| GitLab | none *(limited-evidence page)* | none | none |
| Hugging Face | **3 leaks** | none | none |
| Stripe | **3 leaks** | none | none |
| CrowdStrike | **2 leaks** | none | none |
| Nvidia | none *(limited-evidence page)* | none | none |

Three of three companies that produced a deck leaked; brief and full were
clean for all five. `build_report_slides` printed `thesis["view"]` and
`thesis["transition"]` — the same scaffold removed from `_central_claim` —
plus hypothesis titles, blind-spot tensions, vulnerability mechanisms,
opportunity statements and leadership questions, under a heading reading
"Key strategic signals".

Now filtered at all seven selection points, and the heading is "What the
company has published".

The persona harness then caught real over-reach, which is what it is for:
Linear's ONLY leadership question was the pattern's own falsification question
("Customers describing it as a companion to a system of record…"), so
filtering it left a meeting-prep reader with nothing to investigate. **The
harness had been passing on that sentence** — the answer was never really
there. When no question survives, the deck now derives one from the run's own
dated findings ("Confirm with an independent or customer source: Linear
pricing publishes its prices."), which names something actually retrieved.
Not the library's question reworded, and not the limitations list promoted to
look like an action. Critically, once the library's sentences are gone a
pure-scaffold company falls BELOW `MIN_MEANINGFUL_SLIDES` and gets the
limited-analysis page instead — which is the point. A shorter deck of the same
generic claims would have been the failure, not the fix.

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

## Verified clean on `79e6746`

Re-ran the three companies that leaked. All nine layer-views clean:

| company | `/slides` | `/brief` | `/full` |
|---|---|---|---|
| Hugging Face | none | none | none |
| Stripe | none | none | none |
| CrowdStrike | none | none | none |

Decks stayed substantial (3.0k–4.4k chars), so filtering did not collapse
real companies onto the limited-analysis page — only the pure-scaffold case
falls through, which is the intent.

## The task list that closed this milestone — all done

1. ~~**`_run_page` layout**~~ — done in `b5d80ee`. Fourteen field-shaped
   sections became the eight moves of an argument, and `381f2f5` took the
   legacy claim-id view off the fallback path entirely.
2. ~~**Landing examples**~~ — done in `5b1a99f`. Labelled *Example analysis*,
   stated as not current. The company is deliberately unnamed: it is the
   console maker a golden gate keeps off that page.
3. ~~**Mobile inspection**~~ — done in `91113fa`. 375×812, live browser, on a
   real Airbnb run. Two defects found and fixed; no overflow anywhere.
4. ~~**Brief signal quality**~~ — done in `36ea85b` (the company is the
   grammatical subject, all 27 signals state a consequence) and `198e351`
   (raw page furniture no longer reaches a slide or a bullet).

See [`LAUNCH_READINESS.md`](LAUNCH_READINESS.md) for what each fix actually
changed, and for the limitations that remain open.

## What is genuinely next

**Live Trading Training System.** Founder Intelligence is the stable
foundation now; treat it as one.

The one thing that would most improve Founder Intelligence if picked up later
is **retrieval on JS-rendered sites**. Three of the five validation companies
produced no strategic report for that single reason. It is a retrieval gap,
not a reasoning gap, and closing it converts those runs from an honest
limited page into a full report.

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
