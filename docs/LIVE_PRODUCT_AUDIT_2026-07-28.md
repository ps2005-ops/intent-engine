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
