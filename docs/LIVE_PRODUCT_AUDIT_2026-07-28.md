# Live product audit — 2026-07-28

Deployed commit `ec337f5` at `https://intent-engine-oatc.onrender.com`.

**None of the ten commits from the last four programmes are deployed.** The
live service is the code from before any of that work. Everything a user sees
today is the original product. That single fact governs this whole audit.

Used as a first-time user, no prior knowledge, browser only.

---

## Fresh company: Chipotle Mexican Grill

`/runs/01KYN4GV76AMSWSJYD8AN6FR35`, run live. Verbatim from the rendered page:

> **Limited public evidence.** This company publishes too little for a full
> briefing.
>
> Chipotle offers fundraising for schools, sports teams, clubs and more.
>
> **There is not yet enough approved strategic evidence to form a defensible
> outside-in view of Chipotle Mexican Grill.**
>
> WHAT SUPPORTS IT
> 2026-07-28 Document exposes a surface others can build on
> 2026-07-28 It starts with 48 whole avocados. Celebrate National Day at
> Chipotle with fresh guac that's made fresh every day.
> 2026-07-28 EARNINGS RELEASE PR Contact: Laurie Schalow (949) 524-4035 …
> Three months ended March 31, 2026 … Food and beverage revenue $3,072,730

### What a normal person sees, in order

| # | Defect | Severity |
|---|---|---|
| 1 | The primary CTA "Analyze my company" **discards the filled form and redirects to a login page** with no signup and "Password reset: NOT AVAILABLE". The demo needs a different button clicked *first*. | dead end |
| 2 | An interstitial methodology wall with **six identical "Got it — start an analysis" buttons** | clutter |
| 3 | Result page titled "**Analysis progress**", badge "**PARTIAL**", raw run id `01KYN4GV76AMSWSJYD8AN6FR35`, and "These are real lifecycle stages, not decoration" — the product explaining itself | internal language |
| 4 | Result is **behind a click** ("Open the result"); brief opens before presentation | hierarchy |
| 5 | "**This company publishes too little for a full briefing**" — about a ~$60B public company. Flatly false. | credibility |
| 6 | First content is "**Chipotle offers fundraising for schools, sports teams, clubs**" — a fundraising page's meta description | no value |
| 7 | "**Document exposes a surface others can build on**" — the `"api"`-inside-`"capital"` substring bug, live, on a burrito chain, with the entity rendered as the literal word "Document" | wrong |
| 8 | "**48 whole avocados … fresh guac**" presented under WHAT SUPPORTS IT | marketing as evidence |
| 9 | **Scraped PR contact names, phone numbers and emails** rendered into the brief | privacy / polish |
| 10 | Every evidence line prefixed `2026-07-28` — the retrieval date, identical on all | noise |
| 11 | "produced by the current version of the product", "Analysis version 1.5.0-executive-intelligence" | internal |
| 12 | The central view is printed **twice, verbatim** | repetition |

### The finding that matters most

The run **did retrieve the Q1 2026 earnings release**, including real revenue
figures, and then reported that there was not enough evidence to say anything.

That is not a retrieval failure. The evidence was in hand and the reasoning
layer threw it away, because an observation only existed if it matched a
controlled-vocabulary signal — and an earnings release matches none of them.

---

## Does the branch fix this?

Verified against the same text, on `feat/strategic-intelligence-v2`:

```
live text containing "Capital expenditures and rapid restaurant expansion"
  live  -> "Document exposes a surface others can build on"
  branch-> signals = []                                    (defect 7 fixed)

Chipotle fundraising page + Q1 earnings release
  old signal-gated path -> 0 observations   (why live says "not enough evidence")
  derive_analyst_evidence -> 2 kept, including the investor_material release
```

So defects 5, 6, 7, 8 and 12 have fixes sitting on the branch. Defects 1, 2, 3,
4, 9, 10 and 11 are webapp-layer and are **not** fixed by anything written so
far.

---

## Scope not covered by this audit

Stated plainly rather than left implied:

- **One fresh company was run live, not twelve.** The pattern above is from a
  single deep run plus the earlier offline fresh set of ten.
- **No baseline comparison** against Perplexity, ChatGPT or Claude was run. I
  have no access to those accounts, and fabricating their outputs to compare
  against would be worthless.
- **No human validation.** Zero people have used this.
- **Nothing is deployed**, so no post-deployment verification exists.

---

# Post-deployment verification — `91eada2`

PR #13 merged; Render redeployed. `/version` reports `91eada2`.

## Verified fixed on production

| Defect | Before (`ec337f5`) | After (`91eada2`) |
|---|---|---|
| Login dead end | `POST /analyze` anonymous → `303 /login`, form discarded | `303 /runs/<id>/progress` + `sid=…; HttpOnly; SameSite=Lax; Secure` |
| Result behind a click | status page → "Open the result" | `GET …/progress` → `303 …/slides` |
| Capability invisible | `/readyz` had no reasoning key | `capabilities.strategic_reasoning: false` — now checkable, not inferred |

## OPEN REGRESSION — production 500

`POST /analyze` for **Vercel** returned `500` repeatedly (error references
`fd45f08fc39d`, `65dd3dfa504e`). The first Vercel run of the session succeeded
(`01KYN705V618AQ59VHPFGQYZHY`); Datadog and Ramp also succeeded. Subsequent
Vercel attempts failed.

What was ruled out:
- not the minted session — `auth.session(create_anonymous_session())` returns a
  valid anonymous session with csrf, and the rate limiter accepts it
- not request headers — the header bisect was confounded by the per-IP quota;
  the later 429s were quota, not the header under test
- not repeat-company collision — three fresh visitors analysing the same
  company locally all succeed
- not reproducible locally at all, including with an invalid cookie, an
  established session, autorun on, and the real-company entity-resolution path

The remaining difference between the passing local runs and the failing
production ones is **real network retrieval**. Diagnosing further needs the
server-side traceback.

**Owner action:** Render dashboard → Logs → search `fd45f08fc39d` or
`65dd3dfa504e`. I cannot read those logs.

I have not attributed this to the deploy. It may predate it — the pre-deploy
audit never ran Vercel.

## Live validation not completed

The per-IP demo quota is now exhausted from this address, so further live runs
return 429. Of the 20 fresh technology companies the programme asks for, **3
were run on production after deployment** (Vercel, Datadog, Ramp) and only
their HTTP outcomes were captured — no rendered decks were inspected, because
the runs that reached a deck belonged to a curl session and the browser session
could not read them.

---

# The 500, root-caused

Reproduced by running the app locally against the **real network** — the one
condition never previously tested. Fixture transports always succeeded, which
is why five earlier reproduction attempts came back clean.

## Layer 1 (fixed, `5e0f6cb`)

```
ValueError: idempotency_key 'complete:<run>' was already used for
            different content
```

`fi.run_completed` was keyed on the run alone. That promised a run completes
once with one result — untrue, because re-analysing produces a fresh set of
limitations from freshly retrieved pages. The guard correctly refused the
mismatch and the exception reached the user as "Something went wrong".

Fixed by putting a digest of the recorded payload inside the key: an identical
retry still collapses onto one event, a genuinely different result appends.

## Layer 2 (NOT fixed — the real one)

With layer 1 removed, the third visitor surfaces:

```
FounderIntelligenceError: fi.section_assembled on a terminal run (COMPLETE)
```

The FI run id is derived deterministically from
`analysis_fingerprint(company_input)` — company + approved sources + pipeline
version. Two analyses of the same company, with the same evidence, on the same
build therefore resolve to **the same FI run**. The first completes it. The
second re-runs the pipeline and tries to assemble sections onto a run that is
already terminal.

The determinism is deliberate and correct: identical analyses *should* be one
run. The defect is that the second caller **re-executes** instead of
**reusing** the completed result.

**Where to fix:** `FounderIntelligenceService.run()`. Before assembling, check
whether the derived run is already terminal; if so, rebuild and return its
recorded result rather than replaying the write path. `compose_with_quality`
→ `compose` → `fi_service.run` is the call chain.

This is why the live symptom was "first analysis of a company works, every
later one 500s". In production the store persists, so **the second person to
look at any company hits it.**
