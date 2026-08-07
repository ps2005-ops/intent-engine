# Founder Intelligence — continuation checkpoint

**Updated 2026-08-03.** Branch `feat/founder-decision-experience-v3`,
checkpoint commit `8810aaf`, deployed and verified on
<https://intent-engine-preview-v3.onrender.com>.

Everything below was MEASURED on the deployed preview. Re-verify before
relying on it.

---

## 1. Status

`/readyz`: `strategic_reasoning: true`, `reasoning_key_present: true`.
**The rich path works.** Full suite 3131 passed / 14 skipped, guard EXIT=0.

Fixed and verified live this cycle:

| defect | evidence before | after |
|---|---|---|
| citations showed internal ids | `obs-src-eb15293b7148` ×8 | "About Palantir", "Palantir Foundry", … |
| "Why this matters" was a noun fragment | `how much to invest ahead of the transition` | real consequences (Microsoft, Adobe) |

Gates: `tests/test_citations_are_readable.py` (5),
`tests/test_so_what_is_a_consequence.py` (14). Both fail on revert.

---

## 2. THREE OPERATIONAL FACTS THAT INVALIDATE NAIVE MATRIX RUNS

Learned the hard way this cycle. Read before running the matrix again.

### 2.1 Runs do NOT survive a deploy
Storage is ephemeral (`/readyz` says so). A Tesla run started before a deploy
returned **"Not found"** afterwards. **Run the matrix only after the final
deploy of the session**, or every result is lost.

### 2.2 Runs are idempotent per (domain, user, day)
`create_run` derives a stable id from `ci-run:{domain}:{user_id}:{as_of}`.
Re-submitting Shopify returned the **identical run id** and its previous
failed result — not a fresh analysis. To get a genuinely fresh run for a
company already analysed today, start a **new guest session** (`POST /demo`)
so `user_id` differs. "Do not reuse old runs" is otherwise impossible to
satisfy.

### 2.3 Concurrent analyses throttle each other into false failures
Eight analyses launched back-to-back: the first four largely succeeded, the
last four all returned "no approved source could be retrieved" — including
Shopify, a curated company that succeeds when run alone. This is a
single-instance free-tier artifact, **not** a product defect. Space runs out
and run them sequentially, or the matrix measures the harness rather than the
product.

---

## 3. Matrix so far (commit `8810aaf`)

| company | state | note |
|---|---|---|
| Palantir | RICH | thesis, mechanism, decision, 8 named citations |
| Microsoft | RICH | 251 w, "So what?" is a real consequence |
| Adobe | RICH | 320 w, bounded-but-useful framing, real consequence |
| Tesla | BOUNDED (legitimate) | see §4 |
| Datadog, Cloudflare, NVIDIA, Costco, Shopify, Stripe | INVALID | hit §2.3 — re-run sequentially |

Not yet run: Amazon, Apple, Meta, Alphabet, ASML, Toyota, private company,
small business, sparse company, interrupted run.

---

## 4. Tesla/NVIDIA/Costco are bounded for a REAL reason — do not "fix" it

Tesla re-run with grounded reasoning **fully enabled** still returned a
bounded result: `3 page(s) read; 1 carried usable evidence`, because
`www.tesla.com` answers automated requests with HTTP 401/403 and only SEC
exhibits could be read. One usable source is below the evidence bar, so the
analyst is never invoked.

**This is the product legitimately choosing the bounded path.** The reasoning
key was never the constraint for these companies — retrieval is. Any future
cycle that treats "Tesla is not rich" as a reasoning defect is chasing the
wrong thing. The honest options are better retrieval (rendering, alternative
sources) or accepting a high-quality bounded result — which now exists.

---

## 5. Remaining known defects

### 5.1 Executive brief is under target
Prints `191 words (target 500–900)` on Palantir; the goal is 600–1,000 on
rich results. Sections are omitted rather than padded, which is the right
instinct, so **do not pad**. Likely cause: the brief is built with a dedup
ledger pre-loaded with the 60-second brief's sentences, leaving little to say
when the two overlap. Start at `build_executive_brief` in
`src/intent_engine/founder_brief/layers.py`.

### 5.2 `<style>` blocks sit inside `<main>`
`LAYER_CSS` is emitted inside `<main>` on the dashboard/story/brief layers, so
it appears in `main.innerText`. Invisible to readers, but it pollutes
text-based gates and is invalid placement. Move to `<head>`.

---

## 6. Credentials

| key | preview | local `.env` | consequence |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **present** | present | rich path works |
| `TIINGO_API_KEY` | unverifiable | **present** | producer can run locally |
| `FRED_API_KEY` | unverifiable | **absent** | macro blocked |

`/readyz` still reports nothing about Tiingo or FRED. **First task:** add
presence booleans for both, following the `reasoning_key_present` precedent
(booleans only, values never read). Until then §1.7 cannot be verified.

Owner action for macro:
```
Render Dashboard → intent-engine-preview-v3 → Environment
  → Add FRED_API_KEY → Save Changes → wait for redeploy
```
Also needed **locally** to generate any macro fixture.

---

## 7. Market data — the unanswered design question

Ticker resolution is solved (`2b2e437`, SEC registrant table; Tesla → TSLA/
Nasdaq, Costco → COST/Nasdaq, verified live). The next link is not wired:

- `export_company(ticker=, exchange=, closes=, benchmark_closes=, as_of=)` and
  `write_export(payload, root=)` in
  `~/intent-engine-market/src/intent_engine/market/intelligence_export.py`.
- **It does not fetch prices.** `closes` comes from `get_prices(...)` in
  `~/intent-engine-market/src/intent_engine/core/market_resolution.py`, which
  needs `TIINGO_API_KEY`.
- Consumer: `WebApp._market_snapshot` reads
  `{runtime_root}/reports/market/export/{TICKER}.json`.

**Decide before writing code:** the preview has ephemeral storage and runs
only what is in the repo — it never runs the producer. So exports are either
committed sanitized fixtures, or new runtime-generation code plus Tiingo on
Render. §2.1 means committed fixtures are the only option that survives a
deploy. `_assert_sanitized` already enforces forbidden keys; do not
re-implement it.

---

## 8. Not started

Shared "So what?" contract object · slides audit · full-analysis cleanup ·
Q&A via `POST /conversation` · citation walk beyond Palantir · break-proofs
4,6,7,8,10,11,12 · human review pack.

Break-proofs proven and passing: listed-as-private (6 fail on revert),
identical bounded output (9 fail), citations (5 fail), so-what fragment
(14 tests, incl. one pinned to the exact shipped string).

---

## 9. Invariants

`env="test"` must never reach the network — analyst client and SEC ticker map
are both gated on it. Preserve when adding Tiingo or FRED.

Demo limit is 10 analyses/IP/rolling hour (`demo_ip_analyses_per_hour`). It is
an abuse guardrail on a public URL — do not raise it to speed up testing.

PR #14 stays **draft**. Production stays on `119d345`. Do not merge.

---

# 2026-08-05 — filings became readable

Branch `feat/founder-decision-experience-v3`, deployed and verified on
`b6db86d`. Suite 3885 passed, guard EXIT=0. Production and PR #14 untouched.

## 10. THE DEFECT, AND WHY IT LOOKED LIKE SOMETHING ELSE

`parse_html` buffers character data only while a `_BLOCK` tag is open, and its
block set is the vocabulary of a hand-written page: `p`, `h1`-`h6`, `li`, `td`.
Datadog's 2025 10-K contains **zero** `<p>`, **zero** headings, **zero** `<li>`
— 1,878 `<div>` and 4,857 `<span>`. Every narrative paragraph was discarded and
only the 7,147 table cells survived: 25,787 characters of a 2,086,014-byte
document.

It was not truncation. The parser walked the whole document — the last text it
produced was the signature page — and threw away 93% of it. Three cycles read
that 25,787 as "the fetch stopped early" and went looking at byte caps and
document selection. **A short extract is not evidence of a short read.** Check
whether the tags carrying the text are in the block set before touching the
network layer.

| | before | after |
|---|---|---|
| Datadog 10-K extracted | 25,787 | 382,003 |
| sections located | 0 body | 1, 1A, 2, 3, 7, 7A, 8 |
| filing propositions | 0 | 9 (7 survive retention) |
| what a reader saw | company blog | Item 7 MD&A, cited to the 10-K |

## 11. RULES THAT NOW HOLD

**Filings are parsed by `company_ingestion/filing_text.py`, not `parse_html`.**
Gated on the document being served from EDGAR or already identified as a
filing. Ordinary pages are untouched — that separation is deliberate, and
`test_non_filing_extraction_is_unchanged` fails if it erodes.

**Extraction quality is explicit.** Nine states. "We retrieved the 10-K" and
"we can read the 10-K" were the same fact to every gate, which is how a cover
page travelled as an annual report for three cycles. `COVER_ONLY` is a claim
about volume, never about Item numbering — a 10-K/A carries only the items it
amends and is a complete read of itself.

**Retention is section-aware and every section gets an equal reserve first.**
Front truncation at 120,000 carries 4 of the 9 propositions the Datadog 10-K
supports; the equal-reserve allocation carries 7 under the same bound. Item 1
runs to 39,000 characters and Item 1A to 149,000 — either could eat the budget,
and neither may.

**Topical spans are funded from their own reserve.** Item 1A's reserve buys its
first 24,000 characters, so customer concentration and supplier dependency —
tens of thousands of characters in — are only reachable by looking for them.
Sharing one pool with the Items cost six of nine propositions when measured.

**A cross-reference is not a heading, and a heading is not a section.** "See
Part I, Item 1A" inside MD&A ended MD&A at 4,263 characters and labelled 23,410
characters of it as Risk Factors. A real heading starts its line. A 10-Q prints
"Item 2" twice and only one of them is MD&A.

**Which Item carries MD&A depends on the form.** 7 in an annual report, 2 in a
quarterly one. Read with the annual order a 10-Q reaches Financial Statements
and serves litigation boilerplate.

**Prose about the document is not prose about the company.** This is the one to
remember. Filtering a section's opening framing phrase by phrase does not
converge — removing one promotes the next, measured across five filers and
three deploys. Substance begins at the first real subheading; go there.

**Public identifiers are not credentials.** A cover page prints the commission
file number beside the IRS employer number and the naive card pattern matched
the pair, dropping a whole 8-K. Luhn separates the shape from the thing without
weakening detection.

**Say only what was established.** A registrant whose filing names the subject
is not thereby a competitor; it is "Another registrant's filing".

## 12. MEASURED THIS CYCLE

Extraction, seven filers, all `FULL_BODY_CONFIRMED` with all seven sections
except where noted:

| filer | raw | old | new |
|---|---|---|---|
| Datadog 10-K | 2,086,014 | 25,787 | 382,003 |
| Microsoft 10-K | 8,585,501 | 268,258 | 319,417 |
| Caterpillar 10-K | 6,100,469 | 71,013 | 428,519 |
| NVIDIA 10-K | 1,967,816 | 24,899 | 334,003 |
| Amazon 10-K | 1,968,342 | 33,724 | 279,996 |
| Caterpillar 2007 (pre-XBRL) | 619,098 | 30,304 | 97,845 |
| Shopify 10-K/A | 741,610 | 49,032 | 145,228 (partial, correctly) |

Edge cases classified correctly: EDGAR index → `INDEX_ONLY`; XBRL schema →
`XBRL_METADATA_ONLY`; 8-K → `FULL_BODY_CONFIRMED` (no Items, by design).

Deployed gate on `b6db86d`, sequential, fresh guest session each:

| company | outcome | first evidence |
|---|---|---|
| Datadog | FULL, 973 w | 10-K Item 7 — "Datadog is the AI-powered observability…" |
| Microsoft | FULL, 1,004 w | 10-K Item 7 — "Microsoft is a technology company…" |
| Shopify | FULL, 1,123 w | 10-K — "We believe we can help merchants of all verticals…" |
| Stripe | FULL, 831 w | another registrant's filing (see §13) |
| Constellation Software | WITHHELD, correctly | no SEC filings exist — TSX-only issuer |
| Caterpillar | BOUNDED, legitimately | caterpillar.com timed out; both filings read |

No raw `Bad Request` in any run. Dark and light both pass at 390 px: 42 text
elements, 0 below WCAG AA 4.5:1, `scrollWidth == 390` in both themes.

## 13. STILL OPEN

**Third-party filings surface the filer, not the mention.** Stripe's run cites
Infinite Group's 10-K and shows Infinite Group describing *itself*. The label
is now honest and the excerpt is no longer boilerplate, but the adapter should
return the span that names the subject. Start at `classify_mention`.

**A filings-shaped limitation is used where there are no filings.**
Constellation Software's withheld page says "the company's filings carry this,
so it is stated under legal obligation" as the minimum needed — for a company
with no SEC filings in the run. The template is unconditional.

**Not attempted this cycle:** the authenticated acceptance runner, the
20-company matrix, and the ≥90% useful-rate measurement. §5.1 (brief under
word target) and §5.2 (`<style>` inside `<main>`) are unchanged.

---

# 2026-08-06 — the residual defects, and what the product may claim

Branch `feat/founder-decision-experience-v3`. Suite 3928+, guard EXIT=0.
Production and PR #14 untouched.

## 14. WHAT WAS CLOSED

**§5.2 `<style>` inside `<main>` — FIXED, live-verified.** `LAYER_CSS` is
prepended to the fragment each layer renderer returns, so `/story` and
`/dashboard` each carried a stylesheet inside the element holding the reading.
Hoisted in `_stylize`, the single function every HTML response passes through.
A rule enforced at twenty call sites is a rule that will be missed at the
twenty-first. Cascade order preserved: shared sheet → accessibility floor →
the page's own rules.

**Raw Bad Request — FIXED, live-verified.** `GET /runs/{id}` on an unapproved
run answered `Bad request / approve at least one source`: a framework status
and an exception. Now every customer-visible failure resolves to a named
category in `webapp/failures.py` carrying what worked, what did not, why, and
one next step. Verified live: unknown run and revoked share link both explain
themselves.

The rule that made it work: **internal text is suppressed only where it was
understood.** Where classification fails, the message is still shown — the 500
handler puts the log-correlation reference there, debug puts the traceback
there, a revoked share link explains itself there. The first attempt dropped
it unconditionally and three existing tests correctly failed.

**§2B limitation language — FIXED, live-verified.** Constellation Software, a
TSX-only issuer with no SEC filing, was told "the company's filings carry
this". `discovery.py` assigns `investor_material` by URL keyword ("investor",
"/ir", "earnings"); `edgar.py` assigns the same class to a 10-K. Accountability
was being inferred from a URL family. It is a property of the document: a
regulator's archive served it, or nobody did. Live after: "every source here is
published by the company itself." The same cause ran the other way too — an IR
page that is not a filing fell through to "none", understating evidence the run
did obtain.

**§2A third-party filing span — FIXED, live-verified.** Stripe's run showed
"Infinite Group is a developer of cybersecurity software" as evidence about
Stripe: accurate, accountable, correctly cited, wrong company. `subject_span`
now selects the sentences that name the subject and returns nothing when none
do, and the caller drops the document. Live after: "payments became due on
August 15, 2022, and consisted of 25% of the Company's receivables processed
through Stripe."

Aliases are deliberately conservative — a suffix is removable, a leading token
is not. "Linear Minerals Corp." once satisfied the alias "Linear".

## 15. RULES ADDED TO THE DOCTRINE

15. A limitation that overstates the evidence is worse than no limitation.
    Every limitation is derived from the source mixture actually obtained.
16. Accountability is a property of the document, never of a URL family.
17. A filing written by someone else is read for what it says about the
    subject. If it never names the subject, it is not evidence about it.
18. No customer-visible failure may be a status line and an exception. Every
    one names what worked, what did not, why, and one next step.
19. Internal text is hidden only where it was understood well enough to say
    something better. Unrecognised, it is still the only information there is.
20. A `<style>` block is not content and never belongs inside `<main>`.
21. A statement on a failure page must be true of THAT failure. "The company
    you entered was recorded" is false on a 404 for an unknown run.

## 16. WEEKLY QUALITY CYCLE

Each cycle, in this order, and each reports live baseline → matrix → useful
rate → failure clusters → deployed repairs → before/after → regression tests →
remaining blockers.

| week | cycle | gate |
|---|---|---|
| 1 | Reliability | no raw framework error on any tested path |
| 2 | Company-universe coverage | 20-company matrix, ≥90% useful |
| 3 | Evidence and filing integrity | no span attributed to the wrong company |
| 4 | Founder reasoning | first two minutes answer the eight questions |
| 5 | Presentation | slide 1 conclusion-first, no source prose |
| 6 | Dark mode and accessibility | every surface, both themes, 375–1440 |

## 17. NOT DONE THIS CYCLE — precise handoff

**§5.1 executive brief word count: NOT MEASURED.** The one run that reached
`/brief` this cycle was a withheld result (310 words, correctly), which is not
a valid measurement. Measure on a RICH result before touching
`build_executive_brief` — the causal fields it was said to be missing were
wired in an earlier cycle and the defect may already be closed.

**Authenticated acceptance runner: NOT BUILT.** This is the blocker for
everything below it. The public demo quota is 10 analyses per IP per rolling
hour, which is why the 20-company matrix cannot be driven from the guest flow.
Build it per §4 of the 2026-08-06 brief: preview-only, authenticated, bounded
cost and concurrency, resumable, structured per-company result contract.

**20-company matrix: NOT RUN.** Denominator is fixed and every company stays in
it: Microsoft, Amazon, Alphabet, NVIDIA, Caterpillar, Visa, Datadog,
Cloudflare, HubSpot, MongoDB, Snowflake, Shopify, Constellation Software, CGI,
Brookfield, RBC, Stripe, Ramp, Anduril, Notion.

**Full dark-mode surface sweep: PARTIAL.** One result page measured at 390px in
both themes (42 elements, 0 below WCAG AA, no overflow). The remaining
surfaces, widths (375/768/1280/1440) and states are unmeasured.

**Worktree note.** The `d4928192-.../fiv3` worktree was destroyed mid-session
by another agent session sharing that path — `.git` removed and most of `src`
deleted. All committed work was safe on `origin`; uncommitted edits were
rescued file-by-file and rebuilt in a worktree owned by this session. Do not
share a scratchpad worktree path between sessions.

---

# CYCLE 2026-08-06 — the twenty-company matrix, measured

Branch `feat/founder-decision-experience-v3`, deployed and verified on
`intent-engine-preview-v3`. Everything below was measured on the deployed
service, not reasoned about.

## The matrix was run WITHOUT the acceptance runner

The runner is built and its refusal path is proven live (no auth, wrong token
and empty token all return byte-identical 404s and never echo the token), but
it stayed switched off: enabling it needs a secret set on the hosted service,
and that is the owner's action, not the agent's.

**It was not needed.** The public guest path is the same `_analyze`, and its
quota is 10 analyses per IP per rolling hour — so twenty companies is two
windows of ordinary use, not a bypass. Verdicts came from the product's own
`webapp.acceptance.score`, so a row means what a runner row would have meant.

**Rule: the runner is a convenience, not a precondition.** A matrix that
cannot be run without new infrastructure has usually mis-stated its blocker.

## Useful rate: 19/20

One failure: Alphabet (`https://abc.xyz`). Every other company returned a
useful full or honestly-bounded result.

## Six defects, and the shape they share

Five of the six were a CORRECT rule that could not reach the thing it governed:

| defect | the rule was right | it could not reach |
|---|---|---|
| filing read, "marketing only" limitation | `evidence_classes` grants an ACCOUNTABLE tier | `has_filing` searched `source_refs` for a URL that production never puts there — it is on `origin` |
| identical answer on 5 of 7 companies | pattern says it needs an embedded delivery model | a 2-of-3 threshold let an API page + a products page assert it |
| landing page unreadable in dark | `_A11Y_CSS` has a dark block | `form.analyze label` and `.sample-quote` outrank its selectors |
| focus ring 2.76:1 in dark | `.brief`/`.deck` re-point var(--accent) | the global floor hard-coded `#1d4ed8` |
| progress page white-on-white | the floor covers `.card`/`details` | it has no rule for `[role=status]`, `.coverage` |
| "no approved source could be retrieved" | `compose` decides on the documents | the page decided on the last state transition |

**Rule: when a fix lands and the defect survives, suspect the seam, not the
rule.** Every one of these had a passing test for the rule in isolation.

**Rule: a page may not name a colour.** A colour a page names is a colour the
dark block cannot re-point. Tested structurally now, not by eyeballing.

## The instrument drifts too, and in both directions

Three measurement defects were found, and correcting them is not weakening a
gate:

* the runner scored an honest withheld result FAILED, because two markers were
  guesses at the wording ("no strategic reading" for "No strategic reading",
  "What you can do" for "What you do next"). The old bounded fixture had been
  written to satisfy the markers, which is why it could not catch them;
* the persona harness matched slides by `id`, and ids are suffixed per
  instance, so a deck that answered "what to investigate next" was scored as
  not answering it;
* the slide floor treated "composition lost slides" and "the run supported
  fewer findings" as one failure — so removing an unsupported reading made the
  gate demand it back.

**Rule: build fixtures from what the product renders, never from what the
checker looks for.** **Rule: a gate must never be satisfiable only by a
fabrication.**

## Do not re-route a failed run; fix what its page says

Two attempts to route Alphabet's FAILED-but-has-documents run to a richer
surface both answered HTTP 500 live (`/full` and `/slides` first, then the
primary screen). Those pages are built for a run that composed something.

The defect was the sentence, not the routing: the page claimed nothing had
been retrieved while the same store held the 10-K and the 10-Q. It now reads
the store and says what was read, with a link to the brief.

**Rule: prefer correcting what a page SAYS over sending the reader somewhere
else.** **Rule: a 500 is worse than the wrong page.**

## Still open

* **Alphabet remains the one not-useful row.** Its page is now truthful and
  points at a 1060-word brief that IS decision-useful, but the primary screen
  carries no analysis. It was NOT reclassified — tuning the scorer in the
  measurer's own favour is how a denominator gets edited.
* **`services_to_product` still dominates.** Requiring the services signal
  fixed Visa live and is proven offline, but most large vendors do publish
  professional-services pages, so the signal fires legitimately and the same
  answer still recurs. The next lever is the disconfirming signal:
  `pricing_published` is already declared and currently only lowers
  confidence.
* **Executive brief composition.** Measured on 19 briefs: median 1426 words
  (7.1 min). For public companies "What the market appears to expect" is
  24–37% of the brief, and 62% on NVIDIA — a bounded result whose brief is
  mostly share-price commentary.
* **Progress page transient states.** During an Alphabet-shaped run the
  primary screen answers 400 then 500 before settling at 200. Both are the
  product's own four-section pages with a safe reference, not raw framework
  errors, but neither should be reachable.

---

# CYCLE 2026-08-06b — closure: four items

Branch `feat/founder-decision-experience-v3`. Measured on the deployed
preview, not reasoned about.

## The reads were writes — one projection, and no route mutates

The transient 400→500 was never a rendering bug. `_autorun` approves and
fetches and `_real_result` composes, both from a GET, both racing the async
worker doing the same thing. All six routes sampled together at a183f51 on one
Alphabet run:

    t= 0.0s  /=400  /progress=200  /brief=200  /full=200  /slides=200
    t=11.2s  /=200  /progress=200  /brief=200  /full=200  /slides=303

`_availability(run_id)` now derives what exists and touches nothing; every run
route asks it first and answers the progress page while the worker works.
After the fix, the same trace reads:

    t= 0.0s  /=303  /progress=200  /brief=303  /full=303  /slides=303
    t=23.3s  /=303  /progress=200  /brief=200  /full=200  /slides=200
    t=37.0s  /=200(541w)

**Rule: a page a reader refreshes may never be the thing that mutates the run.**
**Rule: the transitional answer is a redirect to progress, never an error.**

## Having services is not the transition

Requiring `services_motion` was right and insufficient — nearly every large
vendor publishes an implementation page. The reading still dominated MongoDB,
Cloudflare, HubSpot, Snowflake and Amazon. `productization` is now its own
signal and the pattern requires BOTH halves, and a pattern may declare
BLOCKING signals (a subset of its disconfirming ones) that cost it first place
while keeping it as a secondary hypothesis.

Live, before → after: MongoDB and Cloudflare and HubSpot and Snowflake all
carried the identical "the engagement teaches the workflow" sentence; they now
read "the second buyer arrives with requirements the first never had", an
honest withhold, and two regulated-buyer readings. Amazon reads "when agents
transact, the rails they call matter more than the human-facing storefront".

**Rule: a threshold counts evidence and cannot say what the reading is ABOUT.**
**Rule: blocking is declared per pattern.** A blanket penalty on
counter-evidence was tried and broke nine tests, correctly — the flagship
reading is SUPPOSED to have been argued with.

## Two attempts at Alphabet made it worse before one made it better

Re-routing the FAILED-with-evidence run to the report renderer answered 500 on
`/full` and `/slides`; routing it to `_insufficient_evidence_page` answered 500
on the primary screen. Both pages are built for a run that composed something.

What worked was two separate things: the failure page now reads the store and
says what WAS read, and the primary screen renders the founder brief whenever
the run has documents and a result — the test is "could anything be read", not
"is there a report", because `/brief` was composing 1060 words off a run with
no `strategic_report` while the primary served 278.

**Rule: prefer correcting what a page SAYS over sending the reader elsewhere.**

## Still open

* **Alphabet is not deterministic.** One live run settles the primary at 541
  words off the dossier; another ends with no cached result and serves the
  truthful 278-word failure page. The remaining gap is the case where compose
  itself raises, leaving documents but nothing composed.
* **A new repetition, smaller than the old one.** HubSpot and Snowflake now
  share a regulated-buyer answer. Two companies, not five, and a different
  pattern — but the same shape of problem.
* **The visual matrix is broad, not exhaustive.** Nine surfaces measured across
  375/768/1280/1440 in dark and light; share links, Q&A, dashboard and the
  retry state are not covered.

---

# CYCLE 2026-08-06c — the guard was right, the blast radius was not

## One sentence took the whole run

Measured live, after adding the stage and message to the failure log (the old
line said only "ValueError", and `PersonalError` subclasses it, so it named
the base class of the thing that failed and no stage):

    stage=composition PersonalError: claim text overclaims: ['always']

Alphabet's SEC 10-K and 10-Q had been read successfully. One claim tripped the
editorial language wall and the entire run was abandoned.

Claims are validated downstream, when a SECTION is validated — so an
overclaiming sentence was only caught after it had been folded into a card,
and taking the card down took the run with it. `_claim` now asks the wall at
the claim boundary: an optional claim that fails is refused ALONE and logged
with its id; `u.identity`, `u.offering` and `u.scope` still abort, because a
page missing what the company sells is worse than no page.

Live result: Alphabet went from five identical failure pages, to five
identical bounded pages, to **five identical `useful_full` results at 1030
words** — "businesses that subsidise each other are managed together and
disclosed apart", read from its own filing.

**Rule: an editorial guard stays strict and fails at the smallest safe scope.**
**Rule: the wall is never relaxed to make a company synthesise** — no banned
term was removed, and a test re-validates every surviving claim.

## Two measurement lessons

* **Five runs, not two.** The previous cycle called Alphabet nondeterministic
  from two samples, one of which was an interim page. Five identical runs
  showed it was a deterministic abort all along.
* **Sort captures by mtime, not by name.** The previous cycle reported the
  bounded-page contradiction as unfixed; it had been fixed, and the file
  inspected was a stale capture from an earlier build whose run id happened to
  sort last.

## Still open

* HubSpot and Snowflake still share a regulated/public-sector answer.
* Dashboard, Q&A, valid share, revoked share, retry state and the system-mode
  branches remain unmeasured.

---

# CYCLE 2026-08-06b — causal gating, measured live

Branch `feat/founder-decision-experience-v3`, deployed and verified on
`intent-engine-preview-v3` at **`7595334`** (`/version` confirms). Everything
below was measured on the deployed service.

## What changed

`tool_to_system_of_record` and `single_to_multi_segment` now require a causal
mechanism. Gated patterns 2 → 4 of 12; ungated debt 9 → 8. Full suite 4313
passed / 6 skipped, EXIT=0.

## The matrix, run after the final deploy

Seven companies, each on a fresh guest identity (a new cookie jar posting
straight to `/analyze` mints its own session — do NOT `POST /demo` first, that
creates a session and the next POST then needs a CSRF token from a rendered
form). Sequential, 20s apart.

| company | dominant reading | system-of-record sentence |
|---|---|---|
| Palantir | services→product (from filings) | **gone** (present at `dad7d28`) |
| Snowflake | bounded — nothing cleared the bar | **gone** (present at `dad7d28`) |
| MongoDB | ecosystem control vs openness | absent |
| Salesforce | human→agent workflow | absent |
| Linear | one buyer → two buyers | absent |
| HubSpot | portfolio run as one | **still present, as the secondary** |
| Datadog | bounded — not safe to act on | **still present, under "switching costs"** |

Linear's reading is transparently earned: the surfaces render the
`segment_split` label and the evidence is HubSpot-style plain — "the startups
and enterprises that choose Linear". That is the gate working in public.

## THE RESIDUAL, PRECISELY

HubSpot and Datadog still receive the system-of-record reading, and **no
mechanism evidence appears on any surface for either**. Checked three ways on
the deployed pages: the neutral labels ("runs its products over one model of
the customer's data"), the relevance strings ("so the data other systems trust
now lives here"), and the raw mechanism phrases. All absent — while Linear's
`segment_split` label renders, so these surfaces do show signal labels when
they exist.

It is not a hole in the gate. `thesis["transition"]` is `top.statement` and
`top` is a gated hypothesis, so there is no second unguarded path, and the
same build dropped the reading for Palantir and Snowflake. The likely cause is
benign: HubSpot's run retrieves 59 sources and one of them carries a mechanism
phrase, while the surfaces render a selected subset of observations.

**But that is its own defect, and the next piece of work.** The gate fixed
WHICH companies get the reading. It did not change WHAT the sentence says —
still the generic scaffold, name-substituted — or make the run show the
evidence that earned it. A reader looking at HubSpot sees an unfalsifiable
claim with nothing behind it. The fix is mechanism-specific rendering: the
statement should name the authoritative object and cite the observation that
established it, and a reading whose mechanism observation is not renderable
should not assert itself.

## Next highest risk, measured not guessed

Feeding four corpora of ordinary B2B copy through `_hypothesis_for` for every
pattern, then a commerce corpus: after these two repairs, **`product_to_platform`
is the only ungated pattern that still asserts itself on generic copy**
(commerce, via `product_breadth + platform_control`). It is named as the next
target in `_UNGATED_DEBT`.

## Not measured this cycle

Multi-identity stability harness, share verification, and the retry lifecycle
on this HEAD. Unchanged from the previous cycle's status.

---

# CYCLE 2026-08-06c — mechanism transparency, measured live

Branch `feat/founder-decision-experience-v3`, deployed and verified on
`intent-engine-preview-v3` at **`bdd007a`**. Full suite 4346 passed / 16
skipped, EXIT=0.

## The defect, and why it was not a gating defect

HubSpot's 10-K says "Our customer platform includes a system of record for
maintaining a unified view of the customer experience". The reading was right
and the gate was right. What the page showed as its evidence was "We provide
an agentic customer platform that helps marketing, sales, and customer service
teams drive business growth" — the document's first four hundred characters.

Structural: an observation is one DOCUMENT carrying every signal found
anywhere in it (HubSpot's filing carried eighteen), while `excerpt` is chosen
once for the whole document. It is therefore the right evidence for at most
one signal, and for a long filing usually for none.

Fixed by capturing the sentence per signal (`observations.signal_spans`),
attaching the qualifying ones to the hypothesis (`records.MechanismEvidence`,
built in `reasoning._mechanism_evidence` — the last place that knows WHICH
signal qualified), and rendering through one module (`mechanism.py`) that the
deck and the brief both call and no one else may.

**Silence is not transparency.** Dropping an unevidenced gated claim was tried
first and measured worse: `services_to_product` lost a company-specific
section and its page moved CLOSER to an unrelated company's. Three states now,
distinguishable to a reader: quoted / stated-as-unevidenced / unchanged
(ungated, claims no mechanism).

## Live matrix, ten companies on the deployed build

| company | reading | mechanism shown | quoted evidence |
|---|---|---|---|
| HubSpot | tool→system of record | yes | "…includes a system of record for maintaining a unified view of the customer experience" |
| Datadog | tool→system of record | yes | "…powered by a common data model that is extensible…" |
| Palantir | services→product | yes | the O&M / professional-services passage |
| Linear | one buyer → two buyers | yes | "the startups and enterprises that choose Linear" |
| Microsoft | one buyer → two buyers | yes | see defect below |
| Amazon | one buyer → two buyers | yes | see defect below |
| Snowflake | bounded, none asserted | n/a | — |
| MongoDB | ecosystem control (UNGATED) | no | — |
| Stripe | portfolio run as one (UNGATED) | no | — |
| Shopify | product→platform (UNGATED) | no | — |

Counter-evidence and falsifier present on all ten. Taxonomy leak ("customers
describing it as a companion to a system of record") gone — the dossier now
applies the same `reads_as_taxonomy` filter the deck always had.

Every reading WITHOUT a shown mechanism is one of the eight ungated patterns
recorded in `_UNGATED_DEBT`. Those declare no mechanism at all, so there is
none to show; the fix for them is gating, not rendering. MongoDB's "breadth
plus partners raise switching costs" is exactly the unevidenced structural
claim that debt still permits.

## WHAT TRANSPARENCY IMMEDIATELY EXPOSED

Microsoft and Amazon qualified `single_to_multi_segment` on `segment_split`,
and the quoted sentence shows why that is wrong:

> "Our competitors are developing new software and devices, while also
> deploying competing cloud-based services for consumers and businesses."

The pair phrase "consumers and businesses" is in the document, but the
sentence is about COMPETITORS' offerings, not about who Microsoft sells to.
Amazon's is the same shape — a competitor list in a 10-K risk factor.

The phrase-level gate cannot read the subject of the sentence it matched. This
was always happening; it was invisible until the evidence was shown, and it
became visible the same day. **That is the argument for this cycle**: a
detection defect that reaches a founder as an unsupported sentence is
undetectable, and one that reaches them next to its own quotation is obvious.

**Next cycle: subject-scope the span.** A pair phrase inside a sentence whose
subject is competitors, customers-of-customers, or a risk factor is not
evidence about this company's buyers. `filing_detectors` already matches
sentence-scoped; this needs the same discipline plus a subject test.
