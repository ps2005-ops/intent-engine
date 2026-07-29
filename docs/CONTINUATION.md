# Founder Intelligence — continuation

Written at a context handoff. Verified live, not assumed.

## State

| | |
|---|---|
| **Deployed SHA** | `f0bbfb2` verified. A newer commit is pushed, deploy unverified |
| **main SHA** | see `git log -1` |
| **Working tree** | clean |
| **`/readyz`** | `degraded` — non-durable storage, honestly reported |
| **strategic_reasoning** | `false` — `ANTHROPIC_API_KEY` unset (owner) |

## Verified live on production (`f0bbfb2`)

**Presentation is clean.** Sentry opens on "Sentry acquired Codecov.", cited to
the acquisition page. Checked on the deployed deck and absent:
`system of record`, `tool-to-system-of-record`, `broadening from a focused
tool`, `strategic signal`, `analysis version`.

**The watch item is gone.** It used to say "Customers describing it as a
companion to a system of record rather than the record itself" — the pattern's
own falsification question, which a reader cannot observe. Filtered at the
point the watch bullet is SELECTED (`founder_view_from_report`), nowhere else.
Sentry has no company-specific observable to substitute, so the watch screen is
honestly omitted rather than filled with filler.

**Still leaking on production, in the OLD renderers only:**

| layer | leaks |
|---|---|
| `/slides` | none |
| `/brief` | `system of record` |
| `/full` | `system of record`, `tool-to-system-of-record`, `broadening from a focused tool` |

## Pushed but not yet deploy-verified

The brief now opens from the **same** anchor as the deck
(`brief.py:build_brief`) instead of selecting its own from `thesis["view"]` —
that divergence is why the brief kept the scaffold claim alive after the deck
was clean. When no anchor exists and the only candidate is ontology, the
central claim is left empty rather than asserted.

## Next task — exact

1. **Deploy and verify** the pushed commit; re-run the three-layer leak check
   (the loop in this session's transcript checks `/slides`, `/brief`, `/full`
   for the five phrases).
2. **`_run_page` (`app.py` ~1180)** — the full analysis still renders scaffold
   hypotheses directly, which is where the remaining two leaks live. It is the
   last renderer selecting its own claim. Apply the same rule: open from the
   shared anchor, and where a section's only content is taxonomy, omit the
   section rather than filter its words.
3. **`_brief_page` (`app.py` ~1600)** — the claim is now shared, but the page
   is still field-shaped cards rather than one reading column (Task 4).
4. **Landing examples** — now unblocked. "Sentry acquired Codecov." is verified
   live output and can be used as a labelled *Example analysis*.
5. **Five-company rendered batch incl. mobile** — still never completed.

## Do not

- Restore the global `_cap()` taxonomy filter. It stripped honest limitation
  and counter-evidence prose and broke several persona cases.
- Filter source text, limitations, evaluator explanations, operator pages or
  genuine counterarguments. A counterargument that names the mechanism being
  doubted is doing its job.

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
- `test_product_maturity.py` and `test_product_eval.py` are what catch
  over-reach. Run them after every narrowing change, before the full suite.
